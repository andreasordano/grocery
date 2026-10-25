# =============================================================================
# WEEKLY PLANS  (the newsletter's dinners, WEB-37)
# plans(token, title, dinners JSON, featured, created): the dinners of one newsletter edition,
# opened in the app with /?plan=<token>, which loads them as one trip, priced fresh for whoever opens it.
# dinners are recipe ids of any kind (classics, "nd-…" NutriData dishes, "sh-…" snapshots such as a
# featured dinner imported from a store's recipe page). featured: the one shown as "Featured", or None.
# Made by core/editions.py. Postgres (core/db.py); the table comes from supabase/migrations.
# =============================================================================

import secrets
from datetime import datetime, timezone

from psycopg.types.json import Jsonb

from core import db


def create(title, dinners, featured=None):
    """Store a plan and return its token. featured must be one of the dinners."""
    dinners = list(dict.fromkeys(d for d in dinners if d))
    if not dinners:
        raise ValueError("A plan needs at least one dinner.")
    if featured and featured not in dinners:
        raise ValueError("The featured dinner must be one of the plan's dinners.")
    token = secrets.token_urlsafe(6)
    with db.connection() as conn:
        conn.execute("INSERT INTO plans (token, title, dinners, featured, created) VALUES (%s, %s, %s, %s, %s)",
                     (token, title.strip()[:80] or "This week", Jsonb(dinners), featured, datetime.now(timezone.utc)))
    return token


def get(token):
    """{token, title, dinners, featured}, or None."""
    rows = db.query("SELECT token, title, dinners, featured FROM plans WHERE token = %s", (token,))
    if not rows:
        return None
    r = rows[0]
    return {"token": r[0], "title": r[1], "dinners": r[2], "featured": r[3]}
