# =============================================================================
# PANTRYRUN'S OWN DINNERS  (the recipes table, edited in /admin.html; WEB-53)
# A dinner is typed items for `servings` people, priced like someone's own dinner, plus what its card and
# recipe show. Ids are "pr-<name>" and stay: a dinner is archived, never deleted, so usage data
# (metrics.dinner_usage) keeps pointing at it. The app sees published dinners only, read at most once a minute
# and again at once after an edit. The chips above the dinners (data/dinner_chips.yaml) are worked out here
# for every kind of dinner.
# =============================================================================

import re
import threading
import time
import unicodedata
from datetime import date, datetime
from zoneinfo import ZoneInfo

from core import catalog, db

FIELDS = ("id", "name", "about", "method", "emoji", "image", "servings", "minutes", "ingredients", "pantry", "tags",
          "months", "brand", "label", "rights", "status", "review_by", "notes", "created", "updated")
EDITABLE = FIELDS[1:-2]
STATUSES = ("draft", "published", "archived")
WORKED_OUT = ("quick", "seasonal")  # chips nobody tags: they come from the minutes and the months
TTL = 60  # seconds the app keeps the published dinners before reading them again
MAX_LINES = 30

_cache = {"at": 0.0, "rows": None}
_lock = threading.Lock()
_SELECT = "SELECT " + ", ".join(f"r.{f}" for f in FIELDS) + " FROM recipes r"


class RecipeError(ValueError):
    """A dinner that can't be saved; the message is for the owner."""


def chips():
    return catalog.load_yaml("dinner_chips.yaml")


def this_month(now=None):
    return (now or datetime.now(ZoneInfo("Europe/Tallinn"))).month


def _rows(sql, params=()):
    return [dict(zip(FIELDS, r)) for r in db.query(sql, params)]


def published():
    """The dinners the app shows, by name; none without a database (tests of the store matching)."""
    if not db.configured():
        return []
    with _lock:
        if _cache["rows"] is not None and time.monotonic() - _cache["at"] < TTL:
            return _cache["rows"]
    rows = _rows(_SELECT + " WHERE r.status = 'published' ORDER BY r.name")
    with _lock:
        _cache.update(at=time.monotonic(), rows=rows)
    return rows


def forget():
    """Read the published dinners again next time (after an edit)."""
    with _lock:
        _cache["rows"] = None


def get(recipe_id):
    """One dinner, whatever its status (a draft can be checked at the stores), or None."""
    if not db.configured():
        return None
    rows = _rows(_SELECT + " WHERE r.id = %s", (recipe_id,))
    return rows[0] if rows else None


def with_usage():
    """Every dinner for the admin page, drafts first, each with how testers use it (metrics.dinner_usage)."""
    cols = ("views", "answers", "people", "copies", "cooked", "last_used")
    rows = db.query(_SELECT[:-len(" FROM recipes r")] + ", " + ", ".join(f"u.{c}" for c in cols)
                    + " FROM recipes r LEFT JOIN metrics.dinner_usage u ON u.id = r.id"
                    + " ORDER BY array_position(ARRAY['draft','published','archived'], r.status), r.name")
    out = []
    for r in rows:
        d = dict(zip(FIELDS, r))
        d["usage"] = {c: (v if v is not None else 0) if c != "last_used" else v for c, v in zip(cols, r[len(FIELDS):])}
        out.append(d)
    return out


# ── saving ───────────────────────────────────────────────────────────────────

def _text(value, field, limit, required=False, lines=False):
    """Text from the form, trimmed (one line unless `lines`), or None when empty."""
    value = "" if value is None else str(value)
    value = "\n".join(l.rstrip() for l in value.strip().splitlines()) if lines else " ".join(value.split())
    if required and not value:
        raise RecipeError(f"The {field} can't be empty.")
    if len(value) > limit:
        raise RecipeError(f"The {field} is too long (at most {limit} characters).")
    return value or None


def _lines(value, field):
    """A list of typed items from a list or from text, one per line."""
    items = value.splitlines() if isinstance(value, str) else list(value or [])
    items = [" ".join(str(i).split()) for i in items]
    items = list(dict.fromkeys(i for i in items if i))
    if len(items) > MAX_LINES or any(len(i) > 120 for i in items):
        raise RecipeError(f"Too many {field}, or one is too long.")
    return items


def _number(value, field, low, high, required=False):
    if value in (None, ""):
        if required:
            raise RecipeError(f"The {field} is needed.")
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise RecipeError(f"The {field} must be a whole number.")
    if not low <= n <= high:
        raise RecipeError(f"The {field} must be between {low} and {high}.")
    return n


def clean(data):
    """A dinner from the admin form, checked and tidied, or RecipeError."""
    taggable = [c["id"] for c in chips()["chips"] if c["id"] not in WORKED_OUT]
    tags = list(dict.fromkeys(data.get("tags") or []))
    unknown = [t for t in tags if t not in taggable]
    if unknown:
        raise RecipeError(f"Unknown tags: {', '.join(map(str, unknown))}. Quick and In season come from the minutes and months.")
    months = sorted({_number(m, "month", 1, 12) for m in data.get("months") or []})
    image = _text(data.get("image"), "photo address", 500)
    if image and not image.startswith("https://"):
        raise RecipeError("The photo address must start with https://")
    status = data.get("status") or "draft"
    if status not in STATUSES:
        raise RecipeError(f"Status must be one of {', '.join(STATUSES)}.")
    review_by = data.get("review_by") or None
    if review_by:
        try:
            review_by = date.fromisoformat(str(review_by))
        except ValueError:
            raise RecipeError("Review by must be a date (YYYY-MM-DD).")
    ingredients = _lines(data.get("ingredients"), "ingredients")
    if not ingredients:
        raise RecipeError("A dinner needs at least one thing to buy.")
    return {
        "name": _text(data.get("name"), "name", 80, required=True),
        "about": _text(data.get("about"), "description", 300),
        "method": _text(data.get("method"), "method", 5000, lines=True),
        "emoji": _text(data.get("emoji"), "emoji", 8),
        "image": image,
        "servings": _number(data.get("servings"), "number of people", 1, 12, required=True),
        "minutes": _number(data.get("minutes"), "minutes", 1, 600),
        "ingredients": ingredients,
        "pantry": _lines(data.get("pantry"), "things from home"),
        "tags": [t for t in taggable if t in tags],
        "months": months,
        "brand": _text(data.get("brand"), "brand", 80),
        "label": _text(data.get("label"), "label", 80),
        "rights": _text(data.get("rights"), "rights", 300),
        "status": status,
        "review_by": review_by,
        "notes": _text(data.get("notes"), "notes", 2000, lines=True),
    }


def slug(name):
    """"Räimed rukkipaneeringus" → "raimed-rukkipaneeringus": the id's readable part."""
    ascii_ = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_).strip("-")[:40].strip("-") or "dinner"


def save(data, recipe_id=None):
    """Add a dinner (no recipe_id: its id comes from the name) or change one; returns it as stored.
    LookupError when there's no dinner with that id."""
    row = clean(data)
    with db.connection() as conn:
        if recipe_id is None:
            base = "pr-" + slug(row["name"])
            taken = {r[0] for r in conn.execute("SELECT id FROM recipes WHERE id = %s OR id LIKE %s", (base, base + "-%"))}
            recipe_id = next(i for i in [base] + [f"{base}-{n}" for n in range(2, 1000)] if i not in taken)
            conn.execute(f"INSERT INTO recipes (id, {', '.join(EDITABLE)}) VALUES (%s, {', '.join(['%s'] * len(EDITABLE))})",
                         (recipe_id, *(row[f] for f in EDITABLE)))
        else:
            cur = conn.execute(f"UPDATE recipes SET {', '.join(f'{f} = %s' for f in EDITABLE)}, updated = now() WHERE id = %s",
                               (*(row[f] for f in EDITABLE), recipe_id))
            if cur.rowcount == 0:
                raise LookupError(recipe_id)
    forget()
    return get(recipe_id)


def check(recipe_id, stores):
    """What each store would sell for the dinner, as a tester would get it: [{store, status, total, missing}].
    LookupError when there's no such dinner."""
    recipe = get(recipe_id)
    if recipe is None:
        raise LookupError(recipe_id)
    res = catalog.recommend(recipe_id, recipe["servings"], [], stores)
    return [{"store": b["store"], "status": b["status"], "total": b["total_price"], "missing": b["missing"]}
            for b in res["baskets"]]


# ── chips ────────────────────────────────────────────────────────────────────

def _words(text):
    return re.findall(r"[a-zõäöüšž]+", (text or "").lower())


def _says(word, chip):
    return (any(word.startswith(w) or word.endswith(w) for w in chip["words"])
            and not any(word.startswith(n) for n in chip.get("not", ())))


def tags_of(dinner, month, cfg=None):
    """A dinner's chips, in the chips' order: its own tags (pantryrun's dinners and the classics), or for a store
    recipe the kind its category names plus pasta or rice from its words; then quick and seasonal from its
    minutes and months."""
    cfg = cfg or chips()
    out = set(dinner.get("tags") or ())
    if not out and dinner.get("category"):
        out = {c["id"] for c in cfg["chips"] if dinner["category"] in c.get("categories", ())}
        lines = [catalog.parse_quantity(i)[0] for i in dinner["ingredients"] if isinstance(i, str)]
        words = [w for text in [dinner["name"], *lines] for w in _words(text)]
        out |= {c["id"] for c in cfg["chips"] if c.get("words") and any(_says(w, c) for w in words)}
    if dinner.get("minutes") and dinner["minutes"] <= cfg["quick_minutes"]:
        out.add("quick")
    if month in (dinner.get("months") or ()):
        out.add("seasonal")
    return [c["id"] for c in cfg["chips"] if c["id"] in out]
