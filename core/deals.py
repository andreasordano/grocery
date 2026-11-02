# =============================================================================
# THIS WEEK'S DEALS  (WEB-28, WEB-29)
# Every dinner the app shows is priced at each store the way a person would get it (catalog.recommend), and the
# lines bought on sale are counted: a regular price above the shelf price, or a loyalty-card price below it. No
# new mapping: the products are the ones data/rules.yaml and the free-text search already pick. A dinner with at
# least MIN_ON_SALE lines on sale, and everything in stock, is a deal dinner at that store; the larger the share of
# its cost on sale, the better. The "Cheap this week" chip shows each store's best (chip_ids), and "At the store"
# shows one store's (GET /deals).
# It runs on the server, in the cache warm-up thread (Selver blocks requests from outside Estonia), and is kept in
# memory: after a restart the saved searches make the first run quick. Until it has run, there are no deals.
# unmatched_food() is the monthly review list: Selver's discounted food that no ingredient rule catches.
# =============================================================================

import threading
from datetime import datetime, timezone

import requests

from core import catalog
from core import recipes as own_recipes

MIN_ON_SALE = 2   # lines on sale for a dinner to count as a deal
CHIP_PER_STORE = 6  # each store's best deal dinners in the "Cheap this week" chip
CHIP = "deals"      # its id in data/dinner_chips.yaml

_lock = threading.Lock()
_state = {"at": None, "stores": {}}  # store → deal dinners, best first


def on_sale(line):
    """A receipt line bought at a discount: the regular price is higher, or the loyalty card's is lower."""
    return (line.get("regular_cost") or 0) > line["cost"] or (line.get("card_cost") or line["cost"]) < line["cost"]


def percent_off(line):
    lower = min(line["cost"], line.get("card_cost") or line["cost"])
    regular = max(line["cost"], line.get("regular_cost") or 0)
    return round(100 * (1 - lower / regular)) if regular else 0


def score(dinner_id, basket):
    """One store's basket for a dinner as a deal, or None when it isn't one (something missing, too little on sale)."""
    if basket["status"] != "ok" or basket["missing"] or not basket["total_price"]:
        return None
    sale = list({l["label"].lower(): l for l in basket["lines"] if on_sale(l)}.values())  # a recipe can list a thing twice
    if len(sale) < MIN_ON_SALE:
        return None
    return {
        "id": dinner_id,
        "count": len(basket["lines"]),
        "on_sale": [{"label": l["label"], "product": l["product"], "off": percent_off(l)} for l in sale],
        "share": round(sum(l["cost"] for l in basket["lines"] if on_sale(l)) / basket["total_price"], 2),  # of the cost
        "saving": round(basket["savings"] + basket["card_savings"], 2),
        "total": basket["total_price"],
    }


def candidates():
    """The dinners the app shows (GET /recipes), desserts and other chips kept apart left out."""
    store = catalog.load_store_recipes()
    dishes = store["dinners"] or catalog.load_dishes()["dishes"]
    cfg, month = own_recipes.chips(), own_recipes.this_month()
    apart = {c["id"] for c in cfg["chips"] if c.get("apart")}
    return [d for d in catalog.load_recipes()["recipes"] + own_recipes.published() + dishes
            if d.get("ingredients") and not apart & set(own_recipes.tags_of(d, month, cfg))]


def refresh(stores):
    """Price every dinner at every store and keep the deal dinners. A store that answered for no dinner keeps
    what it had: a store being down shouldn't empty its deals."""
    found, answered = {s: [] for s in stores}, set()
    for d in candidates():
        try:
            res = catalog.recommend(d["id"], d.get("servings") or catalog.BASE_SERVINGS, [], stores)
        except Exception as exc:  # one dinner shouldn't stop the others
            print(f"deals: {d['id']} failed: {exc}")
            continue
        for b in res["baskets"]:
            if b["status"] == "ok":
                answered.add(b["store"])
            deal = score(d["id"], b)
            if deal:
                found[b["store"]].append(deal)
    with _lock:
        stores_now = dict(_state["stores"])
        for s in answered:
            stores_now[s] = sorted(found[s], key=lambda x: (-x["share"], -x["saving"]))
        _state.update(at=datetime.now(timezone.utc), stores=stores_now)
    return {s: len(v) for s, v in stores_now.items()}


def week():
    """{at: when it was worked out (None: not yet), stores: {store: deal dinners, best first}}."""
    with _lock:
        return {"at": _state["at"].isoformat() if _state["at"] else None, "stores": dict(_state["stores"])}


def chip_ids():
    """The dinners under "Cheap this week": each store's best few."""
    with _lock:
        return {d["id"] for deals in _state["stores"].values() for d in deals[:CHIP_PER_STORE]}


def badge(dinner_id):
    """Where a dinner in the chip is a deal, for its card: {store, on_sale, count} at its best store, or None."""
    with _lock:
        best = [(d, s) for s, deals in _state["stores"].items() for d in deals[:CHIP_PER_STORE] if d["id"] == dinner_id]
    if not best:
        return None
    d, store = max(best, key=lambda x: x[0]["share"])
    return {"store": store, "on_sale": len(d["on_sale"]), "count": d["count"]}


def set_week(stores, worked_out=True):
    """Put deals in place (tests); worked_out=False is the state before the first run."""
    with _lock:
        _state.update(at=datetime.now(timezone.utc) if worked_out else None, stores=stores)


# ── the monthly review: discounted food no rule catches ──────────────────────

SELVER_URL = "https://www.selver.ee/api/catalog/vue_storefront_catalog_et/product/_search"
# Selver files each discount under one of two virtual categories; only food ones are listed.
SELVER_FOOD_DEALS = "Soodushinnaga toidukaubad"
# Food shelves that never make dinner, left out of the list.
NOT_DINNER = ("vein", "joogid", "šampan", "õlled", "konjak", "viin", "liköör", "siidr", "veed", "kohvid",
              "teed", "šokolaad", "komm", "küpsis", "jäätis", "lastetoid", "mahlad", "toidulisand",
              "nätsud", "maiustus", "hommikuhelbed", "kassi", "koera")


def unmatched_food(rules=None, shelves=30, examples=3):
    """Discounted Selver food that no ingredient rule accepts, by shelf, most first: pages Selver's whole
    catalogue (about 12,000 products, 12 requests). Rimi and Barbora can't be paged that way.
    {total, on_sale, unmatched, shelves: [{shelf, count, examples}]}"""
    rules = rules or catalog.load_rules()
    after, counts, names, total, sale = None, {}, {}, 0, 0
    while True:
        body = {"query": {"match_all": {}}, "size": 1000, "sort": [{"_id": "asc"}],
                "_source": ["name", "final_price", "price", "original_price", "product_group_price", "category", "stock"]}
        if after:
            body["search_after"] = after
        r = requests.post(SELVER_URL, json=body, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        r.raise_for_status()
        hits = r.json()["hits"]["hits"]
        if not hits:
            break
        for h in hits:
            total += 1
            s = h["_source"]
            price, regular = s.get("final_price") or s.get("price"), s.get("original_price")
            card = s.get("product_group_price")  # Partnerkaart price, as in api/selver_api.py
            try:
                if not (price and ((regular and float(regular) > float(price) + 0.004)
                                   or (card and float(card) < float(price) - 0.004))):
                    continue
            except (TypeError, ValueError):
                continue
            sale += 1
            cats = s.get("category") or []
            shelf = next((c.get("name") for c in cats if str(c.get("is_virtual")).lower() != "true" and c.get("name")), None)
            if SELVER_FOOD_DEALS not in [c.get("name") for c in cats] or not shelf \
                    or any(x in shelf.lower() for x in NOT_DINNER):
                continue
            p = {"name": s.get("name"), "category": [c.get("name") for c in cats if c.get("name")],
                 "in_stock": (s.get("stock") or {}).get("stock_status", 1) == 1}
            if any(catalog.matches_rule(p, rule) for key in rules for rule in catalog.rule_chain(rules, key, "selver")):
                continue
            counts[shelf] = counts.get(shelf, 0) + 1
            names.setdefault(shelf, []).append(p["name"])
        after = hits[-1]["sort"]
    top = sorted(counts.items(), key=lambda x: -x[1])[:shelves]
    return {"total": total, "on_sale": sale, "unmatched": sum(counts.values()),
            "shelves": [{"shelf": s, "count": c, "examples": names[s][:examples]} for s, c in top]}
