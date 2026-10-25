"""The weekly plan newsletter (WEB-37): build an edition, let new subscribers in, and log what was sent.

Each week, with production's DATABASE_URL and the MAILERLITE_* settings in the environment:

  1. python -m scripts.weekly_plan promote
       Subscribers whose first visit to pantryrun was 7 or more days ago move from the new group to the
       weekly group: no reminders in a tester's first week (PROD-5).
  2. python -m scripts.weekly_plan build --title "Week 46" --dinners nd-1318,kana-riis,nd-831357 \\
         --featured-url https://www.rimi.ee/retseptid/... [--servings 2]
       Saves the plan, prices it at every store, prints a summary and writes the email (logs/edition-<plan>.html,
       from scripts/weekly_plan_email.html): the plan link, each dinner with its photo, recipe link and
       "Did you cook it?" links, the shopping list and the cheapest store.
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
import html
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
EMAIL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "weekly_plan_email.html")


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
    others = elsewhere(result["baskets"][1:])
    if others:
        out += ["   Elsewhere: " + others]
    if best["missing"]:
        out += ["   Not in the e-shop: " + ", ".join(best["missing"])]
    out += ["", "Prices are e-shop prices on the day this was written; the plan link shows today's."]
    return "\n".join(out)


def euro(v):
    return f"{v:.2f} €".replace(".", ",")


def elsewhere(baskets, money=lambda v: f"{v:.2f} €"):
    """The other stores' totals; a store missing items says how many, as in the app, since it looks cheaper."""
    return ", ".join(f"{SHOP.get(b['store'], b['store'])} {money(b['total_price'])}"
                     + (f" ({len(b['missing'])} missing)" if b["missing"] else "")
                     for b in baskets if b["status"] == "ok")


def _dinner_html(d, base, token):
    e = html.escape
    cooked = links(base, token, d["id"])
    sticker = ('<span style="display:inline-block; margin-left:8px; padding:2px 9px; border-radius:999px; background:#ffd84d; '
               'color:#1c1f4a; font-size:11px; font-weight:700; letter-spacing:.5px; vertical-align:middle;">FEATURED</span>'
               if d.get("featured") else "")
    photo = (f'<tr><td style="padding:0 0 12px;"><img src="{e(d["image"])}" alt="" width="560" '
             f'style="display:block; width:100%; max-width:560px; height:auto; border-radius:18px;"></td></tr>' if d.get("image") else "")
    recipe = (f'<a href="{e(d["link"])}" style="color:#d6284b; font-weight:700;">The recipe</a> · ' if d.get("link") else "")
    return f"""<tr><td style="padding:0 0 26px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      {photo}
      <tr><td style="font-size:21px; font-weight:700; line-height:1.2;" lang="et">{e(d["name"])}{sticker}</td></tr>
      <tr><td style="padding:6px 0 0; font-size:14px; color:#5b5f86;">{recipe}Did you cook it?
        <a href="{e(cooked["yes"])}" style="color:#1c1f4a; font-weight:700;">Yes</a> ·
        <a href="{e(cooked["no"])}" style="color:#1c1f4a;">Not this time</a></td></tr>
    </table>
  </td></tr>"""


def edition_html(title, token, result, base, date):
    """The edition as an email, from scripts/weekly_plan_email.html."""
    e = html.escape
    best = result["baskets"][0]
    others = elsewhere(result["baskets"][1:], euro)
    n = len(result["dinners"])
    lines = "".join(
        f'<tr><td style="padding:7px 0; border-top:1px solid rgba(28,31,74,.12);"><b>{e(l["label"])}</b><br>'
        f'<span style="color:#5b5f86; font-size:13px;">{e(l["product"])}</span></td>'
        f'<td align="right" style="padding:7px 0; border-top:1px solid rgba(28,31,74,.12); white-space:nowrap;">{euro(l["cost"])}</td></tr>'
        for l in best["lines"])
    parts = {
        "TITLE": e(title),
        "PREHEADER": e(f"{n} dinners for {result['servings']}, one shop at {SHOP.get(best['store'], best['store'])}: {euro(best['total_price'])}"),
        "SUMMARY": e(f"{n} dinners for {result['servings']}, one shop, {euro(best['total_price'])} in total."),
        "PLAN_LINK": e(links(base, token)),
        "DINNERS": "".join(_dinner_html(d, base, token) for d in result["dinners"]),
        "STORE": e(SHOP.get(best["store"], best["store"])),
        "LINES": lines,
        "TOTAL": euro(best["total_price"]),
        "ELSEWHERE": e("Elsewhere: " + others) if others else "",
        "DATE": e(date),
        "BASE": e(base),
    }
    out = open(EMAIL, encoding="utf-8").read()
    for key, value in parts.items():
        out = out.replace(f"@@{key}@@", value)
    return out


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
    base = args.base_url.rstrip("/")
    print(f"Plan saved: {token}\n")
    print(edition(args.title, token, result, base))
    if result["baskets"][0]["status"] == "ok":
        path = os.path.join("logs", f"edition-{token}.html")
        os.makedirs("logs", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(edition_html(args.title, token, result, base, datetime.now().strftime("%-d %B %Y")))
        print(f"\nThe email: {path} (paste it into MailerLite's Custom HTML editor)")
    print(f"After sending: python -m scripts.weekly_plan sent --plan {token}")


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
