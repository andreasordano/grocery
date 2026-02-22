# =============================================================================
# FETCHERS  (delegated to the individual API modules)
# This module defines functions to fetch product data from different stores (Rimi, Selver, Barbora) based on a search term.
# The main function, `fetch_all`, orchestrates the fetching process for all items in the grocery list and selected stores, applies relevance scoring, and extracts weight/volume information. 
# It returns a structured dictionary of products along with any warnings encountered during the fetching process.
# It runs after the initial grocery list parsing and before the scoring and optimization phases, which rely on the fetched product data
# =============================================================================

from collections import defaultdict
import os
import json
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

# Load macro labels from normalized catalog to support macro-based fallback queries
_MACRO_LABELS = set()
try:
    _CATALOG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "catalog", "normalized_catalog.json"))
    with open(_CATALOG_PATH, "r", encoding="utf-8") as _f:
        _cat = json.load(_f)
    for _rec in _cat:
        m = _rec.get("macro")
        if m:
            _MACRO_LABELS.add(m.lower())
except Exception:
    _MACRO_LABELS = set()


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
            # If no relevant candidates found, try falling back to individual keyword tokens
            if not all_products[display_name]:
                # build simple tokens from include keywords
                include_tokens = []
                for kw in rules.get("include", []):
                    if not kw:
                        continue
                    for t in re.findall(r"[\wäöüõšžÄÖÜÕŠŽ]+", kw.lower()):
                        if len(t) > 1:
                            include_tokens.append(t)

                tried = set()
                for token in include_tokens:
                    # try token query
                    if token not in tried:
                        tried.add(token)
                        try:
                            raw2 = _FETCHERS[store](token)
                        except Exception:
                            raw2 = []
                        for item in raw2:
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

                    # try macro-label queries that contain the token
                    for macro_label in list(_MACRO_LABELS):
                        if token in macro_label and macro_label not in tried:
                            tried.add(macro_label)
                            try:
                                raw3 = _FETCHERS[store](macro_label)
                            except Exception:
                                raw3 = []
                            for item in raw3:
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