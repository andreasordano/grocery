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

import yaml

from core.fetch import _cached_fetch
from core.scoring import parse_price

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


# Never suitable for a dinner basket, whatever the ingredient: pre-order and bulk listings.
GLOBAL_EXCLUDE = ["ettetellimisel", "hulgi "]


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


MAX_OPTIONS = 12


def _fold(text):
    """Spelling-tolerant form for preference words: "spaghetti" and "Spagetid" both become "spageti…"."""
    t = text.lower()
    t = re.sub(r"(?<=[gctp])h", "", t)   # spaghetti → spagetti
    return re.sub(r"(.)\1+", r"\1", t)  # double letters → single


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
    words = [_fold(w.strip()) for w in pref.get("words") or [] if w.strip()]
    if words:
        for o in options:
            if all(w in _fold(o["product"]) for w in words):
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
                options.append({"product": p["name"], "price": parse_price(p["price"]), "cost": cost,
                                "packs": packs, "how": how, "substitute": level > 0})
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

def free_text_offers(items, stores):
    """Options per store for typed items with no ingredient rule (best guess first)."""
    from core.fetch import fetch_all, spec_for  # deferred: fetch is only needed for free text

    if not items:
        return {}
    all_products, _ = fetch_all({it: spec_for(it) for it in items}, stores)
    out = {}
    for it in items:
        out[it] = {}
        for store in stores:
            cands = sorted((p for p in all_products.get(it, []) if p["store"] == store), key=lambda p: p["score"])
            out[it][store] = [{"product": p["name"], "price": p["price"], "cost": p["price"], "packs": 1,
                               "how": f"1 × {p['price']:.2f} €", "substitute": False} for p in cands]
    return out


def _line(key, label, need, unit, offer, options, extra):
    return {
        "key": key, "ingredient": key if not key.startswith("text:") else None,
        "label": label, "need": need, "unit": unit, "extra": extra,
        **offer,
        "options": [{"product": o["product"], "cost": o["cost"], "how": o["how"]} for o in options[:MAX_OPTIONS]],
    }


def build_basket(store, recipe, servings, items, prefs, recipes, rules, free):
    lines, missing = [], []
    for ing in recipe["ingredients"] if recipe else []:
        key = ing["item"]
        spec = recipes["ingredients"][key]
        need = ing["amount"] * servings / BASE_SERVINGS
        offer, options = ingredient_offers(key, need, store, recipes, rules, prefs.get(key))
        if offer:
            lines.append(_line(key, spec["name"], need, spec["unit"], offer, options, extra=False))
        else:
            missing.append(spec["name"])

    for item in items:
        key = match_ingredient(item, recipes)
        if key:
            spec = recipes["ingredients"][key]
            need = list_amount(key, recipes)
            offer, options = ingredient_offers(key, need, store, recipes, rules, prefs.get(key))
            unit = spec["unit"]
        else:
            key, need, unit = "text:" + _norm(item), None, None
            options = free.get(item, {}).get(store, [])
            offer = _pick(options, prefs.get(key), store)
        if offer:
            lines.append(_line(key, item, need, unit, offer, options, extra=True))
        else:
            missing.append(item)

    return {
        "store": store,
        "lines": lines,
        "missing": missing,
        "total_price": round(sum(l["cost"] for l in lines), 2),
    }


def recommend(recipe_id, servings, items, stores, prefs=None):
    """Rank stores for a recipe (optional) plus extra items: fewest missing, then cheapest.

    prefs: {ingredient key or "text:<item>": {"products": {store: name}, "words": [...]}}
    """
    recipes, rules = load_recipes(), load_rules()
    recipe = None
    if recipe_id:
        recipe = next((r for r in recipes["recipes"] if r["id"] == recipe_id), None)
        if recipe is None:
            raise KeyError(recipe_id)
    items = list(dict.fromkeys(i.strip() for i in items if i and i.strip()))
    prefs = prefs or {}

    keys = [ing["item"] for ing in recipe["ingredients"]] if recipe else []
    matched = {it: match_ingredient(it, recipes) for it in items}
    keys += [k for k in matched.values() if k]
    unmatched = [it for it, k in matched.items() if not k]

    # Rule searches and free-text searches run side by side.
    with ThreadPoolExecutor(max_workers=2) as pool:
        warm = pool.submit(prefetch, rules, set(keys), stores)
        free_job = pool.submit(free_text_offers, unmatched, stores)
        warm.result()
        free = free_job.result()

    baskets = [build_basket(s, recipe, servings, items, prefs, recipes, rules, free) for s in stores]
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
