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


def test_list_offers_uses_rules_for_known_words(fake_store):
    offers = catalog.list_offers(["Munad", "jogurt"], ["a", "b"])
    assert list(offers) == ["Munad"]  # jogurt is left to free-text search
    assert [(o["store"], o["name"], o["price"]) for o in offers["Munad"]] == [("a", "Munad 10 tk", 2.0)]


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
    monkeypatch.setattr(catalog, "free_text_offers", lambda items, stores: {
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
    monkeypatch.setattr(catalog, "free_text_offers", lambda items, stores: {})
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
