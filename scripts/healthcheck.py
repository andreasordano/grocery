"""Daily health check: are the store integrations and ingredient rules still working?

Prints a Markdown report and exits 1 when something needs attention:
  - a store adapter returns nothing for a basic query (site changed / blocked)
  - an ingredient rule finds no product (product renamed, category moved, ...)
  - a recipe total for 2 people is outside a sane range (price parsing broke)

  python -m scripts.healthcheck
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import catalog  # noqa: E402
from stores_config import get_store_names  # noqa: E402

CANARY_QUERY = "piim"
DINNER_STORES = ["selver", "rimi", "barbora"]
SANE_TOTAL = (1.0, 40.0)  # € for one recipe, 2 people


def main():
    problems, notes = [], []

    for store in get_store_names():
        try:
            n = len(catalog._cached_fetch(store, CANARY_QUERY))
        except Exception as exc:
            n, err = 0, f" ({exc})"
        else:
            err = ""
        if n == 0:
            problems.append(f"**{store}** adapter returned no products for `{CANARY_QUERY}`{err}")

    recipes, rules = catalog.load_recipes(), catalog.load_rules()
    for key, per_store in rules.items():
        for store, rule in per_store.items():
            chain = catalog.rule_chain(rules, key, store)
            level = next((i for i, r in enumerate(chain) if catalog.find_products(r, store)), None)
            if level is None:
                msg = f"`{key}` @ **{store}**: no product matches the rule" + (" or its fallbacks" if len(chain) > 1 else "")
                (notes if rule.get("expect_missing") else problems).append(msg)
            elif level > 0:
                notes.append(f"`{key}` @ {store}: using fallback #{level} ({catalog._queries(chain[level])[0]})")

    for recipe in recipes["recipes"]:
        res = catalog.recommend_dinner(recipe["id"], 2, DINNER_STORES)
        for b in res["baskets"]:
            if b["lines"] and not SANE_TOTAL[0] <= b["total_price"] <= SANE_TOTAL[1]:
                problems.append(f"`{recipe['id']}` @ **{b['store']}**: total {b['total_price']:.2f} € looks wrong")
            notes.append(f"`{recipe['id']}` @ {b['store']}: {b['total_price']:.2f} €"
                         + (f" (missing: {', '.join(b['missing'])})" if b["missing"] else ""))

    print("## pantryrun health check\n")
    if problems:
        print("### Needs attention\n")
        print("\n".join(f"- {p}" for p in problems))
        print("\nFix with `python -m scripts.rules_preview <ingredient> --all` and edit `data/rules.yaml`.\n")
    else:
        print("All store integrations and rules OK.\n")
    print("<details><summary>Details</summary>\n")
    print("\n".join(f"- {n}" for n in notes))
    print("\n</details>")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
