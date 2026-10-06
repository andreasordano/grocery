# =============================================================================
# CATALOG  (recipes → one-store dinner recommendation)
# Recipes (data/recipes.yaml) list ingredients with amounts for 2 servings.
# Rules (data/rules.yaml) say, per ingredient and store, how to find acceptable
# products: search query + store category + excluded words. No product IDs are
# pinned, so new brands, pack changes and out-of-stock items need no upkeep.
# For each ingredient we pick the acceptable product that is cheapest for the
# amount needed: whole packs for packaged goods, price × weight for loose goods.
# A rule may list `fallback` rules (substitutes), tried in order only when the
# rules before them find nothing.
# =============================================================================

import math
import os
import re
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

import yaml

from core.fetch import GLOBAL_EXCLUDE, _cached_fetch, discount_fields
from core.scoring import fold, parse_price

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
BASE_SERVINGS = 2

_SIZE_RE = re.compile(r"(?:(\d+)\s*[x×]\s*)?(\d+(?:[.,]\d+)?)\s*(kg|g|ml|cl|l|tk)\b")
_EGG_RE = re.compile(r"\b[SMLX]{1,2}(\d{1,2})\b")  # egg packs like "M10", "L6", "XL10"


def load_yaml(name):
    with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_recipes():
    return load_yaml("recipes.yaml")


def load_rules():
    return load_yaml("rules.yaml")


@lru_cache(maxsize=1)
def load_dishes():
    """Dishes generated from NutriData (scripts/import_nutridata.py). Ingredients are either
    `item` (an ingredient rule key) or `text` (a free-text search word), amounts for 2 servings."""
    return load_yaml("dishes.yaml")


def find_recipe(recipe_id, recipes, user_id=None):
    """A hand-written recipe, a NutriData dish ("nd-…") or one of this person's dinners ("my-…"), or None."""
    if recipe_id.startswith(("my-", "sh-")):
        from core import my_dinners
        if recipe_id.startswith("sh-"):  # shared by link: anyone with it may open it
            return my_dinners.as_recipe(my_dinners.shared(recipe_id[3:]))
        return my_dinners.as_recipe(my_dinners.get(user_id, recipe_id))
    pool = recipes["recipes"] + (load_dishes()["dishes"] if recipe_id.startswith("nd-") else [])
    return next((r for r in pool if r["id"] == recipe_id), None)


# ── pack sizes ───────────────────────────────────────────────────────────────

def parse_pack(name, volume=None):
    """Return (amount, base_unit) for a packaged product, base_unit in g/ml/pcs, or None."""
    for text in (volume, name):
        if not text:
            continue
        t = text.lower()
        m = _SIZE_RE.search(t)
        if m:
            count = int(m.group(1)) if m.group(1) else 1
            value = float(m.group(2).replace(",", ".")) * count
            unit = m.group(3)
            if unit == "kg":
                return value * 1000, "g"
            if unit == "g":
                return value, "g"
            if unit == "l":
                return value * 1000, "ml"
            if unit == "cl":
                return value * 10, "ml"
            if unit == "ml":
                return value, "ml"
            return value, "pcs"
        m = _EGG_RE.search(text)
        if m:
            return float(m.group(1)), "pcs"
    return None


def _convert(amount, from_unit, to_unit, piece_g=None):
    """Convert between g/ml/pcs. g and ml are treated as equal (density ~1)."""
    if from_unit == to_unit:
        return amount
    mass = {"g", "ml"}
    if from_unit in mass and to_unit in mass:
        return amount
    if piece_g:
        if from_unit == "pcs" and to_unit in mass:
            return amount * piece_g
        if from_unit in mass and to_unit == "pcs":
            return amount / piece_g
    return None


def cost_for(product, need, need_unit, piece_g=None):
    """Price to pay for `need` of an ingredient using this product, or None if unknown.

    Returns (cost, packs, description).
    """
    price = parse_price(product.get("price"))
    if price == float("inf"):
        return None
    unit = (product.get("unit") or "").lower()

    if unit in ("kg", "l"):  # loose goods, priced per kg / l
        grams = _convert(need, need_unit, "g", piece_g)
        if grams is None:
            return None
        return round(price * grams / 1000, 2), None, f"{grams:.0f} g × {price:.2f} €/{unit}"

    pack = parse_pack(product.get("name") or "", product.get("volume"))
    if not pack:
        return None
    size, pack_unit = pack
    needed = _convert(need, need_unit, pack_unit, piece_g)
    if not needed or size <= 0:
        return None
    packs = max(1, math.ceil(needed / size - 1e-9))
    return round(packs * price, 2), packs, f"{packs} × {price:.2f} €"


# ── rule matching ────────────────────────────────────────────────────────────

def _category_ok(categories, wanted):
    if not wanted:
        return True
    cats = [c.lower() for c in categories or []]
    for w in (x.lower() for x in wanted):
        if any(c == w or c.startswith(w + "-") for c in cats):
            return True
    return False




def matches_rule(product, rule):
    name = (product.get("name") or "").lower()
    if product.get("in_stock") is False:
        return False
    if any(x.lower() in name for x in GLOBAL_EXCLUDE + rule.get("exclude", [])):
        return False
    require = rule.get("require", [])
    if require and not any(x.lower() in name for x in require):
        return False
    return _category_ok(product.get("category"), rule.get("category"))


def _safe_fetch(store, query):
    try:
        return _cached_fetch(store, query)
    except Exception as exc:
        print(f"catalog fetch failed {store}/{query}: {exc}")
        return []


def find_products(rule, store):
    """All in-stock products at `store` that satisfy the rule (deduplicated)."""
    seen, found = set(), []
    for q in _queries(rule):
        for p in _safe_fetch(store, q):
            key = p.get("id") or p.get("sku") or p.get("code") or p.get("name")
            if key in seen:
                continue
            seen.add(key)
            if matches_rule(p, rule):
                found.append(p)
    return found


def rule_chain(rules, ingredient_key, store):
    """The ingredient's rule at this store followed by its fallbacks, in order."""
    rule = (rules.get(ingredient_key) or {}).get(store)
    return [rule] + list(rule.get("fallback", [])) if rule else []


def _queries(rule):
    return rule["query"] if isinstance(rule["query"], list) else [rule["query"]]


def _with_discount(option, product):
    """Add discount info to an option. Regular and card costs scale with the cost
    (same packs or weight), so they compare directly with it."""
    d = discount_fields(product)
    price, cost = option["price"], option["cost"]
    scale = lambda other: round(cost * other / price, 2) if other and price else None
    return {**option, **d, "regular_cost": scale(d["regular_price"]), "card_cost": scale(d["card_price"])}


def _looks(product):
    """What helps a person recognise a product: its photo and the store shelf it sits on.
    Rimi only gives shelf codes (SH-19-5), which mean nothing to a person, so those are left out."""
    shelf = product.get("shelf")
    return {"image": product.get("image"), "shelf": None if not shelf or re.match(r"SH-\d", shelf) else shelf}


MAX_OPTIONS = 100  # alternatives per line; the web app also previews preferences against them


def _pick(options, pref, store):
    """Choose from options (cheapest first) honouring a preference, if any.

    pref = {"products": {store: product name}, "words": ["alma", "3,2%"]}
    A product pinned at this store wins; otherwise the cheapest option whose name
    contains all preferred words; otherwise the cheapest option.
    """
    if not options:
        return None
    pref = pref or {}
    pinned = (pref.get("products") or {}).get(store)
    if pinned:
        for o in options:
            if o["product"] == pinned:
                return {**o, "pinned": True}
    words = [fold(w.strip()) for w in pref.get("words") or [] if w.strip()]
    if words:
        for o in options:
            if all(w in fold(o["product"]) for w in words):
                return {**o, "preferred": True}
    return options[0]


def ingredient_offers(ingredient_key, need, store, recipes, rules, pref=None):
    """(chosen offer or None, acceptable options cheapest first) for one ingredient.

    Fallback rules are only used when the rules before them find nothing;
    their offers are marked as substitutes.
    """
    spec = recipes["ingredients"][ingredient_key]
    for level, rule in enumerate(rule_chain(rules, ingredient_key, store)):
        options = []
        for p in find_products(rule, store):
            priced = cost_for(p, need, spec["unit"], spec.get("piece_g"))
            if priced:
                cost, packs, how = priced
                options.append(_with_discount({"product": p["name"], "price": parse_price(p["price"]), "cost": cost,
                                               "packs": packs, "how": how, "substitute": level > 0,
                                               **_looks(p)}, p))
        if options:
            options.sort(key=lambda o: o["cost"])
            return _pick(options, pref, store), options
    return None, []


def best_offer(ingredient_key, need, store, recipes=None, rules=None):
    """Cheapest acceptable product for the amount needed, or None."""
    recipes = recipes or load_recipes()
    rules = rules or load_rules()
    return ingredient_offers(ingredient_key, need, store, recipes, rules)[0]


def prefetch(rules, keys, stores):
    """Warm the fetch cache with every search these ingredients need, concurrently."""
    searches = {
        (store, q)
        for key in keys
        for store in stores
        for rule in rule_chain(rules, key, store)
        for q in _queries(rule)
    }
    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(lambda sq: _safe_fetch(*sq), searches))


# ── shopping list: typed words → known ingredients ──────────────────────────

def _norm(text):
    return " ".join(text.lower().split())


def cap(text):
    return text[:1].upper() + text[1:]


def match_ingredient(text, recipes=None):
    """Ingredient key whose name, key or aliases equal the typed text, else None."""
    recipes = recipes or load_recipes()
    t = _norm(text)
    for key, spec in recipes["ingredients"].items():
        names = {key.replace("_", " "), spec["name"]} | set(spec.get("aliases", []))
        if t in {_norm(n) for n in names}:
            return key
    return None


def list_amount(key, recipes):
    """Amount to price for a shopping-list item: the largest amount any recipe uses."""
    amounts = [i["amount"] for r in recipes["recipes"] for i in r["ingredients"] if i["item"] == key]
    return max(amounts) if amounts else 1


# ── quantities typed with an item ("paprika 600g", "2 piim", "3 tk sidrun") ──

_QTY = r"(?P<n>\d+(?:[.,]\d+)?)\s*(?P<u>kg|g|dl|cl|ml|l|tk|x|×)?"
_LEADING_QTY = re.compile(rf"^\s*{_QTY}\s+(?P<name>\S.*)$", re.I)
_TRAILING_QTY = re.compile(rf"^(?P<name>.*\S)\s+{_QTY}\s*$", re.I)
_UNITS = {"kg": (1000, "g"), "g": (1, "g"), "l": (1000, "ml"), "dl": (100, "ml"), "cl": (10, "ml"), "ml": (1, "ml"),
          "tk": (1, "pcs"), "x": (1, "packs"), "×": (1, "packs"), None: (1, "packs")}


def parse_quantity(text):
    """(name, (amount, unit) or None) for a typed item. Units come out as g, ml, pcs or packs;
    a bare number means packs ("2 piim"). "Piim 2,5%" keeps its number: it's part of the name."""
    text = " ".join(text.split())
    for pattern in (_LEADING_QTY, _TRAILING_QTY):
        m = pattern.match(text)
        if m:
            factor, unit = _UNITS[(m["u"] or "").lower() or None]
            amount = float(m["n"].replace(",", ".")) * factor
            if 0 < amount <= (50 if unit in ("packs", "pcs") else 20000):
                return m["name"].strip(), (amount, unit)
    return text, None


def _amount_label(amount, unit):
    if unit == "packs":
        return f"{amount:g} pack" + ("" if amount == 1 else "s")
    if unit == "pcs":
        return f"{amount:g} tk"
    big = {"g": "kg", "ml": "l"}[unit]
    return f"{amount / 1000:g} {big}" if amount >= 1000 else f"{amount:g} {unit}"


def to_need(item, recipes):
    """What to buy for one typed item: an ingredient rule with an amount, or a free-text search
    with an amount (grams/ml) or a number of packs. Without a quantity, a rule item gets its usual
    amount (largest any recipe uses) and a free-text item one pack."""
    name, qty = parse_quantity(item)
    key = match_ingredient(name, recipes)
    need = {"label": name, "asked": _amount_label(*qty) if qty else None}
    if key:
        spec = recipes["ingredients"][key]
        usual = list_amount(key, recipes)
        amount = None
        if qty and qty[1] != "packs":
            amount = _convert(qty[0], qty[1], spec["unit"], spec.get("piece_g"))
        if amount is None:  # no quantity, a number of packs, or pieces of something sold by weight
            amount = usual * (qty[0] if qty else 1)
        return {**need, "rule": key, "amount": amount, "unit": spec["unit"]}
    if qty and qty[1] in ("g", "ml"):
        return {**need, "text": name, "amount": qty[0], "unit": qty[1]}
    return {**need, "text": name, "packs": qty[0] if qty else 1}


def recipe_as_items(recipe, recipes):
    """A recipe's ingredients as typed items ("kodune hakkliha 400g", "küüslauk 11g", "4 tk munad"),
    so a classic or NutriData dish can be shared and saved like someone's own dinner."""
    out = []
    for ing in recipe["ingredients"]:
        if isinstance(ing, str):
            out.append(ing)
            continue
        if "item" in ing:
            spec = recipes["ingredients"][ing["item"]]
            name, unit = spec["name"].lower(), spec["unit"]
        else:
            name, unit = ing["text"], "g"
        amount = round(ing["amount"])
        out.append(f"{amount} tk {name}" if unit == "pcs" else f"{name} {amount}{unit}")
    return out


def recipe_needs(recipe, servings, recipes):
    """A recipe's ingredients as needs for this many people. Hand-written recipes and NutriData
    dishes give `item`/`text` amounts for 2; people's own dinners are typed items for their servings."""
    scale = servings / recipe.get("servings", BASE_SERVINGS)
    out = []
    for ing in recipe["ingredients"]:
        if isinstance(ing, str):
            n = to_need(ing, recipes)
        elif "item" in ing:
            spec = recipes["ingredients"][ing["item"]]
            n = {"label": spec["name"], "rule": ing["item"], "amount": ing["amount"], "unit": spec["unit"]}
        else:
            n = {"label": cap(ing["text"]), "text": ing["text"], "amount": ing["amount"], "unit": "g"}
        if n.get("amount") is not None:
            n["amount"] = n["amount"] * scale
        if n.get("packs"):
            n["packs"] = max(1, math.ceil(n["packs"] * scale - 1e-9))
        out.append({**n, "asked": None})
    return out


def list_offers(items, stores):
    """Rule-based offers for typed items that match a known ingredient.

    Returns {item: [product dicts, one per store that has it]} for matched items
    only; unmatched items are left to free-text search.
    """
    recipes, rules = load_recipes(), load_rules()
    matched = {item: key for item in items if (key := match_ingredient(item, recipes))}
    prefetch(rules, set(matched.values()), stores)

    out = {}
    for item, key in matched.items():
        out[item] = []
        for store in stores:
            offer = best_offer(key, list_amount(key, recipes), store, recipes, rules)
            if offer:
                out[item].append({"item": item, "store": store, "name": offer["product"], "price": offer["cost"],
                                  "score": 0.0, "ingredient": key, "substitute": offer["substitute"]})
    return out


# ── baskets: an optional recipe plus extra items, per store ─────────────────

def free_text_offers(items, stores, needs=None):
    """Options per store for items with no ingredient rule (best guess first).

    needs: {item: grams} for dish ingredients. Those are priced for the amount (whole packs, or
    weight × price for loose goods) and, within a match tier, ordered cheapest for that amount.
    Other items cost one pack.
    """
    from core.fetch import fetch_all, spec_for  # deferred: fetch is only needed for free text

    if not items:
        return {}
    needs = needs or {}
    all_products, _ = fetch_all({it: spec_for(it) for it in items}, stores)
    out = {}
    for it in items:
        out[it] = {}
        for store in stores:
            options = []
            for p in (p for p in all_products.get(it, []) if p["store"] == store):
                priced = cost_for(p, needs[it], "g") if it in needs else None
                cost, packs, how = priced or (p["price"], 1, f"1 × {p['price']:.2f} €")
                options.append((p.get("relevance", 0), p["score"], _with_discount(
                    {"product": p["name"], "price": p["price"], "cost": cost, "packs": packs, "how": how,
                     "substitute": False, **_looks(p)}, p)))
            by_amount = it in needs
            options.sort(key=lambda o: (-o[0], o[2]["cost"]) if by_amount else o[1])
            out[it][store] = [o[2] for o in options]
    return out


def _line(key, label, need, unit, offer, options, extra):
    return {
        "key": key, "ingredient": key if not key.startswith("text:") else None,
        "label": label, "need": need, "unit": unit, "extra": extra,
        **offer,
        "options": [{k: o.get(k) for k in ("product", "cost", "how", "regular_cost", "card_cost", "deal", "image", "shelf")}
                    for o in options[:MAX_OPTIONS]],
    }


def _times(option, n):
    """An option bought n times (n packs of a free-text item)."""
    if n == 1:
        return option
    mul = lambda v: round(v * n, 2) if v is not None else None
    return {**option, "cost": mul(option["cost"]), "regular_cost": mul(option.get("regular_cost")),
            "card_cost": mul(option.get("card_cost")), "packs": n, "how": f"{n:g} × {option['price']:.2f} €"}


def build_basket(store, needs, prefs, recipes, rules, free):
    """One store's basket. needs: recipe ingredients (extra=False) then list items (extra=True)."""
    lines, missing = [], []
    for n in needs:
        if n.get("rule"):
            key = n["rule"]
            offer, options = ingredient_offers(key, n["amount"], store, recipes, rules, prefs.get(key))
            need, unit = n["amount"], n["unit"]
        else:
            key = "text:" + _norm(n["text"])
            options = free.get(n["text"], {}).get(store, [])
            if n.get("packs"):
                options = [_times(o, n["packs"]) for o in options]
                need, unit = None, None
            else:
                need, unit = n["amount"], n["unit"]
            offer = _pick(options, prefs.get(key), store)
        if offer:
            line = _line(key, n["label"], need, unit, offer, options, extra=n["extra"])
            lines.append({**line, "asked": n.get("asked")})
        else:
            missing.append(n["label"])

    total = round(sum(l["cost"] for l in lines), 2)
    return {
        "store": store,
        "lines": lines,
        "missing": missing,
        "total_price": total,
        # Already included in total_price: what the discounts take off regular prices.
        "savings": round(sum((l.get("regular_cost") or l["cost"]) - l["cost"] for l in lines), 2),
        # Not included: what loyalty-card prices would take off on top.
        "card_savings": round(sum(l["cost"] - (l.get("card_cost") or l["cost"]) for l in lines), 2),
    }


def recommend(recipe_id, servings, items, stores, prefs=None, user_id=None):
    """Rank stores for a recipe (optional) plus extra items: fewest missing, then cheapest.

    prefs: {ingredient key or "text:<item>": {"products": {store: name}, "words": [...]}}
    """
    recipes, rules = load_recipes(), load_rules()
    recipe = None
    if recipe_id:
        recipe = find_recipe(recipe_id, recipes, user_id)
        if recipe is None:
            raise KeyError(recipe_id)
    items = list(dict.fromkeys(i.strip() for i in items if i and i.strip()))
    prefs = prefs or {}

    needs = [{**n, "extra": False} for n in (recipe_needs(recipe, servings, recipes) if recipe else [])]
    needs += [{**to_need(it, recipes), "extra": True} for it in items]
    keys = {n["rule"] for n in needs if n.get("rule")}
    # Free-text searches; those with an amount are priced for it (grams or ml).
    amounts = {n["text"]: n["amount"] for n in needs if n.get("text") and n.get("amount") is not None}
    free_items = list(dict.fromkeys(n["text"] for n in needs if n.get("text")))

    # Rule searches and free-text searches run side by side.
    with ThreadPoolExecutor(max_workers=2) as pool:
        warm = pool.submit(prefetch, rules, keys, stores)
        free_job = pool.submit(free_text_offers, free_items, stores, amounts)
        warm.result()
        free = free_job.result()

    baskets = [build_basket(s, needs, prefs, recipes, rules, free) for s in stores]
    baskets.sort(key=lambda b: (len(b["missing"]), b["total_price"]))

    return {
        "recipe": {"id": recipe["id"], "name": recipe["name"], "pantry": recipe.get("pantry", [])} if recipe else None,
        "servings": servings,
        "items": items,
        "store": baskets[0]["store"] if baskets else None,
        "baskets": baskets,
    }


def recommend_dinner(recipe_id, servings, stores):
    """A recipe on its own (no extra items or preferences)."""
    return recommend(recipe_id, servings, [], stores)
