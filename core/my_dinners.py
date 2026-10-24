# =============================================================================
# MY DINNERS  (people's own recipes, and dinners shared by link)
# my_dinners(id, user_id, name, servings, items JSON, method, link, image, created, updated).
# shares(token, user_id, recipe_id, name, servings, items JSON, pantry JSON, method, link, image, created):
# a snapshot of a dinner someone sent; anyone with the link can open it.
# Items are typed lines with optional quantities ("paprika 600g", "2 piim"), priced
# like a shopping list and scaled from `servings` to the number of people cooking.
# `method` (how to cook it), `link` (a recipe page) and `image` (its photo URL, from a recipe
# link: core/recipe_import.py) are optional. Until the image column's migration has run on
# Postgres, dinners are kept without their photo.
# Owners are the name in the personal link (?u=…); there are no passwords, so the
# links given to testers should be unique. Same database as the event log:
# Postgres when DATABASE_URL is set, otherwise the local SQLite file at EVENTS_DB.
# =============================================================================

import json
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime, timezone

MAX_ITEMS = 60
MAX_METHOD = 4000  # characters of "how to cook it"

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS my_dinners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    servings INTEGER NOT NULL,
    items TEXT NOT NULL,
    method TEXT,
    link TEXT,
    image TEXT,
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
    method TEXT,
    link TEXT,
    image TEXT,
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
    method TEXT,
    link TEXT,
    image TEXT,
    created TIMESTAMPTZ NOT NULL,
    updated TIMESTAMPTZ NOT NULL
)
"""


_NOTES = ("method", "link", "image")  # the optional columns
_image_column = {"there": False, "checked": 0.0}


def _notes(conn, postgres):
    """The optional columns this database has. On Postgres the image column comes with a migration
    (supabase/migrations); until it has run, dinners are saved without their photo."""
    if postgres and not _image_column["there"] and time.time() - _image_column["checked"] > 300:
        _image_column["checked"] = time.time()
        _image_column["there"] = conn.execute(
            "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' "
            "AND table_name IN ('my_dinners', 'shares') AND column_name = 'image'").fetchone()[0] == 2
    return _NOTES if not postgres or _image_column["there"] else _NOTES[:2]


def _connect():
    """(connection, placeholder, optional columns it has) with the tables created."""
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
    if not url:  # local files made before the optional columns existed (Postgres: supabase/migrations)
        for table in ("my_dinners", "shares"):
            have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            for column in _NOTES:
                if column not in have:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
    return conn, ph, _notes(conn, bool(url))


def _row(r, notes):
    items = r[3] if isinstance(r[3], list) else json.loads(r[3])
    return {"id": f"my-{r[0]}", "name": r[1], "servings": r[2], "items": items,
            **{k: None for k in _NOTES}, **dict(zip(notes, r[4:]))}


def _num(dinner_id):
    try:
        return int(str(dinner_id).removeprefix("my-"))
    except ValueError:
        return None


_WEB = re.compile(r"https?://[^\s/]+\.[^\s]+$")


def clean_notes(method, link, image=None):
    """Validated {method, link, image}: each may be None. ValueError with a message for the person."""
    method = (method or "").strip()[:MAX_METHOD] or None
    link = (link or "").strip() or None
    if link and not _WEB.match(link):
        raise ValueError("The recipe link should be a web address, like https://nami-nami.ee/…")
    image = (image or "").strip() or None
    if image and (not _WEB.match(image) or len(image) > 1000):
        image = None  # a photo is a nicety: never a reason to refuse the dinner
    return {"method": method, "link": link[:500] if link else None, "image": image}


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
    conn, ph, notes = _connect()
    try:
        rows = conn.execute(f"SELECT id, name, servings, items, {', '.join(notes)} FROM my_dinners "
                            f"WHERE user_id = {ph} ORDER BY name", (user_id,)).fetchall()
        return [_row(r, notes) for r in rows]
    finally:
        conn.close()


def get(user_id, dinner_id):
    """This person's dinner, or None (also for someone else's)."""
    num = _num(dinner_id)
    if not user_id or num is None:
        return None
    conn, ph, notes = _connect()
    try:
        r = conn.execute(f"SELECT id, name, servings, items, {', '.join(notes)} FROM my_dinners "
                         f"WHERE id = {ph} AND user_id = {ph}", (num, user_id)).fetchone()
        return _row(r, notes) if r else None
    finally:
        conn.close()


def save(user_id, name, servings, items, dinner_id=None, method=None, link=None, image=None):
    """Create a dinner, or update one this person owns. Returns it, or None if not theirs."""
    name, servings, items = clean(name, servings, items)
    extra = clean_notes(method, link, image)
    now = datetime.now(timezone.utc).isoformat()
    conn, ph, notes = _connect()
    kept = [extra[k] for k in notes]
    try:
        if dinner_id is None:
            cols = ["user_id", "name", "servings", "items", *notes, "created", "updated"]
            cur = conn.execute(
                f"INSERT INTO my_dinners ({', '.join(cols)}) VALUES ({', '.join([ph] * len(cols))}) RETURNING id",
                (user_id, name, servings, json.dumps(items, ensure_ascii=False), *kept, now, now))
            num = cur.fetchone()[0]
        else:
            num = _num(dinner_id)
            sets = ", ".join(f"{c} = {ph}" for c in ["name", "servings", "items", *notes, "updated"])
            cur = conn.execute(
                f"UPDATE my_dinners SET {sets} WHERE id = {ph} AND user_id = {ph}",
                (name, servings, json.dumps(items, ensure_ascii=False), *kept, now, num, user_id))
            if cur.rowcount == 0:
                return None
        conn.commit()
        return {"id": f"my-{num}", "name": name, "servings": servings, "items": items,
                **{k: None for k in _NOTES}, **dict(zip(notes, kept))}
    finally:
        conn.close()


def delete(user_id, dinner_id):
    """True if this person's dinner was deleted."""
    conn, ph, _ = _connect()
    try:
        cur = conn.execute(f"DELETE FROM my_dinners WHERE id = {ph} AND user_id = {ph}", (_num(dinner_id), user_id))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def share(user_id, recipe_id, name, servings, items, pantry=(), method=None, link=None, image=None):
    """Store a snapshot of a dinner and return its link token. Later edits don't change what was sent."""
    name, servings, items = clean(name, servings, items)
    extra = clean_notes(method, link, image)
    token = secrets.token_urlsafe(6)  # 8 characters, ~48 bits: not guessable
    conn, ph, notes = _connect()
    cols = ["token", "user_id", "recipe_id", "name", "servings", "items", "pantry", *notes, "created"]
    try:
        conn.execute(
            f"INSERT INTO shares ({', '.join(cols)}) VALUES ({', '.join([ph] * len(cols))})",
            (token, user_id, recipe_id, name, servings, json.dumps(items, ensure_ascii=False),
             json.dumps(list(pantry), ensure_ascii=False), *[extra[k] for k in notes],
             datetime.now(timezone.utc).isoformat()))
        conn.commit()
        return token
    finally:
        conn.close()


def shared(token):
    """The dinner behind a link, or None."""
    conn, ph, notes = _connect()
    try:
        r = conn.execute(f"SELECT token, name, servings, items, pantry, {', '.join(notes)} FROM shares WHERE token = {ph}",
                         (token,)).fetchone()
    finally:
        conn.close()
    if not r:
        return None
    load = lambda v: v if isinstance(v, list) else json.loads(v)
    return {"id": f"sh-{r[0]}", "token": r[0], "name": r[1], "servings": r[2], "items": load(r[3]), "pantry": load(r[4]),
            **{k: None for k in _NOTES}, **dict(zip(notes, r[5:]))}


def as_recipe(dinner):
    """A saved dinner in the shape catalog.recommend uses: typed items are its ingredients."""
    if dinner is None:
        return None
    return {"id": dinner["id"], "name": dinner["name"], "servings": dinner["servings"],
            "ingredients": dinner["items"], "pantry": dinner.get("pantry", []),
            **{k: dinner.get(k) for k in _NOTES}}
