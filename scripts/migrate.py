"""Apply supabase/migrations to a local or test Postgres (the docker-compose db), in order, each once.

Production is migrated with `supabase db push`, never with this. Applied versions are kept in the table
_migrations. Supabase's own roles (anon, authenticated) are created when missing, so the migrations run
as they do there.

  python -m scripts.migrate                  # DATABASE_URL, e.g. postgresql://groceries:groceries@localhost:5433/groceries
  python -m scripts.migrate <database url>
"""

import os
import sys
from pathlib import Path

import psycopg

MIGRATIONS = Path(__file__).resolve().parent.parent / "supabase" / "migrations"


def migrate(url):
    """Apply the migrations not applied yet; returns their versions."""
    if "supabase" in url:
        raise SystemExit("This is Supabase: migrate production with `supabase db push`.")
    done = []
    with psycopg.connect(url, autocommit=True) as conn:
        for role in ("anon", "authenticated"):
            if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone():
                conn.execute(f"CREATE ROLE {role} NOLOGIN")
        conn.execute("CREATE TABLE IF NOT EXISTS _migrations (version TEXT PRIMARY KEY, applied TIMESTAMPTZ DEFAULT now())")
        applied = {r[0] for r in conn.execute("SELECT version FROM _migrations")}
        for path in sorted(MIGRATIONS.glob("*.sql")):
            version = path.name.split("_", 1)[0]
            if version in applied:
                continue
            with conn.transaction():
                conn.execute(path.read_text())
                conn.execute("RESET search_path")
                conn.execute("INSERT INTO _migrations (version) VALUES (%s)", (version,))
            done.append(version)
    return done


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DATABASE_URL")
    if not url:
        sys.exit(__doc__)
    applied = migrate(url)
    print(f"Applied {len(applied)} migrations{': ' + ', '.join(applied) if applied else ''}.")
