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
        "_source": ["name", "final_price", "price", "original_price", "special_to_date",
                    "sku", "product_brand", "product_volume", "category", "stock"]
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    r = requests.post(url, json=payload, headers=headers, timeout=15)
    if r.status_code != 200:
        print(f"Selver error: {r.status_code}")
        return []

    products = []
    for h in r.json().get("hits", {}).get("hits", []):
        src = h["_source"]
        volume = (src.get("product_volume") or "").strip()
        price = src.get("final_price") or src.get("price")
        # Campaign price: original_price is the regular price. Selver's loyalty (Partnerkaart)
        # prices are per numbered customer group and can't be identified, so they're not used.
        regular = src.get("original_price")
        on_sale = bool(regular and price and float(regular) > float(price) + 0.004)
        products.append({
            "store": "selver",
            "name": src.get("name"),
            "price": price,
            "regular_price": float(regular) if on_sale else None,
            "deal_until": (src.get("special_to_date") or "")[:10] or None if on_sale else None,
            "sku": src.get("sku"),
            "brand": src.get("product_brand"),
            "volume": volume,
            # Loose goods have product_volume "kg"/"l" and are priced per that unit.
            "unit": volume.lower() if volume.lower() in ("kg", "l") else None,
            "category": list(dict.fromkeys(c.get("name") for c in src.get("category") or [] if c.get("name"))),
            "in_stock": (src.get("stock") or {}).get("stock_status", 1) == 1,
        })
    return products


if __name__ == "__main__":
    products = search_selver("piim")
    print(f"Found {len(products)} products\n")
    for p in products:
        print(p)
