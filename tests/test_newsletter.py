"""The weekly plan newsletter (WEB-37): plans, sign-up, "Did you cook it?", MailerLite calls and the weekly script."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from core import events, mailerlite, my_dinners, plans
from scripts import weekly_plan


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "app.db"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("EVENTS_DB", str(path))
    monkeypatch.setattr(events, "_initialized", False)
    for key in ("MAILERLITE_API_KEY", "MAILERLITE_GROUP_NEW", "MAILERLITE_GROUP_WEEKLY"):
        monkeypatch.delenv(key, raising=False)
    return path


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
            sqlite3.connect(db).execute("SELECT user_id, data FROM events WHERE type = ?", (type_,)).fetchall()]


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
    assert "example.ee" not in sqlite3.connect(db).execute("SELECT group_concat(data) FROM events").fetchone()[0]


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

def test_promote_lets_in_only_people_past_their_first_week(monkeypatch, mailer):
    now = datetime.now(timezone.utc)
    waiting = [{"id": "s1", "created_at": "2026-01-01 10:00:00", "fields": {"pantryrun_id": "old"}},
               {"id": "s2", "created_at": "2026-01-01 10:00:00", "fields": {"pantryrun_id": "new"}},
               {"id": "s3", "created_at": (now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S"), "fields": {}}]
    moved = []
    monkeypatch.setattr(mailerlite, "group_subscribers", lambda g: waiting)
    monkeypatch.setattr(mailerlite, "move", lambda sid, a, b: moved.append((sid, a, b)))

    class Conn:
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(weekly_plan, "_postgres", lambda: Conn())
    monkeypatch.setattr(weekly_plan, "first_seen", lambda conn, ids: {"old": now - timedelta(days=8), "new": now - timedelta(days=3)})
    weekly_plan.main(["promote"])
    assert moved == [("s1", "g-new", "g-weekly")]


def test_edition_has_tagged_links_the_featured_label_and_the_list():
    result = {"servings": 2, "dinners": [{"id": "kanasupp", "name": "Kanasupp", "image": None, "link": None, "featured": False},
                                         {"id": "sh-x", "name": "Kõrvitsasupp", "image": "https://img/1.jpg",
                                          "link": "https://rimi.ee/r/1", "featured": True}],
              "baskets": [{"store": "rimi", "status": "ok", "total_price": 9.5, "missing": [],
                           "lines": [{"label": "Kana", "product": "Kanafilee 500g", "cost": 5.0},
                                     {"label": "Kõrvits", "product": "Kõrvits kg", "cost": 4.5}]},
                          {"store": "selver", "status": "ok", "total_price": 10.2, "missing": [], "lines": []}]}
    text = weekly_plan.edition("Week 46", "T0K", result, "https://pantryrun.example")
    assert "https://pantryrun.example/?plan=T0K&from=newsletter&u={$pantryrun_id}" in text
    assert "FEATURED (label it \"Featured\"): Kõrvitsasupp" in text
    assert "/cooked?plan=T0K&dinner=sh-x&u={$pantryrun_id}&answer=yes" in text
    assert "SHOPPING LIST at Rimi, for 2 people:" in text and "Total: 9.50 €" in text and "Selver 10.20 €" in text
