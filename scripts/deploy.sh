#!/usr/bin/env bash
# Deploy the FLOWW shop to dev or prod on Google Cloud Run.
#
#   scripts/deploy.sh dev              test, build the image for this commit, migrate, deploy dev, verify
#   scripts/deploy.sh prod             promote the exact image running on dev: back up the database, migrate, deploy
#   scripts/deploy.sh rollback <env>   send traffic back to the previous revision
#   scripts/deploy.sh status           what is running where
#
# Options:  --dry-run      run every check and print what would change, without changing anything
#           --skip-tests   skip lint and tests (dev only; prod always requires the commit to be on dev)
#           --yes          don't ask for confirmation (for CI)
#
# Needs: git, curl, python3, terraform, gcloud, docker (dev only), uv (dev only).
# Sign in once: gcloud auth login && gcloud auth configure-docker europe-west2-docker.pkg.dev
# For prod: export NEON_API_KEY=... (for the backup before each deploy).
# Names and ids come from `terraform output` in terraform/environments/{shared,dev,prod}.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NEON_API="https://console.neon.tech/api/v2"
DRY_RUN=false SKIP_TESTS=false ASSUME_YES=false

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
step() { printf '\n\033[1;34m▶ %s\033[0m\n' "$*"; }
ok()   { printf '\033[32m✓ %s\033[0m\n' "$*"; }
warn() { printf '\033[33m! %s\033[0m\n' "$*" >&2; }
die()  { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

usage() { sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

json() {  # json '<python expression on d>'  reads JSON from stdin
  python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"
}

need() { command -v "$1" >/dev/null || die "$1 is not installed."; }

run() {  # run a command, or print it in a dry run
  if $DRY_RUN; then printf '  [dry run] %s\n' "$*"; else "$@"; fi
}

confirm() {
  $ASSUME_YES && return 0
  local answer
  read -r -p "$1 Type '$2' to continue: " answer
  [[ $answer == "$2" ]] || die "Cancelled."
}

# ---------- Terraform outputs ----------

tf_out() {  # tf_out <dev|prod|shared> <name>
  terraform -chdir="$ROOT/terraform/environments/$1" output -raw "$2" 2>/dev/null \
    || die "No '$2' for $1. Run 'terraform apply' in terraform/environments/$1 first."
}

# ---------- health ----------

running_version() {  # the commit the service reports from /healthz (which never touches the database)
  curl -s --max-time 30 "$1/healthz" 2>/dev/null | json "d.get('version','')" 2>/dev/null || true
}

verify() {  # verify <url> <sha>
  local version=""
  for _ in 1 2 3 4 5 6; do
    version=$(running_version "$1")
    [[ $version == "$2" ]] && { ok "$1 is healthy and running ${2:0:7}"; return 0; }
    sleep 5
  done
  warn "$1 reports version '${version:-none}', expected ${2:0:7}."
  return 1
}

# ---------- git ----------

require_clean_tree() {
  git -C "$ROOT" diff --quiet && git -C "$ROOT" diff --cached --quiet \
    || die "You have uncommitted changes. Commit or stash them first."
}

push_fast_forward() {  # push_fast_forward <sha> <branch>
  git -C "$ROOT" fetch -q origin "$2" 2>/dev/null || true
  if git -C "$ROOT" rev-parse -q --verify "origin/$2" >/dev/null \
     && ! git -C "$ROOT" merge-base --is-ancestor "origin/$2" "$1"; then
    die "origin/$2 has commits that ${1:0:7} doesn't include. Merge them first."
  fi
  run git -C "$ROOT" push origin "$1:refs/heads/$2"
}

# ---------- Cloud Run ----------

rollout() {  # rollout <env> <image> <sha> <url>
  local env=$1 image=$2 sha=$3 url=$4 project region service job
  project=$(tf_out "$env" project_id)
  region=$(tf_out "$env" region)
  service=$(tf_out "$env" service_name)
  job=$(tf_out "$env" migrate_job_name)
  local where=(--project "$project" --region "$region" --quiet)

  step "Migrate the database"
  run gcloud run jobs update "$job" --image "$image" "${where[@]}"
  run gcloud run jobs execute "$job" --wait "${where[@]}" \
    || die "The migration failed, so the running version was left alone. See: gcloud run jobs executions list --job $job ${where[*]}"

  step "Deploy to Cloud Run"
  run gcloud run services update "$service" --image "$image" "${where[@]}"
  run gcloud run services update-traffic "$service" --to-latest "${where[@]}"  # undo a pinned rollback
  if $DRY_RUN; then ok "Dry run finished. Nothing was changed."; return 0; fi

  verify "$url" "$sha" || {
    warn "To send traffic back to the previous revision: scripts/deploy.sh rollback $env"
    exit 1
  }
  bold "Done: $env runs ${sha:0:7}"
}

image_exists() {  # image_exists <image>
  gcloud artifacts docker images describe "$1" --quiet >/dev/null 2>&1
}

# ---------- commands ----------

deploy_dev() {
  need git; need curl; need python3; need terraform; need gcloud; need docker
  require_clean_tree
  local sha registry image url
  sha=$(git -C "$ROOT" rev-parse HEAD)
  registry=$(tf_out shared registry)
  image="$registry/app:$sha"
  url=$(tf_out dev url)
  bold "Deploying ${sha:0:7} to dev ($url)"

  if $SKIP_TESTS; then warn "Skipping lint and tests."; else
    step "Lint and tests"
    need uv
    (cd "$ROOT" && uv run ruff check src tests && uv run pytest -q) || die "Tests failed. Nothing was deployed."
    ok "All checks pass"
  fi

  step "Push to develop"
  push_fast_forward "$sha" develop

  step "Build the image"
  if ! $DRY_RUN && image_exists "$image"; then
    ok "Image for ${sha:0:7} already built"
  else
    # Cloud Run runs linux/amd64; building for it explicitly also works on Apple-silicon Macs.
    run docker buildx build --platform linux/amd64 --build-arg "FLOWSHOP_VERSION=$sha" -t "$image" --push "$ROOT"
  fi

  rollout dev "$image" "$sha" "$url"
}

deploy_prod() {
  need git; need curl; need python3; need terraform; need gcloud
  require_clean_tree
  local sha registry image url dev_url dev_version
  sha=$(git -C "$ROOT" rev-parse HEAD)
  registry=$(tf_out shared registry)
  image="$registry/app:$sha"
  url=$(tf_out prod url)
  bold "Deploying ${sha:0:7} to prod ($url)"

  step "Check this commit is running on dev"
  dev_url=$(tf_out dev url)
  dev_version=$(running_version "$dev_url")
  [[ -n $dev_version ]] || die "Dev ($dev_url) isn't reachable or doesn't report a version."
  [[ $dev_version == "$sha" ]] \
    || die "Dev runs ${dev_version:0:7}, not ${sha:0:7}. Deploy to dev and check it there first: scripts/deploy.sh dev"
  $DRY_RUN || image_exists "$image" || die "No image for ${sha:0:7} in the registry. Deploy it to dev first."
  ok "Dev runs ${sha:0:7}; prod gets the same image, with no rebuild"
  confirm "This deploys ${sha:0:7} to PROD, where real customers order." prod

  step "Push to main"
  push_fast_forward "$sha" main

  step "Back up the prod database"
  # With no parent given, Neon branches from the project's default branch, which is the one prod uses.
  local project name
  project=$(tf_out prod neon_project_id)
  name="backup-$(date -u +%Y%m%d-%H%M%S)-${sha:0:7}"
  if $DRY_RUN; then
    printf '  [dry run] POST %s/projects/%s/branches  name=%s (from the default branch)\n' "$NEON_API" "$project" "$name"
  else
    [[ -n ${NEON_API_KEY:-} ]] || die "Set NEON_API_KEY for the pre-deploy backup."
    curl -sS --fail-with-body -X POST "$NEON_API/projects/$project/branches" \
      -H "Authorization: Bearer $NEON_API_KEY" -H "Content-Type: application/json" \
      -d "{\"branch\": {\"name\": \"$name\"}}" >/dev/null \
      || die "The backup failed, so nothing was deployed."
    ok "Backup branch $name"
  fi

  rollout prod "$image" "$sha" "$url"
}

rollback() {  # rollback <dev|prod>
  local env=$1 project region service previous
  need gcloud; need terraform
  project=$(tf_out "$env" project_id)
  region=$(tf_out "$env" region)
  service=$(tf_out "$env" service_name)
  previous=$(gcloud run revisions list --service "$service" --project "$project" --region "$region" \
    --sort-by "~metadata.creationTimestamp" --format "value(metadata.name)" --limit 2 | sed -n 2p)
  [[ -n $previous ]] || die "No earlier revision to roll back to."
  confirm "This sends all $env traffic to revision $previous." "$env"
  run gcloud run services update-traffic "$service" --to-revisions "$previous=100" \
    --project "$project" --region "$region" --quiet
  warn "Rolled back the code. If the bad version changed the database, restore the backup branch in Neon too."
  warn "The next scripts/deploy.sh $env sends traffic to the new version again."
}

status() {
  need curl; need python3; need terraform
  local env url version
  for env in dev prod; do
    url=$(terraform -chdir="$ROOT/terraform/environments/$env" output -raw url 2>/dev/null) || { echo "$env: not set up"; continue; }
    version=$(running_version "$url")
    version=${version:0:7}
    printf '%-5s %-60s %s\n' "$env" "$url" "${version:-unreachable}"
  done
}

# ---------- main ----------

args=()
for a in "$@"; do
  case $a in
    --dry-run) DRY_RUN=true ;;
    --skip-tests) SKIP_TESTS=true ;;
    --yes|-y) ASSUME_YES=true ;;
    -h|--help) usage ;;
    *) args+=("$a") ;;
  esac
done
set -- "${args[@]+"${args[@]}"}"

case ${1:-} in
  dev) deploy_dev ;;
  prod) deploy_prod ;;
  rollback) [[ ${2:-} == dev || ${2:-} == prod ]] || usage 1; rollback "$2" ;;
  status) status ;;
  *) usage 1 ;;
esac
