"""The weekly plan newsletter (WEB-37): plans, sign-up, "Did you cook it?", MailerLite calls and the weekly script."""

import json
import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from conftest import rows
from core import editions, events, mailerlite, my_dinners, plans
from scripts import weekly_plan


@pytest.fixture
def db(pg, monkeypatch):
    """The test database, and MailerLite not set up."""
    for key in ("MAILERLITE_API_KEY", "MAILERLITE_GROUP_NEW", "MAILERLITE_GROUP_WEEKLY"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def api(db):
    from api import service
    return service


def status(call):
    """The HTTP status an endpoint answers with when it refuses."""
    try:
        call()
    except HTTPException as exc:
        return exc.status_code
    return 200


@pytest.fixture
def mailer(monkeypatch):
    """MailerLite configured, with its HTTP calls recorded instead of sent."""
    monkeypatch.setenv("MAILERLITE_API_KEY", "key")
    monkeypatch.setenv("MAILERLITE_GROUP_NEW", "g-new")
    monkeypatch.setenv("MAILERLITE_GROUP_WEEKLY", "g-weekly")
    calls = []

    class Resp:
        status_code, content, text = 200, b"{}", "{}"
        def json(self):
            return {}

    monkeypatch.setattr(mailerlite.requests, "request", lambda method, url, **kw: calls.append((method, url, kw)) or Resp())
    return calls


def logged(db, type_):
    return [(u, json.loads(d)) for u, d in
            rows("SELECT user_id, data::text FROM events WHERE type = %s ORDER BY id", (type_,))]


# ── plans ────────────────────────────────────────────────────────────────────

def test_plan_keeps_its_dinners_in_order_and_the_featured_one(db):
    token = plans.create("Week 46", ["kanasupp", "nd-1318", "kanasupp"], featured="nd-1318")
    assert plans.get(token) == {"token": token, "title": "Week 46", "dinners": ["kanasupp", "nd-1318"], "featured": "nd-1318"}
    assert plans.get("nope") is None
    with pytest.raises(ValueError):
        plans.create("x", ["kanasupp"], featured="nd-1")


def test_plan_link_returns_its_dinners_with_sent_ones_whole(api, db):
    sh = "sh-" + my_dinners.share(None, None, "Rimi kõrvitsasupp", 4, ["kõrvits 1kg", "koor"], link="https://www.rimi.ee/r/1")
    token = plans.create("Week 46", ["kanasupp", sh, "gone-dinner"], featured=sh)
    body = api.open_plan(token, user_id="mari", came_from="newsletter")
    assert body["title"] == "Week 46"
    assert [d["id"] for d in body["dinners"]] == ["kanasupp", sh]  # a dinner that no longer exists is left out
    assert body["dinners"][0] == {"id": "kanasupp", "featured": False}
    assert body["dinners"][1]["name"] == "Rimi kõrvitsasupp" and body["dinners"][1]["featured"] is True
    assert logged(db, "plan_opened") == [("mari", {"plan": token, "from": "newsletter", "country": "EE",
                                                   "app_version": events.APP_VERSION, "internal": False})]
    assert status(lambda: api.open_plan("nope")) == 404


def test_cooked_link_logs_the_answer_and_says_thanks(api, db):
    r = api.cooked(plan="abc", dinner="kanasupp", answer="yes", u="mari")
    assert r.status_code == 303 and r.headers["location"] == "/thanks.html"
    api.cooked(plan="abc", dinner="kanasupp", answer="maybe", u="mari")
    assert [(u, d["answer"]) for u, d in logged(db, "cooked")] == [("mari", "yes")]


# ── sign-up ──────────────────────────────────────────────────────────────────

def signup(api, **kw):
    return api.newsletter_signup(api.NewsletterRequest(**{"email": "mari@example.ee", "consent": True, "user_id": "mari", **kw}))


def test_signup_checks_the_address_and_the_consent(api):
    assert status(lambda: signup(api, email="not an email")) == 400
    assert status(lambda: signup(api, consent=False)) == 400
    assert status(lambda: signup(api)) == 503  # MailerLite isn't set up


def test_signup_goes_to_mailerlite_unconfirmed_and_the_address_isnt_logged(api, db, mailer):
    assert signup(api, email=" mari@example.ee ", user_id="u-1", name="Mari", where="receipt") == {"ok": True}
    method, url, kw = mailer[0]
    assert (method, url) == ("POST", "https://connect.mailerlite.com/api/subscribers")
    assert kw["json"] == {"email": "mari@example.ee", "fields": {"pantryrun_id": "u-1", "name": "Mari"},
                          "status": "unconfirmed", "groups": ["g-new"]}
    assert kw["headers"]["Authorization"] == "Bearer key"
    [(user, data)] = logged(db, "newsletter_signup")
    assert user == "u-1" and data["ok"] is True and data["where"] == "receipt"
    assert "example.ee" not in rows("SELECT string_agg(data::text, ',') FROM events")[0][0]


def test_signup_says_so_when_mailerlite_fails(api, db, mailer, monkeypatch):
    monkeypatch.setattr(mailerlite, "_call", lambda *a, **kw: (_ for _ in ()).throw(mailerlite.MailerLiteError("500")))
    assert status(lambda: signup(api, user_id="u-1")) == 502
    assert [d["ok"] for _, d in logged(db, "newsletter_signup")] == [False]


def test_group_subscribers_follows_the_cursor(monkeypatch, mailer):
    pages = iter([{"data": [{"id": "1"}], "meta": {"next_cursor": "c2"}}, {"data": [{"id": "2"}], "meta": {"next_cursor": None}}])
    seen = []
    monkeypatch.setattr(mailerlite, "_call", lambda method, path, **kw: seen.append(kw["params"]) or next(pages))
    assert [s["id"] for s in mailerlite.group_subscribers("g-new")] == ["1", "2"]
    assert seen[0]["filter[status]"] == "active" and "cursor" not in seen[0] and seen[1]["cursor"] == "c2"


# ── the weekly script ────────────────────────────────────────────────────────

def test_promote_lets_in_only_people_past_their_first_week(db, mailer, monkeypatch):
    now = datetime.now(timezone.utc)
    events.log_event("visit", {}, user_id="old")
    events.log_event("visit", {}, user_id="new")
    rows("UPDATE events SET ts = %s WHERE user_id = 'old' RETURNING id", (now - timedelta(days=8),))
    waiting = [{"id": "s1", "created_at": "2026-01-01 10:00:00", "fields": {"pantryrun_id": "old"}},
               {"id": "s2", "created_at": "2026-01-01 10:00:00", "fields": {"pantryrun_id": "new"}},  # visited 0 days ago
               {"id": "s3", "created_at": (now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S"), "fields": {}},
               {"id": "s4", "created_at": (now - timedelta(days=9)).strftime("%Y-%m-%d %H:%M:%S"), "fields": {"pantryrun_id": "never-came"}}]
    moved = []
    monkeypatch.setattr(mailerlite, "group_subscribers", lambda g: waiting)
    monkeypatch.setattr(mailerlite, "move", lambda sid, a, b: moved.append((sid, a, b)))
    assert editions.promote() == {"moved": 2, "waiting": 4}
    assert moved == [("s1", "g-new", "g-weekly"), ("s4", "g-new", "g-weekly")]


def test_record_sent_logs_a_reminder_for_each_reader(db, mailer, monkeypatch):
    token = plans.create("Week 46", ["kanasupp"])
    monkeypatch.setattr(mailerlite, "group_subscribers",
                        lambda g: [{"id": "1", "fields": {"pantryrun_id": "anna"}}, {"id": "2", "fields": {}}] if g == "g-weekly" else [])
    assert editions.record_sent(token) == {"logged": 1}
    assert rows("SELECT user_id, channel, note FROM nudges") == [("anna", "newsletter", f"plan {token}")]
    with pytest.raises(editions.EditionError, match="No plan nope"):
        editions.record_sent("nope")


def test_owner_steps_need_the_token_and_say_why_they_fail(api, db, monkeypatch):
    assert status(lambda: api.promote_subscribers(authorization="Bearer x")) == 503  # EDITION_TOKEN not set
    monkeypatch.setenv("EDITION_TOKEN", "s3cret")
    assert status(lambda: api.promote_subscribers(authorization="Bearer wrong")) == 401
    assert status(lambda: api.edition_sent("x", authorization=None)) == 401
    assert status(lambda: api.promote_subscribers(authorization="Bearer s3cret")) == 422  # MailerLite not set up
    monkeypatch.setattr(editions, "promote", lambda: (_ for _ in ()).throw(mailerlite.MailerLiteError("500")))
    assert status(lambda: api.promote_subscribers(authorization="Bearer s3cret")) == 502


def test_script_reads_the_token_from_the_keychain(monkeypatch):
    monkeypatch.delenv("EDITION_TOKEN", raising=False)

    class Found:
        returncode, stdout = 0, "from-keychain\n"
    asked = []
    monkeypatch.setattr(weekly_plan.subprocess, "run", lambda cmd, **kw: asked.append(cmd) or Found())
    assert weekly_plan.token() == "from-keychain"
    assert asked == [["security", "find-generic-password", "-s", "pantryrun-edition", "-w"]]
    monkeypatch.setenv("EDITION_TOKEN", "from-env")
    assert weekly_plan.token() == "from-env"


def test_edition_has_tagged_links_the_featured_label_and_the_list():
    result = {"servings": 2, "dinners": [{"id": "kanasupp", "name": "Kanasupp", "image": None, "link": None, "featured": False},
                                         {"id": "sh-x", "name": "Kõrvitsasupp", "image": "https://img/1.jpg",
                                          "link": "https://rimi.ee/r/1", "featured": True}],
              "baskets": [{"store": "rimi", "status": "ok", "total_price": 9.5, "missing": [],
                           "lines": [{"label": "Kana", "product": "Kanafilee 500g", "cost": 5.0},
                                     {"label": "Kõrvits", "product": "Kõrvits kg", "cost": 4.5}]},
                          {"store": "selver", "status": "ok", "total_price": 10.2, "missing": [], "lines": []}]}
    text = editions.edition("Week 46", "T0K", result, "https://pantryrun.example")
    assert "https://pantryrun.example/?plan=T0K&from=newsletter&u={$pantryrun_id}" in text
    assert "FEATURED (label it \"Featured\"): Kõrvitsasupp" in text
    assert "/cooked?plan=T0K&dinner=sh-x&u={$pantryrun_id}&answer=yes" in text
    assert "SHOPPING LIST at Rimi, for 2 people:" in text and "Total: 9.50 €" in text and "Selver 10.20 €" in text


def test_edition_email_fills_every_part_and_keeps_the_merge_tags():
    result = {"servings": 2, "dinners": [{"id": "kanasupp", "name": "Kanasupp", "image": None, "link": None, "featured": False},
                                         {"id": "sh-x", "name": "Kõrvitsasupp <3", "image": "https://img/1.jpg",
                                          "link": "https://rimi.ee/r/1", "featured": True}],
              "baskets": [{"store": "barbora", "status": "ok", "total_price": 9.5, "missing": [],
                           "lines": [{"label": "Kana", "product": "Kanafilee 500g", "cost": 5.0}]},
                          {"store": "selver", "status": "ok", "total_price": 10.2, "missing": [], "lines": []},
                          {"store": "rimi", "status": "ok", "total_price": 4.1, "missing": ["kana", "riis"], "lines": []}]}
    email = editions.edition_html("Week 46", "T0K", result, "https://pantryrun.example", "25 October 2026")
    assert not re.search(r"@@[A-Z_]+@@", email)  # every part filled in
    assert 'href="https://pantryrun.example/?plan=T0K&amp;from=newsletter&amp;u={$pantryrun_id}"' in email
    assert email.count(">FEATURED</span>") == 1 and "Kõrvitsasupp &lt;3" in email
    assert "Maxima (Barbora&#x27;s prices)" in email and "9,50 €" in email and "Elsewhere: Selver 10,20 €, Rimi 4,10 € (2 missing)" in email
    assert 'href="{$unsubscribe}"' in email and "answer=yes" in email


# ── making an edition on the server ──────────────────────────────────────────

def priced(statuses):
    """What catalog.recommend answers, with each store's status: {store: "ok" | "no_answer"}."""
    def recommend(recipe_id, servings, items, stores, dinners=None, **kw):
        baskets = [{"store": s, "status": st, "total_price": 10.0 + i if st == "ok" else None, "missing": [],
                    "lines": [{"label": "Kana", "product": "Kana 500g", "cost": 5.0}] if st == "ok" else []}
                   for i, (s, st) in enumerate(statuses.items())]
        ok = [b for b in baskets if b["status"] == "ok"]
        return {"servings": servings, "dinners": [{"id": d["id"], "name": d["id"], "image": None, "link": None} for d in dinners],
                "store": ok[0]["store"] if ok else None, "baskets": ok + [b for b in baskets if b["status"] != "ok"]}
    return recommend


def test_edition_is_refused_when_a_store_didnt_answer(db, monkeypatch):
    monkeypatch.setattr(editions.catalog, "recommend", priced({"rimi": "ok", "barbora": "ok", "selver": "no_answer"}))
    with pytest.raises(editions.EditionError, match="Selver didn't answer"):
        editions.make("Week 46", ["kanasupp", "pasta_hakklihaga"])
    assert rows("SELECT count(*) FROM plans") == [(0,)]  # nothing saved


def test_edition_is_refused_when_even_the_best_store_lacks_something(db, monkeypatch):
    recommend = priced({"selver": "ok", "rimi": "ok", "barbora": "ok"})
    def lacking(*a, **kw):
        result = recommend(*a, **kw)
        for b in result["baskets"]:
            b["missing"] = ["Lõhefilee"]
        return result
    monkeypatch.setattr(editions.catalog, "recommend", lacking)
    with pytest.raises(editions.EditionError, match="even Selver lacks Lõhefilee. Swap the dinner"):
        editions.make("Week 46", ["lohe_kartul"])


def test_edition_saves_the_plan_with_the_featured_dinner(db, monkeypatch):
    monkeypatch.setattr(editions.catalog, "recommend", priced({"selver": "ok", "rimi": "ok", "barbora": "ok"}))
    made = editions.make("Week 46", ["kanasupp"], featured="pasta_hakklihaga", base="https://pantryrun.example/")
    assert plans.get(made["token"])["dinners"] == ["kanasupp", "pasta_hakklihaga"]
    assert plans.get(made["token"])["featured"] == "pasta_hakklihaga"
    assert f"?plan={made['token']}&amp;from=newsletter" in made["html"] and "SHOPPING LIST at Selver" in made["text"]
    with pytest.raises(editions.EditionError, match="Unknown dinners: nope"):
        editions.make("x", ["nope"])


def test_editions_endpoint_needs_the_owners_token(api, db, monkeypatch):
    monkeypatch.setattr(editions.catalog, "recommend", priced({"selver": "ok", "rimi": "ok", "barbora": "ok"}))
    req = api.EditionRequest(title="Week 46", dinners=["kanasupp"])
    assert status(lambda: api.make_edition(req, authorization="Bearer x")) == 503  # not set on the server
    monkeypatch.setenv("EDITION_TOKEN", "s3cret")
    assert status(lambda: api.make_edition(req, authorization="Bearer wrong")) == 401
    assert status(lambda: api.make_edition(req, authorization=None)) == 401
    assert "token" in api.make_edition(req, authorization="Bearer s3cret")


def test_build_asks_the_live_site_and_writes_the_email(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EDITION_TOKEN", "s3cret")
    sent = {}

    class Resp:
        status_code, content = 200, b"x"
        def json(self):
            return {"token": "T0K", "text": "SUMMARY", "html": "<html>email</html>"}
    monkeypatch.setattr(weekly_plan.requests, "post", lambda url, **kw: sent.update(url=url, **kw) or Resp())
    weekly_plan.main(["--base-url", "https://site.example/", "build", "--title", "Week 46", "--dinners", "kanasupp,nd-1318"])
    assert sent["url"] == "https://site.example/editions"
    assert sent["headers"] == {"Authorization": "Bearer s3cret"}
    assert sent["json"]["dinners"] == ["kanasupp", "nd-1318"]
    assert (tmp_path / "logs" / "edition-T0K.html").read_text() == "<html>email</html>"
    assert "sent --plan T0K" in capsys.readouterr().out
