
# This module handles database interactions using SQLAlchemy. 
# It provides functions to create tables, upsert products, and load JSON data into the database.
# It runs after the initial data parsing and before the scoring and optimization phases, which rely on this structured product data.
# =============================================================================

import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from .models import Base, Product


DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///groceries.db")


engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_tables():
    Base.metadata.create_all(bind=engine)
    # ensure legacy DB has `macro` column
    ensure_macro_column()


def upsert_product(session, product_data: dict):
    pid = product_data.get("product_id")
    if not pid:
        return None
    obj = session.query(Product).filter_by(product_id=pid).first()
    if obj is None:
        obj = Product(
            product_id=pid,
            name=product_data.get("name"),
            price=product_data.get("price"),
            unit=product_data.get("unit"),
            store=product_data.get("store"),
            category=product_data.get("category"),
                macro=product_data.get("macro"),
                metadata_=product_data.get("metadata"),
        )
        session.add(obj)
    else:
        obj.name = product_data.get("name", obj.name)
        obj.price = product_data.get("price", obj.price)
        obj.unit = product_data.get("unit", obj.unit)
        obj.store = product_data.get("store", obj.store)
        obj.category = product_data.get("category", obj.category)
        obj.macro = product_data.get("macro", obj.macro)
        obj.metadata_ = product_data.get("metadata", obj.metadata_)
    session.commit()
    return obj


def load_json_into_db(json_path: str):
    import json
    from sqlalchemy.exc import SQLAlchemyError

    with open(json_path, "r", encoding="utf-8") as f:
        products = json.load(f)

    create_tables()
    # ensure macro column exists before inserting
    ensure_macro_column()
    session = SessionLocal()
    inserted = 0
    try:
        for p in products:
            upsert_product(session, p)
            inserted += 1
    except SQLAlchemyError:
        session.rollback()
        raise
    finally:
        session.close()

    return inserted


def ensure_macro_column():
    """Add `macro` column to products table if it doesn't exist.

    This helper inspects existing table columns and issues an ALTER TABLE
    to add the `macro` column when missing. Works for SQLite and Postgres.
    For other DBs a proper migration tool is recommended.
    """
    from sqlalchemy import inspect

    inspector = inspect(engine)
    if "products" not in inspector.get_table_names():
        return
    cols = [c["name"] for c in inspector.get_columns("products")]
    if "macro" in cols:
        return
    # add column using SQL that works for Postgres and SQLite
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE products ADD COLUMN macro VARCHAR;"))
            conn.commit()
        except Exception:
            # best-effort only; let higher-level code surface errors if persistent
            pass
