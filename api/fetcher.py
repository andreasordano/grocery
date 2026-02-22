import json
import os
from api.selver_api import search_selver
from api.barbora_api import search_barbora
from api.rimi_api import search_rimi
from core import db
from catalog import normalize_catalog


STORE_SEARCH = {
    "selver": search_selver,
    "barbora": search_barbora,
    "rimi": lambda q, size=40: search_rimi(q, page=0),
}


def build_product_id(store: str, remote_id: str, name: str) -> str:
    base = f"{store}-{remote_id or name}"
    return base.replace(" ", "-").lower()


def fetch_and_upsert(normalized_path=None, stores=None, limit=None):
    if normalized_path is None:
        normalized_path = os.path.join(os.path.dirname(__file__), "..", "catalog", "normalized_catalog.json")
        normalized_path = os.path.normpath(normalized_path)
    if stores is None:
        stores = list(STORE_SEARCH.keys())

    with open(normalized_path, "r", encoding="utf-8") as f:
        items = json.load(f)

    db.create_tables()
    session = db.SessionLocal()
    touched = 0

    try:
        for i, prod in enumerate(items):
            if limit and i >= limit:
                break
            q = prod.get("name")
            for store in stores:
                try:
                    results = STORE_SEARCH[store](q, size=40)
                except Exception as e:
                    print(f"Error fetching {q} from {store}: {e}")
                    continue
                for r in results:
                    remote_id = r.get("id") or r.get("sku") or r.get("code")
                    pid = build_product_id(store, remote_id, r.get("name"))
                    record = {
                        "product_id": pid,
                        "name": r.get("name") or q,
                        "price": r.get("price"),
                        "unit": r.get("unit") or r.get("volume") or None,
                        "store": store,
                        "category": prod.get("category", "uncategorized"),
                        "metadata": r,
                    }
                    db.upsert_product(session, record)
                    touched += 1
    finally:
        session.close()

    return touched


if __name__ == "__main__":
    n = fetch_and_upsert(limit=200)
    print(f"Upserted {n} products")
