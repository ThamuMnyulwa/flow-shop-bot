#!/bin/sh
# Starts as root only to make the storage folder (a mounted disk on Render) writable, then runs everything as
# the unprivileged app user.
set -e
STORAGE="${FLOWSHOP_STORAGE_DIR:-/app/var/storage}"
if [ "$(id -u)" = "0" ]; then
  mkdir -p "$STORAGE"
  chown -R app:app "$STORAGE"
  exec setpriv --reuid=app --regid=app --init-groups "$@"
fi
exec "$@"
