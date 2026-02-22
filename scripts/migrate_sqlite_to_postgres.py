import os
import sys
import json
import sqlite3

# Ensure project root is on sys.path so `from core import db` works inside container
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import db as core_db


def migrate(sqlite_path="/app/groceries.db"):
    if not os.path.exists(sqlite_path):
        print(f"No sqlite DB at {sqlite_path}; skipping migration")
        return 0

    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # check if products table exists
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='products'")
    if cur.fetchone() is None:
        print("No products table in sqlite DB; skipping")
        return 0

    cur.execute("SELECT product_id, name, price, unit, store, category, metadata FROM products")
    rows = cur.fetchall()
    if not rows:
        print("No rows found in sqlite products table")
        return 0

    print(f"Migrating {len(rows)} products from {sqlite_path} into Postgres")
    core_db.create_tables()
    session = core_db.SessionLocal()
    migrated = 0
    try:
        for r in rows:
            meta = r[6]
            try:
                metadata = json.loads(meta) if meta else None
            except Exception:
                metadata = None

            record = {
                "product_id": r[0],
                "name": r[1],
                "price": r[2],
                "unit": r[3],
                "store": r[4],
                "category": r[5] or "uncategorized",
                "metadata": metadata,
            }
            core_db.upsert_product(session, record)
            migrated += 1
    finally:
        session.close()
        conn.close()

    print(f"Migration complete: {migrated} rows upserted")
    return migrated


if __name__ == "__main__":
    migrate()
