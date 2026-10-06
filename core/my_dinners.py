# =============================================================================
# MY DINNERS  (people's own recipes, and dinners shared by link)
# my_dinners(id, user_id, name, servings, items JSON, created, updated).
# shares(token, user_id, recipe_id, name, servings, items JSON, pantry JSON, created):
# a snapshot of a dinner someone sent; anyone with the link can open it.
# Items are typed lines with optional quantities ("paprika 600g", "2 piim"), priced
# like a shopping list and scaled from `servings` to the number of people cooking.
# Owners are the name in the personal link (?u=…); there are no passwords, so the
# links given to testers should be unique. Same database as the event log:
# Postgres when DATABASE_URL is set, otherwise the local SQLite file at EVENTS_DB.
# =============================================================================

import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone

MAX_ITEMS = 60

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS my_dinners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    servings INTEGER NOT NULL,
    items TEXT NOT NULL,
    created TEXT NOT NULL,
    updated TEXT NOT NULL
)
"""

_SQLITE_SHARES = """
CREATE TABLE IF NOT EXISTS shares (
    token TEXT PRIMARY KEY,
    user_id TEXT,
    recipe_id TEXT,
    name TEXT NOT NULL,
    servings INTEGER NOT NULL,
    items TEXT NOT NULL,
    pantry TEXT NOT NULL,
    created TEXT NOT NULL
)
"""

_POSTGRES_SHARES = _SQLITE_SHARES.replace("items TEXT", "items JSONB").replace("pantry TEXT", "pantry JSONB") \
    .replace("created TEXT", "created TIMESTAMPTZ")

_POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS my_dinners (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    servings INTEGER NOT NULL,
    items JSONB NOT NULL,
    created TIMESTAMPTZ NOT NULL,
    updated TIMESTAMPTZ NOT NULL
)
"""


def _connect():
    """(connection, placeholder) with the table created."""
    url = os.environ.get("DATABASE_URL")
    if url:
        import psycopg  # only needed when Postgres is configured
        conn, schemas, ph = psycopg.connect(url), (_POSTGRES_SCHEMA, _POSTGRES_SHARES), "%s"
    else:
        path = os.environ.get("EVENTS_DB", "logs/events.db")
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        conn, schemas, ph = sqlite3.connect(path), (_SQLITE_SCHEMA, _SQLITE_SHARES), "?"
    for schema in schemas:
        conn.execute(schema)
    return conn, ph


def _row(r):
    items = r[3] if isinstance(r[3], list) else json.loads(r[3])
    return {"id": f"my-{r[0]}", "name": r[1], "servings": r[2], "items": items}


def _num(dinner_id):
    try:
        return int(str(dinner_id).removeprefix("my-"))
    except ValueError:
        return None


def clean(name, servings, items):
    """Validated (name, servings, items), or ValueError with a message for the person."""
    name = " ".join((name or "").split())[:80]
    items = list(dict.fromkeys(" ".join(i.split())[:80] for i in items or [] if i and i.strip()))
    if not name:
        raise ValueError("Give the dinner a name.")
    if not items:
        raise ValueError("Add at least one thing to buy.")
    if len(items) > MAX_ITEMS:
        raise ValueError(f"A dinner can have at most {MAX_ITEMS} things to buy.")
    return name, max(1, min(int(servings or 2), 12)), items


def list_for(user_id):
    conn, ph = _connect()
    try:
        rows = conn.execute(f"SELECT id, name, servings, items FROM my_dinners WHERE user_id = {ph} ORDER BY name",
                            (user_id,)).fetchall()
        return [_row(r) for r in rows]
    finally:
        conn.close()


def get(user_id, dinner_id):
    """This person's dinner, or None (also for someone else's)."""
    num = _num(dinner_id)
    if not user_id or num is None:
        return None
    conn, ph = _connect()
    try:
        r = conn.execute(f"SELECT id, name, servings, items FROM my_dinners WHERE id = {ph} AND user_id = {ph}",
                         (num, user_id)).fetchone()
        return _row(r) if r else None
    finally:
        conn.close()


def save(user_id, name, servings, items, dinner_id=None):
    """Create a dinner, or update one this person owns. Returns it, or None if not theirs."""
    name, servings, items = clean(name, servings, items)
    now = datetime.now(timezone.utc).isoformat()
    conn, ph = _connect()
    try:
        if dinner_id is None:
            cur = conn.execute(
                f"INSERT INTO my_dinners (user_id, name, servings, items, created, updated) "
                f"VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}) RETURNING id",
                (user_id, name, servings, json.dumps(items, ensure_ascii=False), now, now))
            num = cur.fetchone()[0]
        else:
            num = _num(dinner_id)
            cur = conn.execute(
                f"UPDATE my_dinners SET name = {ph}, servings = {ph}, items = {ph}, updated = {ph} "
                f"WHERE id = {ph} AND user_id = {ph}",
                (name, servings, json.dumps(items, ensure_ascii=False), now, num, user_id))
            if cur.rowcount == 0:
                return None
        conn.commit()
        return {"id": f"my-{num}", "name": name, "servings": servings, "items": items}
    finally:
        conn.close()


def delete(user_id, dinner_id):
    """True if this person's dinner was deleted."""
    conn, ph = _connect()
    try:
        cur = conn.execute(f"DELETE FROM my_dinners WHERE id = {ph} AND user_id = {ph}", (_num(dinner_id), user_id))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def share(user_id, recipe_id, name, servings, items, pantry=()):
    """Store a snapshot of a dinner and return its link token. Later edits don't change what was sent."""
    name, servings, items = clean(name, servings, items)
    token = secrets.token_urlsafe(6)  # 8 characters, ~48 bits: not guessable
    conn, ph = _connect()
    try:
        conn.execute(
            f"INSERT INTO shares (token, user_id, recipe_id, name, servings, items, pantry, created) "
            f"VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})",
            (token, user_id, recipe_id, name, servings, json.dumps(items, ensure_ascii=False),
             json.dumps(list(pantry), ensure_ascii=False), datetime.now(timezone.utc).isoformat()))
        conn.commit()
        return token
    finally:
        conn.close()


def shared(token):
    """The dinner behind a link, or None."""
    conn, ph = _connect()
    try:
        r = conn.execute(f"SELECT token, name, servings, items, pantry FROM shares WHERE token = {ph}",
                         (token,)).fetchone()
    finally:
        conn.close()
    if not r:
        return None
    load = lambda v: v if isinstance(v, list) else json.loads(v)
    return {"id": f"sh-{r[0]}", "token": r[0], "name": r[1], "servings": r[2], "items": load(r[3]), "pantry": load(r[4])}


def as_recipe(dinner):
    """A saved dinner in the shape catalog.recommend uses: typed items are its ingredients."""
    if dinner is None:
        return None
    return {"id": dinner["id"], "name": dinner["name"], "servings": dinner["servings"],
            "ingredients": dinner["items"], "pantry": dinner.get("pantry", [])}
