# This script collects product names from multiple grocery store APIs and generates a consolidated catalog in JSON format.
# It uses predefined search terms to query each store's API, collects the product names, and saves them in a JSON file for later use.
# The generated catalog can be used by other parts of the application to provide product information without needing to query the APIs in real-time.

import json
from groceries.api.rimi_api import search_rimi
from groceries.api.selver_api import search_selver
from groceries.api.barbora_api import search_barbora


SEARCH_TERMS = [
    "piim",
    "leib",
    "sai",
    "juust",
    "kana",
    "hakkliha",
    "jogurt",
    "kohv",
    "tee",
    "või",
    "õun",
    "banaan",
    "kartul",
    "riis",
]


def collect_product_names():

    stores = [
        ("rimi", search_rimi),
        ("selver", search_selver),
        ("barbora", search_barbora),
    ]

    catalog = set()

    for term in SEARCH_TERMS:

        print(f"Searching: {term}")

        for store_name, search_fn in stores:

            try:

                products = search_fn(term)

                for p in products:

                    name = p["name"].lower()

                    catalog.add(name)

            except Exception as e:

                print(f"Error {store_name}: {e}")

    return sorted(list(catalog))


def generate_catalog():

    product_names = collect_product_names()

    catalog = {
        "Auto-generated": product_names
    }

    with open("groceries/catalog/catalog.json", "w") as f:

        json.dump(catalog, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(product_names)} products")


if __name__ == "__main__":

    generate_catalog()