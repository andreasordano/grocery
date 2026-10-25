# =============================================================================
# MY DINNERS  (people's own recipes, and dinners shared by link)
# my_dinners(id, user_id, name, servings, items JSON, method, link, image, created, updated).
# shares(token, user_id, recipe_id, name, servings, items JSON, pantry JSON, method, link, image, created):
# a snapshot of a dinner someone sent; anyone with the link can open it.
# Items are typed lines with optional quantities ("paprika 600g", "2 piim"), priced
# like a shopping list and scaled from `servings` to the number of people cooking.
# `method` (how to cook it), `link` (a recipe page) and `image` (its photo URL, from a recipe
# link: core/recipe_import.py) are optional.
# Owners are the name in the personal link (?u=…); there are no passwords, so the
# links given to testers should be unique. Postgres (core/db.py); tables from supabase/migrations.
# =============================================================================

import re
import secrets
from datetime import datetime, timezone

from psycopg.types.json import Jsonb

from core import db

MAX_ITEMS = 60
MAX_METHOD = 4000  # characters of "how to cook it"

_NOTES = ("method", "link", "image")  # the optional columns
_COLUMNS = f"id, name, servings, items, {', '.join(_NOTES)}"


def _row(r):
    return {"id": f"my-{r[0]}", "name": r[1], "servings": r[2], "items": r[3], **dict(zip(_NOTES, r[4:]))}


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
    rows = db.query(f"SELECT {_COLUMNS} FROM my_dinners WHERE user_id = %s ORDER BY name", (user_id,))
    return [_row(r) for r in rows]


def get(user_id, dinner_id):
    """This person's dinner, or None (also for someone else's)."""
    num = _num(dinner_id)
    if not user_id or num is None:
        return None
    rows = db.query(f"SELECT {_COLUMNS} FROM my_dinners WHERE id = %s AND user_id = %s", (num, user_id))
    return _row(rows[0]) if rows else None


def save(user_id, name, servings, items, dinner_id=None, method=None, link=None, image=None):
    """Create a dinner, or update one this person owns. Returns it, or None if not theirs."""
    name, servings, items = clean(name, servings, items)
    notes = clean_notes(method, link, image)
    values = (name, servings, Jsonb(items), *(notes[k] for k in _NOTES))
    now = datetime.now(timezone.utc)
    with db.connection() as conn:
        if dinner_id is None:
            num = conn.execute(f"INSERT INTO my_dinners (name, servings, items, {', '.join(_NOTES)}, user_id, created, updated) "
                               "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id", (*values, user_id, now, now)).fetchone()[0]
        else:
            num = _num(dinner_id)
            sets = ", ".join(f"{c} = %s" for c in ("name", "servings", "items", *_NOTES, "updated"))
            if conn.execute(f"UPDATE my_dinners SET {sets} WHERE id = %s AND user_id = %s",
                            (*values, now, num, user_id)).rowcount == 0:
                return None
    return {"id": f"my-{num}", "name": name, "servings": servings, "items": items, **notes}


def delete(user_id, dinner_id):
    """True if this person's dinner was deleted."""
    with db.connection() as conn:
        return conn.execute("DELETE FROM my_dinners WHERE id = %s AND user_id = %s", (_num(dinner_id), user_id)).rowcount > 0


def share(user_id, recipe_id, name, servings, items, pantry=(), method=None, link=None, image=None):
    """Store a snapshot of a dinner and return its link token. Later edits don't change what was sent."""
    name, servings, items = clean(name, servings, items)
    notes = clean_notes(method, link, image)
    token = secrets.token_urlsafe(6)  # 8 characters, ~48 bits: not guessable
    with db.connection() as conn:
        conn.execute(f"INSERT INTO shares (token, user_id, recipe_id, name, servings, items, pantry, {', '.join(_NOTES)}, created) "
                     "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                     (token, user_id, recipe_id, name, servings, Jsonb(items), Jsonb(list(pantry)),
                      *(notes[k] for k in _NOTES), datetime.now(timezone.utc)))
    return token


def shared(token):
    """The dinner behind a link, or None."""
    rows = db.query(f"SELECT token, name, servings, items, pantry, {', '.join(_NOTES)} FROM shares WHERE token = %s", (token,))
    if not rows:
        return None
    r = rows[0]
    return {"id": f"sh-{r[0]}", "token": r[0], "name": r[1], "servings": r[2], "items": r[3], "pantry": r[4],
            **dict(zip(_NOTES, r[5:]))}


def as_recipe(dinner):
    """A saved dinner in the shape catalog.recommend uses: typed items are its ingredients."""
    if dinner is None:
        return None
    return {"id": dinner["id"], "name": dinner["name"], "servings": dinner["servings"],
            "ingredients": dinner["items"], "pantry": dinner.get("pantry", []),
            **{k: dinner.get(k) for k in _NOTES}}
