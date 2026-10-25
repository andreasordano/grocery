"""The weekly plan newsletter (WEB-37): build an edition, let new subscribers in, and log what was sent.

Each week, with production's DATABASE_URL, EDITION_TOKEN and the MAILERLITE_* settings in the environment:

  1. python -m scripts.weekly_plan promote
       Subscribers whose first visit to pantryrun was 7 or more days ago move from the new group to the
       weekly group: no reminders in a tester's first week (PROD-5).
  2. python -m scripts.weekly_plan build --title "Week 46" --dinners nd-1318,kana-riis,nd-831357 \\
         --featured-url https://www.rimi.ee/retseptid/... [--servings 2]
       The live site prices the plan at every store (core/editions.py; it refuses when a store didn't answer)
       and saves it; this prints a summary and writes the email (logs/edition-<plan>.html): the plan link,
       each dinner with its photo, recipe link and "Did you cook it?" links, the shopping list and the
       cheapest store.
       --featured <id> instead of --featured-url when the featured dinner is already in pantryrun.
  3. In MailerLite: new campaign to the weekly group → Custom HTML editor → paste the file, send a test to
     yourself, then send.
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

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import mailerlite, plans  # noqa: E402

BASE_URL = "https://grocery-j3en.onrender.com"
FIRST_WEEK = timedelta(days=7)


def _postgres():
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("Set DATABASE_URL to production's (the session pooler URL).")
    import psycopg
    return psycopg.connect(url)


def build(args):
    """Ask the live site to make the edition: it prices from Frankfurt, where every store answers."""
    secret = os.environ.get("EDITION_TOKEN")
    if not secret:
        sys.exit("Set EDITION_TOKEN (the same as on Render).")
    body = {"title": args.title, "dinners": [d for d in args.dinners.split(",") if d.strip()], "featured": args.featured,
            "featured_url": args.featured_url, "servings": args.servings}
    base = args.base_url.rstrip("/")
    r = requests.post(f"{base}/editions", json=body, headers={"Authorization": f"Bearer {secret}"}, timeout=180)
    if r.status_code != 200:
        sys.exit(f"The site refused ({r.status_code}): {r.json().get('detail', r.text) if r.content else ''}")
    made = r.json()
    path = os.path.join("logs", f"edition-{made['token']}.html")
    os.makedirs("logs", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(made["html"])
    print(f"Plan saved: {made['token']}\n\n{made['text']}")
    print(f"\nThe email: {path} (paste it into MailerLite's Custom HTML editor)")
    print(f"After sending: python -m scripts.weekly_plan sent --plan {made['token']}")


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
