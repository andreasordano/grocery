"""The store registry (stores_config.py): one place that lists the stores, and the shape every connector returns."""
import inspect

import pytest

import stores_config
from core import catalog, fetch, price_log
from stores_config import PRODUCT_FIELDS, REQUIRED_FIELDS, STORES


def assert_product_contract(products, store):
    """A connector's products have the fields of stores_config.PRODUCT_FIELDS, and the required ones filled."""
    assert products, f"{store}: no products to check"
    for p in products:
        assert set(p) <= set(PRODUCT_FIELDS), f"{store}: unknown fields {set(p) - set(PRODUCT_FIELDS)}"
        missing = [f for f in REQUIRED_FIELDS if f not in p or (p[f] is None and f != "price")]
        assert not missing, f"{store}: {p.get('name')} lacks {missing}"
        assert p["store"] == store


@pytest.mark.parametrize("store", list(STORES))
def test_every_store_has_a_working_connector_and_a_known_chain(store):
    search = stores_config.connector(store)
    assert list(inspect.signature(search).parameters)[:2] == ["query", "limit"]
    assert STORES[store]["chain"] in stores_config.CHAINS
    assert stores_config.max_concurrency(store) >= 1


@pytest.mark.parametrize("store", stores_config.dinner_stores())
def test_every_dinner_store_has_a_rule_for_every_ingredient(store):
    rules = catalog.load_rules()
    missing = [key for key in catalog.load_recipes()["ingredients"] if store not in (rules.get(key) or {})]
    assert not missing, f"{store} has no rule for {missing}"


def test_store_names_come_from_the_registry():
    assert stores_config.display_name("barbora") == "Maxima" and stores_config.display_name("rimi") == "Rimi"
    page = stores_config.public()
    assert page["stores"]["barbora"] == {"name": "Barbora", "chain": "maxima", "shown_as": "Maxima", "card": "Aitäh kaart"}
    assert page["stores"]["rimi"]["card"] is None  # no card prices
    assert page["chains"] == stores_config.CHAINS


def test_a_new_store_needs_only_its_connector_and_an_entry(monkeypatch):
    """What adding a store takes: a connector in the contract's shape and one registry entry."""
    def search_coop(query, limit=40):
        return [{"store": "coop", "store_id": "c1", "name": f"{query} 500g", "price": 1.5, "in_stock": True}]
    monkeypatch.setitem(STORES, "coop", {"name": "Coop", "chain": "coop", "connector": "x.search_coop",
                                         "max_concurrency": 2, "prices_dinners": False})
    monkeypatch.setitem(stores_config.CHAINS, "coop", "Coop")
    monkeypatch.setattr(fetch, "connector", lambda s: search_coop if s == "coop" else stores_config.connector(s))
    monkeypatch.setattr(price_log, "enabled", lambda: False)
    fetch._CACHE.clear()

    assert "coop" in stores_config.stores() and "coop" not in stores_config.dinner_stores()  # no rules yet
    assert stores_config.public()["stores"]["coop"]["shown_as"] == "Coop"
    products, _ = fetch.fetch_all({"kohv": fetch.spec_for("kohv")}, ["coop"])
    assert [(p["store"], p["store_id"]) for p in products["kohv"]] == [("coop", "c1")]
    fetch._CACHE.clear()
