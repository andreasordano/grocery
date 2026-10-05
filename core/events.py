# =============================================================================
# EVENTS  (validation data)
# Append-only log of what users do: requests, recommendations, accept/reject.
# One table: events(id, ts, user_id, session_id, type, data JSON).
# Uses Postgres when DATABASE_URL is set (needed on hosts with ephemeral disks,
# e.g. Render), otherwise a local SQLite file at EVENTS_DB.
# Logging must never break a user request, so failures are swallowed.
# =============================================================================

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone

_lock = threading.Lock()
_initialized = False

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    user_id TEXT,
    session_id TEXT,
    type TEXT NOT NULL,
    data TEXT
)
"""

_POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL,
    user_id TEXT,
    session_id TEXT,
    type TEXT NOT NULL,
    data JSONB
)
"""


def _connect():
    url = os.environ.get("DATABASE_URL")
    if url:
        import psycopg  # only needed when Postgres is configured
        return psycopg.connect(url), _POSTGRES_SCHEMA, ("%s::timestamptz", "%s", "%s", "%s", "%s::jsonb")
    path = os.environ.get("EVENTS_DB", "logs/events.db")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    return sqlite3.connect(path), _SQLITE_SCHEMA, ("?",) * 5


def log_event(type: str, data: dict | None = None, user_id: str | None = None, session_id: str | None = None):
    """Append one event. Returns True on success, False if logging failed."""
    global _initialized
    try:
        with _lock:
            conn, schema, placeholders = _connect()
            try:
                if not _initialized:
                    conn.execute(schema)
                    _initialized = True
                conn.execute(
                    f"INSERT INTO events (ts, user_id, session_id, type, data) VALUES ({', '.join(placeholders)})",
                    (
                        datetime.now(timezone.utc).isoformat(),
                        user_id,
                        session_id,
                        type,
                        json.dumps(data or {}, ensure_ascii=False, default=str),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return True
    except Exception as exc:
        print(f"event logging failed ({type}): {exc}")
        return False
