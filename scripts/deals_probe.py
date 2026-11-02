"""Probe: do this week's discounts make dinners? (PROD-11, WEB-28)

For each store, searches every dish ingredient the way the app does: rule ingredients through
data/rules.yaml, free-text ones by their word, accepting a product only when the word is its
head noun ("Brokoli, kg", not "Brokolisupp"). Keeps the products on discount (regular price
or loyalty-card price below the shelf price), then counts how many dishes get a discounted
ingredient and a discounted protein, and lists the best dishes.

--unmatched also pages Selver's whole catalogue (about 12,000 products) and lists the
discounted food that no rule catches, by shelf: the monthly review list for new rules.
Rimi and Barbora can't be paged that way.

  python -m scripts.deals_probe                       # all stores
  python -m scripts.deals_probe --store rimi --top 20
  python -m scripts.deals_probe --store selver --unmatched
"""

import argparse
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import catalog, deals  # noqa: E402
from core.fetch import _cached_fetch  # noqa: E402
from core.scoring import fold  # noqa: E402
from stores_config import dinner_stores  # noqa: E402

STORES = dinner_stores()  # the stores with ingredient rules (stores_config.py)
PROTEIN_RULES = {"hakkliha", "broileri_koivad", "kanafilee", "sealiha", "lohefilee", "keeduvorst"}
PROTEIN_WORDS = ("veise", "sea", "kana", "broiler", "kala", "forell", "lõhe", "tursk", "heik", "räim",
                 "kilu", "sink", "peekon", "vorst", "viiner", "kalkun", "part", "krevet", "tuunikala",
                 "tofu", "hakkliha", "maks")


def is_discounted(p):
    """The adapters set regular_price only above the shelf price, card_price only below it."""
    return bool(p.get("regular_price") or p.get("card_price"))


def head(name):
    return fold(re.split(r"[ ,]", (name or "").strip())[0])


def head_matches(name, word):
    """The word names the product: its first word, allowing a short case ending."""
    h, w = head(name), fold(word)
    return h == w or (h.startswith(w) and len(h) - len(w) <= 3)


def discounted_rule_products(rules, key, store):
    found = []
    for rule in catalog.rule_chain(rules, key, store):
        found += [p for p in catalog.find_products(rule, store) if is_discounted(p)]
    return found


def discounted_text_products(word, store):
    try:
        results = _cached_fetch(store, word)
    except Exception as exc:
        print(f"  {store}/{word}: {exc}", file=sys.stderr)
        return []
    return [p for p in results if p.get("in_stock") is not False and is_discounted(p)
            and head_matches(p.get("name"), word)]


def is_protein(ing):
    if ing.get("item"):
        return ing["item"] in PROTEIN_RULES
    return any(fold(ing["text"]).startswith(fold(w)) for w in PROTEIN_WORDS)


def probe(store, dishes, rules, top):
    keys = sorted({i["item"] for d in dishes for i in d["ingredients"] if i.get("item")})
    words = sorted({i["text"] for d in dishes for i in d["ingredients"] if i.get("text")})
    by_item = {k: discounted_rule_products(rules, k, store) for k in keys}
    by_text = {}
    for n, w in enumerate(words, 1):
        by_text[w] = discounted_text_products(w, store)
        print(f"  {store}: {n}/{len(words)} free-text words", end="\r", file=sys.stderr)
    print(file=sys.stderr)

    def hits(ing):
        return by_item.get(ing["item"]) if ing.get("item") else by_text.get(ing["text"])

    scored = []
    for d in dishes:
        found = [(i, hits(i)) for i in d["ingredients"] if hits(i)]
        protein = any(is_protein(i) for i, _ in found)
        scored.append((len(found), protein, d, found))

    n = len(scored)
    print(f"\n=== {store.upper()} ===")
    print(f"Rule ingredients with a discounted product: {sum(bool(v) for v in by_item.values())} of {len(keys)}"
          f"  (none: {', '.join(k for k, v in by_item.items() if not v) or '-'})")
    print(f"Free-text words with a discounted product: {sum(bool(v) for v in by_text.values())} of {len(words)}")
    print(f"Dishes ({n}): ≥1 discounted ingredient {sum(s[0] >= 1 for s in scored)}, ≥2 {sum(s[0] >= 2 for s in scored)}, "
          f"≥3 {sum(s[0] >= 3 for s in scored)}; discounted protein {sum(s[1] for s in scored)}, "
          f"protein + ≥2 {sum(s[1] and s[0] >= 2 for s in scored)}")
    proteins = Counter()
    for _, _, _, found in scored:
        for i, ps in found:
            if is_protein(i):
                proteins[i.get("item") or i["text"]] += 1
    print(f"Discounted proteins (dishes using them): {', '.join(f'{k} {v}' for k, v in proteins.most_common()) or '-'}")
    print(f"Top {top} (★ = discounted protein; then most discounted ingredients):")
    for count, protein, d, found in sorted(scored, key=lambda s: (-s[1], -s[0]))[:top]:
        items = ", ".join(f"{i.get('item') or i['text']}" for i, _ in found)
        print(f"  {count}/{len(d['ingredients'])} {'★' if protein else ' '} {d['name']}  [{items}]")


def selver_unmatched(rules):
    """Discounted Selver food that no rule accepts, by shelf (core/deals.py; the site's /deals/unmatched too)."""
    found = deals.unmatched_food(rules)
    print(f"\n=== SELVER UNMATCHED === {found['total']} products, {found['on_sale']} on sale, "
          f"{found['unmatched']} discounted food products match no rule")
    for s in found["shelves"]:
        print(f"  {s['count']:4}  {s['shelf']}: {'; '.join(s['examples'])}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", choices=STORES, action="append", help="store(s) to probe (default: all)")
    ap.add_argument("--top", type=int, default=10, help="dishes to list per store")
    ap.add_argument("--unmatched", action="store_true", help="also list Selver's discounted food no rule catches")
    args = ap.parse_args()

    rules = catalog.load_rules()
    dishes = [d for d in catalog.load_dishes()["dishes"] + catalog.load_recipes()["recipes"] if d.get("ingredients")]
    for store in args.store or STORES:
        probe(store, dishes, rules, args.top)
    if args.unmatched:
        selver_unmatched(rules)


if __name__ == "__main__":
    main()
