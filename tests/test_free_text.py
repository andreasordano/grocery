"""Free-text matching for typed items without an ingredient rule.

Fixtures are real store answers (tests/fixtures/free_text.json, saved 6 Oct 2026; Barbora and
Rimi answers for the wrong products people reported added 16 Oct), so these tests show what a
person typing the word would get.
"""
import json
import os

import pytest

from core import fetch
from core.scoring import fold, head_weight, relevance_score, shares_stem, word_match

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
    ("kintsuliha", "kanakintsuliha", 2),       # last part of a typed compound (Br.kintsuliha)
    ("liha", "kanakintsuliha", 0),             # too short to tell
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


def test_participles_in_front_still_name_the_thing_first():
    rules = {"include": ["veiseliha"]}
    assert head_weight("Hautatud veiseliha MAAILU, 325g", rules) == 1
    assert head_weight("Vahustatud kassitoit veiseliha ARDOUR85g", rules) == 0.5


def test_shares_stem():
    assert shares_stem("Maapähklikreem SANTE crunchy 350g", {"include": ["maapähklivõi"]})
    assert not shares_stem("Juust Tilsit FARM MILK viilutatud, 500g", {"include": ["tilaapia"]})
    assert not shares_stem("LED-lamp PAR16 35 DIM 3,4W GU10, OSRAM, 1 tk", {"include": ["porru"]})


# ── wrong products people reported (Oct 2026) ────────────────────────────────

def test_store_search_noise_is_not_picked(stores, monkeypatch):
    """When nothing in the answer is the thing, the store's look-alikes don't decide the shelf:
    Selver answered "porru" with a lamp and "tilaapia" with a board game."""
    noise = [{"store_id": "1", "name": "LED-lamp PAR16 35 DIM 3,4W GU10, OSRAM, 1 tk", "price": 6.99, "shelf": "Lambid"},
             {"store_id": "2", "name": "LED-lamp GU10 4W, OSRAM, 1 tk", "price": 4.99, "shelf": "Lambid"},
             {"store_id": "3", "name": 'Lauamäng "Kogu pere Reaalsuskontroll", DADA FUN, 1 tk', "price": 19.9, "shelf": "Mängud"}]
    monkeypatch.setattr(fetch, "_cached_fetch", lambda store, query, size=40: noise)
    assert picks("porru", "selver") == []
    assert picks("tilaapia", "selver") == []


def test_tilapia_is_fish_not_tilsit_cheese(stores):
    assert picks("tilaapia", "barbora")[0] == "Külm.tilapiafileed nahata NOWACO 400g"
    assert not any("Tilsit" in n or "Till" in n for n in picks("tilaapia", "barbora"))


def test_beef_is_not_pet_food_stock_or_tinned(stores):
    found = picks("veiseliha", "barbora")
    assert found[0] == "Jahutatud veise koot kondig.WELL DONE,kg"
    made_from = ("kassi", "koera", "puljong", "püree", "hautatud", "omas mahlas", "kuiv", "vinnut", "borš", "pelmeen")
    assert not any(w in n.lower() for n in found for w in made_from), found
    # Rimi's "veiseliha" search finds only stock, tins, jerky, baby and pet food: none of it is offered
    # (real searches also ask for "veise", which finds the cuts).
    assert picks("veiseliha", "rimi") == []


@pytest.mark.parametrize("name, typed, expected", [
    ("Küüslauk ürtidega päevalilleõlis, CITRES, 290 g", "küüslauk", True),
    ("Šampinjonid marin. Rimi Smart 280g/165g", "šampinjonid", True),
    ("Marineeritud šampinjonid EXTRA LINE 500g", "marineeritud šampinjonid", False),  # asked for
    ("Piparmünditee EXTRA LINE,20x1.5g", "piparmünt", True),
    ("Pelmeenid Hiina Uvic 700g", "hiina kapsas", True),
    ("Õun-porg.-pastin.p.ELLA'S KITCHEN120g4k", "pastinaak", True),  # baby food, by its age
    ("Kikerhernes Rimi 400g/250g", "kikerhernes", False),
    ("Pastinaak kg", "pastinaak", False),
    ("Täissuitsuvorst veise RANNAROOTSI,240g", "suitsuvorst", False),
])
def test_made_from_the_thing_is_not_the_thing(name, typed, expected):
    from core.scoring import made_from
    assert made_from(name, typed) is expected


def test_two_typed_words_written_as_one_are_the_thing():
    from core.scoring import relevance_score
    assert relevance_score("Hiinakapsas, kg", {"include": ["hiina", "kapsas"]}) == 5
    assert fetch._build_queries(fetch.spec_for("hiina kapsas"))[:2] == ["hiina kapsas", "hiinakapsas"]
    assert "veise" in fetch._build_queries(fetch.spec_for("veiseliha"))


def test_chicken_legs_are_found_by_their_last_part(stores):
    found = picks("kanakintsuliha", "barbora")
    assert "kintsuliha" in found[0].lower()
    assert all(n.lower().startswith(("br", "eestimaine br")) for n in found)  # broiler, from the poultry shelf


def test_full_words_find_leek_and_chilli(stores):
    """The dishes used to search "porru" and "tšilli" (cut from porrulauk and tšillipipar), which
    picked tomato-leek corn sticks and chilli crisps."""
    assert picks("porrulauk", "barbora")[0] == "Porrulauk, kg"
    assert picks("porrulauk", "rimi") == ["Porrulauk kg"]
    for store in ("barbora", "rimi"):
        found = picks("tšillipipar", store)
        assert found and all("tšilli" in n.lower() and "pip" in n.lower() for n in found), (store, found)  # pipar, pipra


def test_oil_is_cooking_oil(stores):
    """Liquids rank by price per 100 ml: 10 ml essential oils used to come second when packs were compared."""
    found = picks("õli", "barbora")
    assert "ol.õli" in found[0].lower() and not any("Eeterlik" in n for n in found[:5])
    assert not any("CarPlan" in n for n in picks("õli", "rimi"))


def test_out_of_stock_products_are_never_options(monkeypatch):
    stock = [{"store": "rimi", "store_id": "1", "name": "Kohv Paulig 500g", "price": 5.0, "in_stock": False},
             {"store": "rimi", "store_id": "2", "name": "Kohv Löfbergs 500g", "price": 6.0, "in_stock": True}]
    monkeypatch.setattr(fetch, "_cached_fetch", lambda store, q: stock)
    products, _ = fetch.fetch_all({"kohv": fetch.spec_for("kohv")}, ["rimi"])
    assert [p["name"] for p in products["kohv"]] == ["Kohv Löfbergs 500g"]


@pytest.mark.parametrize("name, typed, expected", [
    ("Keedusalaami Paruni NÕO, 90g viil", "parma juust", True),             # neither cheese nor parma
    ("Hele kaiser kukkel seemnetega 60g", "küpsetatud pardiliha", True),
    ("Kooritud kreeka pähklid EXTRA LINE 150g", "kooritud mandel", True),  # "kooritud" only describes
    ("Broileri kintsuliha, värske, A-kl Tallegg kg", "lamba kintsuliha", True),  # the wrong animal
    ("Lamba kintsuliha kg", "lamba kintsuliha", False),
    ("Punane sibul, kg", "sibul punane", False),                            # Rimi's recipes: noun first
    ("Sibul,kg", "kollane sibul", False),
    ("Riisinuudlid EXOTIC FOOD 250g", "riisinuudlid santa maria", False),   # another brand is fine
    ("Kartul lahtine, kg", "kartul", False),                                # one word: not checked here
])
def test_an_item_of_several_words_needs_the_word_that_names_it(name, typed, expected):
    from core.scoring import misses_the_thing
    assert misses_the_thing(name, typed) is expected


def test_typed_as_one_word_written_as_two():
    from core.scoring import relevance_score
    assert relevance_score("Hiina kapsas, kg", {"include": ["hiinakapsa"]}) >= 4   # Barbora's spelling
    assert relevance_score("Hiinapärane kaste poolmagus FELIX 500g", {"include": ["hiinakapsa"]}) == 0


def test_sold_out_match_comes_back_alone_marked(monkeypatch):
    stock = [{"store": "rimi", "store_id": "1", "name": "Kuldne meriahven, sulatatud, kg", "price": None, "in_stock": False,
              "shelf": "SH-8-20"}]
    monkeypatch.setattr(fetch, "_cached_fetch", lambda store, q, size=40: stock)
    found, _ = fetch._fetch_item_store("meriahven", fetch.spec_for("meriahven"), "rimi", 12)
    assert [(p["name"], p["sold_out"]) for p in found] == [("Kuldne meriahven, sulatatud, kg", True)]
    from core import catalog
    gone = {}
    assert catalog.free_text_offers(["meriahven"], ["rimi"], sold_out=gone) == {"meriahven": {"rimi": []}}
    assert gone == {("meriahven", "rimi"): "Kuldne meriahven, sulatatud, kg"}


def test_another_name_is_tried_when_nothing_is_exactly_the_thing(monkeypatch):
    stock = {"parmesan": [{"name": "Juust Rimi Tilsit 500g", "price": 4.0, "shelf": "Juust"},
                          {"name": "Juust Parmigiano Reggiano 100g", "price": 3.0, "shelf": "Juust"}],
             "parmigiano": [{"name": "Juust Parmigiano Reggiano 100g", "price": 3.0, "shelf": "Juust"}]}
    monkeypatch.setattr(fetch, "_cached_fetch", lambda store, q, size=40: [{"store": store, "store_id": p["name"], **p}
                                                                          for p in stock.get(q, [])])
    assert fetch.synonyms("parmesan")[:1] == ["parmesani juust"]
    assert picks("parmesan", "rimi") == ["Juust Parmigiano Reggiano 100g"]  # not the cheapest cheese on the shelf


def test_smoked_fish_does_not_outvote_the_fresh_fish_shelf(monkeypatch):
    stock = [{"name": "Kuumsuitsu kuldne meriahven, 300g", "price": 3.99, "shelf": "Suitsukala"},
             {"name": "Kuumsuitsu kuldne meriahven, kg-lett", "price": 12.0, "unit": "kg", "shelf": "Suitsukala"},
             {"name": "Sulatatud roogitud kuldne meriahven, kg", "price": 7.49, "unit": "kg", "shelf": "Värske kala"}]
    monkeypatch.setattr(fetch, "_cached_fetch", lambda store, q, size=40: [{"store": store, "store_id": p["name"], **p} for p in stock])
    assert picks("meriahven", "barbora") == ["Sulatatud roogitud kuldne meriahven, kg"]


@pytest.mark.parametrize("name, typed, expected", [
    ("Õuna-sidruni-piparmün.mahlKADARBIKU250ml", "piparmünt", True),   # a juice: the brand is written onto "mahl"
    ("Külms.lõhefilee viil. M.V.WOOL, 200g", "lõhefilee", True),       # cold-smoked
    ("Külmsuitsu lõhe 100g", "külmsuitsu lõhe", False),                # asked for
    ("Parmesani juustu Super Snack M&M,85g", "parmesan", True),
])
def test_more_things_made_from_it(name, typed, expected):
    from core.scoring import made_from
    assert made_from(name, typed) is expected


def test_selver_fresh_tomatoes_are_found_under_their_compound_names(monkeypatch):
    # Selver's search matches whole words: "tomat" brings sauces and tins (as on 29 Oct), never "Kobartomat, kg".
    answers = {"tomat": [{"name": "Pastakaste Tomat ja Juust, TARTU MILL, 340 g", "price": 3.99, "shelf": "Ketšupid, tomatipastad, kastmed"},
                         {"name": "Tükeldatud tomatid, POMI, 500 g", "price": 2.02, "shelf": "Hoidised"},
                         {"name": "Tomati püree, GESTUS, 700 g", "price": 2.39, "shelf": "Ketšupid, tomatipastad, kastmed"}],
               "kobartomat": [{"name": "Kobartomat, kg", "price": 3.49, "unit": "kg", "shelf": "Köögiviljad, juurviljad"}]}
    monkeypatch.setattr(fetch, "_cached_fetch", lambda store, q, size=40: [{"store": store, "store_id": p["name"], **p}
                                                                          for p in answers.get(q, [])])
    assert picks("tomat", "selver") == ["Kobartomat, kg"]


def test_a_swap_is_tried_last_and_marked(monkeypatch):
    answers = {"pangaasiusefilee": [{"name": "Pangaasiusefilee Northland 800g", "price": 6.99, "shelf": "Külmutatud kala"}],
               "merluusifilee": [{"name": "Vaikse ookeani merluusifilee 800g", "price": 7.49, "shelf": "Külmutatud kala"}]}
    monkeypatch.setattr(fetch, "_cached_fetch", lambda store, q, size=40: [{"store": store, "store_id": p["name"], **p}
                                                                          for p in answers.get(q, [])])
    found, _ = fetch._fetch_item_store("tursafilee", fetch.spec_for("tursafilee"), "rimi", 12)
    assert [(p["name"], p["swap"], p["item"]) for p in found] == [("Pangaasiusefilee Northland 800g", True, "tursafilee"),
                                                                 ("Vaikse ookeani merluusifilee 800g", True, "tursafilee")]
    from core import catalog
    offers = catalog.free_text_offers(["tursafilee"], ["rimi"], {"tursafilee": 400})
    assert offers["tursafilee"]["rimi"][0]["substitute"] is True  # the receipt says "swap"
