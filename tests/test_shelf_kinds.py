"""Free text never picks a gin, a body lotion or a comb for food (WEB-54), and still finds them when asked.

Fixtures are real Rimi and Barbora answers (tests/fixtures/shelf_kinds.json, saved 2 Nov 2026).
"""
import json
import os

import pytest

from core import fetch
from core.scoring import fold, made_from, word_match

FIXTURES = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "shelf_kinds.json"), encoding="utf-8"))


@pytest.fixture(autouse=True)
def stores(monkeypatch):
    monkeypatch.setattr(fetch, "_cached_fetch", lambda store, query, size=40: FIXTURES.get(f"{store}|{query}", []))


def first(item, store):
    found, _ = fetch._fetch_item_store(item, fetch.spec_for(item), store, 12)
    return found[0]["name"] if found else None


@pytest.mark.parametrize("item, store, picked", [
    ("kookospiim", "barbora", "Kookoskreem väherasvane THAI-CHOICE 400ml"),   # was a body lotion
    ("rabarber", "barbora", "Külm.maasikas,rabarber HÄRMAVILI 300g"),         # was a gin
    ("kama", "barbora", "Keefir GEFILUS kama, 300g"),                         # was a comb
    ("nelk", "rimi", "Nelk Santa Maria 10g"),                                 # was an air freshener
    ("taimeõli", "barbora", "Toiduõli OILIO 1L"),                             # was plant fertiliser
    ("peet", "barbora", "Aurutatud riiv.peet vaakumis 350g"),                 # was buttermilk (pett)
    ("terve kana", "rimi", "Broiler, värske, A-klass Rimi kg"),               # was milk (brand Tere)
    ("suvikõrvits", "rimi", "Suvikõrvits roheline kg"),                       # was a pumpkin, a near form
    ("vaarikad", "barbora", "Vaarikad WELL DONE, 125g"),                      # was raspberries in chocolate
    ("viinamarjad", "rimi", "Viinamari tume seemnetega Moldova 1kl, kg"),     # was nectar
])
def test_food_is_food(item, store, picked):
    assert first(item, store) == picked


@pytest.mark.parametrize("item, store, picked", [
    ("šampoon", "barbora", "Šampoon RBA Takja 550ml"),         # nothing else fits: non-food is found
    ("õunamahl", "barbora", "Õunamahl MIO&RIO 1l"),            # names a drink
    ("kakaopulber", "barbora", "Kakaopulber KALEV 150g"),      # starts with one (Barbora keeps it with tea)
    ("sooda", "rimi", "Söögisooda Rimi Smart, 400g"),          # long vowels don't stop compounds
    ("pitsatainas", "barbora", "Külm.pitsataigen EESTI PAGAR,600g"),
])
def test_what_was_asked_for_is_still_found(item, store, picked):
    assert first(item, store) == picked


def test_shelf_kinds_per_store():
    assert fetch.shelf_kind(["SH-1-10-45"]) == "alcohol"     # Rimi: its sub-codes count
    assert fetch.shelf_kind(["SH-10-18-3"]) == "nonfood"     # ...but SH-10 isn't SH-1
    assert fetch.shelf_kind(["Joogid", "Kange alkohol", "Džinnid"]) == "alcohol"
    assert fetch.shelf_kind(["Kehakreemid, ihupiimad", "FB"]) == "nonfood"
    assert fetch.shelf_kind(["Piimatooted ja munad", "Piimad"]) == "food"
    assert fetch.shelf_kind(None) == "food"


def test_a_long_vowel_makes_another_word():
    assert word_match(fold("pett"), fold("peet")) == 0
    assert word_match(fold("piim"), fold("piim")) == 3
    assert word_match(fold("söögisooda"), fold("sooda")) == 3
    assert word_match(fold("tilapiafileed"), fold("tilaapia")) >= 1   # a typed long vowel is still a spelling


@pytest.mark.parametrize("name, typed", [
    ("Glasuur. skyr mustikadessert FARMI 40g", "glasuur"),
    ("Vaarikad piima-kakaoglasuuris PICKS 90g", "vaarikad"),
    ("Sulatatud juust kukeseen. MEREVAIK 200g", "kukeseened"),
    ("Nektar punase viinamarja Rimi 1l", "viinamarjad"),
    ("Kaerapuder aprik&pirn&õun Nõgel öko 190g", "aprikoos"),
    ("Mandlite ja marjade segu Pähklinäpp 200g", "mandlid"),
])
def test_made_from_it(name, typed):
    assert made_from(name, typed)


def test_a_brand_written_like_a_word_doesnt_name_the_thing():
    assert fetch._without_brand("Piim laktoosivaba Tere 2,5% 1l", "Tere", "terve kana") == "Piim laktoosivaba 2,5% 1l"
    assert fetch._without_brand("Sulat.juust HIIRTE JUUST kukeseened", "HIIRTE JUUST", "kukeseened") == \
        "Sulat.juust HIIRTE JUUST kukeseened"   # in capitals: left as it is
    assert fetch._without_brand("Ketšup Salvest 500g", "Salvest", "salvest ketšup") == "Ketšup Salvest 500g"


def test_thawed_fish_and_mince_mix_are_the_thing():
    assert not made_from("Sulatatud roogitud kuldne meriahven, kg", "meriahven")
    assert not made_from("Delikatess broilerihakklihasegu, TALLEGG, 300 g", "broilerihakkliha")


# Selver's answer for "kukeseened" and "kukeseen" (production search cache, 2 Nov 2026): no fresh or frozen ones.
SELVER_KUKESEENED = [
    {"name": "Gouda Kukeseene, NOPRI, 250 g", "price": 5.68, "category": ["Juustud", "Gluteenivaba", "FB"], "shelf": "Juustud"},
    {"name": "Koorene Kukeseene kaste, FOODSTUDIO, 230ml", "price": 3.89,
     "category": ["Köögiviljad, juurviljad", "Jahutatud valmistoidud", "FB"], "shelf": "Köögiviljad, juurviljad"},
    {"name": "Kuivatatud kukeseen, EESTI AND, 30 g", "price": 5.39, "category": ["Seened", "FB"], "shelf": "Seened"},
    {"name": "Kukeseen marineeritud, EESTI AND, 500 g", "price": 7.99, "category": ["Seened", "FB"], "shelf": "Seened"},
    {"name": "Kartulikrõpsud kukeseente ja juustukastme maitselised, ESTRELLA, 170g", "price": 2.45,
     "category": ["Sipsid", "FB"], "shelf": "Sipsid"},
    {"name": "Sulatatud juust kukeseentega, MEREVAIK, 200 g", "price": 1.99, "category": ["Määrdejuustud", "FB"],
     "shelf": "Määrdejuustud"},
]


def test_of_it_is_another_thing_and_a_jar_is_the_last_resort(monkeypatch):
    monkeypatch.setattr(fetch, "_cached_fetch", lambda store, query, size=40: SELVER_KUKESEENED)
    found, _ = fetch._fetch_item_store("kukeseened", fetch.spec_for("kukeseened"), "selver", 12)
    # Gouda "of chanterelle" is cheese, the sauce is a sauce, 30 g dried isn't 400 g: the jar, marked as a swap
    assert [(p["name"], p.get("swap")) for p in found] == [("Kukeseen marineeritud, EESTI AND, 500 g", True)]
    assert word_match(fold("kukeseene"), fold("kukeseened")) == 1
