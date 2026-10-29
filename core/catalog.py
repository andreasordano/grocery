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
import threading
from concurrent.futures import ThreadPoolExecutor

import yaml

from core.fetch import GLOBAL_EXCLUDE, _cached_fetch, discount_fields
from core.scoring import fold, pack_size, parse_price

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
BASE_SERVINGS = 2



_loaded = {}  # file name → (modified time, parsed data)
_load_lock = threading.Lock()


def load_yaml(name):
    """A data file, parsed once and again only when the file changes (parsing rules.yaml takes ~25 ms).
    The data is shared: treat it as read-only."""
    path = os.path.join(DATA_DIR, name)
    mtime = os.path.getmtime(path)
    with _load_lock:
        hit = _loaded.get(name)
        if hit and hit[0] == mtime:
            return hit[1]
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        _loaded[name] = (mtime, data)
        return data


def load_recipes():
    return load_yaml("recipes.yaml")


def load_rules():
    return load_yaml("rules.yaml")


def load_dishes():
    """Dishes generated from NutriData (scripts/import_nutridata.py). Ingredients are either
    `item` (an ingredient rule key) or `text` (a free-text search word), amounts for 2 servings."""
    return load_yaml("dishes.yaml")


def load_store_recipes():
    """Dinners from Rimi's recipe pages (scripts/import_rimi_recipes.py): a photo, the time, typed items for
    `servings` people, and a link to the method. Empty until the script has run."""
    try:
        return load_yaml("store_recipes.yaml")
    except FileNotFoundError:
        return {"categories": [], "dinners": []}


def _index(data, build, _cache={}):
    """build(data), computed once per loaded data object (it changes only when its file does)."""
    key = (id(data), build.__name__)
    hit = _cache.get(key)
    if hit is None or hit[0] is not data:
        hit = _cache[key] = (data, build(data))
    return hit[1]


def _by_id(collection):
    return {r["id"]: r for r in collection}


def find_recipe(recipe_id, recipes, user_id=None):
    """A hand-written recipe, a NutriData dish ("nd-…"), a store's recipe ("rm-…") or one of this person's
    dinners ("my-…"), or None."""
    if recipe_id.startswith(("my-", "sh-")):
        from core import my_dinners
        if recipe_id.startswith("sh-"):  # shared by link: anyone with it may open it
            return my_dinners.as_recipe(my_dinners.shared(recipe_id[3:]))
        return my_dinners.as_recipe(my_dinners.get(user_id, recipe_id))
    if recipe_id.startswith("nd-"):
        return _index(load_dishes()["dishes"], _by_id).get(recipe_id)
    if recipe_id.startswith("rm-"):
        return _index(load_store_recipes()["dinners"], _by_id).get(recipe_id)
    return _index(recipes["recipes"], _by_id).get(recipe_id)


# ── pack sizes ───────────────────────────────────────────────────────────────

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


def sold_quantity(quantity, min_qty=None, step=None):
    """The amount of a loose good (kg or l) a store sells you when you want `quantity`: at least its
    minimum, then whole steps above it. Barbora gives both (a 0.9 kg tray: min 0.9, step 0.9), Rimi
    only the minimum; without them any amount can be bought."""
    if min_qty and quantity < min_qty:
        return min_qty
    if min_qty and step:
        return round(min_qty + math.ceil((quantity - min_qty) / step - 1e-9) * step, 3)
    return quantity


def cost_for(product, need, need_unit, piece_g=None):
    """Price to pay for `need` of an ingredient using this product, or None if unknown.

    Returns (cost, packs, description, bought): bought is the grams or ml of a loose good the
    store sells you when that is more than the need (its minimum or step), else None.
    """
    price = parse_price(product.get("price"))
    if price == float("inf"):
        return None
    unit = (product.get("unit") or "").lower()

    if unit in ("kg", "l"):  # loose goods, priced per kg / l
        grams = _convert(need, need_unit, "g", piece_g)
        if grams is None:
            return None
        sold = sold_quantity(grams / 1000, product.get("min_qty"), product.get("qty_step")) * 1000
        bought = sold if sold > grams + 0.5 else None
        return round(price * sold / 1000, 2), None, f"{sold:.0f} g × {price:.2f} €/{unit}", bought

    pack = pack_size(product.get("name") or "", product.get("volume"))
    if not pack:
        return None
    size, pack_unit = pack
    needed = _convert(need, need_unit, pack_unit, piece_g)
    if not needed or size <= 0:
        return None
    packs = max(1, math.ceil(needed / size - 1e-9))
    return round(packs * price, 2), packs, f"{packs} × {price:.2f} €", None


def used_cost(product, need, need_unit, piece_g=None):
    """What the amount needed is worth, leftovers not counted: 300 g of a 1.6 kg minimum or of a 500 g pack is
    300 g's worth. For "best value for what you use"; what you pay is cost_for's. None if unknown."""
    price = parse_price(product.get("price"))
    if price == float("inf") or need is None:
        return None
    if (product.get("unit") or "").lower() in ("kg", "l"):
        grams = _convert(need, need_unit, "g", piece_g)
        return round(price * grams / 1000, 2) if grams is not None else None
    pack = pack_size(product.get("name") or "", product.get("volume"))
    needed = _convert(need, need_unit, pack[1], piece_g) if pack else None
    return round(price * needed / pack[0], 2) if needed and pack[0] > 0 else None


def cart_qty(product, need, need_unit, packs, piece_g=None):
    """What to put in the e-shop's cart for what cost_for priced: packs, or kg (l) of a loose good."""
    if packs:
        return packs
    grams = _convert(need, need_unit, "g", piece_g) if need is not None else None
    if (product.get("unit") or "").lower() in ("kg", "l") and grams:
        return sold_quantity(grams / 1000, product.get("min_qty"), product.get("qty_step"))
    return None


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


def _safe_fetch(store, query, refresh=False, failed=None):
    """A store search, or [] when the store didn't answer (the store is then added to `failed`)."""
    try:
        return _cached_fetch(store, query, refresh=True) if refresh else _cached_fetch(store, query)
    except Exception as exc:
        print(f"catalog fetch failed {store}/{query}: {exc}")
        if failed is not None:
            failed.add(store)
        return []


def find_products(rule, store):
    """All in-stock products at `store` that satisfy the rule (deduplicated)."""
    seen, found = set(), []
    for q in _queries(rule):
        for p in _safe_fetch(store, q):
            key = p.get("store_id") or p.get("name")
            if key in seen:
                continue
            seen.add(key)
            if matches_rule(p, rule):
                found.append(p)
    return found


def sold_out_product(rules, ingredient_key, store):
    """A product the ingredient's rule would take at this store but that's sold out online, or None: so the
    receipt can say "sold out online" instead of "not in the e-shop". Searches are cached by now."""
    for rule in rule_chain(rules, ingredient_key, store):
        for q in _queries(rule):
            for p in _safe_fetch(store, q):
                if p.get("in_stock") is False and matches_rule({**p, "in_stock": True}, rule):
                    return p.get("name")
    return None


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
    """What helps a person recognise a product: its photo, the store shelf it sits on and its page
    in the e-shop. Rimi only gives shelf codes (SH-19-5), which mean nothing to a person, so those are left out."""
    shelf = product.get("shelf")
    return {"image": product.get("image"), "shelf": None if not shelf or re.match(r"SH-\d", shelf) else shelf,
            "url": product.get("url"),
            "store_id": product.get("store_id")}  # the store's own id: what its cart takes


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
                cost, packs, how, bought = priced
                options.append(_with_discount({"product": p["name"], "price": parse_price(p["price"]), "cost": cost,
                                               "used_cost": used_cost(p, need, spec["unit"], spec.get("piece_g")),
                                               "packs": packs, "how": how, "bought": bought, "substitute": level > 0,
                                               "cart_qty": cart_qty(p, need, spec["unit"], packs, spec.get("piece_g")),
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


def prefetch(rules, keys, stores, refresh=False, failed=None):
    """Warm the fetch cache with every search these ingredients need, concurrently.
    refresh=True asks the stores again even when the results are still cached.
    Stores with a search that failed are added to `failed`."""
    searches = {
        (store, q)
        for key in keys
        for store in stores
        for rule in rule_chain(rules, key, store)
        for q in _queries(rule)
    }
    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(lambda sq: _safe_fetch(*sq, refresh=refresh, failed=failed), searches))


def warm_cache(stores, refresh=False):
    """Every ingredient rule's searches at every store, so dinners price quickly even right after a
    restart (Barbora answers one request at a time, so a cold dinner can take 5–20 s)."""
    rules = load_rules()
    prefetch(rules, set(rules), stores, refresh)


# ── shopping list: typed words → known ingredients ──────────────────────────

def _norm(text):
    return " ".join(text.lower().split())


def cap(text):
    return text[:1].upper() + text[1:]


def _names(ingredients):
    """Typed form → ingredient key, for each ingredient's key, name and aliases (the first ingredient wins)."""
    index = {}
    for key, spec in ingredients.items():
        for n in [key.replace("_", " "), spec["name"], *spec.get("aliases", [])]:
            index.setdefault(_norm(n), key)
    return index


def match_ingredient(text, recipes=None):
    """Ingredient key whose name, key or aliases equal the typed text, else None."""
    recipes = recipes or load_recipes()
    return _index(recipes["ingredients"], _names).get(_norm(text))


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


def merge_needs(per_dinner):
    """Several dinners' needs as one list, the same ingredient added up before it becomes packs:
    300 g and 400 g of mince buy 700 g, not two 500 g packs. per_dinner: [(dinner name, needs)].
    Each need says which dinners it's `for`. A free-text item asked by weight in one dinner and by
    packs in another counts the weighed one as a pack."""
    merged = {}
    for name, needs in per_dinner:
        for n in needs:
            key = n.get("rule") or "text:" + _norm(n["text"])
            have = merged.get(key)
            if have is None:
                merged[key] = {**n, "for": [name]}
                continue
            if name not in have["for"]:
                have["for"].append(name)
            if have.get("packs") or n.get("packs"):
                have["packs"] = (have.get("packs") or 1) + (n.get("packs") or 1)
                have["amount"] = have["unit"] = None
            else:
                have["amount"] += n["amount"]
    return list(merged.values())


# ── baskets: an optional recipe plus extra items, per store ─────────────────

def free_text_offers(items, stores, needs=None, failed=None, sold_out=None):
    """Options per store for items with no ingredient rule (best guess first).

    needs: {item: grams} for dish ingredients. Those are priced for the amount (whole packs, or
    weight × price for loose goods) and, within a match tier, ordered cheapest for that amount.
    Other items cost one pack. Stores with a search that failed are added to `failed`; items a store has but
    sold out online go in `sold_out` as {(item, store): product name}.
    """
    from core.fetch import fetch_all, spec_for  # deferred: fetch is only needed for free text

    if not items:
        return {}
    needs = needs or {}
    all_products, warnings = fetch_all({it: spec_for(it) for it in items}, stores)
    if failed is not None:
        failed.update(w.split("/", 1)[0] for w in warnings)  # warnings are "store/item: error"
    out = {}
    for it in items:
        out[it] = {}
        for store in stores:
            options = []
            for p in (p for p in all_products.get(it, []) if p["store"] == store):
                if p.get("sold_out"):
                    if sold_out is not None:
                        sold_out[(it, store)] = p["name"]
                    continue
                priced = cost_for(p, needs[it], "g") if it in needs else None
                cost, packs, how, bought = priced or (p["price"], 1, f"1 × {p['price']:.2f} €", None)
                options.append((p.get("relevance", 0), p["score"], _with_discount(
                    {"product": p["name"], "price": p["price"], "cost": cost, "packs": packs, "how": how, "bought": bought,
                     "substitute": bool(p.get("swap")),
                     "used_cost": used_cost(p, needs[it], "g") if it in needs else None,
                     "cart_qty": cart_qty(p, needs[it], "g", packs) if it in needs else packs,
                     **_looks(p)}, p)))
            by_amount = it in needs
            options.sort(key=lambda o: (-o[0], o[2]["cost"]) if by_amount else o[1])
            out[it][store] = [o[2] for o in options]
    return out


def _line(key, label, need, unit, offer, options, extra):
    return {
        "key": key, "ingredient": key if not key.startswith("text:") else None,
        "label": label, "need": need, "unit": unit, "extra": extra,
        **offer,
        "options": [{k: o.get(k) for k in ("product", "cost", "how", "bought", "regular_cost", "card_cost", "deal", "image", "shelf", "url", "store_id", "cart_qty")}
                    for o in options[:MAX_OPTIONS]],
    }


def _times(option, n):
    """An option bought n times (n packs of a free-text item)."""
    if n == 1:
        return option
    mul = lambda v: round(v * n, 2) if v is not None else None
    return {**option, "cost": mul(option["cost"]), "regular_cost": mul(option.get("regular_cost")), "used_cost": mul(option.get("used_cost")),
            "card_cost": mul(option.get("card_cost")), "packs": n, "cart_qty": n, "how": f"{n:g} × {option['price']:.2f} €"}


def build_basket(store, needs, prefs, recipes, rules, free, sold_out=None):
    """One store's basket. needs: recipe ingredients (extra=False) then list items (extra=True).
    sold_out: {(free-text item, store): product name} from free_text_offers."""
    lines, missing, missing_keys, missing_why = [], [], [], []
    for n in needs:
        if n.get("rule"):
            key = n["rule"]
            offer, options = ingredient_offers(key, n["amount"], store, recipes, rules, prefs.get(key))
            need, unit = n["amount"], n["unit"]
        else:
            key = need_key(n)
            options = free.get(n["text"], {}).get(store, [])
            if n.get("packs"):
                options = [_times(o, n["packs"]) for o in options]
                need, unit = None, None
            else:
                need, unit = n["amount"], n["unit"]
            offer = _pick(options, prefs.get(key), store)
        if offer:
            line = _line(key, n["label"], need, unit, offer, options, extra=n["extra"])
            lines.append({**line, "asked": n.get("asked"), "for": n.get("for")})
        else:
            missing.append(n["label"])
            missing_keys.append(need_key(n))
            gone = (sold_out or {}).get((n["text"], store)) if n.get("text") else sold_out_product(rules, n["rule"], store)
            missing_why.append({"sold_out": gone} if gone else None)

    total = round(sum(l["cost"] for l in lines), 2)
    return {
        # What the lines are worth for what's needed, leftovers not counted (a 1.6 kg minimum for 300 g is 300 g).
        "used_price": round(sum(l["cost"] if l.get("used_cost") is None else min(l["used_cost"], l["cost"]) for l in lines), 2),
        "store": store,
        "status": "ok",
        "lines": lines,
        "missing": missing,
        "missing_keys": missing_keys,  # the same, as line keys (to leave one out)
        "missing_why": missing_why,    # the same again: {"sold_out": product} when the store has it but sold out online
        "total_price": total,
        # Already included in total_price: what the discounts take off regular prices.
        "savings": round(sum((l.get("regular_cost") or l["cost"]) - l["cost"] for l in lines), 2),
        # Not included: what loyalty-card prices would take off on top.
        "card_savings": round(sum(l["cost"] - (l.get("card_cost") or l["cost"]) for l in lines), 2),
    }


def no_answer_basket(store):
    """A store that didn't answer: nothing is known about what it has, so it isn't ranked."""
    return {"store": store, "status": "no_answer", "lines": [], "missing": [], "total_price": None,
            "savings": 0, "card_savings": 0}


MAX_DINNERS = 5  # dinners in one trip


BEST_VALUE_MARGIN = 0.3  # € a store must beat the cheapest one by, for what's used, to be named best value


def _best_value(baskets):
    """The store that's cheapest for what the dinners use (leftovers from big minimums and packs not counted),
    when that isn't the store that's cheapest to pay: Barbora's 1.6 kg of salmon costs more today, but is worth
    more. Only among stores with as few missing as the cheapest. None when it's the same store."""
    ok = [b for b in baskets if b["status"] == "ok"]
    if len(ok) < 2:
        return None
    first = ok[0]
    rivals = [b for b in ok[1:] if len(b["missing"]) == len(first["missing"])]
    best = min(rivals, key=lambda b: b["used_price"], default=None)
    return best["store"] if best and best["used_price"] <= first["used_price"] - BEST_VALUE_MARGIN else None


def need_key(n):
    """The key a need's receipt line has: its ingredient rule, or "text:<item>"."""
    return n["rule"] if n.get("rule") else "text:" + _norm(n["text"])


def recommend(recipe_id, servings, items, stores, prefs=None, user_id=None, dinners=None, skip=()):
    """Rank stores for a recipe (optional) plus extra items: fewest missing, then cheapest.

    dinners: several dinners for one trip, [{"id", "servings"}], priced together (merge_needs);
    recipe_id with servings is the same as a list of one.

    A store with a search that failed didn't answer: its basket has status "no_answer" and comes
    after the ranked ones, rather than looking like a store that doesn't sell the things.

    prefs: {ingredient key or "text:<item>": {"products": {store: name}, "words": [...]}}
    skip: line keys the person took off the receipt (they have it, or don't want it). They're left out at every
    store, so the stores are ranked without them, and come back as `skipped` to be put back.
    """
    recipes, rules = load_recipes(), load_rules()
    if not dinners:
        dinners = [{"id": recipe_id, "servings": servings}] if recipe_id else []
    dinners = list({d["id"]: d for d in dinners}.values())[:MAX_DINNERS]  # each dinner once
    picked = []
    for d in dinners:
        recipe = find_recipe(d["id"], recipes, user_id)
        if recipe is None:
            raise KeyError(d["id"])
        picked.append((recipe, d.get("servings") or servings))
    items = list(dict.fromkeys(i.strip() for i in items if i and i.strip()))
    prefs = prefs or {}

    each = [recipe_needs(r, people, recipes) for r, people in picked]
    dinner_needs = each[0] if len(each) == 1 else merge_needs([(r["name"], n) for (r, _), n in zip(picked, each)])
    needs = [{**n, "extra": False} for n in dinner_needs]
    needs += [{**to_need(it, recipes), "extra": True} for it in items]
    skip = set(skip or ())
    skipped = list({need_key(n): {"key": need_key(n), "label": n["label"]} for n in needs if need_key(n) in skip}.values())
    needs = [n for n in needs if need_key(n) not in skip]
    keys = {n["rule"] for n in needs if n.get("rule")}
    # Free-text searches; those with an amount are priced for it (grams or ml).
    amounts = {n["text"]: n["amount"] for n in needs if n.get("text") and n.get("amount") is not None}
    free_items = list(dict.fromkeys(n["text"] for n in needs if n.get("text")))

    # Rule searches and free-text searches run side by side.
    failed = set()
    with ThreadPoolExecutor(max_workers=2) as pool:
        warm = pool.submit(prefetch, rules, keys, stores, failed=failed)
        sold_out = {}
        free_job = pool.submit(free_text_offers, free_items, stores, amounts, failed=failed, sold_out=sold_out)
        warm.result()
        free = free_job.result()

    baskets = [build_basket(s, needs, prefs, recipes, rules, free, sold_out) for s in stores if s not in failed]
    baskets.sort(key=lambda b: (len(b["missing"]), b["total_price"]))
    baskets += [no_answer_basket(s) for s in stores if s in failed]
    best_value = _best_value(baskets)

    # Each dinner as a recipe card: its ingredients for this many people, and how to cook it when known.
    about = [card(r, people, needs) for (r, people), needs in zip(picked, each)]
    return {
        # One dinner: `recipe` as before. Several: `recipe` is None and `dinners` lists them.
        "recipe": {k: about[0][k] for k in ("id", "name", "pantry")} if len(about) == 1 else None,
        "dinners": about,
        "pantry": list(dict.fromkeys(p for d in about for p in d["pantry"])),
        "servings": servings,
        "items": items,
        "skipped": skipped,
        "store": baskets[0]["store"] if baskets and baskets[0]["status"] == "ok" else None,
        "best_value": best_value,
        "baskets": baskets,
    }


def card(recipe, servings, needs):
    """A dinner as its recipe card shows it: ingredients for this many people, and how to cook it when known."""
    return {"id": recipe["id"], "name": recipe["name"], "servings": servings, "pantry": recipe.get("pantry", []),
            "ingredients": [{k: n.get(k) for k in ("label", "amount", "unit", "packs", "asked")} for n in needs],
            **{k: recipe.get(k) for k in ("method", "link", "image", "about", "minutes", "steps")}}


def recipe_card(recipe_id, servings, user_id=None):
    """One dinner's recipe card, without asking any store: for the dinner's own page. None if unknown."""
    recipes = load_recipes()
    recipe = find_recipe(recipe_id, recipes, user_id)
    if recipe is None:
        return None
    return card(recipe, servings, recipe_needs(recipe, servings, recipes))


def recommend_dinner(recipe_id, servings, stores):
    """A recipe on its own (no extra items or preferences)."""
    return recommend(recipe_id, servings, [], stores)
