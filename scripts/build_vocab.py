"""Build web/vocab.json: product words people can pick while typing a shopping list.

Reads every product name in Selver's e-shop (about 12,000; its catalog API can be paged)
and keeps the words that name products: "maapähklikreem", "maapähklivõie", "õun".
Brands, sizes, adjectives and "with X" forms are dropped. Each word comes with how many
products use it and the shelf most of them sit on, which the app shows as a hint.

Re-run every month or two; an outdated list does no harm.

  python -m scripts.build_vocab
"""

import json
import os
import re
import sys
from collections import Counter, defaultdict

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import catalog  # noqa: E402
from core.scoring import _WORD_RE  # noqa: E402

URL = "https://www.selver.ee/api/catalog/vue_storefront_catalog_et/product/_search"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "vocab.json")
MIN_PRODUCTS = 2
MIN_SHELF_SHARE = 0.4  # show a shelf hint only when it is where most of the word's products are
# Case endings that turn a word into "for/from/in X": kanale, piimast. Dropped when the bare word exists.
_CASE_ENDINGS = ("le", "lt", "st", "ks", "sse", "s", "l")

# Words that describe rather than name a product. Endings catch most adjectives and participles
# (jahvatatud, kreemjas, kodune, maitseline); the list catches the rest.
_DESCRIBING_ENDINGS = ("tud", "dud", "line", "lised", "jas", "ne", "sed", "lik")
_DESCRIBING = {"mahe", "eesti", "värske", "suur", "väike", "uus", "öko", "light", "klassika",
               "klassikaline", "originaal", "pakk", "pakend", "kott", "karp", "purk", "kile", "tükki",
               "erinevad", "sordid", "kg", "tk", "portsjonit", "jaoks", "ilma", "lahtine", "rasvata"}
_VOWELS = "aeiouõäöü"


def fetch_catalog():
    """(name, shelf) for every product, paged by id."""
    out, after = [], None
    while True:
        body = {"query": {"match_all": {}}, "size": 1000, "sort": [{"_id": "asc"}],
                "_source": ["name", "category"]}
        if after:
            body["search_after"] = after
        r = requests.post(URL, json=body, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        r.raise_for_status()
        hits = r.json()["hits"]["hits"]
        if not hits:
            return out
        for h in hits:
            src = h["_source"]
            shelf = next((c.get("name") for c in src.get("category") or []
                          if str(c.get("is_virtual")).lower() != "true" and c.get("name")), None)
            if src.get("name"):
                out.append((src["name"], shelf))
        after = hits[-1]["sort"]
        print(f"  {len(out)} products", file=sys.stderr)


def product_words(name):
    """Words that may name the product, from the part before the brand ("Name, BRAND, size")."""
    title = name.split(",")[0]
    has_lower = any(c.islower() for c in title)
    words = []
    for group in _WORD_RE.findall(title):
        if has_lower and group.isupper():
            continue  # brand
        w = group.split("-")[-1].lower()  # "mango-banaani" → banaani; "maapähkli-" → ""
        if len(w) < 3 or w in _DESCRIBING or w.endswith(_DESCRIBING_ENDINGS):
            continue
        if w.endswith(("ga", "ta")) and w[-3] in _VOWELS:
            continue  # "with/without X": võiga, suhkruta
        words.append(w)
    return words


def _base(word, counts):
    """The bare word another form belongs to: banaani/õuna ("of X") → banaan/õun, kanale → kana."""
    if word[-1] in _VOWELS and len(word) > 3 and counts.get(word[:-1]):
        return word[:-1]
    for end in _CASE_ENDINGS:
        stem = word[:-len(end)]
        if word.endswith(end) and len(stem) >= 3 and counts.get(stem):
            return stem
    return word


def build(products):
    counts, shelves = Counter(), defaultdict(Counter)
    for name, shelf in products:
        for w in set(product_words(name)):
            counts[w] += 1
            if shelf:
                shelves[w][shelf] += 1

    # Fold "of X" and case forms into the bare word, so "banaan" collects banaani's products.
    for w in sorted(counts, key=len, reverse=True):
        base = _base(w, counts)
        if base != w:
            counts[base] += counts.pop(w)
            shelves[base].update(shelves.pop(w, Counter()))

    def hint(w):
        if not shelves[w]:
            return ""
        shelf, n = shelves[w].most_common(1)[0]
        return shelf if n >= MIN_SHELF_SHARE * sum(shelves[w].values()) else ""

    vocab = {w: [w, n, hint(w)] for w, n in counts.items() if n >= MIN_PRODUCTS}

    # Words with an ingredient rule always come first: they get the hand-checked match.
    # No shelf hint for them: Selver's word use can mislead ("lõhe" is mostly cat food).
    recipes = catalog.load_recipes()
    for spec in recipes["ingredients"].values():
        for alias in spec.get("aliases", []):
            a = alias.lower()
            vocab[a] = [a, 1000 + counts.get(a, 0), ""]
    return sorted(vocab.values(), key=lambda v: (-v[1], v[0]))


def main():
    products = fetch_catalog()
    vocab = build(products)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(vocab, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(vocab)} words from {len(products)} products → {OUT} ({os.path.getsize(OUT) // 1024} KB)")


if __name__ == "__main__":
    main()
