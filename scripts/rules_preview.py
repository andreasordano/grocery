"""Preview what the ingredient rules pick, to write or check data/rules.yaml.

Examples:
  python -m scripts.rules_preview                    # every ingredient, every store
  python -m scripts.rules_preview kanafilee munad    # selected ingredients
  python -m scripts.rules_preview kanafilee --all    # also show rejected products and why
  python -m scripts.rules_preview --raw "hapukapsas" --store selver   # raw search with categories
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import catalog  # noqa: E402

STORES = ["selver", "rimi", "barbora"]


def typical_need(recipes, key):
    amounts = [i["amount"] for r in recipes["recipes"] for i in r["ingredients"] if i["item"] == key]
    return max(amounts) if amounts else 1


def reject_reason(product, rule):
    name = (product.get("name") or "").lower()
    if product.get("in_stock") is False:
        return "out of stock"
    hit = [x for x in rule.get("exclude", []) if x.lower() in name]
    if hit:
        return f"exclude {hit[0]!r}"
    if rule.get("require") and not any(x.lower() in name for x in rule["require"]):
        return "require"
    return "category"


def preview(key, stores, show_all, recipes, rules):
    spec = recipes["ingredients"][key]
    need = typical_need(recipes, key)
    print(f"\n=== {key} — {spec['name']} (need {need} {spec['unit']})")
    for store in stores:
        chain = catalog.rule_chain(rules, key, store)
        if not chain:
            print(f"  {store:7} NO RULE")
            continue
        best = catalog.best_offer(key, need, store, recipes, rules)
        sub = "  [SUBSTITUTE]" if best and best["substitute"] else ""
        print(f"  {store:7} → {best['product'] + '  ' + format(best['cost'], '.2f') + ' €  (' + best['how'] + ')' + sub if best else 'NOTHING FOUND'}")
        for level, rule in enumerate(chain):
            if level:
                print(f"    fallback #{level}: {catalog._queries(rule)}")
            show_rule(rule, store, need, spec, show_all)


def show_rule(rule, store, need, spec, show_all):
    accepted = catalog.find_products(rule, store)
    for p in accepted:
        priced = catalog.cost_for(p, need, spec["unit"], spec.get("piece_g"))
        cost = f"{priced[0]:6.2f} €" if priced else "  size?"
        print(f"      ok  {cost}  {p['name'][:60]}  [{', '.join(p.get('category') or [])[:40]}]")
    if show_all:
        seen = {p["name"] for p in accepted}
        for q in catalog._queries(rule):
            for p in catalog._safe_fetch(store, q):
                if p["name"] in seen:
                    continue
                seen.add(p["name"])
                print(f"      --  {reject_reason(p, rule):16} {p['name'][:50]}  [{', '.join(p.get('category') or [])[:40]}]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ingredients", nargs="*")
    ap.add_argument("--store", choices=STORES)
    ap.add_argument("--all", action="store_true", help="also list rejected products")
    ap.add_argument("--raw", help="raw search query (shows categories, ignores rules)")
    args = ap.parse_args()
    stores = [args.store] if args.store else STORES

    if args.raw:
        for store in stores:
            print(f"\n=== raw {args.raw!r} @ {store}")
            for p in catalog._safe_fetch(store, args.raw):
                print(f"  {str(p.get('price')):>6}  {str(p.get('unit') or ''):4} {p['name'][:55]:55}  {p.get('category')}")
        return

    recipes, rules = catalog.load_recipes(), catalog.load_rules()
    keys = args.ingredients or list(recipes["ingredients"])
    for key in keys:
        preview(key, stores, args.all, recipes, rules)


if __name__ == "__main__":
    main()
