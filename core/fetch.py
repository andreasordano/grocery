# =============================================================================
# FETCH  (store searches, and products for typed items)
# _cached_fetch asks a store's connector (stores_config.py) and caches the answer; every store request goes
# through it, and each one is written to the price log (core/price_log.py).
# fetch_all finds products for free-text items (anything without an ingredient rule): it searches each store
# with the typed words, sorts the results into match tiers using the store's own shelves, and ranks them by
# price per 100 g within a tier. Ingredients with rules are found in core/catalog.py instead.
# =============================================================================

from collections import Counter, defaultdict
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from core import db, price_log
from core.cache import TTLCache
from core.scoring import head_weight, made_from, misses_the_thing, pack_size, parse_price, relevance_score, score, shares_stem
from stores_config import connector, max_concurrency


# Never suitable for a basket, whatever the item: pre-order and bulk listings.
GLOBAL_EXCLUDE = ["ettetellimisel", "hulgi "]


# Cache store search responses to keep API usage and latency low. About 130 rule searches and 600 free-text
# ones (the NutriData dishes' words) per store set: 2048 keeps them all.
_CACHE = TTLCache(
    ttl_seconds=int(os.environ.get("FETCH_CACHE_TTL", 6 * 3600)),
    maxsize=int(os.environ.get("FETCH_CACHE_MAX", 2048)),
)
SIZE = 40  # products per search

_inflight = {}  # cache key → Future of the store request already on its way
_lock = threading.Lock()
_limits = {}  # store → semaphore: at most max_concurrency requests at once (stores_config)


def _limit(store):
    with _lock:
        if store not in _limits:
            _limits[store] = threading.BoundedSemaphore(max_concurrency(store))
        return _limits[store]


def _cached_fetch(store: str, query: str, size: int = SIZE, refresh: bool = False):
    """Store search results, cached for FETCH_CACHE_TTL. refresh=True asks the store again (cache warm-up).
    The same search asked by several people at once goes to the store once; each store gets at most its
    max_concurrency requests at a time, however many answers are being priced."""
    key = (store, query.strip().lower(), size)
    cached = None if refresh else _CACHE.get(key)
    if cached is not None:
        return cached
    with _lock:
        pending = _inflight.get(key)
        if pending is None:
            pending = _inflight[key] = Future()
            mine = True
        else:
            mine = False
    if not mine:
        return pending.result()  # someone else's request for the same search: share its answer (or error)
    try:
        with _limit(store):
            data = _ask_store(store, query, size, "refresh" if refresh else "search")
        # Don't cache empty results: they are often a transient store error, and
        # caching them would hide the product for the whole TTL.
        if data:
            _CACHE.set(key, data)
        pending.set_result(data)
        return data
    except Exception as exc:
        pending.set_exception(exc)
        raise
    finally:
        with _lock:
            _inflight.pop(key, None)


def load_saved_searches():
    """Fill the cache with the store answers saved in the database that are still fresh (search_cache, written
    by the price log), so a restart doesn't ask every store again. Returns how many were loaded."""
    if not db.configured():
        return 0
    since = datetime.now(timezone.utc) - timedelta(seconds=_CACHE.ttl)
    try:
        rows = db.query("SELECT retailer, query, fetched_at, products FROM search_cache WHERE fetched_at > %s", (since,))
    except Exception as exc:  # e.g. before the table's migration
        print(f"saved searches not loaded: {exc}")
        return 0
    loaded = 0
    for retailer, query, fetched_at, products in rows:
        if products and "store_id" in products[0]:  # answers saved before the connector contract are left out
            _CACHE.set((retailer, query, SIZE), products, at=fetched_at.timestamp())
            loaded += 1
    return loaded


def _ask_store(store, query, size, kind):
    """One request to a store's connector, logged in the price log (and saved for restarts) either way."""
    started = datetime.now(timezone.utc)
    try:
        data = connector(store)(query, limit=size)
    except Exception as exc:
        price_log.record(store, query, kind, started, error=exc)
        raise
    price_log.record(store, query, kind, started, products=data)
    return data



def discount_fields(item: dict) -> dict:
    """Discount info from a store adapter's product: regular price (when on sale), loyalty-card
    price, multi-buy note and offer end date. Missing values are None."""
    def num(v):
        p = parse_price(v)
        return None if p == float("inf") else p
    return {
        "regular_price": num(item.get("regular_price")),
        "card_price": num(item.get("card_price")),
        "deal": item.get("deal"),
        "deal_until": item.get("deal_until"),
    }


def _normalize_candidate(item: dict, display_name: str, store: str, rules: dict):
    # Out of stock: never recommended, but kept (sold_out) so a receipt can say "sold out online" rather
    # than "not in the e-shop". Rimi gives those no price.
    sold_out = item.get("in_stock") is False
    name = item.get("name") or ""
    price = parse_price(item.get("price") or item.get("retail_price"))
    if price == float("inf") and not sold_out:
        return None

    size = pack_size(name, item.get("volume"))
    weight = size[0] if size and size[1] == "g" else None
    volume = size[0] if size and size[1] == "ml" else None

    # Fallbacks for loose/bulk items priced per kg/l when size isn't embedded.
    unit_field = str(item.get("unit") or "").lower()
    name_l = name.lower()
    tokens = set(re.findall(r"[\wäöüõšžÄÖÜÕŠŽ]+", name_l))

    if weight is None and (unit_field == "kg" or "kg" in tokens or "kg" in name_l):
        weight = 1000.0
    if volume is None and (unit_field == "l" or "l" in tokens or " l" in name_l):
        volume = 1000.0

    # Drop obviously bogus large sizes that slipped through.
    if weight and weight > 10000:
        weight = None
    if volume and volume > 10000:
        volume = None

    rel = relevance_score(name, rules)
    if any(x in name.lower() for x in GLOBAL_EXCLUDE):
        return None
    return {
        "item": display_name,
        "store": store,
        "name": name,
        "price": price,
        **discount_fields(item),
        "brand": item.get("brand"),
        "shelf": item.get("shelf"),
        "image": item.get("image"),
        "url": item.get("url"),        # the product's page in the e-shop
        "store_id": item.get("store_id"),  # what the store's cart takes
        "unit": item.get("unit"),      # "kg"/"l" for loose goods (catalog.cost_for)
        "min_qty": item.get("min_qty"),    # loose goods: the least the store sells, in kg/l
        "qty_step": item.get("qty_step"),  # and the steps above it
        "volume": item.get("volume"),  # pack size when the name lacks it (Selver)
        "weight_g": weight,
        "volume_ml": volume,
        "match": rel,
        "related": rel >= 1 or shares_stem(name, rules),
        "weight": head_weight(name, rules),
        # Made from it ("Br.kintsuliha jogurtimarinaadis" for kanakintsuliha): it shows which shelf the thing
        # is on, so it votes, but it isn't offered.
        "made_from": made_from(name, display_name) or misses_the_thing(name, display_name),
        "sold_out": sold_out,
    }


MADE_FROM_VOTE = 0.4
MADE_FROM_CAP = 0.9


def _shelves(candidates):
    """Shelves the typed thing sits on at this store, as (top shelf, shelves to trust).

    Votes come from the best matches available: exact words (õun), else near forms
    (maapähklivõie), else the store's own top results that are related to the typed word (it
    knows maapähklikreem is peanut butter; a lamp it returns for "porru" doesn't count). Votes are weighted by how early the name says the word (see head_weight), so
    two "Banaan, kg" outvote three smoothie mixes listing banana. A shelf is trusted if it
    is the top one, or holds at least two matches and either names the thing first on one
    of them ("Veiseliha steik") or gets half the top shelf's votes ("Ol.õli", "Päevalille õli"
    on the olive and sunflower oil shelves). Shelves where it only comes later in the names
    ("Kassitoit veiseliha", "Puljong veiseliha") hold something else made with it, and a lone
    cat litter "roh.tee" or car "Õli mitmeotstarbeline" doesn't count."""
    # The best match level that has something real (not made from it) votes: at Rimi every exact "veiseliha" is
    # a tin, stock or pet food, and the fresh beef is "Veise kaelaliha" (a near form), so the near forms vote.
    for level in (5, 4):
        voters = [p for p in candidates if p["match"] == level and p.get("shelf")]
        if any(not p.get("made_from") for p in voters):
            break
    else:
        voters = [p for p in candidates if p["match"] >= 4 and p.get("shelf")]
    if not voters:
        voters = [{**p, "weight": 1.0} for p in candidates[:8] if p.get("shelf") and p.get("related")]
    if not voters:
        return None, set()
    weights, made, counts = Counter(), Counter(), Counter()
    for p in voters:
        # Made from it (smoked, marinated, tinned) still says where the thing is kept, but less loudly than the
        # thing, and all of them on a shelf together count less than one real match: two hot-smoked redfish, or
        # seven tins of stewed beef, mustn't outvote the fresh one on its own shelf.
        if p.get("made_from"):
            made[p["shelf"]] += p["weight"] * MADE_FROM_VOTE
        else:
            weights[p["shelf"]] += p["weight"]
        counts[p["shelf"]] += 1
    for shelf, w in made.items():
        weights[shelf] += min(w, MADE_FROM_CAP)
    top = weights.most_common(1)[0][0]
    if counts.most_common(1)[0][1] == 1:  # too few matches to tell outliers apart: trust them all
        return top, set(counts)
    named_first = {p["shelf"] for p in voters if p["match"] >= 4 and p["weight"] == 1.0}
    return top, {top} | {s for s, n in counts.items()
                         if n >= 2 and (s in named_first or weights[s] >= weights[top] / 2)}


def _tier(product, top, trusted):
    """Match tier: 5 the thing on a trusted shelf, 4 something else from the top shelf
    (maapähklikreem when you typed maapähklivõi), 2 a mention when the store has no
    shelf information. None = drop."""
    match, shelf = product["match"], product.get("shelf")
    if match >= 4 and (top is None or shelf in trusted):
        return 5
    if top is not None and shelf == top:
        return 4
    if top is None and match >= 1:
        return 2
    return None


def spec_for(item: str) -> dict:
    """Search spec for a typed item: the text itself plus its keyword tokens (sizes dropped)."""
    tokens = [t for t in re.findall(r"\w+", item.lower())
              if len(t) > 1 and not re.fullmatch(r"\d+(?:[.,]\d+)?(?:g|kg|ml|l)?", t)]
    return {"search_term": item, "include": tokens}


def _build_queries(spec: dict):
    base = spec.get("search_term", "").strip()
    includes = [kw for kw in spec.get("include", []) if kw]
    tokens = []
    for kw in includes + [base]:
        for t in re.findall(r"[\wäöüõšžÄÖÜÕŠŽ]+", kw.lower()):
            if len(t) > 1:
                tokens.append(t)

    queries = []
    if base:
        queries.append(base)
    words = base.lower().split()
    if len(words) == 2 and all(w.isalpha() for w in words):
        queries.append("".join(words))  # "hiina kapsas": the store may only know "Hiinakapsas"

    # Add individual tokens as fallbacks.
    for t in tokens:
        queries.append(t)
    # "veiseliha": stores name the animal, then the cut ("Veise kaelaliha").
    queries += [t[:-4] for t in tokens if len(t) >= 7 and t.endswith("liha")]

    # Deduplicate while preserving order.
    seen = set()
    uniq = []
    for q in queries:
        if not q:
            continue
        qn = q.lower().strip()
        if qn in seen:
            continue
        seen.add(qn)
        uniq.append(q)
    return uniq


def _singular(item):
    """"õunad" → "õun", "banaanid" → "banaan": some stores only find fresh fruit by the singular."""
    w = item.strip().lower()
    if " " in w or len(w) < 5 or not w.endswith("d"):
        return None
    return w[:-2] if w[-2] in "aeiu" else w[:-1]


def synonyms(item, kind="groups"):
    """Other names for the same thing (data/synonyms.yaml): "passata" for "passeeritud tomatid".
    kind="swaps": different things that do the same job ("pangaasiusefilee" for "tursafilee")."""
    from core.catalog import load_yaml  # deferred: catalog imports this module
    from core.scoring import _DESCRIBES
    words = item.lower().split()
    # "külmutatud tursk" is tursk: describing words in front don't make it another thing
    for name in (" ".join(words), " ".join(w for w in words if not w.endswith(_DESCRIBES))):
        for group in load_yaml("synonyms.yaml").get(kind) or []:
            if name in group:
                return [g for g in group if g != name]
    return []


def _exact(candidates):
    """How many are exactly the thing and could be offered: twelve tins of stewed beef don't mean the search for
    "veiseliha" can stop before the fresh cuts ("Veise kaelaliha") are found."""
    return sum(p["match"] == 5 and not p["made_from"] and not p["sold_out"] for p in candidates)


def _fetch_item_store(display_name: str, spec: dict, store: str, per_store_limit: int, alternatives=True):
    """Run the query fallbacks for one item at one store; return (candidates, warnings).
    Candidates are best first. When none is in stock, the best one that would match but is sold out comes
    back alone, marked sold_out (for "sold out online").
    When nothing is exactly the thing (tier 5), the item's other names are tried (synonyms): the first that
    finds the thing exactly wins ("Parmigiano Reggiano" for parmesan, not the cheapest cheese on its shelf).
    Then its swaps: the cheapest exact match among them, marked swap ("Pangaasiusefilee" for tursafilee)."""
    rules = {"include": spec.get("include", [])}
    store_candidates = []
    warnings = []
    seen_ids = set()

    singular = _singular(spec.get("search_term", ""))
    for q in _build_queries(spec) + ([singular] if singular else []):
        if q == singular and _exact(store_candidates) >= per_store_limit // 2:
            break  # the plural found enough already
        try:
            raw = _cached_fetch(store, q)
        except Exception as exc:
            warnings.append(f"{store}/{display_name}: {exc}")
            raw = []

        for item in raw:
            remote_id = item.get("store_id") or item.get("name")
            if not remote_id:
                continue
            dedup_key = f"{store}:{str(remote_id).lower()}"
            if dedup_key in seen_ids:
                continue
            seen_ids.add(dedup_key)

            product = _normalize_candidate(item, display_name, store, rules)
            if product:
                store_candidates.append(product)

        if _exact(store_candidates) >= per_store_limit:
            break

    # Trust the store's shelves: the shelf most real matches sit on decides what else
    # counts (same shelf) and what doesn't ("with peanut butter" snacks elsewhere).
    top, trusted = _shelves(store_candidates)
    ranked = []
    sold_out = []
    for p in store_candidates:
        tier = _tier(p, top, trusted)
        if tier is None or p["made_from"]:
            continue
        p["relevance"] = tier
        if p["sold_out"]:
            sold_out.append(p)
            continue
        p["score"] = score(p)
        ranked.append(p)
    ranked.sort(key=lambda p: p["score"])
    if alternatives and not any(p["relevance"] == 5 for p in ranked):
        for alt in synonyms(spec.get("search_term", display_name)):
            found, more = _fetch_item_store(alt, spec_for(alt), store, per_store_limit, alternatives=False)
            for p in found:
                p["item"] = display_name  # found under another name, for the item that was asked
            warnings += more
            if any(p["relevance"] == 5 and not p["sold_out"] for p in found):
                return [p for p in found if p["relevance"] == 5], warnings
        swaps = []
        for alt in synonyms(spec.get("search_term", display_name), "swaps"):
            found, more = _fetch_item_store(alt, spec_for(alt), store, per_store_limit, alternatives=False)
            warnings += more
            swaps += [{**p, "item": display_name, "swap": True} for p in found if p["relevance"] == 5 and not p["sold_out"]]
        if swaps:
            return sorted(swaps, key=lambda p: p["score"])[:per_store_limit], warnings
    sold_out.sort(key=lambda p: -p["relevance"])
    return (ranked[:per_store_limit] if ranked else sold_out[:1]), warnings


def fetch_all(grocery_list, selected_stores):
    """
    Fetch and score products for every item/store combination using short,
    generic queries with cached responses, relevance tiers and a per-store shelf vote.
    Item/store combinations are fetched concurrently; results are assembled
    in grocery-list and store order so output is deterministic.
    """
    PER_STORE_LIMIT = int(os.environ.get("PER_STORE_LIMIT", 12))
    MAX_WORKERS = int(os.environ.get("FETCH_WORKERS", 12))

    jobs = [(name, store) for name in grocery_list for store in selected_stores]
    results = {}

    with ThreadPoolExecutor(max_workers=max(1, MAX_WORKERS)) as pool:
        futures = {
            pool.submit(_fetch_item_store, name, grocery_list[name], store, PER_STORE_LIMIT): (name, store)
            for name, store in jobs
        }
        for fut in as_completed(futures):
            name, store = futures[fut]
            try:
                results[(name, store)] = fut.result()
            except Exception as exc:
                results[(name, store)] = ([], [f"{store}/{name}: {exc}"])

    all_products = defaultdict(list)
    warnings = []
    for name, store in jobs:
        candidates, job_warnings = results[(name, store)]
        all_products[name].extend(candidates)
        warnings.extend(job_warnings)
    return all_products, warnings