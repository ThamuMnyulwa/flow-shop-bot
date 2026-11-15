#!/bin/sh
# The scheduler container (E12): every JOBS_INTERVAL seconds it asks the service to send payment reminders and
# release stock held for 48 hours without proof of payment. Running it more often than needed is harmless.
set -u
: "${APP_URL:=http://app:8000}"
: "${JOBS_INTERVAL:=900}"
echo "jobs: calling $APP_URL/jobs/run every ${JOBS_INTERVAL}s"
while true; do
  if out=$(wget -q -O - --header "Authorization: Bearer $FLOWSHOP_JOBS_TOKEN" --post-data "" "$APP_URL/jobs/run" 2>&1); then
    echo "$(date -u +%FT%TZ) $out"
  else
    echo "$(date -u +%FT%TZ) jobs call failed: $out" >&2
  fi
  sleep "$JOBS_INTERVAL"
done
