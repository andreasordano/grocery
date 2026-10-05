import json
import sqlite3

import pytest

from api import rimi_api
from core import events, fetch
from core.optimiser import optimize_cart


def _p(item, store, price, score=1.0):
    return {"item": item, "store": store, "name": f"{item}@{store}", "price": price, "score": score}


# ── optimiser ────────────────────────────────────────────────────────────────

def test_recommends_cheapest_complete_single_store():
    all_products = {
        "piim": [_p("piim", "rimi", 1.0), _p("piim", "selver", 1.2)],
        "leib": [_p("leib", "rimi", 2.0), _p("leib", "selver", 1.5)],
    }
    cart, _, info = optimize_cart(all_products, ["piim", "leib"], ["rimi", "selver"])

    assert info["store"] == "selver"  # 2.70 < 3.00
    assert {p["store"] for p in cart} == {"selver"}  # never split across stores
    assert [b["store"] for b in info["baskets"]] == ["selver", "rimi"]


def test_coverage_beats_price():
    all_products = {
        "piim": [_p("piim", "rimi", 1.0), _p("piim", "selver", 5.0)],
        "kana": [_p("kana", "selver", 5.0)],
    }
    _, _, info = optimize_cart(all_products, ["piim", "kana"], ["rimi", "selver"])

    assert info["store"] == "selver"
    assert info["baskets"][1] == {"store": "rimi", "total_price": 1.0, "missing": ["kana"]}


def test_picks_best_score_within_store():
    all_products = {"piim": [_p("piim", "rimi", 0.5, score=9.0), _p("piim", "rimi", 1.0, score=1.0)]}
    cart, _, _ = optimize_cart(all_products, ["piim"], ["rimi"])
    assert cart[0]["price"] == 1.0


def test_no_results():
    cart, _, info = optimize_cart({}, ["piim"], ["rimi"])
    assert cart == [] and info["store"] is None and info["missing"] == ["piim"]


# ── fetch ────────────────────────────────────────────────────────────────────

def test_fetch_all_is_ordered_and_isolates_failures(monkeypatch):
    def fake_fetch(store, query, size=40):
        if store == "broken":
            raise RuntimeError("down")
        return [{"id": f"{store}-{query}", "name": f"{query} 1 kg", "price": 1.0}]

    monkeypatch.setattr(fetch, "_cached_fetch", fake_fetch)
    grocery_list = {it: {"search_term": it, "include": [it]} for it in ["riis", "sibul"]}

    all_products, warnings = fetch.fetch_all(grocery_list, ["selver", "broken", "rimi"])

    assert [p["store"] for p in all_products["riis"]][:1] == ["selver"]
    assert {p["store"] for p in all_products["sibul"]} == {"selver", "rimi"}
    assert warnings and all(w.startswith("broken/") for w in warnings)


# ── rimi parser ──────────────────────────────────────────────────────────────

RIMI_HTML = """
<div data-product-code="1" data-gtm-eec-product='{"brand":"Alma","price":1.39}'>
  <p class="card__name">Piim Alma 2,5% 1,5l</p>
  <div class="price-tag card__price"><span class="sr-only">1.39 €
        per pcs.</span><span aria-hidden="true">1</span><div><sup>39</sup><sub>€/pcs.</sub></div></div>
</div>
<div data-product-code="2" data-gtm-eec-product='{"brand":null,"price":5.25}'>
  <p class="card__name">Maasuitsu kanafilee kg</p>
  <div class="price-tag card__price"><span class="sr-only">20.99 € per kg</span></div>
</div>
<div data-product-code="3"><p class="card__name">Piim laktoosivaba</p> Out of stock!</div>
"""


def test_rimi_parses_shelf_price_and_unit(monkeypatch):
    class Resp:
        text = RIMI_HTML

    monkeypatch.setattr(rimi_api.requests, "get", lambda *a, **kw: Resp())
    milk, chicken, oos = rimi_api.search_rimi("piim")

    assert (milk["price"], milk["unit"], milk["brand"]) == (1.39, "pcs", "Alma")
    assert (chicken["price"], chicken["unit"]) == (20.99, "kg")  # per kg, not GTM's 0.25 kg price
    assert oos["price"] is None


# ── events ───────────────────────────────────────────────────────────────────

@pytest.fixture
def sqlite_events(tmp_path, monkeypatch):
    path = tmp_path / "events.db"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("EVENTS_DB", str(path))
    monkeypatch.setattr(events, "_initialized", False)
    return path


def test_log_event_writes_row(sqlite_events):
    assert events.log_event("accept", {"store": "rimi", "price": 8.6}, user_id="u1", session_id="s1")

    row = sqlite3.connect(sqlite_events).execute("SELECT user_id, session_id, type, data FROM events").fetchone()
    assert row[:3] == ("u1", "s1", "accept")
    assert json.loads(row[3]) == {"store": "rimi", "price": 8.6}


def test_log_event_never_raises(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    assert events.log_event("optimize", {}) is False


# ── barbora parser ───────────────────────────────────────────────────────────

def test_barbora_reads_embedded_product_list(monkeypatch):
    from api import barbora_api

    class Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        text = (
            '<script>window.b_productList = [{"id": "1", "title": "Kanamunad M 10tk", "price": 1.99,'
            ' "units": [{"unit": "tk"}], "comparative_unit": "tk", "status": "active",'
            ' "category_name_full_path": "Piimatooted ja munad/Munad/Kanamunad"},'
            ' {"id": "2", "title": "Sibul, kg", "price": 0.39, "units": [{"unit": "kg"}],'
            ' "comparative_unit": "kg", "status": "inactive", "category_name_full_path": "Köögiviljad"}];'
            ' window.other = 1;</script>'
        )

    monkeypatch.setattr(barbora_api.requests, "get", lambda *a, **kw: Resp())
    eggs, onion = barbora_api.search_barbora("munad")

    assert (eggs["name"], eggs["price"], eggs["unit"], eggs["in_stock"]) == ("Kanamunad M 10tk", 1.99, "tk", True)
    assert eggs["category"] == ["Piimatooted ja munad", "Munad", "Kanamunad"]
    assert (onion["unit"], onion["in_stock"]) == ("kg", False)


def test_barbora_page_without_product_list_raises(monkeypatch):
    from api import barbora_api

    class Resp:
        status_code = 200
        text = "<html>Please verify you are human</html>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(barbora_api.requests, "get", lambda *a, **kw: Resp())
    monkeypatch.setattr(barbora_api, "_RETRY_DELAYS", (0, 0))
    with pytest.raises(RuntimeError):
        barbora_api.search_barbora("piim")


def test_empty_results_are_not_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(fetch, "get_fetcher", lambda store: lambda q, **kw: calls.append(q) or [])
    monkeypatch.setattr(fetch, "get_pagination_param", lambda store: "size")
    fetch._cached_fetch("teststore", "uncached-query")
    fetch._cached_fetch("teststore", "uncached-query")
    assert len(calls) == 2
