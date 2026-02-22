import requests
import json


# ========================
# SELVER (Vue Storefront)
# ========================

def search_selver(query, size=10):
    url = "https://www.selver.ee/api/catalog/vue_storefront_catalog_et/product/_search"
    payload = {
        "query": {
            "query_string": {"query": query}
        },
        "size": size,
        "_source": ["name", "final_price", "price", "sku", "product_brand", "product_volume", "product_compare_unit"]
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    r = requests.post(url, json=payload, headers=headers)
    if r.status_code != 200:
        print(f"Selver error: {r.status_code}")
        return []

    products = []
    for h in r.json().get("hits", {}).get("hits", []):
        src = h["_source"]
        products.append({
            "store": "selver",
            "name": src.get("name"),
            "price": src.get("final_price") or src.get("price"),
            "sku": src.get("sku"),
            "brand": src.get("product_brand"),
            "volume": src.get("product_volume"),
            "unit": src.get("product_compare_unit"),
        })
    return products


if __name__ == "__main__":
    products = search_selver("piim")
    print(f"Found {len(products)} products\n")
    for p in products:
        print(p)
