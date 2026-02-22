#!/bin/sh
set -e

echo "Waiting for database defined by DATABASE_URL=${DATABASE_URL:-<unset>}"
if [ -z "$DATABASE_URL" ]; then
  echo "DATABASE_URL is not set; skipping wait and starting server"
  exec "$@"
fi

try_connect() {
  python - <<'PY'
import os,sys
import urllib.parse
import psycopg2

url = os.environ.get('DATABASE_URL')
if not url:
    sys.exit(2)
u = urllib.parse.urlparse(url)
dbname = u.path.lstrip('/')
user = u.username
password = u.password
host = u.hostname
port = u.port or 5432
try:
    conn = psycopg2.connect(dbname=dbname, user=user, password=password, host=host, port=port)
    conn.close()
    print('OK')
    sys.exit(0)
except Exception as e:
    # print(e)
    sys.exit(1)
PY
}

echo "Checking database readiness..."
until try_connect; do
  echo "Database is unavailable - sleeping 1"
  sleep 1
done

echo "Database is up — running optional migration from normalized_catalog.json (if present)"
if [ -f "/app/catalog/normalized_catalog.json" ]; then
  echo "Found normalized_catalog.json — checking for macros and loading into DB"
  python - <<'PY'
from core import db
import json, os
print('Creating tables if needed...')
db.create_tables()
norm='/app/catalog/normalized_catalog.json'
with open(norm,'r',encoding='utf-8') as f:
  items=json.load(f)
need_macro = not items or 'macro' not in items[0]
if need_macro:
  # Respect CATALOG_RUN_ON_START: if it's set to "1" run auto-group on
  # startup, otherwise skip to avoid expensive clustering during container
  # boot (useful in development).
  import os
  if os.environ.get('CATALOG_RUN_ON_START', '1') == '1':
    print('normalized_catalog.json missing macro field — running auto-group')
    try:
      from catalog.auto_group_catalog import run_auto_group
      run_auto_group(norm_path=norm, backup=True, reload_db=False)
    except Exception as e:
      print('Auto-group failed:', e)
      # continue and attempt load
  else:
    print('normalized_catalog.json missing macro field — skipping auto-group due to CATALOG_RUN_ON_START!=1')
print('Loading normalized_catalog.json into DB')
db.load_json_into_db(norm)
print('Migration/load completed')
PY
else
  echo "No normalized_catalog.json found — generating catalog, normalizing and auto-grouping"
  python - <<'PY'
import traceback
try:
    from catalog.generate_catalog import generate_catalog
    generate_catalog()
except Exception:
    traceback.print_exc()
    print('Catalog generation failed')
    # still attempt to load if file created
if True:
    from core import db
    import os
    norm='/app/catalog/normalized_catalog.json'
    if os.path.exists(norm):
        print('Creating tables and loading generated normalized_catalog.json')
        db.create_tables()
        db.load_json_into_db(norm)
    else:
        print('normalized_catalog.json still missing after generation')
PY
fi

echo "Checking for local sqlite DB to migrate (/app/groceries.db)"
if [ -f "/app/groceries.db" ]; then
  echo "Found sqlite DB — running migration script"
  python /app/scripts/migrate_sqlite_to_postgres.py || echo "SQLite->Postgres migration failed (continuing)"
else
  echo "No sqlite DB found — skipping sqlite migration"
fi

echo "Starting server"

# Start a background scheduler to regenerate the catalog periodically
# Controlled by environment variable `CATALOG_GENERATE_INTERVAL_HOURS` (default 12)
# Set `DISABLE_CATALOG_SCHEDULE=1` to disable the background scheduler.
CATALOG_INTERVAL_HOURS=${CATALOG_GENERATE_INTERVAL_HOURS:-12}
# Control whether to run once immediately on container start (default: 1)
CATALOG_RUN_ON_START=${CATALOG_RUN_ON_START:-1}
# Maximum age (hours) before generation considered stale (not used here but available)
CATALOG_MAX_AGE_HOURS=${CATALOG_MAX_AGE_HOURS:-${CATALOG_INTERVAL_HOURS}}
LOCKFILE=/tmp/catalog-generator.lock
LOGFILE=/app/logs/catalog-generator.log

if [ "${DISABLE_CATALOG_SCHEDULE:-0}" != "1" ]; then
  mkdir -p /app/logs
  echo "Starting background catalog generator every ${CATALOG_INTERVAL_HOURS} hours (logs: ${LOGFILE})"
  (
    # Optionally run once immediately on start
    if [ "${CATALOG_RUN_ON_START}" = "1" ]; then
      echo "$(date '+%Y-%m-%d %H:%M:%S') - Initial scheduled run: generate_catalog()" >> ${LOGFILE} 2>&1 || true
      # If catalog file exists and is newer than CATALOG_MAX_AGE_HOURS, skip initial run
      NORM_FILE=/app/catalog/normalized_catalog.json
      SKIP_BY_AGE=0
      if [ -f "${NORM_FILE}" ]; then
        now=$(date +%s)
        mtime=$(stat -c %Y "${NORM_FILE}" 2>/dev/null || stat -f %m "${NORM_FILE}")
        age_seconds=$((now - mtime))
        age_hours=$((age_seconds / 3600))
        if [ "${age_hours}" -lt "${CATALOG_MAX_AGE_HOURS}" ]; then
          SKIP_BY_AGE=1
          echo "$(date '+%Y-%m-%d %H:%M:%S') - Skipping initial generation: catalog age ${age_hours}h < ${CATALOG_MAX_AGE_HOURS}h" >> ${LOGFILE} 2>&1 || true
        fi
      fi

      if [ "${SKIP_BY_AGE}" -eq 1 ]; then
        :
      else
        if [ -f "${LOCKFILE}" ] && kill -0 "$(cat ${LOCKFILE})" 2>/dev/null; then
          echo "$(date '+%Y-%m-%d %H:%M:%S') - Initial run skipped, previous run in progress (pid $(cat ${LOCKFILE}))" >> ${LOGFILE} 2>&1 || true
        else
          python - <<'PY' >> ${LOGFILE} 2>&1 &
try:
    from catalog.generate_catalog import generate_catalog
    generate_catalog()
except Exception:
    import traceback; traceback.print_exc()
PY
          echo $! > "${LOCKFILE}"
          wait $!
          rm -f "${LOCKFILE}"
        fi
      fi
    fi

    # Periodic loop
    while true; do
      sleep $((CATALOG_INTERVAL_HOURS * 3600))
      echo "$(date '+%Y-%m-%d %H:%M:%S') - Scheduled run: generate_catalog()" >> ${LOGFILE} 2>&1 || true
      # Skip periodic run if catalog file is newer than threshold
      NORM_FILE=/app/catalog/normalized_catalog.json
      if [ -f "${NORM_FILE}" ]; then
        now=$(date +%s)
        mtime=$(stat -c %Y "${NORM_FILE}" 2>/dev/null || stat -f %m "${NORM_FILE}")
        age_seconds=$((now - mtime))
        age_hours=$((age_seconds / 3600))
        if [ "${age_hours}" -lt "${CATALOG_MAX_AGE_HOURS}" ]; then
          echo "$(date '+%Y-%m-%d %H:%M:%S') - Skipping scheduled generation: catalog age ${age_hours}h < ${CATALOG_MAX_AGE_HOURS}h" >> ${LOGFILE} 2>&1 || true
          continue
        fi
      fi

      if [ -f "${LOCKFILE}" ] && kill -0 "$(cat ${LOCKFILE})" 2>/dev/null; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') - Previous run still in progress, skipping scheduled run" >> ${LOGFILE} 2>&1 || true
        continue
      fi
      python - <<'PY' >> ${LOGFILE} 2>&1 &
try:
    from catalog.generate_catalog import generate_catalog
    generate_catalog()
except Exception:
    import traceback; traceback.print_exc()
PY
      echo $! > "${LOCKFILE}"
      wait $!
      rm -f "${LOCKFILE}"
    done
  ) &
else
  echo "Catalog scheduler disabled by DISABLE_CATALOG_SCHEDULE=1"
fi

exec "$@"
