#!/bin/sh
# Nightly database backup: a compressed pg_dump in /backups, keeping the last BACKUP_KEEP_DAYS days.
# Restore with:  gunzip -c /backups/<file>.sql.gz | psql "$DATABASE_URL"
set -u
: "${BACKUP_HOUR_UTC:=0}"          # 00:00 UTC is 02:00 in South Africa
: "${BACKUP_KEEP_DAYS:=14}"
mkdir -p /backups
echo "backup: daily at ${BACKUP_HOUR_UTC}:00 UTC, keeping ${BACKUP_KEEP_DAYS} days"

backup() {
  file="/backups/flowshop-$(date -u +%Y%m%d-%H%M%S).sql.gz"
  if pg_dump --no-owner --clean --if-exists | gzip > "$file.part" && mv "$file.part" "$file"; then
    echo "$(date -u +%FT%TZ) saved $file ($(du -h "$file" | cut -f1))"
    find /backups -name 'flowshop-*.sql.gz' -mtime +"$BACKUP_KEEP_DAYS" -delete
  else
    rm -f "$file.part"
    echo "$(date -u +%FT%TZ) BACKUP FAILED" >&2
  fi
}

backup  # one at start-up, so a fresh install has a backup straight away
while true; do
  now=$(date -u +%s)
  wait=$(( (BACKUP_HOUR_UTC * 3600 - now % 86400 + 86400) % 86400 ))
  [ "$wait" -eq 0 ] && wait=86400
  sleep "$wait"
  backup
done
