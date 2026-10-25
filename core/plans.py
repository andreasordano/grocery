# =============================================================================
# WEEKLY PLANS  (the newsletter's dinners, WEB-37)
# plans(token, title, dinners JSON, featured, created): the dinners of one newsletter edition,
# opened in the app with /?plan=<token>, which loads them as one trip, priced fresh for whoever opens it.
# dinners are recipe ids of any kind (classics, "nd-…" NutriData dishes, "sh-…" snapshots such as a
# featured dinner imported from a store's recipe page). featured: the one shown as "Featured", or None.
# Made by scripts/weekly_plan.py. Same database as the event log (core/events.py).
# =============================================================================

import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS plans (
    token TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    dinners TEXT NOT NULL,
    featured TEXT,
    created TEXT NOT NULL
)
"""

_POSTGRES_SCHEMA = _SQLITE_SCHEMA.replace("dinners TEXT", "dinners JSONB").replace("created TEXT", "created TIMESTAMPTZ")


def _connect():
    url = os.environ.get("DATABASE_URL")
    if url:
        import psycopg  # only needed when Postgres is configured
        conn, schema, ph = psycopg.connect(url), _POSTGRES_SCHEMA, "%s"
    else:
        path = os.environ.get("EVENTS_DB", "logs/events.db")
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        conn, schema, ph = sqlite3.connect(path), _SQLITE_SCHEMA, "?"
    conn.execute(schema)
    return conn, ph


def create(title, dinners, featured=None):
    """Store a plan and return its token. featured must be one of the dinners."""
    dinners = list(dict.fromkeys(d for d in dinners if d))
    if not dinners:
        raise ValueError("A plan needs at least one dinner.")
    if featured and featured not in dinners:
        raise ValueError("The featured dinner must be one of the plan's dinners.")
    token = secrets.token_urlsafe(6)
    conn, ph = _connect()
    try:
        conn.execute(f"INSERT INTO plans (token, title, dinners, featured, created) VALUES ({', '.join([ph] * 5)})",
                     (token, title.strip()[:80] or "This week", json.dumps(dinners), featured,
                      datetime.now(timezone.utc).isoformat()))
        conn.commit()
        return token
    finally:
        conn.close()


def get(token):
    """{token, title, dinners, featured}, or None."""
    conn, ph = _connect()
    try:
        r = conn.execute(f"SELECT token, title, dinners, featured FROM plans WHERE token = {ph}", (token,)).fetchone()
    finally:
        conn.close()
    if not r:
        return None
    return {"token": r[0], "title": r[1], "dinners": r[2] if isinstance(r[2], list) else json.loads(r[2]), "featured": r[3]}
