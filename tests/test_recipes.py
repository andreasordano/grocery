"""pantryrun's own dinners (core/recipes.py, the recipes table, admin.html) and the chips (data/dinner_chips.yaml)."""
from pathlib import Path

import pytest
from fastapi import HTTPException

from conftest import rows
from core import catalog, db, events
from core import recipes as own

SAMPLES = Path(__file__).resolve().parent.parent / "supabase" / "migrations" / "20261029120100_recipes_samples.sql"

DINNER = {"name": "Kanakarri riisiga", "servings": 2, "minutes": 30, "tags": ["chicken", "rice"], "months": [],
          "ingredients": "400 g kanafilee\n200 g basmati riis\n\n400 ml kookospiim", "pantry": ["õli", "sool"],
          "about": "  Chicken   curry. ", "method": "1. Cook the rice.\n2. Fry the chicken.  \n"}


@pytest.fixture
def api(pg, monkeypatch):
    from api import service
    monkeypatch.setenv("EDITION_TOKEN", "s3cret")
    own.forget()
    return service


def status(call):
    try:
        call()
    except HTTPException as exc:
        return exc.status_code
    return 200


# ── chips ────────────────────────────────────────────────────────────────────

def test_store_recipe_gets_its_kind_from_the_category_and_pasta_or_rice_from_its_words():
    rimi = lambda category, items, name="X", minutes=45: {"name": name, "category": category, "minutes": minutes,
                                                          "ingredients": items}
    assert own.tags_of(rimi("mince", ["400 g spagetid", "500 g hakkliha"]), 10) == ["pasta", "meat"]
    assert own.tags_of(rimi("meat", ["2 g tomatipasta", "kontsentreeritud tomatipasta"]), 10) == ["meat"]  # tomato paste
    assert own.tags_of(rimi("veggie", ["180 g riisinuudlid santa maria"]), 10) == ["veggie"]           # rice noodles
    assert own.tags_of(rimi("chicken", ["3 dl pikateraline riis"], minutes=25), 10) == ["quick", "rice", "chicken"]
    assert own.tags_of(rimi("fish", ["tagliatelle munapasta"]), 10) == ["pasta", "fish"]


def test_own_tags_come_first_and_quick_and_seasonal_are_worked_out():
    dinner = {"name": "Kõrvitsasupp", "tags": ["veggie", "soup"], "minutes": 40, "months": [9, 10, 11], "ingredients": []}
    assert own.tags_of(dinner, 10) == ["seasonal", "veggie", "soup"]
    assert own.tags_of(dinner, 3) == ["veggie", "soup"]
    assert own.tags_of({**dinner, "minutes": 30}, 3) == ["quick", "veggie", "soup"]


def test_every_classic_has_known_tags():
    known = {c["id"] for c in own.chips()["chips"]} - set(own.WORKED_OUT)
    for r in catalog.load_recipes()["recipes"]:
        assert r.get("tags") and set(r["tags"]) <= known, r["id"]


# ── checking what the owner typed ────────────────────────────────────────────

def test_clean_tidies_the_form():
    row = own.clean(DINNER)
    assert row["ingredients"] == ["400 g kanafilee", "200 g basmati riis", "400 ml kookospiim"]
    assert row["about"] == "Chicken curry." and row["method"] == "1. Cook the rice.\n2. Fry the chicken."
    assert row["status"] == "draft" and row["emoji"] is None and row["review_by"] is None


@pytest.mark.parametrize("change, message", [
    ({"tags": ["quick"]}, "Unknown tags: quick"),
    ({"tags": ["dessert"]}, "Unknown tags: dessert"),
    ({"months": [13]}, "month must be between 1 and 12"),
    ({"ingredients": " \n "}, "at least one thing to buy"),
    ({"name": "  "}, "name can't be empty"),
    ({"servings": 0}, "between 1 and 12"),
    ({"minutes": "soon"}, "whole number"),
    ({"image": "http://x.ee/a.jpg"}, "https://"),
    ({"status": "live"}, "Status must be"),
    ({"review_by": "next week"}, "YYYY-MM-DD"),
])
def test_clean_says_what_is_wrong(change, message):
    with pytest.raises(own.RecipeError, match=message):
        own.clean({**DINNER, **change})


def test_slug_is_plain_ascii():
    assert own.slug("Šašlõkk ja värsked köögiviljad!") == "saslokk-ja-varsked-koogiviljad"
    assert own.slug("🍲") == "dinner"


# ── the table ────────────────────────────────────────────────────────────────

def test_save_gives_an_id_from_the_name_that_stays(pg):
    first = own.save(DINNER)
    second = own.save(DINNER)
    assert (first["id"], second["id"]) == ("pr-kanakarri-riisiga", "pr-kanakarri-riisiga-2")
    renamed = own.save({**DINNER, "name": "Karri"}, first["id"])
    assert renamed["id"] == first["id"] and renamed["name"] == "Karri" and renamed["updated"] >= first["updated"]
    with pytest.raises(LookupError):
        own.save(DINNER, "pr-nope")


def test_only_published_dinners_reach_the_app_and_an_edit_shows_at_once(pg):
    draft = own.save(DINNER)
    assert own.published() == []
    own.save({**DINNER, "status": "published"}, draft["id"])
    assert [r["id"] for r in own.published()] == [draft["id"]]
    own.save({**DINNER, "status": "archived"}, draft["id"])
    assert own.published() == []


def test_an_own_dinner_is_found_and_priced_like_a_typed_one(pg):
    saved = own.save(DINNER)
    card = catalog.recipe_card(saved["id"], 4, None)
    assert card["name"] == "Kanakarri riisiga" and card["pantry"] == ["õli", "sool"]
    assert [(i["label"], i["amount"]) for i in card["ingredients"]][:2] == [("kanafilee", 800), ("basmati riis", 400)]
    assert catalog.find_recipe("pr-nope", catalog.load_recipes()) is None


def test_usage_counts_testers_only(pg):
    rid = own.save(DINNER)["id"]
    for user in ("anna", "anna", "bert"):
        events.log_event("basket", {"recipe_ids": [rid, "rm-1"]}, user_id=user)
    events.log_event("dinner_view", {"id": rid}, user_id="anna")
    events.log_event("dinner_copy", {"from": rid}, user_id="bert")
    events.log_event("cooked", {"dinner": rid, "answer": "yes"}, user_id="bert")
    events.log_event("cooked", {"dinner": rid, "answer": "no"}, user_id="anna")
    events.log_event("basket", {"recipe_ids": [rid]}, user_id="claude-check")  # internal
    events.flush()
    usage = own.with_usage()[0]["usage"]
    assert {k: usage[k] for k in ("views", "answers", "people", "copies", "cooked")} == \
        {"views": 1, "answers": 3, "people": 2, "copies": 1, "cooked": 1}
    assert rows("SELECT answers FROM metrics.dinner_usage WHERE id = 'rm-1'") == [(3,)]


def test_the_samples_are_drafts_the_admin_would_accept(pg):
    with db.connection() as conn:
        conn.execute(SAMPLES.read_text())
    samples = own.with_usage()
    assert len(samples) == 24 and {r["status"] for r in samples} == {"draft"}
    moments = {t for r in samples for t in own.tags_of(r, 7)}
    assert {"quick", "friends", "seasonal", "pasta", "rice", "fish", "chicken", "meat", "veggie", "soup"} <= moments
    for r in samples:
        assert own.clean(r)["ingredients"] == r["ingredients"], r["id"]
        assert r["id"].startswith("pr-") and r["method"] and r["about"] and r["notes"].startswith("Drafted with AI"), r["id"]


# ── the endpoints ────────────────────────────────────────────────────────────

def test_admin_needs_the_owners_token(api, monkeypatch):
    assert status(lambda: api.admin_recipes(authorization="Bearer wrong")) == 401
    assert status(lambda: api.admin_add_recipe(DINNER, authorization=None)) == 401
    assert status(lambda: api.admin_check_recipe("pr-x", authorization="Bearer nope")) == 401
    monkeypatch.delenv("EDITION_TOKEN")
    assert status(lambda: api.admin_recipes(authorization="Bearer s3cret")) == 503


def test_admin_adds_edits_and_refuses_with_a_reason(api):
    ok = "Bearer s3cret"
    saved = api.admin_add_recipe(DINNER, authorization=ok)
    assert saved["id"] == "pr-kanakarri-riisiga"
    assert status(lambda: api.admin_save_recipe(saved["id"], {**DINNER, "tags": ["quick"]}, authorization=ok)) == 422
    assert status(lambda: api.admin_save_recipe("pr-nope", DINNER, authorization=ok)) == 404
    assert status(lambda: api.admin_check_recipe("pr-nope", authorization=ok)) == 404
    listed = api.admin_recipes(authorization=ok)
    assert [r["id"] for r in listed["recipes"]] == [saved["id"]] and listed["recipes"][0]["usage"]["answers"] == 0
    assert "quick" not in {c["id"] for c in listed["chips"]} and listed["quick_minutes"] == 30


def test_without_the_recipes_table_the_app_goes_on_and_the_admin_says_why(api):
    """Production ran this code before `supabase db push` (29 Oct): the dinners screen must not depend on it."""
    with db.connection() as conn:
        conn.execute("ALTER TABLE recipes RENAME TO recipes_away")
    try:
        own.forget()
        out = api.recipes()
        assert out["dishes"] and not any(d["id"].startswith("pr-") for d in out["dishes"])
        assert catalog.find_recipe("pr-x", catalog.load_recipes()) is None
        ok = "Bearer s3cret"
        assert status(lambda: api.admin_recipes(authorization=ok)) == 503
        assert status(lambda: api.admin_add_recipe(DINNER, authorization=ok)) == 503
        with pytest.raises(HTTPException, match="supabase db push"):
            api.admin_recipes(authorization=ok)
    finally:
        with db.connection() as conn:
            conn.execute("ALTER TABLE recipes_away RENAME TO recipes")
        own.forget()


def test_recipes_endpoint_shows_published_dinners_with_their_chips(api):
    own.save({**DINNER, "status": "published", "label": "With Santa Maria"})
    own.save({**DINNER, "name": "Mustand"})  # a draft stays out
    out = api.recipes()
    mine = [d for d in out["dishes"] if d["id"].startswith("pr-")]
    assert [(d["name"], d["tags"], d["label"]) for d in mine] == [("Kanakarri riisiga", ["quick", "rice", "chicken"], "With Santa Maria")]
    chips = [c["id"] for c in out["categories"]]
    assert chips[0] == "quick" and "friends" in chips  # the classics have friends
    assert all(any(c in d["tags"] for d in out["recipes"] + out["dishes"]) for c in chips)  # no empty chips
