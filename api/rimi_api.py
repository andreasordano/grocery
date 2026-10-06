import requests
import json
import re
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html",
}

# Screen-reader price text, e.g. "1.39 € per pcs." or "20.99 € per kg"
_PRICE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*€\s*per\s*([^\s.]+)")
_NUMBER_RE = re.compile(r"(\d+[.,]\d+)")
# Multi-buy label, e.g. "2 and more -23%"
_MULTIBUY_RE = re.compile(r"(\d+)\s+and more\s*-\s*(\d+)\s*%")


def search_rimi(query, page=0):
    url = "https://www.rimi.ee/epood/en/search"
    r = requests.get(url, params={"query": query, "currentPage": page}, headers=HEADERS, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")

    products = []
    for card in soup.select("[data-product-code]"):
        name_el = card.select_one(".card__name")
        name = name_el.get_text(strip=True) if name_el else None

        # Shelf price per sold unit (per kg for loose items). The GTM "price"
        # field is not used: for loose items it is the price of the default
        # quantity (e.g. 0.25 kg), not the per-kg price.
        price = unit = None
        sr = card.select_one(".price-tag .sr-only")
        m = _PRICE_RE.search(sr.get_text(" ", strip=True)) if sr else None
        if m:
            price = float(m.group(1).replace(",", "."))
            unit = m.group(2)

        gtm = json.loads(card.get("data-gtm-eec-product") or "{}")

        # Discounted cards show the regular price separately ("Regular price: 1,69 €").
        regular = None
        old = card.select_one(".card__old-price, .old-price-tag")
        m = _NUMBER_RE.search(old.get_text(" ", strip=True)) if old else None
        if m and price is not None:
            value = float(m.group(1).replace(",", "."))
            regular = value if value > price + 0.004 else None

        deal = None
        label = card.select_one(".price-label")
        m = _MULTIBUY_RE.search(label.get_text(" ", strip=True)) if label else None
        if m:
            deal = f"{m.group(1)} or more: −{m.group(2)}%"

        # The card's src is a tiny blurred placeholder (q_1); ask Cloudinary for normal quality.
        img = card.select_one("img")
        image = img.get("src").replace(",q_1,", ",q_auto,") if img and img.get("src") else None

        products.append({
            "store": "rimi",
            "name": name,
            "price": price,
            "regular_price": regular,
            "deal": deal,
            "unit": unit,
            "code": card.get("data-product-code"),
            "brand": gtm.get("brand"),
            "category": [gtm["category"]] if gtm.get("category") else [],
            # Category code cut to three levels (SH-11-2-5 → SH-11-2: all yoghurts, not just
            # flavoured ones); Rimi's cards don't name the shelf.
            "shelf": "-".join(gtm["category"].split("-")[:3]) if gtm.get("category") else None,
            "image": image,
            "in_stock": price is not None,
        })

    return products


if __name__ == "__main__":
    products = search_rimi("piim")
    print(f"Found {len(products)} products\n")
    for p in products[:40]:
        print(p)
