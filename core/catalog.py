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


def best_offer(ingredient_key, need, store, recipes=None, rules=None):
    """Cheapest acceptable product for the amount needed, or None.

    Fallback rules are only used when the rules before them find nothing;
    the offer is then marked as a substitute.
    """
    recipes = recipes or load_recipes()
    rules = rules or load_rules()
    spec = recipes["ingredients"][ingredient_key]

    for level, rule in enumerate(rule_chain(rules, ingredient_key, store)):
        offers = []
        for p in find_products(rule, store):
            priced = cost_for(p, need, spec["unit"], spec.get("piece_g"))
            if priced:
                cost, packs, how = priced
                offers.append({"product": p["name"], "price": parse_price(p["price"]), "cost": cost,
                               "packs": packs, "how": how, "substitute": level > 0})
        if offers:
            return min(offers, key=lambda o: o["cost"])
    return None


# ── recipes ──────────────────────────────────────────────────────────────────

def recipe_basket(recipe, store, servings, recipes, rules):
    scale = servings / BASE_SERVINGS
    lines, missing = [], []
    for ing in recipe["ingredients"]:
        key = ing["item"]
        need = ing["amount"] * scale
        offer = best_offer(key, need, store, recipes, rules)
        name = recipes["ingredients"][key]["name"]
        if offer:
            lines.append({"ingredient": key, "label": name, "need": need,
                          "unit": recipes["ingredients"][key]["unit"], **offer})
        else:
            missing.append(name)
    return {
        "store": store,
        "lines": lines,
        "missing": missing,
        "total_price": round(sum(l["cost"] for l in lines), 2),
    }


def recommend_dinner(recipe_id, servings, stores):
    """Rank stores for one recipe: fewest missing ingredients, then cheapest."""
    recipes, rules = load_recipes(), load_rules()
    recipe = next((r for r in recipes["recipes"] if r["id"] == recipe_id), None)
    if recipe is None:
        raise KeyError(recipe_id)

    # Warm the fetch cache with every search this recipe needs, concurrently.
    searches = {
        (store, q)
        for ing in recipe["ingredients"]
        for store in stores
        for rule in rule_chain(rules, ing["item"], store)
        for q in _queries(rule)
    }
    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(lambda sq: _safe_fetch(*sq), searches))

    baskets = [recipe_basket(recipe, s, servings, recipes, rules) for s in stores]
    baskets.sort(key=lambda b: (len(b["missing"]), b["total_price"]))

    return {
        "recipe": {"id": recipe["id"], "name": recipe["name"], "pantry": recipe.get("pantry", [])},
        "servings": servings,
        "store": baskets[0]["store"] if baskets else None,
        "baskets": baskets,
    }
