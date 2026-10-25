"""The weekly plan newsletter (WEB-37): build an edition, let new subscribers in, and log what was sent.

Each week, with production's DATABASE_URL and the MAILERLITE_* settings in the environment:

  1. python -m scripts.weekly_plan promote
       Subscribers whose first visit to pantryrun was 7 or more days ago move from the new group to the
       weekly group: no reminders in a tester's first week (PROD-5).
  2. python -m scripts.weekly_plan build --title "Week 46" --dinners nd-1318,kana-riis,nd-831357 \\
         --featured-url https://www.rimi.ee/retseptid/... [--servings 2]
       Saves the plan, prices it at every store and prints the edition: the plan link, each dinner with its
       photo, recipe link and "Did you cook it?" links, the shopping list and the cheapest store.
       --featured <id> instead of --featured-url when the featured dinner is already in pantryrun.
  3. In MailerLite: duplicate last week's campaign, paste the edition in, send a test to yourself, then send
     it to the weekly group.
  4. python -m scripts.weekly_plan sent --plan <token>
       Logs the edition as a reminder (table nudges) for everyone in the weekly group, so the metrics can
       tell prompted visits from unprompted ones (metrics.return_7d).

Links carry {$pantryrun_id}, MailerLite's merge tag for the subscriber's pantryrun id: the plan opens as the
same person on any device. Check it in the test email before sending.
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import catalog, mailerlite, my_dinners, plans, recipe_import  # noqa: E402

DINNER_STORES = ["selver", "rimi", "barbora"]
BASE_URL = "https://grocery-j3en.onrender.com"
PERSON = "{$" + mailerlite.ID_FIELD + "}"  # MailerLite fills in each subscriber's pantryrun id
FIRST_WEEK = timedelta(days=7)
SHOP = {"barbora": "Maxima (Barbora's prices)", "selver": "Selver", "rimi": "Rimi"}


def _postgres():
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("Set DATABASE_URL to production's (the session pooler URL).")
    import psycopg
    return psycopg.connect(url)


def featured_from_link(url, servings):
    """A store's or brand's recipe page saved as a snapshot (like a dinner sent by link): its "sh-…" id."""
    found = recipe_import.import_recipe(url)
    if not found["items"]:
        sys.exit(f"Couldn't read what to buy from {url}. Make it a dinner in the app, then use --featured <id>.")
    token = my_dinners.share(None, None, found["name"], found.get("servings") or servings, found["items"],
                             link=found["link"], image=found.get("image"))
    return "sh-" + token


def links(base, token, dinner_id=None):
    plan = f"{base}/?plan={token}&from=newsletter&u={PERSON}"
    if dinner_id is None:
        return plan
    cooked = f"{base}/cooked?plan={token}&dinner={quote(dinner_id)}&u={PERSON}"
    return {"yes": cooked + "&answer=yes", "no": cooked + "&answer=no"}


def edition(title, token, result, base):
    """The edition as plain text, block by block, to paste into MailerLite's editor."""
    best = result["baskets"][0]
    out = [f"SUBJECT: {title}: {len(result['dinners'])} dinners, one shop",
           "", f"BUTTON \"Open this week's plan\": {links(base, token)}", ""]
    for d in result["dinners"]:
        tag = "FEATURED (label it \"Featured\")" if d.get("featured") else "DINNER"
        out += [f"── {tag}: {d['name']}",
                f"   photo: {d.get('image') or '(none: use a stock photo or leave it out)'}",
                f"   recipe: {d.get('link') or '(the plan link: pantryrun shows what to buy)'}",
                f"   Did you cook it?  yes: {links(base, token, d['id'])['yes']}",
                f"                     no:  {links(base, token, d['id'])['no']}", ""]
    if best["status"] != "ok":
        out.append("!! No store could price this plan. Check the dinners before sending.")
        return "\n".join(out)
    out += [f"SHOPPING LIST at {SHOP.get(best['store'], best['store'])}, for {result['servings']} people:"]
    out += [f"   {l['label']}: {l['product']}  {l['cost']:.2f} €" for l in best["lines"]]
    out += [f"   Total: {best['total_price']:.2f} €"]
    others = [b for b in result["baskets"][1:] if b["status"] == "ok"]
    if others:
        out += ["   Elsewhere: " + ", ".join(f"{SHOP.get(b['store'], b['store'])} {b['total_price']:.2f} €" for b in others)]
    if best["missing"]:
        out += ["   Not in the e-shop: " + ", ".join(best["missing"])]
    out += ["", "Prices are e-shop prices on the day this was written; the plan link shows today's."]
    return "\n".join(out)


def build(args):
    ids = [d.strip() for d in args.dinners.split(",") if d.strip()]
    featured = args.featured or (featured_from_link(args.featured_url, args.servings) if args.featured_url else None)
    if featured and featured not in ids:
        ids.append(featured)
    if len(ids) > catalog.MAX_DINNERS:
        sys.exit(f"At most {catalog.MAX_DINNERS} dinners, the featured one included.")
    recipes = catalog.load_recipes()
    unknown = [d for d in ids if catalog.find_recipe(d, recipes) is None]
    if unknown:
        sys.exit(f"Unknown dinners: {', '.join(unknown)}")
    result = catalog.recommend(None, args.servings, [], DINNER_STORES, dinners=[{"id": d, "servings": args.servings} for d in ids])
    for d in result["dinners"]:
        d["featured"] = d["id"] == featured
    token = plans.create(args.title, ids, featured)
    print(f"Plan saved: {token}\n")
    print(edition(args.title, token, result, args.base_url.rstrip("/")))
    print(f"\nAfter sending: python -m scripts.weekly_plan sent --plan {token}")


def first_seen(conn, person_ids):
    rows = conn.execute("SELECT user_id, min(ts) FROM events WHERE user_id = ANY(%s) GROUP BY user_id",
                        (list(person_ids),)).fetchall()
    return dict(rows)


def promote(args):
    new, weekly = os.environ["MAILERLITE_GROUP_NEW"], os.environ["MAILERLITE_GROUP_WEEKLY"]
    waiting = mailerlite.group_subscribers(new)
    with _postgres() as conn:
        seen = first_seen(conn, {s["fields"].get(mailerlite.ID_FIELD) for s in waiting} - {None})
    now, moved = datetime.now(timezone.utc), 0
    for s in waiting:
        since = seen.get(s["fields"].get(mailerlite.ID_FIELD))
        if since is None:  # never used the app under that id: count from the sign-up
            since = datetime.fromisoformat(s["created_at"]).replace(tzinfo=timezone.utc)
        if now - since >= FIRST_WEEK:
            mailerlite.move(s["id"], new, weekly)
            moved += 1
    print(f"{moved} of {len(waiting)} new subscribers moved to the weekly group.")


def sent(args):
    if plans.get(args.plan) is None:
        sys.exit(f"No plan {args.plan}.")
    readers = [s["fields"].get(mailerlite.ID_FIELD) for s in mailerlite.group_subscribers(os.environ["MAILERLITE_GROUP_WEEKLY"])]
    readers = [r for r in readers if r]
    with _postgres() as conn:
        for person in readers:
            conn.execute("INSERT INTO nudges (user_id, channel, note) VALUES (%s, 'newsletter', %s)",
                         (person, f"plan {args.plan}"))
    print(f"Logged the edition as a reminder for {len(readers)} subscribers.")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="step", required=True)
    b = sub.add_parser("build", help="save a plan and print the edition")
    b.add_argument("--title", required=True)
    b.add_argument("--dinners", required=True, help="dinner ids, comma-separated (classics, nd-… dishes, sh-… dinners sent by link)")
    b.add_argument("--featured", help="the featured dinner's id")
    b.add_argument("--featured-url", help="a store's or brand's recipe page to feature")
    b.add_argument("--servings", type=int, default=2)
    b.add_argument("--base-url", default=BASE_URL)
    sub.add_parser("promote", help="move subscribers past their first week into the weekly group")
    s = sub.add_parser("sent", help="log a sent edition as a reminder for its readers")
    s.add_argument("--plan", required=True)
    args = p.parse_args(argv)
    if args.step != "build" and not mailerlite.configured():
        sys.exit("Set MAILERLITE_API_KEY, MAILERLITE_GROUP_NEW and MAILERLITE_GROUP_WEEKLY.")
    {"build": build, "promote": promote, "sent": sent}[args.step](args)


if __name__ == "__main__":
    main()
