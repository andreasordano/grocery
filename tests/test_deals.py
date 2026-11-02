"""This week's deals (core/deals.py, WEB-28): which dinners are deals at which store, the "Cheap this week" chip,
and At the store's GET /deals (WEB-29)."""
import pytest
from fastapi import HTTPException

from core import catalog, deals
from core import recipes as own


def line(label, cost, regular=None, card=None):
    return {"label": label, "product": label.upper(), "cost": cost, "regular_cost": regular, "card_cost": card}


def basket(store, *lines, missing=(), status="ok"):
    return {"store": store, "status": status, "lines": list(lines), "missing": list(missing),
            "total_price": round(sum(l["cost"] for l in lines), 2) if status == "ok" else None,
            "savings": round(sum((l["regular_cost"] or l["cost"]) - l["cost"] for l in lines), 2),
            "card_savings": round(sum(l["cost"] - (l["card_cost"] or l["cost"]) for l in lines), 2)}


@pytest.fixture(autouse=True)
def no_deals():
    deals.set_week({}, worked_out=False)
    yield
    deals.set_week({}, worked_out=False)


def test_a_deal_has_two_lines_on_sale_and_nothing_missing():
    chicken, rice = line("Kanafilee", 6.0, regular=8.0), line("Riis", 2.0, card=1.5)
    onion = line("Sibul", 2.0)
    d = deals.score("kanakarri", basket("rimi", chicken, rice, onion))
    assert d == {"id": "kanakarri", "count": 3, "share": 0.8, "saving": 2.5, "total": 10.0,
                 "on_sale": [{"label": "Kanafilee", "product": "KANAFILEE", "off": 25},
                             {"label": "Riis", "product": "RIIS", "off": 25}]}
    assert deals.score("x", basket("rimi", chicken, onion)) is None                       # one line on sale
    assert deals.score("x", basket("rimi", chicken, onion, line("kanafilee", 6.0, regular=8.0))) is None  # one thing, twice
    assert deals.score("x", basket("rimi", chicken, rice, missing=["Kookospiim"])) is None  # not buyable there
    assert deals.score("x", basket("rimi", status="no_answer")) is None


def test_refresh_ranks_by_share_and_a_store_that_didnt_answer_keeps_its_deals(monkeypatch):
    sale = lambda: (line("A", 1.0, regular=2.0), line("B", 1.0, regular=2.0))
    priced = {
        "half": [basket("rimi", *sale(), line("C", 2.0)), basket("selver", status="no_answer")],
        "all": [basket("rimi", *sale()), basket("selver", status="no_answer")],
        "none": [basket("rimi", line("C", 2.0)), basket("selver", status="no_answer")],
    }
    monkeypatch.setattr(deals, "candidates", lambda: [{"id": i} for i in priced])
    monkeypatch.setattr(catalog, "recommend", lambda rid, servings, items, stores: {"baskets": priced[rid]})
    deals.set_week({"selver": [{"id": "old", "share": 1.0}]})

    assert deals.refresh(["rimi", "selver"]) == {"rimi": 2, "selver": 1}
    week = deals.week()
    assert week["at"] and [d["id"] for d in week["stores"]["rimi"]] == ["all", "half"]
    assert week["stores"]["selver"] == [{"id": "old", "share": 1.0}]  # Selver was down: last week's stay


def test_cheap_this_week_is_each_stores_best_few_and_says_where():
    rimi = [{"id": f"r{n}", "share": 1 - n / 10, "on_sale": [{}, {}], "count": 5} for n in range(deals.CHIP_PER_STORE + 1)]
    deals.set_week({"rimi": rimi, "selver": [{"id": "r1", "share": 0.95, "on_sale": [{}, {}, {}], "count": 4}]})
    assert deals.chip_ids() == {f"r{n}" for n in range(deals.CHIP_PER_STORE)}  # the 7th at Rimi isn't in it
    assert deals.badge("r1") == {"store": "selver", "on_sale": 3, "count": 4}  # its best store
    assert deals.badge("r6") is None
    assert own.tags_of({"id": "r1", "tags": ["chicken"]}, 10, cheap=deals.chip_ids()) == ["deals", "chicken"]
    assert own.tags_of({"id": "r1", "tags": ["chicken"]}, 10) == ["chicken"]


def test_recipes_endpoint_has_the_chip_only_when_there_are_deals():
    from api import service
    out = service.recipes()
    assert "deals" not in [c["id"] for c in out["categories"]]
    assert not any("deal" in d for d in out["recipes"] + out["dishes"])

    first = out["recipes"][0]["id"]
    deals.set_week({"rimi": [{"id": first, "share": 0.5, "on_sale": [{}, {}], "count": 6}]})
    out = service.recipes()
    chip = next(c for c in out["categories"] if c["id"] == "deals")
    assert chip == {"id": "deals", "name": "Cheap this week", "moment": True}
    shown = next(d for d in out["recipes"] if d["id"] == first)
    assert "deals" in shown["tags"] and shown["deal"] == {"store": "rimi", "on_sale": 2, "count": 6}


def test_deals_endpoint_sends_each_stores_best_and_none_before_the_first_run(monkeypatch):
    from api import service
    assert service.week_deals() == {"at": None, "stores": {}}
    deals.set_week({"rimi": [{"id": str(n)} for n in range(20)]})
    out = service.week_deals()
    assert out["at"] and len(out["stores"]["rimi"]) == service.DEALS_SHOWN


def test_unmatched_food_is_for_the_owner(monkeypatch):
    from api import service
    monkeypatch.setenv("EDITION_TOKEN", "s3cret")
    monkeypatch.setattr(deals, "unmatched_food", lambda: {"total": 1, "on_sale": 1, "unmatched": 0, "shelves": []})
    with pytest.raises(HTTPException) as refused:
        service.deals_unmatched(authorization="Bearer nope")
    assert refused.value.status_code == 401
    assert service.deals_unmatched(authorization="Bearer s3cret")["total"] == 1


def test_unmatched_food_lists_discounted_food_no_rule_catches(monkeypatch):
    def product(name, price, regular, shelf, food=True):
        cats = [{"name": shelf, "is_virtual": "false"}]
        if food:
            cats.append({"name": deals.SELVER_FOOD_DEALS, "is_virtual": "true"})
        return {"_source": {"name": name, "final_price": price, "original_price": regular, "category": cats},
                "sort": [name]}
    pages = [[product("Kanafilee, kg", 6, 8, "Kana"),               # a rule catches it
              product("Peekon 200 g", 2, 3, "Lihatooted"),
              product("Peekon suitsu 150 g", 2, 3, "Lihatooted"),
              product("Vein punane", 5, 7, "Veinid"),               # never dinner
              product("Pesupulber", 5, 7, "Kodu", food=False),      # not food
              product("Sibul, kg", 1, None, "Köögiviljad")], []]   # not on sale
    rules = {"kanafilee": {"selver": {"query": "kanafilee", "require": ["kanafilee"]}}}

    class Answer:
        def __init__(self, hits): self.hits = hits
        def raise_for_status(self): pass
        def json(self): return {"hits": {"hits": self.hits}}
    monkeypatch.setattr(deals.requests, "post", lambda *a, **k: Answer(pages.pop(0)))

    found = deals.unmatched_food(rules)
    assert (found["total"], found["on_sale"], found["unmatched"]) == (6, 5, 2)
    assert found["shelves"] == [{"shelf": "Lihatooted", "count": 2, "examples": ["Peekon 200 g", "Peekon suitsu 150 g"]}]
