# =============================================================================
# FETCHERS  (delegated to the individual API modules)
# =============================================================================

from collections import defaultdict
from api.selver_api import search_selver
from api.barbora_api import search_barbora
from core.scoring import build_rules, compute_product_score, extract_weight_volume, parse_price, relevance_score
from api.rimi_api import search_rimi


def _fetch_rimi(search_term, size=40):
    return [{"name": p["name"], "price": p["price"], "brand": p.get("brand")} for p in search_rimi(search_term, page=0)]

def _fetch_selver(search_term, size=40):
    return [{"name": p["name"], "price": p["price"], "brand": p.get("brand")} for p in search_selver(search_term, size=size)]

def _fetch_barbora(search_term, size=40):
    return [{"name": p["name"], "price": p["price"], "brand": p.get("brand")} for p in search_barbora(search_term, size=size)]


_FETCHERS = {
    "rimi": _fetch_rimi,
    "selver": _fetch_selver,
    "barbora": _fetch_barbora,
}


def fetch_all(grocery_list, selected_stores, on_progress=None):
    """
    Fetch and score products for every item/store combination.

    Args:
        grocery_list:    dict of {display_name: spec}
        selected_stores: list of store names
        on_progress:     optional callable(count, total, store, display_name)
                         called after each store/item pair is processed

    Returns:
        (all_products, warnings)
          all_products — defaultdict(list) keyed by display_name
          warnings     — list of error strings for failed fetches
    """
    all_products = defaultdict(list)
    warnings = []
    total = len(grocery_list) * len(selected_stores)
    count = 0
    for display_name, spec in grocery_list.items():
        rules = build_rules(spec)
        for store in selected_stores:
            try:
                raw = _FETCHERS[store](spec["search_term"])
            except Exception as exc:
                warnings.append(f"{store}/{display_name}: {exc}")
                raw = []
            for item in raw:
                name = item.get("name") or ""
                price = parse_price(item.get("price"))
                rel = relevance_score(name, rules)
                if rel < 0:
                    continue
                weight, volume = extract_weight_volume(name)
                product = {
                    "item": display_name,
                    "store": store,
                    "name": name,
                    "price": price,
                    "relevance": rel,
                    "weight_g": weight,
                    "volume_ml": volume,
                }
                score, explanation = compute_product_score(product, rules)
                product["score"] = score
                product["explanation"] = explanation
                all_products[display_name].append(product)
            count += 1
            if on_progress:
                on_progress(count, total, store, display_name)
    return all_products, warnings