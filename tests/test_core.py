import json

import pytest

from api import rimi_api
from conftest import rows
from test_stores import assert_product_contract
from core import catalog, db, events, fetch


# ── fetch ────────────────────────────────────────────────────────────────────

def test_fetch_all_is_ordered_and_isolates_failures(monkeypatch):
    def fake_fetch(store, query, size=40):
        if store == "broken":
            raise RuntimeError("down")
        return [{"store_id": f"{store}-{query}", "name": f"{query} 1 kg", "price": 1.0}]

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
  <input type="number" value="0.6" min="0.6" max="100" data-amount="0.6" data-unit="kg">
</div>
<div data-product-code="3"><p class="card__name">Piim laktoosivaba</p> Out of stock!</div>
"""


class RimiResp:
    status_code = 200
    text = RIMI_HTML

    def raise_for_status(self):
        pass


def test_rimi_parses_shelf_price_and_unit(monkeypatch):
    monkeypatch.setattr(rimi_api.requests, "get", lambda *a, **kw: RimiResp())
    found = rimi_api.search_rimi("piim")
    assert_product_contract(found, "rimi")
    milk, chicken, oos = found

    assert (milk["price"], milk["unit"], milk["brand"]) == (1.39, "pcs", "Alma")
    assert (chicken["price"], chicken["unit"]) == (20.99, "kg")  # per kg, not GTM's 0.25 kg price
    assert (chicken["min_qty"], milk["min_qty"]) == (0.6, None)
    assert oos["price"] is None


def test_rimi_search_with_no_results_is_empty(monkeypatch):
    class Resp(RimiResp):
        text = '<div class="error-page"><p class="error-page__heading">No product found</p></div>'

    monkeypatch.setattr(rimi_api.requests, "get", lambda *a, **kw: Resp())
    assert rimi_api.search_rimi("qqzz") == []


def test_rimi_page_without_products_or_notice_raises(monkeypatch):
    class Resp(RimiResp):
        text = "<html>Just a moment...</html>"

    monkeypatch.setattr(rimi_api.requests, "get", lambda *a, **kw: Resp())
    with pytest.raises(RuntimeError):
        rimi_api.search_rimi("piim")


# ── selver adapter ───────────────────────────────────────────────────────────

def test_selver_reads_the_minimum_of_loose_goods(monkeypatch):
    from api import selver_api

    def hit(name, volume, **stock):
        return {"_source": {"name": name, "sku": f"T{len(name)}", "product_volume": volume, "price": 1.0, "category": [],
                            "stock": {"stock_status": 1, "min_sale_qty": 1, "qty_increments": 1,
                                      "enable_qty_increments": False, **stock}}}

    class Resp:  # stock values as Selver sent them on 16 Oct 2026
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"hits": {"hits": [
                hit("Suvikõrvits roheline, kg", "kg", min_sale_qty=0.7, qty_increments=0.7, enable_qty_increments=True),
                hit("Lillkapsas, kg", "kg", min_sale_qty=1.2),
                hit("Ahjuköögiviljad, HÄRMAVILI, 700 g", "700 g"),
            ]}}

    monkeypatch.setattr(selver_api.requests, "post", lambda *a, **kw: Resp())
    found = selver_api.search_selver("köögiviljad")
    assert_product_contract(found, "selver")
    courgette, cauliflower, mix = found

    assert (courgette["unit"], courgette["min_qty"], courgette["qty_step"]) == ("kg", 0.7, 0.7)
    assert (cauliflower["min_qty"], cauliflower["qty_step"]) == (1.2, None)   # steps not enabled
    assert (mix["unit"], mix["min_qty"]) == (None, None)                      # a pack: one piece is no minimum weight


def test_selver_http_error_raises(monkeypatch):
    import requests
    from api import selver_api

    class Resp:
        status_code = 403

        def raise_for_status(self):
            raise requests.HTTPError("403 Forbidden")

    monkeypatch.setattr(selver_api.requests, "post", lambda *a, **kw: Resp())
    with pytest.raises(requests.HTTPError):
        selver_api.search_selver("piim")


# ── events ───────────────────────────────────────────────────────────────────

def test_log_event_writes_row(pg):
    assert events.log_event("accept", {"store": "rimi", "price": 8.6}, user_id="u1", session_id="s1")

    [row] = rows("SELECT user_id, session_id, type, data FROM events")
    assert row[:3] == ("u1", "s1", "accept")
    assert row[3] == {"store": "rimi", "price": 8.6, "country": "EE", "app_version": events.APP_VERSION, "internal": False}


def test_events_are_written_in_the_background_in_batches(pg):
    for i in range(250):
        events.log_event("visit", {"i": i}, user_id="u1")
    assert rows("SELECT count(*), count(DISTINCT data->>'i') FROM events") == [(250, 250)]


@pytest.mark.parametrize("user_id, name, internal", [
    ("andrea", None, True), ("Andrea", None, True),          # the founder's tester link
    ("3f1c…uuid", "andrea", True), ("3f1c…uuid", " Andrea ", True),  # the founder on a new device
    ("claude-check", None, True), ("internal-claude-check", None, True),
    ("3f1c…uuid", "Mari", False), ("mari", None, False), ("andreas", None, False),
])
def test_internal_people_are_flagged_and_the_name_isnt_stored(pg, user_id, name, internal):
    events.log_event("visit", {}, user_id=user_id, name=name)
    [(data,)] = rows("SELECT data FROM events")
    assert data["internal"] is internal
    assert name is None or name.strip() not in str(data)


def test_every_event_the_code_logs_is_listed():
    import pathlib, re
    root = pathlib.Path(__file__).resolve().parent.parent
    code = "".join(p.read_text() for d in ("web/js", "api", "core") for p in (root / d).rglob("*.[jp][sy]"))
    used = set(re.findall(r'logEvent\("([a-z_]+)"', code)) | set(re.findall(r'log_event\(\s*"([a-z_]+)"', code))
    used |= {"accept", "reject"}  # logged from the buttons' data-fb
    assert used - set(events.EVENT_TYPES) == set(), "add new events to core/events.py EVENT_TYPES"
    assert {"usual_store", "delete_request"} <= set(events.EVENT_TYPES)


def test_log_event_never_raises(pg, monkeypatch, capsys):
    def down():
        raise RuntimeError("database down")
    monkeypatch.setattr(db, "connection", down)
    assert events.log_event("visit", {}) is True  # queued: the request goes on
    assert events.flush()
    assert "event logging failed (1 events): database down" in capsys.readouterr().out
    monkeypatch.delenv("DATABASE_URL")
    assert events.log_event("visit", {}) is False  # no database at all


# ── barbora parser ───────────────────────────────────────────────────────────

def test_barbora_reads_embedded_product_list(monkeypatch):
    from api import barbora_api

    class Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        # Shape of the Remix search page since Oct 2026: categories in the main layout's data,
        # products ("inventories") in the search route's data, linked by categoryShortId.
        tree = [{"shortId": "A", "name": "", "names": [{"language": "et", "name": "Piimatooted ja munad"}],
                 "children": [{"shortId": "B", "name": "", "names": [{"language": "et", "name": "Munad"}],
                               "children": [{"shortId": "C", "name": "Kanamunad", "children": []}]}]},
                {"shortId": "V", "name": "Köögiviljad", "children": []}]
        inventories = [
            {"id": "1", "title": "Kanamunad M 10tk", "price": 1.79, "brand": "MUNAKOOK", "categoryShortId": "C",
             "unit": {"type": "units", "min": 1, "step": 1}, "comparativeUnit": {"type": "tk", "price": 0.18},
             "status": "active", "promotion": {"oldPrice": 1.99, "loyaltyCardRequired": False,
                                               "validTo": "2026-10-26T00:00:00Z"}},
            {"id": "2", "title": "Sibul, kg", "price": 0.39, "categoryShortId": "V",
             "unit": {"type": "kg", "min": 0.5, "step": 0.1}, "status": "outOfStock", "promotion": None},
        ]
        context = {"state": {"loaderData": {
            "routes/($lang)._._main_layout": {"dehydratedState": {"queries": [{"state": {"data": {"categories": tree}}}]}},
            "routes/($lang)._._main_layout.search": {"dehydratedState": {"queries": [
                {"state": {"data": {"inventories": inventories, "count": 2}}}]}},
        }}}
        text = f"<script>window.__remixContext = {json.dumps(context)};</script>"

    monkeypatch.setattr(barbora_api.requests, "get", lambda *a, **kw: Resp())
    found = barbora_api.search_barbora("munad")
    assert_product_contract(found, "barbora")
    eggs, onion = found

    assert (eggs["name"], eggs["price"], eggs["unit"], eggs["in_stock"]) == ("Kanamunad M 10tk", 1.79, "tk", True)
    assert (eggs["regular_price"], eggs["deal_until"], eggs["unit_price"]) == (1.99, "2026-10-26", 0.18)
    assert eggs["category"] == ["Piimatooted ja munad", "Munad", "Kanamunad"]
    assert eggs["shelf"] == "Kanamunad" and eggs["brand"] == "MUNAKOOK"
    assert (onion["unit"], onion["in_stock"], onion["category"]) == ("kg", False, ["Köögiviljad"])
    assert (onion["min_qty"], onion["qty_step"]) == (0.5, 0.1)
    assert eggs["min_qty"] is None  # sold by the piece: no minimum weight


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
    monkeypatch.setattr(fetch, "connector", lambda store: lambda q, **kw: calls.append(q) or [])
    fetch._cached_fetch("teststore", "uncached-query")
    fetch._cached_fetch("teststore", "uncached-query")
    assert len(calls) == 2


# ── discounts in adapters ────────────────────────────────────────────────────

@pytest.mark.parametrize("item, expected", [
    ({"price": 1.39, "retail_price": 1.39}, (1.39, None, None, None)),
    ({"price": 1.39, "promotion": {"oldPrice": 1.58, "loyaltyCardRequired": False, "minQuantity": 1}}, (1.39, 1.58, None, None)),
    # card-only: Barbora's price is the card price, the public price is the old one
    ({"price": 7.99, "promotion": {"oldPrice": 10.69, "loyaltyCardRequired": True, "minQuantity": 1}}, (10.69, None, 7.99, None)),
    # multi-buy: one item costs the old price
    ({"price": 1.0, "promotion": {"oldPrice": 1.5, "loyaltyCardRequired": False, "minQuantity": 3}}, (1.5, None, None, "3 or more: 1.00 € each")),
])
def test_barbora_prices(item, expected):
    from api.barbora_api import _prices
    assert _prices(item) == expected


def test_rimi_parses_regular_price_and_multibuy(monkeypatch):
    html = """
    <div data-product-code="1"><p class="card__name">Jogurt Alma 370g</p>
      <div class="price-tag card__price"><span class="sr-only">1.29 € per pcs.</span></div>
      <div class="card__old-price">Regular price: 1,69 € 1,69€</div></div>
    <div data-product-code="2"><p class="card__name">Riivjuust Rimi 80g</p>
      <div class="price-label"><span>2 and more</span> <span>-23%</span> 1 19 €</div>
      <div class="price-tag card__price"><span class="sr-only">1.55 € per pcs.</span></div></div>
    """

    class Resp(RimiResp):
        text = html

    monkeypatch.setattr(rimi_api.requests, "get", lambda *a, **kw: Resp())
    yogurt, cheese = rimi_api.search_rimi("x")
    assert (yogurt["price"], yogurt["regular_price"], yogurt["deal"]) == (1.29, 1.69, None)
    assert (cheese["price"], cheese["regular_price"], cheese["deal"]) == (1.55, None, "2 or more: −23%")


# ── "Make it yours" (WEB-38) ─────────────────────────────────────────────────

def test_any_dinner_can_be_copied_as_typed_items(pg):
    from fastapi import HTTPException
    from api import service
    classic = service.copy_recipe("kanasupp")
    assert classic["from"] == "kanasupp" and classic["name"] == "Kanasupp" and classic["servings"] == 2
    assert classic["items"] and all(isinstance(i, str) and i for i in classic["items"])
    assert classic["method"].startswith("1. Put the chicken legs") and classic["image"] == ""  # the method comes along
    dish = service.copy_recipe(catalog.load_dishes()["dishes"][0]["id"])
    assert dish["items"]
    with pytest.raises(HTTPException) as refused:
        service.copy_recipe("nope")
    assert refused.value.status_code == 404
