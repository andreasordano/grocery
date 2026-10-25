import requests
import json
import time


# ========================
# BARBORA
# ========================
# The search page (a Remix app since Oct 2026) embeds its results in `window.__remixContext`:
# the search route's data holds the products ("inventories"), and the main layout's data holds
# the category tree. Products only carry a category id, so the tree turns it into the named path
# ("Piimatooted ja munad / Piimad / Piimad") that data/rules.yaml and the shelf vote use.

_MARKER = "window.__remixContext = "

# Barbora answers parallel requests with a page that has no product list (throttling): core/fetch.py sends it
# one request at a time (max_concurrency in stores_config), and a page without the list is retried a little later.
_RETRY_DELAYS = (1.0, 2.5)


def search_barbora(query, limit=40):
    """Barbora's search page, from the product list it embeds: products in the shape of stores_config.PRODUCT_FIELDS."""
    url = "https://barbora.ee/search"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html",
    }
    for delay in (0,) + _RETRY_DELAYS:
        time.sleep(delay)
        r = requests.get(url, params={"q": query}, headers=headers, timeout=15)
        r.raise_for_status()
        found = _page_data(r.text)
        if found:
            break
    else:
        # Every search page embeds the list (empty when nothing matches), so a
        # missing one means a changed page or a bot check — surface it.
        raise RuntimeError("Barbora search page has no product list")
    items, paths = found

    products = []
    for item in items[:limit]:
        path = paths.get(item.get("categoryShortId")) or []
        price, regular, card, deal = _prices(item)
        promo = item.get("promotion") or {}
        # Sold unit: "units" for packs, "kg" for loose goods, which come in trays: "min" is the
        # least you can order (0.5 kg) and "step" the steps above it.
        sold = item.get("unit") or {}
        unit = {"units": "tk"}.get(sold.get("type"), sold.get("type") or None)
        products.append({
            "store": "barbora",
            "name": (item.get("title") or "").strip(),
            "price": price,
            "regular_price": regular,
            "card_price": card,
            "deal": deal,
            "deal_until": (promo.get("validTo") or "")[:10] or None if (regular or card) else None,
            "brand": item.get("brand"),
            "unit": unit,
            "min_qty": sold.get("min") if unit in ("kg", "l") else None,
            "qty_step": sold.get("step") if unit in ("kg", "l") else None,
            "unit_price": (item.get("comparativeUnit") or {}).get("price"),
            "store_id": item.get("id"),
            "category": path,
            "shelf": path[-1] if path else None,
            "image": item.get("image"),
            "url": f"https://barbora.ee/p/{item['url']}" if item.get("url") else None,
            "in_stock": item.get("status") == "active",
        })
    return products


def _page_data(html):
    """(products, {category id: [names from the top]}) from a search page, or None without a product list."""
    start = html.find(_MARKER)
    if start < 0:
        return None
    try:
        ctx, _ = json.JSONDecoder().raw_decode(html[start + len(_MARKER):])
        routes = ctx["state"]["loaderData"]
    except (ValueError, KeyError, TypeError):
        return None
    items = tree = None
    for route in routes.values():
        for q in ((route or {}).get("dehydratedState") or {}).get("queries") or []:
            data = (q.get("state") or {}).get("data")
            if isinstance(data, dict) and isinstance(data.get("inventories"), list):
                items = data["inventories"]
            elif isinstance(data, dict) and isinstance(data.get("categories"), list):
                tree = data["categories"]
    if items is None:
        return None
    paths = {}

    def walk(nodes, trail):
        for n in nodes:
            name = n.get("name") or next((x.get("name") for x in n.get("names") or [] if x.get("language") == "et"), "")
            paths[n.get("shortId")] = trail + [name]
            walk(n.get("children") or [], trail + [name])

    walk(tree or [], [])
    return items, paths


def _prices(item):
    """(public price, regular price if discounted, loyalty-card price, multi-buy note).

    For card-only offers (loyaltyCardRequired) Barbora's `price` is already the card price,
    so the public price is the old price. Multi-buy offers only apply from minQuantity,
    so a single item costs the old price.
    """
    price = item.get("price")
    promo = item.get("promotion") or {}
    old = promo.get("oldPrice")
    if not promo or not old or not price or old <= price:
        return price, None, None, None
    if promo.get("loyaltyCardRequired"):
        return old, None, price, None
    if (promo.get("minQuantity") or 1) > 1:
        return old, None, None, f"{promo['minQuantity']} or more: {price:.2f} € each"
    return price, old, None, None


if __name__ == "__main__":
    products = search_barbora("piim")
    print(f"Found {len(products)} products\n")
    for p in products:
        print(p)
