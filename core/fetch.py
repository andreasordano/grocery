# =============================================================================
# FETCHERS  (delegated to the individual API modules)
# This module defines functions to fetch product data from different stores (Rimi, Selver, Barbora) based on a search term.
# The main function, `fetch_all`, orchestrates the fetching process for all items in the grocery list and selected stores, applies relevance scoring, and extracts weight/volume information. 
# It returns a structured dictionary of products along with any warnings encountered during the fetching process.
# It runs after the initial grocery list parsing and before the scoring and optimization phases, which rely on the fetched product data
# =============================================================================

from collections import defaultdict
import os
import re
from api.selver_api import search_selver
from api.barbora_api import search_barbora
from api.rimi_api import search_rimi
from core.cache import TTLCache
from core.scoring import build_rules, compute_product_score, extract_weight_volume, parse_price, relevance_score


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


def _fetch_rimi(search_term, size=40):
    return search_rimi(search_term, page=0)


def _fetch_selver(search_term, size=40):
    return search_selver(search_term, size=size)


def _fetch_barbora(search_term, size=40):
    return search_barbora(search_term, size=size)


_FETCHERS = {
    "rimi": _fetch_rimi,
    "selver": _fetch_selver,
    "barbora": _fetch_barbora,
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
    data = _FETCHERS[store](query, size=size)
    _CACHE.set(key, data)
    return data



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


def fetch_all(grocery_list, selected_stores, on_progress=None):
    """
    Fetch and score products for every item/store combination using short,
    generic queries with cached responses and strict relevance filtering.
    """
    all_products = defaultdict(list)
    warnings = []
    total = len(grocery_list) * len(selected_stores)
    count = 0

    PER_STORE_LIMIT = int(os.environ.get("PER_STORE_LIMIT", 6))

    for display_name, spec in grocery_list.items():
        rules = build_rules(spec)
        queries = _build_queries(spec)

        for store in selected_stores:
            store_candidates = []
            seen_ids = set()

            for q in queries:
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

                if len(store_candidates) >= PER_STORE_LIMIT:
                    break

            # keep best scored candidates per store
            store_candidates.sort(key=lambda p: p.get("score", float("inf")))
            all_products[display_name].extend(store_candidates[:PER_STORE_LIMIT])

            count += 1
            if on_progress:
                on_progress(count, total, store, display_name)
    return all_products, warnings