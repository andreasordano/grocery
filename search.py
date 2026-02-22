from api.rimi_api import search_rimi
from api.barbora_api import search_barbora
from api.selver_api import search_selver

def search_store(store, query):

    if store == "rimi":
        return search_rimi(query)

    elif store == "barbora":
        return search_barbora(query)

    elif store == "selver":
        return search_selver(query)

    else:
        raise ValueError(f"Unknown store: {store}")

def search_all_stores(query):

    all_products = []

    stores = ["rimi", "barbora", "selver"]

    for store in stores:

        try:
            products = search_store(store, query)

            for product in products:
                product["store"] = store

            all_products.extend(products)

        except Exception as e:
            print(f"Error with {store}: {e}")

    return all_products