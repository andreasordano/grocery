"""This week's deals (WEB-28), as the live site worked them out: per store, the dinners with the most of their
cost on sale, and with --unmatched the monthly review list of Selver's discounted food that no ingredient rule
catches (add a rule only where it matters; preview it with scripts/rules_preview.py).

Both come from the site, which reaches every store (Selver blocks requests from outside Estonia). The deals
are public; --unmatched needs EDITION_TOKEN, from the environment or the Keychain (see scripts/weekly_plan.py).

  python -m scripts.deals_report
  python -m scripts.deals_report --store rimi --top 20
  python -m scripts.deals_report --unmatched
"""

import argparse
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.weekly_plan import BASE_URL, WAIT, token  # noqa: E402


def get(base, path, owner=False):
    headers = {"Authorization": f"Bearer {token()}"} if owner else {}
    r = requests.get(f"{base.rstrip('/')}{path}", headers=headers, timeout=WAIT)
    if r.status_code != 200:
        sys.exit(f"The site refused {path} ({r.status_code}): {r.text[:300]}")
    return r.json()


def report(base, stores, top):
    week, shown = get(base, "/deals"), get(base, "/recipes")
    if not week["at"]:
        sys.exit("The site hasn't worked out this week's deals yet (it does a few minutes after a restart).")
    names = {d["id"]: d["name"] for d in shown["recipes"] + shown["dishes"]}
    print(f"Worked out {week['at'][:16].replace('T', ' ')} UTC. Share = how much of the dinner's cost is on sale.")
    for store, deals in week["stores"].items():
        if stores and store not in stores:
            continue
        print(f"\n=== {store.upper()} === {len(deals)} shown")
        for d in deals[:top]:
            sale = ", ".join(f"{s['label']} −{s['off']}%" for s in d["on_sale"])
            print(f"  {d['share']:4.0%}  {len(d['on_sale'])}/{d['count']}  {d['total']:6.2f} €  "
                  f"save {d['saving']:5.2f}  {names.get(d['id'], d['id'])}  [{sale}]")


def unmatched(base):
    found = get(base, "/deals/unmatched", owner=True)
    print(f"\n=== SELVER UNMATCHED === {found['total']} products, {found['on_sale']} on sale, "
          f"{found['unmatched']} discounted food products match no rule")
    for s in found["shelves"]:
        print(f"  {s['count']:4}  {s['shelf']}: {'; '.join(s['examples'])}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url", default=BASE_URL)
    p.add_argument("--store", action="append", help="store(s) to show (default: all)")
    p.add_argument("--top", type=int, default=12, help="dinners per store (the site sends at most 12)")
    p.add_argument("--unmatched", action="store_true", help="also list Selver's discounted food no rule catches")
    args = p.parse_args(argv)
    report(args.base_url, args.store, args.top)
    if args.unmatched:
        unmatched(args.base_url)


if __name__ == "__main__":
    main()
