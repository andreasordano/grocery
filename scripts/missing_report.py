"""What recipes and lists couldn't find, per store: the ingredients behind "Not in the e-shop".

Read from the basket events (each store's missing items, and which of them the store had but sold out
online). Use it to decide what to fix: a name the stores write differently goes in data/synonyms.yaml or an
ingredient rule's aliases; something a store really doesn't sell is just missing there. Needs DATABASE_URL.

  python -m scripts.missing_report               # testers, last 7 days
  python -m scripts.missing_report --days 30 --internal   # everyone, including the team
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import db  # noqa: E402

SQL = """
WITH b AS (
  SELECT e.id, bk->>'store' AS store, bk->'missing' AS missing, COALESCE(bk->'sold_out', '[]') AS sold_out
  FROM events e, jsonb_array_elements(e.data->'baskets') bk
  WHERE e.type = 'basket' AND e.ts > now() - make_interval(days => %s) AND bk->>'status' = 'ok'
    AND (%s OR NOT COALESCE((e.data->>'internal')::boolean, false))
)
SELECT store, lower(m #>> '{}') AS item, count(*) AS times,
       count(*) FILTER (WHERE sold_out @> jsonb_build_array(m)) AS sold_out,
       (SELECT count(*) FROM b b2 WHERE b2.store = b.store) AS baskets
FROM b, jsonb_array_elements(missing) m
GROUP BY store, item ORDER BY times DESC, store, item
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--internal", action="store_true", help="include the team's own baskets")
    ap.add_argument("--top", type=int, default=40)
    args = ap.parse_args()
    rows = db.query(SQL, (args.days, args.internal))
    if not rows:
        print(f"Nothing missing in the last {args.days} days" + ("" if args.internal else " (testers only; --internal for the team)."))
        return
    print(f"Missing in the last {args.days} days ({'everyone' if args.internal else 'testers only'}):\n")
    print(f"{'store':8} {'item':32} {'times':>5} {'sold out':>8} {'of baskets':>10}")
    for store, item, times, sold_out, baskets in rows[:args.top]:
        print(f"{store:8} {item[:32]:32} {times:5} {sold_out or '':>8} {baskets:10}")
    print("\nSold out = the store had it but not in stock online: nothing to fix. The rest: is it really not sold there?"
          "\nCheck with: python -m scripts.rules_preview --raw \"<item>\" --store <store>")


if __name__ == "__main__":
    main()
