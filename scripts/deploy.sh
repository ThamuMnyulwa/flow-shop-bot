#!/usr/bin/env bash
# Deploy the FLOWW shop to dev or prod on Render.
#
#   scripts/deploy.sh dev              test, push the current commit to `develop`, deploy dev, wait, verify
#   scripts/deploy.sh prod             promote the commit running on dev: back up the database, deploy prod, verify
#   scripts/deploy.sh rollback <env>   put the previous live deploy back
#   scripts/deploy.sh status           what is running where
#
# Options:  --dry-run      run every check and print the API calls without making them
#           --skip-tests   skip lint and tests (dev only; prod never skips the dev check)
#           --yes          don't ask for confirmation (for CI)
#
# Needs: git, curl, python3, terraform, uv. Environment: RENDER_API_KEY, and NEON_API_KEY for prod.
# Service and database ids come from `terraform output` in terraform/environments/<env>, so run
# `terraform apply` there once before the first deploy.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RENDER_API="https://api.render.com/v1"
NEON_API="https://console.neon.tech/api/v2"
DRY_RUN=false SKIP_TESTS=false ASSUME_YES=false
DEPLOY_TIMEOUT=${DEPLOY_TIMEOUT:-1200}  # seconds

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

# ---------- Terraform outputs ----------

tf_out() {  # tf_out <env> <name>
  local dir="$ROOT/terraform/environments/$1"
  terraform -chdir="$dir" output -raw "$2" 2>/dev/null \
    || die "No '$2' for $1. Run 'terraform apply' in terraform/environments/$1 first."
}

env_dir_name() { [[ $1 == prod ]] && echo prod || echo dev; }

# ---------- Render API ----------

render() {  # render <METHOD> <path> [json-body]
  [[ -n ${RENDER_API_KEY:-} ]] || die "Set RENDER_API_KEY (Render dashboard → Account settings → API keys)."
  local args=(-sS --fail-with-body -X "$1" -H "Authorization: Bearer $RENDER_API_KEY" -H "Accept: application/json")
  [[ $# -ge 3 ]] && args+=(-H "Content-Type: application/json" -d "$3")
  curl "${args[@]}" "$RENDER_API$2"
}

live_deploy_id() {  # the deploy currently serving traffic
  render GET "/services/$1/deploys?limit=20" \
    | json "next((x['deploy']['id'] for x in d if x['deploy']['status']=='live'), '')"
}

wait_for_deploy() {  # wait_for_deploy <service_id> <deploy_id>
  local started=$SECONDS status=""
  while (( SECONDS - started < DEPLOY_TIMEOUT )); do
    status=$(render GET "/services/$1/deploys/$2" | json "d['status']")
    case $status in
      live) ok "Deploy is live ($(( SECONDS - started ))s)"; return 0 ;;
      build_failed|update_failed|pre_deploy_failed|canceled|deactivated)
        warn "Deploy ended with status '$status'. See the logs in the Render dashboard."; return 1 ;;
      *) printf '  %s… %ss\r' "$status" "$(( SECONDS - started ))" ;;
    esac
    sleep 10
  done
  warn "Timed out after ${DEPLOY_TIMEOUT}s (last status: $status)."
  return 1
}

running_version() {  # the commit the service reports from /healthz
  curl -sS --max-time 20 "$1/healthz" | json "d.get('version','')" 2>/dev/null || true
}

verify() {  # verify <url> <sha>
  local version
  for _ in 1 2 3 4 5 6; do
    version=$(running_version "$1")
    [[ $version == "$2" ]] && { ok "$1 is healthy and running ${2:0:7}"; return 0; }
    sleep 10
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

run() {  # run a command, or print it in a dry run
  if $DRY_RUN; then printf '  [dry run] %s\n' "$*"; else "$@"; fi
}

confirm() {
  $ASSUME_YES && return 0
  local answer
  read -r -p "$1 Type '$2' to continue: " answer
  [[ $answer == "$2" ]] || die "Cancelled."
}

# ---------- commands ----------

deploy() {  # deploy <dev|prod>
  local env=$1 sha service url
  need git; need curl; need python3; need terraform
  require_clean_tree
  sha=$(git -C "$ROOT" rev-parse HEAD)
  service=$(tf_out "$env" web_service_id)
  url=$(tf_out "$env" url)
  bold "Deploying ${sha:0:7} to $env ($url)"

  if [[ $env == dev ]]; then
    if $SKIP_TESTS; then warn "Skipping lint and tests."; else
      step "Lint and tests"
      need uv
      (cd "$ROOT" && uv run ruff check src tests && uv run pytest -q) || die "Tests failed. Nothing was deployed."
      ok "All checks pass"
    fi
    step "Push to develop"
    push_fast_forward "$sha" develop
  else
    step "Check this commit is running on dev"
    local dev_url dev_version
    dev_url=$(tf_out dev url)
    dev_version=$(running_version "$dev_url")
    [[ $dev_version == "$sha" ]] \
      || die "Dev runs '${dev_version:0:7}', not ${sha:0:7}. Deploy to dev and check it there first: scripts/deploy.sh dev"
    ok "Dev runs ${sha:0:7}"
    confirm "This deploys ${sha:0:7} to PROD, where real customers order." prod

    step "Push to main"
    push_fast_forward "$sha" main

    step "Back up the prod database"
    [[ -n ${NEON_API_KEY:-} ]] || die "Set NEON_API_KEY for the pre-deploy backup."
    local project branch name
    project=$(tf_out prod neon_project_id)
    branch=$(tf_out prod neon_branch_id)
    name="backup-$(date -u +%Y%m%d-%H%M%S)-${sha:0:7}"
    if $DRY_RUN; then
      printf '  [dry run] POST %s/projects/%s/branches  name=%s parent=%s\n' "$NEON_API" "$project" "$name" "$branch"
    else
      curl -sS --fail-with-body -X POST "$NEON_API/projects/$project/branches" \
        -H "Authorization: Bearer $NEON_API_KEY" -H "Content-Type: application/json" \
        -d "{\"branch\": {\"name\": \"$name\", \"parent_id\": \"$branch\"}}" >/dev/null \
        || die "The backup failed, so nothing was deployed."
      ok "Backup branch $name"
    fi
  fi

  step "Deploy on Render"
  if $DRY_RUN; then
    printf '  [dry run] POST %s/services/%s/deploys  commitId=%s\n' "$RENDER_API" "$service" "$sha"
    ok "Dry run finished. Nothing was changed."
    return 0
  fi
  local previous deploy_id
  previous=$(live_deploy_id "$service")
  deploy_id=$(render POST "/services/$service/deploys" "{\"commitId\": \"$sha\"}" | json "d['id']")
  echo "  deploy $deploy_id (previous live: ${previous:-none})"
  if ! wait_for_deploy "$service" "$deploy_id" || ! verify "$url" "$sha"; then
    warn "The previous version (${previous:-unknown}) may still be serving. To put it back: scripts/deploy.sh rollback $env"
    exit 1
  fi
  bold "Done: $env runs ${sha:0:7}"
}

rollback() {  # rollback <dev|prod>
  local env=$1 service previous
  need curl; need python3; need terraform
  service=$(tf_out "$env" web_service_id)
  previous=$(render GET "/services/$service/deploys?limit=20" | json \
    "[x['deploy']['id'] for x in d if x['deploy']['status'] in ('live','deactivated')][1] if len([x for x in d if x['deploy']['status'] in ('live','deactivated')])>1 else ''")
  [[ -n $previous ]] || die "No earlier deploy to roll back to."
  confirm "This puts deploy $previous back on $env." "$env"
  if $DRY_RUN; then printf '  [dry run] POST %s/services/%s/rollback deployId=%s\n' "$RENDER_API" "$service" "$previous"; return 0; fi
  local new_id
  new_id=$(render POST "/services/$service/rollback" "{\"deployId\": \"$previous\"}" | json "d['id']")
  wait_for_deploy "$service" "$new_id" || die "The rollback deploy did not go live. Check the Render dashboard."
  warn "Rolled back the code. If a migration changed the database, restore the backup branch in Neon too."
}

status() {
  need curl; need python3; need terraform
  for env in dev prod; do
    local url version
    url=$(terraform -chdir="$ROOT/terraform/environments/$env" output -raw url 2>/dev/null) || { echo "$env: not set up"; continue; }
    version=$(running_version "$url")
    version=${version:0:7}
    printf '%-5s %-45s %s\n' "$env" "$url" "${version:-unreachable}"
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
  dev|prod) deploy "$1" ;;
  rollback) [[ ${2:-} == dev || ${2:-} == prod ]] || usage 1; rollback "$2" ;;
  status) status ;;
  *) usage 1 ;;
esac
