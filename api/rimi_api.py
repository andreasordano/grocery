import requests
import json
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html",
}

def search_rimi(query, page=0):
    url = f"https://www.rimi.ee/epood/en/search?query={query}&currentPage={page}"
    r = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(r.text, "html.parser")

    products = []
    for card in soup.select("[data-product-code]"):
        name_el = card.select_one(".card__name")
        price_int = card.select_one(".price-tag span")  # integer part
        price_sup = card.select_one(".price-tag sup")   # decimal part

        name = name_el.get_text(strip=True) if name_el else None

        # price-tag contains: <span>1</span><sup>29</sup> → "1.29"
        if price_int and price_sup:
            price = float(f"{price_int.get_text(strip=True)}.{price_sup.get_text(strip=True)}")
        else:
            price = None

        gtm_raw = card.select_one("[data-gtm-eec-product]")
        gtm = json.loads(gtm_raw["data-gtm-eec-product"]) if gtm_raw else {}

        products.append({
            "store": "rimi",
            "name": name,
            "price": price,
            "code": card.get("data-product-code"),
            "brand": gtm.get("brand"),
        })

    return products


if __name__ == "__main__":
    products = search_rimi("piim")
    print(f"Found {len(products)} products\n")
    for p in products[:40]:
        print(p)