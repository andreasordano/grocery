# =============================================================================
# WEEKLY PLAN EDITIONS  (the newsletter's content, WEB-37)
# make() prices a set of dinners at every store, saves them as a plan (core/plans.py) and returns the edition:
# a plain-text summary and the email (core/weekly_plan_email.html filled in), to paste into MailerLite.
# It runs on the server (POST /editions), because the stores answer the server's requests but may refuse
# others (Selver blocks requests from outside Estonia). It refuses to build when a store didn't answer
# (a missing store can make the email send people to the wrong one) and when even the best store lacks
# something (a plan should be buyable in one shop: swap the dinner that needs it).
# promote() and record_sent() handle the subscribers around a send (POST /editions/promote, /editions/<plan>/sent),
# also on the server, so the owner's laptop needs no database address and no MailerLite key: only EDITION_TOKEN.
# =============================================================================

import html
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from core import catalog, db, mailerlite, my_dinners, plans, recipe_import
from stores_config import STORES, dinner_stores, display_name

PERSON = "{$" + mailerlite.ID_FIELD + "}"  # MailerLite fills in each subscriber's pantryrun id


def shop(store):
    """The store as the email names it: the chain, and whose prices when it's another e-shop's
    ("Maxima (Barbora's prices)")."""
    name, eshop = display_name(store), STORES.get(store, {}).get("name", store)
    return name if name == eshop else f"{name} ({eshop}'s prices)"
EMAIL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "weekly_plan_email.html")
FIRST_WEEK = timedelta(days=7)  # no reminders in a tester's first week (PROD-5)

class EditionError(ValueError):
    """Why an edition can't be made, in words for the person running the script."""


def featured_from_link(url, servings):
    """A store's or brand's recipe page saved as a snapshot (like a dinner sent by link): its "sh-…" id."""
    try:
        found = recipe_import.import_recipe(url)
    except recipe_import.PageError as exc:
        raise EditionError(f"Couldn't read {url}: {exc}") from exc
    if not found["items"]:
        raise EditionError(f"Couldn't read what to buy from {url}. Make it a dinner in the app, then use --featured <id>.")
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
    out += [f"SHOPPING LIST at {shop(best['store'])}, for {result['servings']} people:"]
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
    return ", ".join(f"{shop(b['store'])} {money(b['total_price'])}"
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
    """The edition as an email, from core/weekly_plan_email.html."""
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
        "PREHEADER": e(f"{n} dinners for {result['servings']}, one shop at {shop(best['store'])}: {euro(best['total_price'])}"),
        "SUMMARY": e(f"{n} dinners for {result['servings']}, one shop, {euro(best['total_price'])} in total."),
        "PLAN_LINK": e(links(base, token)),
        "DINNERS": "".join(_dinner_html(d, base, token) for d in result["dinners"]),
        "STORE": e(shop(best["store"])),
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


def make(title, dinners, featured=None, featured_url=None, servings=2, base="https://grocery-j3en.onrender.com"):
    """Price the dinners, save the plan and return {token, text, html}. EditionError when it can't be done well."""
    ids = list(dict.fromkeys(d.strip() for d in dinners if d and d.strip()))
    recipes = catalog.load_recipes()
    unknown = [d for d in ids + ([featured] if featured else []) if catalog.find_recipe(d, recipes) is None]
    if unknown:
        raise EditionError(f"Unknown dinners: {', '.join(unknown)}")
    if len(ids) + bool(featured or featured_url) - (featured in ids) > catalog.MAX_DINNERS:
        raise EditionError(f"At most {catalog.MAX_DINNERS} dinners, the featured one included.")
    if featured_url and not featured:
        featured = featured_from_link(featured_url, servings)
    if featured and featured not in ids:
        ids.append(featured)
    result = catalog.recommend(None, servings, [], dinner_stores(), dinners=[{"id": d, "servings": servings} for d in ids])
    silent = [b["store"] for b in result["baskets"] if b["status"] == "no_answer"]
    if silent:
        raise EditionError(f"{', '.join(shop(s) for s in silent)} didn't answer, so the cheapest store can't be "
                           "trusted. Try again in a few minutes.")
    if not result["store"]:
        raise EditionError("No store could price this plan. Check the dinners.")
    missing = result["baskets"][0]["missing"]
    if missing:
        raise EditionError(f"No store has everything: even {shop(result['store'])} lacks "
                           f"{', '.join(missing)}. Swap the dinner that needs it.")
    for d in result["dinners"]:
        d["featured"] = d["id"] == featured
    token = plans.create(title, ids, featured)
    base = base.rstrip("/")
    return {"token": token, "text": edition(title, token, result, base),
            "html": edition_html(title, token, result, base, datetime.now().strftime("%-d %B %Y"))}


# ── around a send: who gets it, and recording that they did ─────────────────

def first_seen(person_ids):
    """{person id: their first event}, for the ids that have any."""
    if not person_ids:
        return {}
    return dict(db.query("SELECT user_id, min(ts) FROM events WHERE user_id = ANY(%s) GROUP BY user_id", (list(person_ids),)))


def _groups():
    if not mailerlite.configured():
        raise EditionError("MailerLite isn't set up on the server (MAILERLITE_* settings).")
    return os.environ["MAILERLITE_GROUP_NEW"], os.environ["MAILERLITE_GROUP_WEEKLY"]


def promote(now=None):
    """Move subscribers past their first week with pantryrun from the new group to the weekly one.
    Someone who never used the app under their id counts from the day they signed up."""
    new, weekly = _groups()
    waiting = mailerlite.group_subscribers(new)
    seen = first_seen({s["fields"].get(mailerlite.ID_FIELD) for s in waiting} - {None})
    now, moved = now or datetime.now(timezone.utc), 0
    for s in waiting:
        since = seen.get(s["fields"].get(mailerlite.ID_FIELD)) or datetime.fromisoformat(s["created_at"])
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        if now - since >= FIRST_WEEK:
            mailerlite.move(s["id"], new, weekly)
            moved += 1
    return {"moved": moved, "waiting": len(waiting)}


def record_sent(token):
    """Log a sent edition as a reminder (nudges) for everyone in the weekly group."""
    if plans.get(token) is None:
        raise EditionError(f"No plan {token}.")
    _, weekly = _groups()
    readers = [r for r in (s["fields"].get(mailerlite.ID_FIELD) for s in mailerlite.group_subscribers(weekly)) if r]
    now = datetime.now(timezone.utc)
    with db.connection() as conn, conn.cursor() as cur:
        cur.executemany("INSERT INTO nudges (ts, user_id, channel, note) VALUES (%s, %s, 'newsletter', %s)",
                        [(now, person, f"plan {token}") for person in readers])
    return {"logged": len(readers)}
