# =============================================================================
# PRICE LOG  (DATA-2: "log, don't curate")
# Every fresh store search becomes a collection run, its products are upserted into
# retailer_products, and a price observation is added when it's the product's first
# sighting that day (Estonian time) or its price, offer or availability changed.
# Writes happen on one background thread, so a user's answer never waits for them,
# and failures are printed, never raised. Postgres (core/db.py); PRICE_LOG=0 turns it off.
# The same writer keeps each search's latest answer in search_cache, so a restart starts with a warm cache.
# =============================================================================

import os
import queue
import threading
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import requests

from psycopg.types.json import Jsonb

from core import db
from core.scoring import pack_size, parse_price

MIGRATION = Path(__file__).resolve().parent.parent / "supabase" / "migrations" / "20261022215556_price_log.sql"  # tests

_queue = queue.Queue(maxsize=1000)
_start_lock = threading.Lock()
_started = False



def enabled():
    return db.configured() and os.environ.get("PRICE_LOG", "1") == "1"


def record(store, query, kind, started_at, products=None, error=None):
    """Queue one store search for the log: its products, or the exception it raised."""
    if not enabled():
        return
    try:
        _ensure_writer()
        _queue.put_nowait((store, query, kind, started_at, datetime.now(timezone.utc), products, error))
    except queue.Full:
        print(f"price log queue full, dropped {store}/{query}")
    except Exception as exc:
        print(f"price log failed ({store}/{query}): {exc}")


def classify(error):
    """(status, http_status) for a failed search."""
    if isinstance(error, requests.Timeout):
        return "timeout", None
    if isinstance(error, requests.HTTPError) and error.response is not None:
        code = error.response.status_code
        return ("blocked" if code in (401, 403, 429) else "http_error"), code
    if isinstance(error, requests.RequestException):
        return "http_error", None
    return "parse_error", None


def _num(value):
    p = parse_price(value)
    return None if p == float("inf") else round(p, 4)


def product_id(item):
    pid = item.get("sku") or item.get("id") or item.get("code")
    return str(pid) if pid else None


def pack(item):
    """(sold_by, pack_qty, pack_unit). Loose goods are sold by kg or l and have no pack size."""
    unit = (item.get("unit") or "").lower()
    if unit in ("kg", "l"):
        return unit, None, None
    size = pack_size(item.get("name") or "", item.get("volume"))
    return ("pack", *size) if size else ("pack", None, None)


def product_row(item):
    """retailer_products fields from a store adapter's product, or None without an id or name."""
    pid, name = product_id(item), (item.get("name") or "").strip()
    if not pid or not name:
        return None
    sold_by, qty, qty_unit = pack(item)
    return {
        "retailer_product_id": pid,
        "name": name,
        "brand": item.get("brand") or None,
        "ean": str(item["ean"]).strip() if item.get("ean") else None,
        "pack_qty": qty,
        "pack_unit": qty_unit,
        "sold_by": sold_by,
        "category_path": " > ".join(item.get("category") or []) or None,
        "url": item.get("url"),
        "image_url": item.get("image"),
    }


def observation(item, product, rank):
    """price_observations fields for one product in a search answer."""
    price = _num(item.get("price"))
    unit_price = unit_basis = None
    if price is not None:
        if product["sold_by"] in ("kg", "l"):
            unit_price, unit_basis = price, product["sold_by"]
        elif product["pack_qty"]:
            per, unit_basis = {"g": (1000, "kg"), "ml": (1000, "l"), "pcs": (1, "pcs")}[product["pack_unit"]]
            unit_price = round(price / product["pack_qty"] * per, 4)
    in_stock = item.get("in_stock")
    return {
        "retailer_product_id": product["retailer_product_id"],
        "price": price,
        "regular_price": _num(item.get("regular_price")),
        "card_price": _num(item.get("card_price")),
        "promo_text": item.get("deal") or None,
        "promo_until": item.get("deal_until") or None,
        "unit_price": unit_price,
        "unit_basis": unit_basis,
        "availability": "unknown" if in_stock is None else ("in_stock" if in_stock else "out_of_stock"),
        "search_rank": rank,
    }


_SIGNATURE = ("price", "regular_price", "card_price", "promo_text", "availability")


def changed(previous, obs):
    """Whether obs is worth a row: no observation today yet (previous is None), or something moved."""
    if previous is None:
        return True
    def norm(v):
        return round(float(v), 2) if isinstance(v, (int, float, Decimal)) else v
    return any(norm(previous[k]) != norm(obs[k]) for k in _SIGNATURE)


def rows(products):
    """Deduplicated (product, observation) pairs in search order; the first rank wins."""
    out, seen = [], set()
    for rank, item in enumerate(products or [], start=1):
        product = product_row(item)
        if product is None or product["retailer_product_id"] in seen:
            continue
        seen.add(product["retailer_product_id"])
        out.append((product, observation(item, product, rank)))
    return out


# ── writer ────────────────────────────────────────────────────────────────────

def _ensure_writer():
    global _started
    if _started:
        return
    with _start_lock:
        if not _started:
            threading.Thread(target=_writer, name="price-log", daemon=True).start()
            _started = True


def _writer():
    while True:
        job = _queue.get()
        try:
            with db.connection() as conn:
                write(conn, *job)
        except Exception as exc:
            print(f"price log write failed ({job[0]}/{job[1]}): {exc}")
        save_search(*job)


_save_failed = False


def save_search(store, query, kind, started_at, finished_at, products, error):
    """Keep a successful answer for restarts (search_cache, read by fetch.load_saved_searches): the latest per
    store and query, as the cache keeps it. Its own transaction, so a problem here never loses the price log."""
    global _save_failed
    if error is not None or not products:
        return
    try:
        with db.connection() as conn:
            conn.execute("INSERT INTO search_cache (retailer, query, fetched_at, products) VALUES (%s, %s, %s, %s) "
                         "ON CONFLICT (retailer, query) DO UPDATE SET fetched_at = EXCLUDED.fetched_at, products = EXCLUDED.products",
                         (store, query.strip().lower(), finished_at, Jsonb(products)))
        _save_failed = False
    except Exception as exc:
        if not _save_failed:  # once, not for every search (e.g. before the table's migration)
            print(f"saving searches for restarts failed: {exc}")
        _save_failed = True


def write(conn, store, query, kind, started_at, finished_at, products, error):
    """One collection run with its products and changed observations, in one transaction."""
    status, http_status = (("ok" if products else "empty"), None) if error is None else classify(error)
    pairs = rows(products) if error is None else []
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO collection_runs (retailer, kind, query, started_at, finished_at, status,
                                            http_status, n_products, error)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (store, kind, query, started_at, finished_at, status, http_status, len(products or []),
             str(error)[:500] if error is not None else None),
        )
        run_id = cur.fetchone()[0]
        if pairs:
            cur.executemany(
                """INSERT INTO retailer_products AS rp (retailer, retailer_product_id, name, brand, ean, pack_qty,
                       pack_unit, sold_by, category_path, url, image_url, first_seen_at, last_seen_at)
                   VALUES (%(retailer)s, %(retailer_product_id)s, %(name)s, %(brand)s, %(ean)s, %(pack_qty)s,
                       %(pack_unit)s, %(sold_by)s, %(category_path)s, %(url)s, %(image_url)s, %(seen)s, %(seen)s)
                   ON CONFLICT (retailer, retailer_product_id) DO UPDATE SET
                       name = EXCLUDED.name,
                       brand = COALESCE(EXCLUDED.brand, rp.brand),
                       ean = COALESCE(EXCLUDED.ean, rp.ean),
                       pack_qty = EXCLUDED.pack_qty,
                       pack_unit = EXCLUDED.pack_unit,
                       sold_by = EXCLUDED.sold_by,
                       category_path = COALESCE(EXCLUDED.category_path, rp.category_path),
                       url = COALESCE(EXCLUDED.url, rp.url),
                       image_url = COALESCE(EXCLUDED.image_url, rp.image_url),
                       last_seen_at = GREATEST(rp.last_seen_at, EXCLUDED.last_seen_at)""",
                [{**p, "retailer": store, "seen": finished_at} for p, _ in pairs],
            )
            # Latest observation per product, only if it was made today in Estonia.
            cur.execute(
                f"""SELECT DISTINCT ON (retailer_product_id) retailer_product_id, {", ".join(_SIGNATURE)},
                           (observed_at AT TIME ZONE 'Europe/Tallinn')::date
                             = (%s::timestamptz AT TIME ZONE 'Europe/Tallinn')::date AS today
                    FROM price_observations
                    WHERE retailer = %s AND retailer_product_id = ANY(%s)
                    ORDER BY retailer_product_id, observed_at DESC""",
                (finished_at, store, [p["retailer_product_id"] for p, _ in pairs]),
            )
            cols = [d.name for d in cur.description]
            latest = {r[0]: dict(zip(cols, r)) for r in cur.fetchall()}
            new = []
            for _, obs in pairs:
                prev = latest.get(obs["retailer_product_id"])
                if changed(prev if prev and prev["today"] else None, obs):
                    new.append({**obs, "run_id": run_id, "retailer": store, "observed_at": finished_at})
            if new:
                cur.executemany(
                    """INSERT INTO price_observations (run_id, retailer, retailer_product_id, observed_at, price,
                           regular_price, card_price, promo_text, promo_until, unit_price, unit_basis,
                           availability, search_rank)
                       VALUES (%(run_id)s, %(retailer)s, %(retailer_product_id)s, %(observed_at)s, %(price)s,
                           %(regular_price)s, %(card_price)s, %(promo_text)s, %(promo_until)s, %(unit_price)s,
                           %(unit_basis)s, %(availability)s, %(search_rank)s)""",
                    new,
                )
    conn.commit()
