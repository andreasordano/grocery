# =============================================================================
# EVENTS  (validation data)
# Append-only log of what users do: requests, recommendations, accept/reject.
# One table: events(id, ts, user_id, session_id, type, data JSON).
# Uses Postgres when DATABASE_URL is set (needed on hosts with ephemeral disks,
# e.g. Render), otherwise a local SQLite file at EVENTS_DB.
# Logging must never break a user request, so failures are swallowed.
# Every event's data also says `country`, `app_version` (git commit) and `internal`
# (the founder or Claude: leave those out of every metric).
# =============================================================================

import json
import os
import sqlite3
import subprocess
import threading
from datetime import datetime, timezone

COUNTRY = "EE"

# Every event the app logs, and what it means. tests/test_core.py checks the code uses only these.
EVENT_TYPES = {
    # visits and people
    "visit": "a page load (from: tester_link, shared_dinner or direct; first_visit; referrer)",
    "hello": "the name typed on the first visit",
    "usual_store": "the store someone usually shops at (store, or null for skip)",
    "delete_request": "someone asked for their data to be deleted",
    # answers and what people did with them
    "basket": "a recommendation: every store's basket, with a result_id",
    "accept": "\"I'll go to <store>\" under an answer",
    "reject": "\"Not for me\" under an answer",
    "view_store": "looking at another store's receipt",
    "wrong_product": "reporting a wrong product",
    "preference": "choosing another product or typing preference words",
    "add_pantry": "adding a have-at-home item to the trip",
    "quick_view": "tapping a product's photo",
    "open_product": "opening a product in the store's e-shop (from: quick_view, chooser, cart)",
    "recipe_open": "unfolding a recipe card",
    # choosing dinners and items
    "dinner_category": "picking a kind of dinner",
    "dinner_shuffle": "\"Show me others\"",
    "trip_change": "a dinner added to or taken out of the trip (dinners: how many now)",
    "item_added": "an item added to a list (how: typed or suggestion)",
    "item_changed": "an item edited",
    # people's own dinners and sharing
    "my_dinner_saved": "a dinner of one's own saved",
    "my_dinner_deleted": "a dinner of one's own deleted",
    "recipe_import": "reading a recipe link (site and items, or why it failed)",
    "share_created": "a link made to send a dinner",
    "share_opened": "a sent dinner opened",
    # shopping online
    "cart_click": "\"Send this to the <store> cart\" without the extension",
    "cart_interest": "the answer to \"would you use one tap?\" (wants)",
    "cart_send": "a basket sent to the Rimi extension",
    "extension_download": "the Rimi extension downloaded",
}


def _app_version():
    """The deployed git commit (Render sets RENDER_GIT_COMMIT), else the local one, else "dev"."""
    commit = os.environ.get("RENDER_GIT_COMMIT")
    if not commit:
        try:
            commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=2,
                                    cwd=os.path.dirname(os.path.abspath(__file__))).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            commit = ""
    return commit[:7] or "dev"


APP_VERSION = _app_version()


def is_internal(user_id=None, name=None):
    """The founder (tester link or name "andrea") or Claude's checks: not real testers.
    A stranger who types exactly "Andrea" would be counted as internal too."""
    uid = (user_id or "").strip().lower()
    return uid == "andrea" or uid.startswith(("claude", "internal-")) or (name or "").strip().lower() == "andrea"

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


def log_event(type: str, data: dict | None = None, user_id: str | None = None, session_id: str | None = None,
              name: str | None = None):
    """Append one event. Returns True on success, False if logging failed.
    name: the person's name, only to tell whether they're internal; it isn't stored."""
    data = {**(data or {}), "country": COUNTRY, "app_version": APP_VERSION, "internal": is_internal(user_id, name)}
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
                        json.dumps(data, ensure_ascii=False, default=str),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return True
    except Exception as exc:
        print(f"event logging failed ({type}): {exc}")
        return False
