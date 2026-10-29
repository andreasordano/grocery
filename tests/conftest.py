"""The test database: Postgres, like production (core/db.py).

TEST_DATABASE_URL names a Postgres server (default: the docker-compose db, `docker compose up -d db`).
The tests use their own database on it, <name>_test, created and migrated once (scripts/migrate.py), and
every test that asks for `pg` starts with empty tables.
"""
import os

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from core import db, events
from scripts.migrate import migrate

SERVER = os.environ.get("TEST_DATABASE_URL", "postgresql://groceries:groceries@localhost:5433/groceries")
TABLES = ("events, my_dinners, shares, plans, nudges, price_observations, retailer_products, collection_runs, search_cache, "
          "recipes")


@pytest.fixture(scope="session")
def test_database_url():
    params = conninfo_to_dict(SERVER)
    name = f"{params.get('dbname', 'postgres')}_test"
    try:
        with psycopg.connect(SERVER, autocommit=True) as conn:
            if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone():
                conn.execute(f'CREATE DATABASE "{name}"')
    except psycopg.OperationalError as exc:
        pytest.fail(f"No test database at {SERVER} ({exc}). Start it with `docker compose up -d db`, "
                    "or set TEST_DATABASE_URL.")
    url = make_conninfo(SERVER, dbname=name)
    migrate(url)
    return url


@pytest.fixture
def pg(test_database_url, monkeypatch):
    """The app's database, empty: DATABASE_URL points at the test database."""
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    db.reset()
    with psycopg.connect(test_database_url) as conn:
        conn.execute(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE")
    yield
    events.flush()
    db.reset()


def rows(sql, params=()):
    """Rows from the test database, after the queued events are written."""
    events.flush()
    return db.query(sql, params)
