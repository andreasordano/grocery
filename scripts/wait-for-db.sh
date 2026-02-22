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
  echo "Found normalized_catalog.json — loading into DB (idempotent)"
  python - <<'PY'
from core import db
print('Creating tables if needed...')
db.create_tables()
print('Loading normalized_catalog.json into DB')
db.load_json_into_db('/app/catalog/normalized_catalog.json')
print('Migration/load completed')
PY
else
  echo "No normalized_catalog.json found — skipping data load"
fi

echo "Checking for local sqlite DB to migrate (/app/groceries.db)"
if [ -f "/app/groceries.db" ]; then
  echo "Found sqlite DB — running migration script"
  python /app/scripts/migrate_sqlite_to_postgres.py || echo "SQLite->Postgres migration failed (continuing)"
else
  echo "No sqlite DB found — skipping sqlite migration"
fi

echo "Starting server"
exec "$@"
