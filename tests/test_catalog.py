import pytest

from core import catalog


# ── pack sizes and costs ─────────────────────────────────────────────────────

@pytest.mark.parametrize("name, volume, expected", [
    ("Kodune hakkliha Rimi 500g", None, (500, "g")),
    ("Hapukoor 20% kiles, ALMA, 500 g", "500 g", (500, "g")),
    ("Piim Alma 2,5% 1,5l", None, (1500, "ml")),
    ("Pikateraline riis Bosto 4x125g", None, (500, "g")),
    ("Muna Liisa kanamunad L10, MUNALIISA, 10 tk", "10 tk", (10, "pcs")),
    ("Peremunad M18, EGGO", None, (18, "pcs")),
    ("Kurk Marineeritud Salvest 675g/385g", None, (675, "g")),
    ("Roheline sibul potis", None, None),
])
def test_parse_pack(name, volume, expected):
    assert catalog.parse_pack(name, volume) == expected


def test_cost_whole_packs():
    cost, packs, _ = catalog.cost_for({"name": "Kohupiim 200 g", "price": 0.99}, 400, "g")
    assert (cost, packs) == (1.98, 2)


def test_cost_loose_by_weight():
    cost, packs, _ = catalog.cost_for({"name": "Kartul, kg", "price": 0.99, "unit": "kg"}, 800, "g")
    assert (cost, packs) == (0.79, None)


def test_cost_pieces_sold_per_kg():
    cost, _, _ = catalog.cost_for({"name": "Sidrun, kg", "price": 2.0, "unit": "kg"}, 1, "pcs", piece_g=120)
    assert cost == 0.24


def test_cost_unknown_size_is_skipped():
    assert catalog.cost_for({"name": "Roheline sibul potis", "price": 1.99}, 100, "g") is None


# ── rule matching ────────────────────────────────────────────────────────────

RULE = {"query": "x", "category": ["SH-8-9", "Linnuliha"], "require": ["rinnafil"], "exclude": ["marin"]}


@pytest.mark.parametrize("product, ok", [
    ({"name": "Broileri rinnafilee 500g", "category": ["SH-8-9-25"]}, True),          # sub-code
    ({"name": "Broileri rinnafilee 500g", "category": ["linnuliha"]}, True),          # case-insensitive
    ({"name": "Broileri rinnafilee 500g", "category": ["SH-8-90"]}, False),           # not a sub-code
    ({"name": "Broileri rinnafilee marinaadis", "category": ["SH-8-9-20"]}, False),   # exclude
    ({"name": "Broileri kintsuliha", "category": ["SH-8-9-25"]}, False),              # require
    ({"name": "Broileri rinnafilee", "category": ["SH-8-9-25"], "in_stock": False}, False),
    ({"name": "Broileri rinnafilee, 5 kg, ettetellimisel", "category": ["Linnuliha"]}, False),  # global
])
def test_matches_rule(product, ok):
    assert catalog.matches_rule(product, RULE) is ok


# ── recommendation ───────────────────────────────────────────────────────────

RECIPES = {
    "ingredients": {
        "kartul": {"name": "Kartul", "unit": "g"},
        "munad": {"name": "Kanamunad", "unit": "pcs"},
    },
    "recipes": [{"id": "test", "name": "Test", "ingredients": [
        {"item": "kartul", "amount": 800}, {"item": "munad", "amount": 4}]}],
}
RULES = {
    "kartul": {"a": {"query": "kartul"}, "b": {"query": "kartul"}},
    "munad": {"a": {"query": "munad"}, "b": {"query": "munad"}},
}
CATALOG = {
    ("a", "kartul"): [{"name": "Kartul, kg", "price": 1.0, "unit": "kg"}],
    ("a", "munad"): [{"name": "Munad 10 tk", "price": 2.0}],
    ("b", "kartul"): [{"name": "Kartul 2kg", "price": 1.5}],
    ("b", "munad"): [],
}


@pytest.fixture
def fake_store(monkeypatch):
    monkeypatch.setattr(catalog, "load_recipes", lambda: RECIPES)
    monkeypatch.setattr(catalog, "load_rules", lambda: RULES)
    monkeypatch.setattr(catalog, "_cached_fetch", lambda store, q: CATALOG[(store, q)])


def test_recommend_prefers_complete_basket(fake_store):
    res = catalog.recommend_dinner("test", 2, ["b", "a"])

    assert res["store"] == "a"  # b is cheaper but has no eggs
    best = res["baskets"][0]
    assert best["total_price"] == 2.8  # 0.8 kg × 1.00 + one pack of eggs
    assert res["baskets"][1]["missing"] == ["Kanamunad"]


def test_recommend_scales_servings(fake_store):
    res = catalog.recommend_dinner("test", 4, ["a"])
    lines = {l["ingredient"]: l for l in res["baskets"][0]["lines"]}
    assert lines["kartul"]["cost"] == 1.6 and lines["munad"]["packs"] == 1  # 8 eggs fit in one 10-pack


def test_unknown_recipe(fake_store):
    with pytest.raises(KeyError):
        catalog.recommend_dinner("nope", 2, ["a"])


def test_every_recipe_ingredient_has_rules():
    recipes, rules = catalog.load_recipes(), catalog.load_rules()
    used = {i["item"] for r in recipes["recipes"] for i in r["ingredients"]}
    assert used <= set(recipes["ingredients"])
    for key in used:
        assert set(rules[key]) == {"selver", "rimi", "barbora"}, key


def test_fallback_only_when_primary_finds_nothing(monkeypatch):
    recipes = {"ingredients": {"kapsas": {"name": "Hapukapsas", "unit": "g"}}, "recipes": []}
    rules = {"kapsas": {"a": {"query": "hapukapsas", "fallback": [{"query": "praekapsas"}]}}}
    stock = {"hapukapsas": [], "praekapsas": [{"name": "Praekapsas 900 g", "price": 3.79}]}
    monkeypatch.setattr(catalog, "_cached_fetch", lambda store, q: stock[q])

    offer = catalog.best_offer("kapsas", 800, "a", recipes, rules)
    assert (offer["product"], offer["substitute"]) == ("Praekapsas 900 g", True)

    stock["hapukapsas"] = [{"name": "Hapukapsas 900g", "price": 2.45}]
    offer = catalog.best_offer("kapsas", 800, "a", recipes, rules)
    assert (offer["product"], offer["substitute"]) == ("Hapukapsas 900g", False)


@pytest.mark.parametrize("typed, key", [
    ("piim", "piim"), ("Kanamunad", "munad"), ("munad", "munad"), ("broiler rinnafilee", "kanafilee"),
    ("  pasta ", "makaronid"), ("Broileri rinnafilee", "kanafilee"), ("jogurt", None), ("piimapulber", None),
])
def test_match_ingredient(typed, key):
    assert catalog.match_ingredient(typed) == key


# ── preferences, extra items, other stores ───────────────────────────────────

OPTS = [{"product": "Makaronid EXTRA LINE 400g", "cost": 0.28}, {"product": "Spaghetti DIVELLA 500g", "cost": 0.89},
        {"product": "Spaghetti BARILLA 500g", "cost": 1.99}]


def test_pick_cheapest_by_default():
    assert catalog._pick(OPTS, None, "a")["product"] == "Makaronid EXTRA LINE 400g"


def test_pick_preferred_words_cheapest_match():
    choice = catalog._pick(OPTS, {"words": ["spaghetti"]}, "a")
    assert (choice["product"], choice["preferred"]) == ("Spaghetti DIVELLA 500g", True)


def test_pick_pinned_product_at_that_store_only():
    pref = {"products": {"a": "Spaghetti BARILLA 500g"}, "words": ["spaghetti"]}
    assert catalog._pick(OPTS, pref, "a")["product"] == "Spaghetti BARILLA 500g"
    assert catalog._pick(OPTS, pref, "b")["product"] == "Spaghetti DIVELLA 500g"  # falls back to words


def test_pick_ignores_preference_that_matches_nothing():
    assert catalog._pick(OPTS, {"words": ["penne"]}, "a")["product"] == "Makaronid EXTRA LINE 400g"


def test_recommend_recipe_plus_extra_items(fake_store, monkeypatch):
    monkeypatch.setattr(catalog, "free_text_offers", lambda items, stores, needs=None: {
        "jogurt": {"a": [{"product": "Jogurt 1kg", "price": 1.49, "cost": 1.49, "packs": 1, "how": "", "substitute": False}],
                   "b": []}})
    res = catalog.recommend("test", 2, ["jogurt", "Munad"], ["a", "b"])
    best = res["baskets"][0]

    assert res["store"] == "a"
    assert [l["label"] for l in best["lines"]] == ["Kartul", "Kanamunad", "jogurt", "Munad"]
    assert [l["extra"] for l in best["lines"]] == [False, False, True, True]
    assert best["lines"][2]["key"] == "text:jogurt" and best["lines"][3]["key"] == "munad"
    assert best["total_price"] == round(0.8 + 2.0 + 1.49 + 2.0, 2)
    assert res["baskets"][1]["missing"] == ["Kanamunad", "jogurt", "Munad"]  # store b, every basket returned


def test_recommend_items_only(fake_store, monkeypatch):
    monkeypatch.setattr(catalog, "free_text_offers", lambda items, stores, needs=None: {})
    res = catalog.recommend(None, 2, ["kartul"], ["a", "b"])
    assert res["recipe"] is None and res["store"] == "a"
    assert res["baskets"][0]["lines"][0]["options"][0]["product"] == "Kartul, kg"


@pytest.mark.parametrize("word, product", [
    ("spaghetti", "Spagetid Nr 7 PRESTO 400g"), ("Laktoosivaba", "Piim laktoosivaba Tere 2,5% 1l"),
    ("3,2%", "Piim FARM MILK 3,2%, 1L"), ("alma", "Piim ALMA 2,5%, 1,5L"),
])
def test_preference_words_tolerate_spelling(word, product):
    opts = [{"product": "Cheapest thing 1kg", "cost": 0.1}, {"product": product, "cost": 1.0}]
    assert catalog._pick(opts, {"words": [word]}, "a")["product"] == product


# ── discounts ────────────────────────────────────────────────────────────────

def test_discounts_scale_with_packs_and_add_up(monkeypatch):
    recipes = {"ingredients": {"kohupiim": {"name": "Kohupiim", "unit": "g"}, "sibul": {"name": "Sibul", "unit": "g"}},
               "recipes": [{"id": "r", "name": "R", "ingredients": [{"item": "kohupiim", "amount": 400}, {"item": "sibul", "amount": 500}]}]}
    rules = {"kohupiim": {"a": {"query": "kohupiim"}}, "sibul": {"a": {"query": "sibul"}}}
    stock = {
        "kohupiim": [{"name": "Kohupiim 200 g", "price": 0.99, "regular_price": 1.29, "card_price": 0.89}],
        "sibul": [{"name": "Sibul, kg", "price": 0.40, "unit": "kg", "regular_price": 0.60}],
    }
    monkeypatch.setattr(catalog, "load_recipes", lambda: recipes)
    monkeypatch.setattr(catalog, "load_rules", lambda: rules)
    monkeypatch.setattr(catalog, "_cached_fetch", lambda store, q: stock[q])

    basket = catalog.recommend("r", 2, [], ["a"])["baskets"][0]
    quark, onion = basket["lines"]
    assert (quark["cost"], quark["regular_cost"], quark["card_cost"]) == (1.98, 2.58, 1.78)  # 2 packs
    assert (onion["cost"], onion["regular_cost"]) == (0.2, 0.3)                               # 0.5 kg
    assert basket["savings"] == 0.7 and basket["card_savings"] == 0.2


def test_every_pantry_item_has_rules():
    """Pantry items are offered as buttons on the receipt, so each must map to a rule, not a guess."""
    recipes, rules = catalog.load_recipes(), catalog.load_rules()
    for item in {p for r in recipes["recipes"] for p in r.get("pantry", [])}:
        key = catalog.match_ingredient(item, recipes)
        assert key, item
        assert set(rules[key]) == {"selver", "rimi", "barbora"}, item


# ── NutriData dishes (data/dishes.yaml) ──────────────────────────────────────

def test_dishes_are_well_formed():
    recipes, rules, dishes = catalog.load_recipes(), catalog.load_rules(), catalog.load_dishes()
    categories = {c["id"] for c in dishes["categories"]}
    ids = [d["id"] for d in dishes["dishes"]]
    assert len(ids) == len(set(ids)) and all(i.startswith("nd-") for i in ids)
    for d in dishes["dishes"]:
        assert d["category"] in categories, d["name"]
        assert len(d["ingredients"]) >= 2, d["name"]
        for ing in d["ingredients"]:
            assert ing["amount"] > 0, d["name"]
            if "item" in ing:  # rule-based: the rule must exist for every store
                assert set(rules[ing["item"]]) == {"selver", "rimi", "barbora"}, (d["name"], ing)
            else:
                assert ing["text"].strip(), d["name"]


def test_dish_free_text_ingredient_is_priced_for_the_amount(fake_store, monkeypatch):
    from core import fetch
    dish = {"id": "nd-1", "name": "Küüslaugukartul", "category": "veggie", "pantry": ["õli"],
            "ingredients": [{"item": "kartul", "amount": 800}, {"text": "küüslauk", "amount": 30}]}
    monkeypatch.setattr(catalog, "load_dishes", lambda: {"categories": [], "dishes": [dish]})
    products = [
        {"store": "a", "name": "Küüslauk 3 tk 100g", "price": 0.9, "score": 0.9, "relevance": 5},
        {"store": "a", "name": "Küüslauk, kg", "price": 6.0, "unit": "kg", "score": 0.6, "relevance": 5},
        {"store": "a", "name": "Küüslaugusool 80g", "price": 0.5, "score": 0.5, "relevance": 4},
    ]
    seen = {}
    def fake_fetch_all(grocery_list, stores):
        seen.update(grocery_list)
        return {"küüslauk": products}, []
    monkeypatch.setattr(fetch, "fetch_all", fake_fetch_all)

    res = catalog.recommend("nd-1", 4, [], ["a"])
    line = next(l for l in res["baskets"][0]["lines"] if l["key"] == "text:küüslauk")

    assert "küüslauk" in seen
    assert line["label"] == "Küüslauk" and line["need"] == 60 and not line["extra"]
    assert line["product"] == "Küüslauk, kg" and line["cost"] == 0.36   # 60 g of loose garlic, not a 100 g net
    assert [o["product"] for o in line["options"]][-1] == "Küüslaugusool 80g"  # lower tier stays last
    assert res["recipe"] == {"id": "nd-1", "name": "Küüslaugukartul", "pantry": ["õli"]}


# ── quantities typed with an item ────────────────────────────────────────────

@pytest.mark.parametrize("typed, expected", [
    ("paprika 600g", ("paprika", (600, "g"))),
    ("600 g paprika", ("paprika", (600, "g"))),
    ("kartul 2kg", ("kartul", (2000, "g"))),
    ("Piim 1,5 l", ("Piim", (1500, "ml"))),
    ("2 piim", ("piim", (2, "packs"))),
    ("2x leib", ("leib", (2, "packs"))),
    ("3 tk sidrun", ("sidrun", (3, "pcs"))),
    ("3 lõhe", ("lõhe", (3, "packs"))),                 # "l" followed by more letters isn't litres
    ("Piim 2,5%", ("Piim 2,5%", None)),                # a fat %, not a quantity
    ("paprika", ("paprika", None)),
    ("leib 0", ("leib 0", None)),
])
def test_parse_quantity(typed, expected):
    assert catalog.parse_quantity(typed) == expected


def test_list_item_with_grams_uses_the_rule_for_that_amount(fake_store, monkeypatch):
    monkeypatch.setattr(catalog, "free_text_offers", lambda items, stores, needs=None: {})
    res = catalog.recommend(None, 2, ["kartul 1,5 kg", "6 tk munad"], ["a"])
    lines = {l["key"]: l for l in res["baskets"][0]["lines"]}
    assert lines["kartul"]["need"] == 1500 and lines["kartul"]["cost"] == 1.5   # loose: 1.5 kg × 1.00
    assert lines["kartul"]["label"] == "kartul" and lines["kartul"]["asked"] == "1.5 kg"
    assert lines["munad"]["need"] == 6 and lines["munad"]["packs"] == 1          # 6 eggs fit one 10-pack


def test_list_item_packs_and_grams_for_free_text(fake_store, monkeypatch):
    from core import fetch
    products = [{"store": "a", "name": "Paprika punane, kg", "price": 4.0, "unit": "kg", "score": 0.4, "relevance": 5},
                {"store": "a", "name": "Kohv 500g", "price": 5.0, "score": 1.0, "relevance": 5}]
    seen = {}
    def fake_fetch_all(grocery_list, stores):
        seen.update(grocery_list)
        return {"paprika": products[:1], "kohv": products[1:]}, []
    monkeypatch.setattr(fetch, "fetch_all", fake_fetch_all)

    res = catalog.recommend(None, 2, ["paprika 600g", "2 kohv"], ["a"])
    lines = {l["key"]: l for l in res["baskets"][0]["lines"]}

    assert set(seen) == {"paprika", "kohv"}                       # searched without the quantity
    assert lines["text:paprika"]["cost"] == 2.4                   # 600 g × 4.00 €/kg
    assert lines["text:kohv"]["cost"] == 10.0 and lines["text:kohv"]["packs"] == 2
    assert lines["text:kohv"]["asked"] == "2 packs" and lines["text:kohv"]["options"][0]["cost"] == 10.0


# ── my dinners (people's own recipes) ────────────────────────────────────────

@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("EVENTS_DB", str(tmp_path / "app.db"))


def test_my_dinners_belong_to_their_owner(sqlite_db):
    from core import my_dinners
    d = my_dinners.save("anna", "  Pühapäeva   pasta ", 4, ["makaronid 500g", "hakkliha 400 g", "makaronid 500g"])
    assert d["name"] == "Pühapäeva pasta" and d["items"] == ["makaronid 500g", "hakkliha 400 g"]
    assert my_dinners.list_for("anna") == [d] and my_dinners.list_for("ben") == []
    assert my_dinners.get("ben", d["id"]) is None                                 # not someone else's
    assert my_dinners.save("ben", "x", 2, ["y"], d["id"]) is None                 # can't overwrite it
    assert my_dinners.save("anna", "Pasta", 2, ["makaronid"], d["id"])["name"] == "Pasta"
    assert not my_dinners.delete("ben", d["id"]) and my_dinners.delete("anna", d["id"])
    with pytest.raises(ValueError):
        my_dinners.save("anna", "", 2, ["x"])


def test_my_dinner_scales_from_its_own_servings(fake_store, sqlite_db, monkeypatch):
    from core import my_dinners
    monkeypatch.setattr(catalog, "free_text_offers", lambda items, stores, needs=None: {})
    d = my_dinners.save("anna", "Kartulid", 4, ["kartul 2 kg"])
    res = catalog.recommend(d["id"], 2, [], ["a"], user_id="anna")
    line = res["baskets"][0]["lines"][0]
    assert res["recipe"]["name"] == "Kartulid" and line["need"] == 1000 and not line["extra"]  # 2 kg for 4 → 1 kg for 2
    with pytest.raises(KeyError):
        catalog.recommend(d["id"], 2, [], ["a"], user_id="ben")


# ── dinners shared by link ───────────────────────────────────────────────────

def test_shared_dinner_is_a_snapshot_anyone_can_open(fake_store, sqlite_db, monkeypatch):
    from core import my_dinners
    monkeypatch.setattr(catalog, "free_text_offers", lambda items, stores, needs=None: {})
    d = my_dinners.save("anna", "Kartulid", 4, ["kartul 2 kg"])
    token = my_dinners.share("anna", d["id"], d["name"], d["servings"], d["items"])
    my_dinners.save("anna", "Kartulid", 4, ["kartul 5 kg"], d["id"])         # a later edit…

    shared = my_dinners.shared(token)
    assert shared["items"] == ["kartul 2 kg"] and len(token) == 8           # …doesn't change what was sent
    res = catalog.recommend(f"sh-{token}", 2, [], ["a"], user_id="ben")      # someone else can price it
    assert res["baskets"][0]["lines"][0]["need"] == 1000
    assert my_dinners.shared("nope") is None


def test_dishes_become_typed_items_that_price_the_same(fake_store):
    recipe = {"ingredients": [{"item": "kartul", "amount": 800}, {"item": "munad", "amount": 4},
                              {"text": "küüslauk", "amount": 11}]}
    items = catalog.recipe_as_items(recipe, catalog.load_recipes())
    assert items == ["kartul 800g", "4 tk kanamunad", "küüslauk 11g"]
    needs = [catalog.to_need(i, catalog.load_recipes()) for i in items]
    assert [(n.get("rule") or n.get("text"), n["amount"]) for n in needs] == [("kartul", 800), ("munad", 4), ("küüslauk", 11)]


def test_warm_cache_runs_every_rule_search_and_can_refresh(monkeypatch):
    calls = []
    monkeypatch.setattr(catalog, "load_rules", lambda: RULES)
    monkeypatch.setattr(catalog, "_cached_fetch", lambda store, q, refresh=False: calls.append((store, q, refresh)) or [])
    catalog.warm_cache(["a", "b"])
    assert sorted(calls) == [("a", "kartul", False), ("a", "munad", False), ("b", "kartul", False), ("b", "munad", False)]
    calls.clear()
    catalog.warm_cache(["a"], refresh=True)
    assert all(refresh for _, _, refresh in calls) and len(calls) == 2
