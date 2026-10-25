# =============================================================================
# STORES  (the one place that lists them)
# Everything about a store that the rest of the code needs: its name, the chain it stands for (Barbora's
# prices stand for Maxima's stores), its connector, how many requests it takes at once, and whether it
# prices dinners (it has ingredient rules in data/rules.yaml).
#
# To add a store:
#   1. api/<store>_api.py with search(query, limit) returning products in the shape below (PRODUCT_FIELDS),
#      and a saved answer in tests/fixtures for the contract test (tests/test_stores.py).
#   2. An entry in STORES below.
#   3. For dinners: its rules in data/rules.yaml (python -m scripts.rules_preview helps), then
#      prices_dinners: True, and a health-check run (python -m scripts.healthcheck).
# Nothing else lists stores: the API, the page, the newsletter and the scripts all read them from here.
# =============================================================================

import importlib

STORES = {
    "selver": {"name": "Selver", "chain": "selver", "connector": "api.selver_api.search_selver",
               "max_concurrency": 4, "prices_dinners": True},
    "rimi": {"name": "Rimi", "chain": "rimi", "connector": "api.rimi_api.search_rimi",
             "max_concurrency": 4, "prices_dinners": True},
    # Barbora is Maxima's e-shop: its prices stand for a Maxima store (WEB-25). It answers one request at a time.
    "barbora": {"name": "Barbora", "chain": "maxima", "connector": "api.barbora_api.search_barbora",
                "max_concurrency": 1, "prices_dinners": True},
}

# The chains people shop at, as the page names them ("Where do you usually shop?").
CHAINS = {"selver": "Selver", "rimi": "Rimi", "maxima": "Maxima"}

# What a connector returns for each product. store, store_id, name, price and in_stock are always there;
# the others are None when the store doesn't say.
PRODUCT_FIELDS = {
    "store": "the store's key in STORES",
    "store_id": "the store's own product id: what its cart and product page use",
    "name": "the product name as the store writes it",
    "price": "shelf price in euros (per kg or l for loose goods)",
    "in_stock": "False when the store says it's sold out",
    "regular_price": "the price before a discount, only when on sale",
    "card_price": "the loyalty-card price, when lower",
    "deal": "a multi-buy offer, as text",
    "deal_until": "the offer's last day (YYYY-MM-DD)",
    "unit": "kg or l for loose goods priced by weight, else None",
    "volume": "the pack size when the store gives it apart from the name",
    "min_qty": "loose goods: the least the store sells, in kg or l",
    "qty_step": "loose goods: the steps above the minimum",
    "category": "the store's category path (list)",
    "shelf": "the shelf a person would recognise",
    "image": "a product photo URL",
    "url": "the product's page in the e-shop",
    "ean": "barcode, when the store exposes it (Selver)",
    "brand": "brand, when the store gives it",
    "unit_price": "the store's own price per kg/l/piece, when it gives one",
}
REQUIRED_FIELDS = ("store", "store_id", "name", "price", "in_stock")


def stores():
    """Every store key."""
    return list(STORES)


def dinner_stores():
    """The stores that price dinners (they have ingredient rules)."""
    return [s for s, c in STORES.items() if c["prices_dinners"]]


def display_name(store):
    """What a person calls the store: the chain it stands for ("barbora" → "Maxima")."""
    return CHAINS.get(STORES[store]["chain"], STORES[store]["name"]) if store in STORES else store.capitalize()


def connector(store):
    """The store's search(query, limit) function."""
    if store not in STORES:
        raise ValueError(f"Unknown store: {store}")
    module, function = STORES[store]["connector"].rsplit(".", 1)
    return getattr(importlib.import_module(module), function)


def max_concurrency(store):
    """How many requests this server sends the store at once."""
    return STORES.get(store, {}).get("max_concurrency", 4)


def public():
    """What the page needs to know about the stores (GET /recipes)."""
    return {"stores": {s: {"name": c["name"], "chain": c["chain"], "shown_as": display_name(s)} for s, c in STORES.items()},
            "chains": CHAINS}
