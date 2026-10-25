import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import requests

from core import fetch, price_log


SELVER_MILK = {"store": "selver", "name": "Piim 2,5%, 1 L", "price": 1.19, "regular_price": 1.49,
               "deal_until": "2026-10-26", "store_id": "T000123", "ean": 4740125000016, "brand": "Alma",
               "volume": "1 l", "unit": None, "category": ["Piimatooted", "Piim"], "in_stock": True}
BARBORA_CHEESE = {"store": "barbora", "name": "Juust Eesti 400 g", "price": 4.29, "card_price": 3.49,
                  "store_id": "998877", "unit": "tk", "category": ["Piimatooted", "Juust"], "in_stock": True}
RIMI_APPLES = {"store": "rimi", "name": "Õunad Gala", "price": 2.49, "unit": "kg", "store_id": "123456",
               "category": ["SH-1-2"], "in_stock": True}
RIMI_SOLD_OUT = {"store": "rimi", "name": "Munad 10 tk", "price": None, "store_id": "777", "in_stock": False}


# ── rows from adapter output ────────────────────────────────────────────────

def test_selver_product_keeps_ean_and_pack_size():
    p = price_log.product_row(SELVER_MILK)
    assert p["retailer_product_id"] == "T000123"
    assert p["ean"] == "4740125000016"
    assert (p["sold_by"], p["pack_qty"], p["pack_unit"]) == ("pack", 1000.0, "ml")
    assert p["category_path"] == "Piimatooted > Piim"


def test_observation_prices_per_unit_and_keeps_discounts():
    obs = price_log.observation(SELVER_MILK, price_log.product_row(SELVER_MILK), 3)
    assert (obs["price"], obs["regular_price"], obs["promo_until"]) == (1.19, 1.49, "2026-10-26")
    assert (obs["unit_price"], obs["unit_basis"]) == (1.19, "l")
    assert obs["availability"] == "in_stock" and obs["search_rank"] == 3

    cheese = price_log.observation(BARBORA_CHEESE, price_log.product_row(BARBORA_CHEESE), 1)
    assert (cheese["unit_price"], cheese["unit_basis"], cheese["card_price"]) == (10.725, "kg", 3.49)


def test_loose_goods_are_sold_by_weight_without_pack_size():
    p = price_log.product_row(RIMI_APPLES)
    assert (p["sold_by"], p["pack_qty"]) == ("kg", None)
    obs = price_log.observation(RIMI_APPLES, p, 1)
    assert (obs["unit_price"], obs["unit_basis"]) == (2.49, "kg")


def test_sold_out_product_is_observed_without_price():
    p = price_log.product_row(RIMI_SOLD_OUT)
    assert (p["pack_qty"], p["pack_unit"]) == (10, "pcs")
    obs = price_log.observation(RIMI_SOLD_OUT, p, 1)
    assert obs["price"] is None and obs["unit_price"] is None and obs["availability"] == "out_of_stock"


def test_rows_skip_products_without_id_and_keep_first_rank():
    nameless = {"name": "", "store_id": "X1", "price": 1}
    pairs = price_log.rows([SELVER_MILK, nameless, {**SELVER_MILK, "price": 0.99}, {"name": "No id", "price": 2}])
    assert [(p["retailer_product_id"], o["search_rank"], o["price"]) for p, o in pairs] == [("T000123", 1, 1.19)]


# ── what is worth a new observation ─────────────────────────────────────────

def test_changed_only_when_first_today_or_something_moved():
    obs = price_log.observation(SELVER_MILK, price_log.product_row(SELVER_MILK), 1)
    same = {"price": Decimal("1.19"), "regular_price": Decimal("1.49"), "card_price": None,
            "promo_text": None, "availability": "in_stock"}
    assert price_log.changed(None, obs)
    assert not price_log.changed(same, obs)
    assert price_log.changed({**same, "price": Decimal("1.29")}, obs)
    assert price_log.changed({**same, "availability": "out_of_stock"}, obs)
    assert price_log.changed({**same, "regular_price": None}, obs)


@pytest.mark.parametrize("error, expected", [
    (requests.Timeout("slow"), ("timeout", None)),
    (requests.ConnectionError("down"), ("http_error", None)),
    (RuntimeError("Barbora search page has no product list"), ("parse_error", None)),
])
def test_classify_plain_errors(error, expected):
    assert price_log.classify(error) == expected


@pytest.mark.parametrize("code, status", [(403, "blocked"), (429, "blocked"), (500, "http_error")])
def test_classify_http_errors(code, status):
    resp = requests.Response()
    resp.status_code = code
    assert price_log.classify(requests.HTTPError(response=resp)) == (status, code)


# ── hook in the fetch path ──────────────────────────────────────────────────

@pytest.fixture
def recorded(monkeypatch):
    calls = []
    monkeypatch.setattr(price_log, "record", lambda *a, **kw: calls.append((a, kw)))
    fetch._CACHE.clear()
    yield calls
    fetch._CACHE.clear()


def test_fresh_fetch_is_recorded_and_cache_hit_is_not(recorded, monkeypatch):
    monkeypatch.setattr(fetch, "connector", lambda store: lambda q, **kw: [SELVER_MILK])
    fetch._cached_fetch("selver", "piim")
    fetch._cached_fetch("selver", "piim")
    fetch._cached_fetch("selver", "piim", refresh=True)
    assert [(a[0], a[1], a[2]) for a, _ in recorded] == [("selver", "piim", "search"), ("selver", "piim", "refresh")]
    assert recorded[0][1]["products"] == [SELVER_MILK]


def test_failed_fetch_is_recorded_and_still_raises(recorded, monkeypatch):
    def blocked(q, **kw):
        raise RuntimeError("blocked")
    monkeypatch.setattr(fetch, "connector", lambda store: blocked)
    with pytest.raises(RuntimeError):
        fetch._cached_fetch("selver", "piim")
    assert isinstance(recorded[0][1]["error"], RuntimeError)


def test_record_is_a_no_op_without_postgres(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(price_log, "_ensure_writer", lambda: pytest.fail("writer started"))
    price_log.record("selver", "piim", "search", datetime.now(timezone.utc), products=[SELVER_MILK])


# ── writer against a real Postgres (set TEST_DATABASE_URL, e.g. the docker-compose db) ──

@pytest.fixture
def pg():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    import psycopg
    schema = f"test_price_log_{uuid.uuid4().hex[:8]}"
    conn = psycopg.connect(url)
    conn.execute(f"CREATE SCHEMA {schema}")
    conn.execute(f"SET search_path TO {schema}")
    conn.execute(price_log.MIGRATION.read_text())
    conn.commit()
    yield conn
    conn.rollback()
    conn.execute(f"DROP SCHEMA {schema} CASCADE")
    conn.commit()
    conn.close()


def _counts(conn):
    return tuple(conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                 for t in ("collection_runs", "retailer_products", "price_observations"))


def test_writer_logs_runs_and_only_changed_observations(pg):
    now = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)
    price_log.write(pg, "selver", "piim", "search", now, now, [SELVER_MILK], None)
    price_log.write(pg, "selver", "piim", "refresh", now, now + timedelta(hours=5), [SELVER_MILK], None)
    assert _counts(pg) == (2, 1, 1)  # same price the same day: no new observation

    price_log.write(pg, "selver", "piim", "refresh", now, now + timedelta(hours=6), [{**SELVER_MILK, "price": 1.29}], None)
    price_log.write(pg, "selver", "piim", "refresh", now, now + timedelta(days=1), [{**SELVER_MILK, "price": 1.29}], None)
    assert _counts(pg) == (4, 1, 3)  # a price change, then the next day's first sighting

    ean, last_seen = pg.execute("SELECT ean, last_seen_at FROM retailer_products").fetchone()
    assert ean == "4740125000016" and last_seen == now + timedelta(days=1)


def test_writer_logs_failed_runs_without_products(pg):
    now = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)
    resp = requests.Response()
    resp.status_code = 403
    price_log.write(pg, "selver", "piim", "search", now, now, None, requests.HTTPError("403 Forbidden", response=resp))
    price_log.write(pg, "rimi", "zzz", "search", now, now, [], None)
    runs = pg.execute("SELECT retailer, status, http_status, n_products FROM collection_runs ORDER BY id").fetchall()
    assert runs == [("selver", "blocked", 403, 0), ("rimi", "empty", None, 0)]
    assert _counts(pg)[1:] == (0, 0)
