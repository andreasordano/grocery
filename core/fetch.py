# =============================================================================
# FETCHERS  (delegated to the individual API modules)
# This module defines functions to fetch product data from different stores based on a search term.
# Stores are configurable in stores_config.py — add new stores without modifying this file.
# The main function, `fetch_all`, orchestrates the fetching process for all items in the grocery list and selected stores, applies relevance scoring, and extracts weight/volume information. 
# It returns a structured dictionary of products along with any warnings encountered during the fetching process.
# It runs after the initial grocery list parsing and before the scoring and optimization phases, which rely on the fetched product data
# =============================================================================

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import re
from core.cache import TTLCache
from core.scoring import build_rules, compute_product_score, extract_weight_volume, parse_price, relevance_score
from stores_config import get_fetcher, get_pagination_param


# Default synonyms to broaden searches without requiring exact catalog names.
_SYNONYMS = {
    "piim": ["milk", "täispiim", "lahja piim"],
    "riis": ["rice", "jasmiini riis", "basmati"],
    "sojakaste": ["soy sauce", "soja kaste"],
    "hambapasta": ["toothpaste", "suuhügieen"],
    "õli": ["oil", "oliiviõli"],
    "munad": ["eggs", "kana muna"],
    "leib": ["bread"],
}


# Cache store search responses to keep API usage and latency low.
_CACHE = TTLCache(
    ttl_seconds=int(os.environ.get("FETCH_CACHE_TTL", 6 * 3600)),
    maxsize=int(os.environ.get("FETCH_CACHE_MAX", 512)),
)


def _cached_fetch(store: str, query: str, size: int = 40):
    key = (store, query.strip().lower(), size)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    fetcher = get_fetcher(store)
    param_name = get_pagination_param(store)
    
    # Call fetcher with correct parameter
    # - Rimi uses 'page' (pagination offset, always 0 for first page)
    # - Others use 'size' (number of results to return)
    if param_name == "page":
        data = fetcher(query, page=0)
    else:
        data = fetcher(query, **{param_name: size})

    # Don't cache empty results: they are often a transient store error, and
    # caching them would hide the product for the whole TTL.
    if data:
        _CACHE.set(key, data)
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
    name = item.get("name") or ""
    price = parse_price(item.get("price") or item.get("retail_price"))
    if price == float("inf"):
        return None

    # Try to extract size from name and extra fields.
    extra_text = []
    for key in ("unit", "volume", "product_volume"):
        val = item.get(key)
        if val:
            extra_text.append(str(val))
    weight, volume = extract_weight_volume(name, extra_text)

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

    product = {
        "item": display_name,
        "store": store,
        "name": name,
        "price": price,
        **discount_fields(item),
        "brand": item.get("brand"),
        "weight_g": weight,
        "volume_ml": volume,
    }

    rel = relevance_score(name, rules)
    if rel < 1:
        return None
    product["relevance"] = rel
    score, explanation = compute_product_score(product, rules)
    if score > 5:
        return None
    product["score"] = score
    product["explanation"] = explanation
    return product


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

    # Add synonyms for the first token when known.
    if tokens:
        key = tokens[0]
        for syn in _SYNONYMS.get(key, []):
            queries.append(syn)

    # Add individual tokens as fallbacks.
    for t in tokens:
        queries.append(t)

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


def _fetch_item_store(display_name: str, spec: dict, store: str, per_store_limit: int):
    """Run the query fallbacks for one item at one store; return (candidates, warnings)."""
    rules = build_rules(spec)
    store_candidates = []
    warnings = []
    seen_ids = set()

    for q in _build_queries(spec):
        try:
            raw = _cached_fetch(store, q)
        except Exception as exc:
            warnings.append(f"{store}/{display_name}: {exc}")
            raw = []

        for item in raw:
            remote_id = item.get("id") or item.get("sku") or item.get("code") or item.get("name")
            if not remote_id:
                continue
            dedup_key = f"{store}:{str(remote_id).lower()}"
            if dedup_key in seen_ids:
                continue
            seen_ids.add(dedup_key)

            product = _normalize_candidate(item, display_name, store, rules)
            if not product:
                continue
            store_candidates.append(product)

        if len(store_candidates) >= per_store_limit:
            break

    # keep best scored candidates per store
    store_candidates.sort(key=lambda p: p.get("score", float("inf")))
    return store_candidates[:per_store_limit], warnings


def fetch_all(grocery_list, selected_stores, on_progress=None):
    """
    Fetch and score products for every item/store combination using short,
    generic queries with cached responses and strict relevance filtering.
    Item/store combinations are fetched concurrently; results are assembled
    in grocery-list and store order so output is deterministic.
    """
    PER_STORE_LIMIT = int(os.environ.get("PER_STORE_LIMIT", 6))
    MAX_WORKERS = int(os.environ.get("FETCH_WORKERS", 12))

    jobs = [(name, store) for name in grocery_list for store in selected_stores]
    results = {}
    total = len(jobs)

    with ThreadPoolExecutor(max_workers=max(1, MAX_WORKERS)) as pool:
        futures = {
            pool.submit(_fetch_item_store, name, grocery_list[name], store, PER_STORE_LIMIT): (name, store)
            for name, store in jobs
        }
        for count, fut in enumerate(as_completed(futures), start=1):
            name, store = futures[fut]
            try:
                results[(name, store)] = fut.result()
            except Exception as exc:
                results[(name, store)] = ([], [f"{store}/{name}: {exc}"])
            if on_progress:
                on_progress(count, total, store, name)

    all_products = defaultdict(list)
    warnings = []
    for name, store in jobs:
        candidates, job_warnings = results[(name, store)]
        all_products[name].extend(candidates)
        warnings.extend(job_warnings)
    return all_products, warnings