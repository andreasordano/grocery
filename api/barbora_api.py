import requests
import json


# ========================
# BARBORA
# ========================

def search_barbora(query, size=24):
    url = "https://barbora.ee/api/eshop/v1/search"
    params = {"q": query, "limit": size}
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://barbora.ee",
    }
    params = {"query": query, "limit": size}
    r = requests.get(url, params=params, headers=headers)
    if r.status_code != 200:
        print(f"Barbora error: {r.status_code}")
        return []

    products = []
    for item in r.json().get("products", []):
        products.append({
            "store": "barbora",
            "name": item.get("title", "").strip(),
            "price": item.get("price"),
            "retail_price": item.get("retail_price"),
            "brand": item.get("brand_name"),
            "unit": item.get("comparative_unit"),
            "unit_price": item.get("comparative_unit_price"),
            "id": item.get("id"),
        })
    return products


if __name__ == "__main__":
    products = search_barbora("piim")
    print(f"Found {len(products)} products\n")
    for p in products:
        print(p)
