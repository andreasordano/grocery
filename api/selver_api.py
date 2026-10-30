import requests
import re


# ========================
# SELVER (Vue Storefront)
# ========================

# Characters Elasticsearch's query_string reads as syntax: "sai/leib" or "tomat (kirss" would make Selver
# answer HTTP 500 (shown as "not sold at Selver") unless they're escaped.
_RESERVED = re.compile(r'([+\-=&|><!(){}\[\]^"~*?:\\/])')


def search_selver(query, limit=40):
    """Selver's search, through its Vue Storefront catalog API: products in the shape of stores_config.PRODUCT_FIELDS."""
    url = "https://www.selver.ee/api/catalog/vue_storefront_catalog_et/product/_search"
    payload = {
        "query": {
            "query_string": {"query": _RESERVED.sub(r"\\\1", query)}
        },
        "size": limit,
        "_source": ["name", "final_price", "price", "original_price", "special_to_date", "product_group_price",
                    "sku", "product_brand", "product_volume", "category", "stock", "thumbnail",
                    "product_main_ean", "url_key"]
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    r = requests.post(url, json=payload, headers=headers, timeout=15)
    r.raise_for_status()  # e.g. 403 from Cloudflare's bot check: the store didn't answer, not "no products"
    try:
        hits = r.json()["hits"]["hits"]
    except (ValueError, KeyError, TypeError):
        raise RuntimeError("Selver search answered without a product list")

    products = []
    for h in hits:
        src = h["_source"]
        volume = (src.get("product_volume") or "").strip()
        price = src.get("final_price") or src.get("price")
        # Campaign price: original_price is the regular price. Partnerkaart price: product_group_price
        # (0 or missing without a card offer). The per-group `prices` list isn't it: most products
        # there are 5-10% off for other numbered groups that a card holder doesn't get.
        regular = src.get("original_price")
        on_sale = bool(regular and price and float(regular) > float(price) + 0.004)
        card = src.get("product_group_price")
        card = float(card) if card and price and float(card) < float(price) - 0.004 else None
        categories = src.get("category") or []
        # Virtual categories are campaigns and brands ("FB", "Soodushinnaga toidukaubad"); the first real one is the shelf.
        shelf = next((c.get("name") for c in categories if str(c.get("is_virtual")).lower() != "true" and c.get("name")), None)
        thumb = src.get("thumbnail")
        unit = volume.lower() if volume.lower() in ("kg", "l") else None
        # Loose goods: the least Selver sells (min_sale_qty, 0.7 kg of courgette) and the steps above it.
        # Packaged goods only have the default minimum of one piece, so they're left out.
        stock = src.get("stock") or {}
        min_qty = stock.get("min_sale_qty") if unit else None
        step = stock.get("qty_increments") if unit and stock.get("enable_qty_increments") else None
        products.append({
            "store": "selver",
            "name": src.get("name"),
            "price": price,
            "regular_price": float(regular) if on_sale else None,
            "card_price": card,
            "deal_until": (src.get("special_to_date") or "")[:10] or None if on_sale else None,
            "store_id": src.get("sku"),
            "ean": src.get("product_main_ean") or None,  # only Selver exposes EANs: the anchor for matching stores
            "brand": src.get("product_brand"),
            "volume": volume,
            # Loose goods have product_volume "kg"/"l" and are priced per that unit.
            "unit": unit,
            "min_qty": float(min_qty) if min_qty else None,
            "qty_step": float(step) if step else None,
            "category": list(dict.fromkeys(c.get("name") for c in categories if c.get("name"))),
            "shelf": shelf,
            "image": f"https://www.selver.ee/img/200/200/resize{thumb}" if thumb else None,
            "url": f"https://www.selver.ee/{src['url_key']}" if src.get("url_key") else None,
            "in_stock": stock.get("stock_status", 1) == 1,
        })
    return products


if __name__ == "__main__":
    products = search_selver("piim")
    print(f"Found {len(products)} products\n")
    for p in products:
        print(p)
