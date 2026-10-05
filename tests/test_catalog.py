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
        assert set(rules[key]) == {"selver", "rimi"}, key


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
