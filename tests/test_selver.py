"""Selver's search request (api/selver_api.py), without the internet."""
import pytest

from api import selver_api


@pytest.mark.parametrize("typed, sent", [
    ("sai/leib", r"sai\/leib"),          # Selver answered HTTP 500 for these (WEB-23)
    ("tomat (kirss", r"tomat \(kirss"),
    ("piim 2,5%", "piim 2,5%"),          # ordinary text is left alone
])
def test_query_syntax_characters_are_escaped(typed, sent, monkeypatch):
    seen = {}

    class Answer:
        def raise_for_status(self): pass
        def json(self): return {"hits": {"hits": []}}

    monkeypatch.setattr(selver_api.requests, "post", lambda url, json, **k: seen.update(json) or Answer())
    selver_api.search_selver(typed)
    assert seen["query"]["query_string"]["query"] == sent


def test_partnerkaart_price_is_the_card_price(monkeypatch):
    # Selver's records on 2026-10-30. The prunes: 5.23, 3.59 with Partnerkaart. Milk has no card offer
    # (product_group_price missing) though other numbered groups get it 5-10% off in `prices`.
    prunes = {"name": "Kuivatatud ploomid kivideta, SEEBERGER, 200 g", "final_price": 5.23,
              "original_price": 5.23, "product_group_price": 3.59}
    milk = {"name": "Piim 2,5% pure, FARMI, 1 L", "final_price": 1.19, "original_price": 1.19,
            "product_group_price": None, "prices": [{"customer_group_id": 1, "final_price": 1.07}]}
    juice = {"name": "Kuivatatud ploomi mahl, RYNKEBY, 1 L", "final_price": 4.26, "original_price": 4.26,
             "product_group_price": 0}
    tomato = {"name": "Ploomtomat karbis, 500g", "final_price": 3.39, "original_price": 3.99,
              "special_to_date": "2026-10-30 23:59:59", "product_group_price": 0}

    class Answer:
        def raise_for_status(self): pass
        def json(self): return {"hits": {"hits": [{"_source": s} for s in (prunes, milk, juice, tomato)]}}

    monkeypatch.setattr(selver_api.requests, "post", lambda *a, **k: Answer())
    found = {p["name"]: p for p in selver_api.search_selver("ploomid")}

    assert found[prunes["name"]]["price"] == 5.23
    assert found[prunes["name"]]["card_price"] == 3.59
    assert found[prunes["name"]]["regular_price"] is None
    assert found[milk["name"]]["card_price"] is None
    assert found[juice["name"]]["card_price"] is None
    assert found[tomato["name"]]["card_price"] is None       # a campaign price, for everyone
    assert found[tomato["name"]]["regular_price"] == 3.99
