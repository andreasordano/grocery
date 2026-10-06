"""Free-text matching for typed items without an ingredient rule.

Fixtures are real store answers (tests/fixtures/free_text.json, saved 6 Oct 2026), so these
tests show what a person typing the word would get.
"""
import json
import os

import pytest

from core import fetch
from core.scoring import fold, relevance_score, word_match

FIXTURES = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "free_text.json"), encoding="utf-8"))


@pytest.fixture
def stores(monkeypatch):
    monkeypatch.setattr(fetch, "_cached_fetch", lambda store, query, size=40: FIXTURES.get(f"{store}|{query}", []))


def picks(item, store):
    found, _ = fetch._fetch_item_store(item, fetch.spec_for(item), store, 12)
    return [p["name"] for p in found]


# ── words ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("word, query, expected", [
    ("õun", "õunad", 3),                       # singular of what was typed
    ("rukkileib", "leib", 3),                  # compound ending in it
    ("maapähklivõie", "maapähklivõi", 2),      # close variant
    ("õuna", "õunad", 2),                      # "of apple" (õuna mahl)
    ("maapähklivõie", "maapäklivõi", 2),       # typo
    ("maapähklivõiga", "maapähklivõi", 1),     # "with peanut butter"
    ("võiga", "või", 1),
    ("maapähklivõi-proteiini", "maapähklivõi", 1),  # hyphen prefix: a protein bar
    ("mango-banaani", "banaanid", 2),         # last hyphen part counts
    ("kassiliiv", "tee", 0),
])
def test_word_match(word, query, expected):
    assert word_match(fold(word), fold(query)) == expected


def test_relevance_ignores_brands_in_capitals():
    rules = {"include": ["piim"]}
    assert relevance_score("Juust Eesti E-PIIM light viilutatud,300g", rules) < 4
    assert relevance_score("Piim ALMA 2,5%, 0,5L", rules) == 5


def test_relevance_for_and_flavoured_are_not_the_thing():
    assert relevance_score("Astelpajumarjapüree tee jaoks 4 portsjonit, MASHIE, 180g", {"include": ["tee"]}) == 2
    assert relevance_score("Valgubatoon maapähklivõimaitseline Fiteg2 35g", {"include": ["maapähklivõi"]}) == 2
    assert relevance_score("Must tee metallpurgis, SELAVI", {"include": ["tee"]}) == 5


def test_relevance_drops_excluded_words():
    assert relevance_score("Piim laktoosivaba 1L", {"include": ["piim"], "exclude": ["laktoosivaba"]}) == -1


# ── shelves ──────────────────────────────────────────────────────────────────

def test_peanut_butter_keeps_spreads_and_drops_snacks(stores):
    barbora = picks("maapähklivõi", "barbora")
    assert barbora and all("Maapähklikreem" in n for n in barbora)  # the store knows these are peanut butter
    assert not any("REESE" in n for n in barbora)                   # "with peanut butter" chocolate bar

    selver = picks("maapähklivõi", "selver")
    assert any("maapähklivõie" in n for n in selver)
    assert any("Maapähklikreem" in n for n in selver)               # same shelf, other name
    assert not any(w in n.lower() for n in selver for w in ("batoon", "šokolaad", "müsli"))

    assert not any("batoon" in n.lower() for n in picks("maapähklivõi", "rimi"))


def test_tea_does_not_include_cat_litter(stores):
    rimi = picks("tee", "rimi")
    assert len(rimi) >= 6
    assert not any("Kassiliiv" in n for n in rimi)


def test_butter_is_butter_not_things_with_butter(stores):
    selver = picks("või", "selver")
    assert selver and not any("võiga" in n.lower() for n in selver)


def test_plural_falls_back_to_singular_for_fresh_fruit(stores):
    selver = picks("banaanid", "selver")
    assert selver[0].startswith("Banaan")       # real bananas first, not baby food
    assert not any("6+" in n for n in selver[:3])


def test_brand_does_not_make_cheese_milk(stores):
    assert not any("Juust" in n for n in picks("piim", "barbora")[:6])
