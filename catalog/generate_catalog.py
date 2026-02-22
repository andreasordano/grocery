# This script collects product names from multiple grocery store APIs and generates a consolidated catalog in JSON format.
# It uses predefined search terms to query each store's API, collects the product names, and saves them in a JSON file for later use.
# The generated catalog can be used by other parts of the application to provide product information without needing to query the APIs in real-time.

import json
import os
import inspect
from api.rimi_api import search_rimi
from api.selver_api import search_selver
from api.barbora_api import search_barbora
from catalog.normalize_catalog import normalize_catalog

# Prefixes to crawl: a-z, digits and some common Estonian characters/prefixes.
PREFIXES = [c for c in "abcdefghijklmnopqrstuvwxyz0123456789"] + ["õ", "ä", "ö", "ü", "ri", "pa", "ka", "le"]


def collect_product_names():

    stores = [
        ("rimi", search_rimi),
        ("selver", search_selver),
        ("barbora", search_barbora),
    ]

    catalog = set()

    for prefix in PREFIXES:
        print(f"Searching prefix: {prefix}")
        for store_name, search_fn in stores:
            try:
                sig = inspect.signature(search_fn)
                params = sig.parameters
                products = []
                if 'size' in params:
                    products = search_fn(prefix, size=200) or []
                elif 'page' in params:
                    # try a few pages to collect more results
                    for pg in range(0, 3):
                        try:
                            chunk = search_fn(prefix, page=pg) or []
                        except TypeError:
                            chunk = search_fn(prefix) or []
                        if not chunk:
                            break
                        products.extend(chunk)
                else:
                    products = search_fn(prefix) or []

                for p in products:
                    name = (p.get("name") or "").lower()
                    if name:
                        catalog.add(name)
            except Exception as e:
                print(f"Error {store_name} for prefix '{prefix}': {e}")

    return sorted(list(catalog))


def generate_catalog():

    product_names = collect_product_names()

    catalog = {
        "Auto-generated": product_names
    }
    base = os.path.dirname(__file__)
    catalog_path = os.path.join(base, "catalog.json")
    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(product_names)} products -> {catalog_path}")

    # Immediately run the normalizer so a `normalized_catalog.json` is available
    try:
        normalize_catalog(input_path=catalog_path)
    except Exception as e:
        print(f"Normalization failed: {e}")
    # Run auto-group to add `macro` labels and reload DB
    try:
        from catalog import auto_group_catalog
        auto_group_catalog.run_auto_group()
    except Exception as e:
        print(f"Auto-group failed: {e}")


if __name__ == "__main__":

    generate_catalog()