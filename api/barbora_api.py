import requests
import json
import threading
import time


# ========================
# BARBORA
# ========================
# The JSON search API (/api/eshop/v1/search) ranks poorly (e.g. "munad" returns
# chocolate eggs). The website's search page embeds its much better results as
# `window.b_productList = [...]`, so we read that instead.

_MARKER = "window.b_productList = "

# Barbora answers parallel requests with a page that has no product list (throttling),
# so send one at a time and retry a short while later.
_CONCURRENCY = threading.Semaphore(1)
_RETRY_DELAYS = (1.0, 2.5)


def search_barbora(query, size=24):
    url = "https://barbora.ee/otsing"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html",
    }
    for delay in (0,) + _RETRY_DELAYS:
        time.sleep(delay)
        with _CONCURRENCY:
            r = requests.get(url, params={"q": query}, headers=headers, timeout=15)
        r.raise_for_status()
        start = r.text.find(_MARKER)
        if start >= 0:
            break
    else:
        # Every search page embeds the list (empty when nothing matches), so a
        # missing marker means a changed page or a bot check — surface it.
        raise RuntimeError("Barbora search page has no product list")
    items, _ = json.JSONDecoder().raw_decode(r.text[start + len(_MARKER):])

    products = []
    for item in items[:size]:
        path = item.get("category_name_full_path") or ""
        products.append({
            "store": "barbora",
            "name": (item.get("title") or "").strip(),
            "price": item.get("price"),
            "retail_price": item.get("retail_price"),
            "brand": item.get("brand_name"),
            # Sold unit ("tk" or "kg" for loose goods); comparative_unit is only the price-comparison unit.
            "unit": ((item.get("units") or [{}])[0].get("unit") or "").lower() or None,
            "unit_price": item.get("comparative_unit_price"),
            "id": item.get("id"),
            "category": [c.strip() for c in path.split("/") if c.strip()],
            "in_stock": item.get("status") == "active",
        })
    return products


if __name__ == "__main__":
    products = search_barbora("piim")
    print(f"Found {len(products)} products\n")
    for p in products:
        print(p)
