# =============================================================================
# DATABASE  (Postgres, the only database)
# One connection pool for the whole app, from DATABASE_URL: production is Supabase's session pooler, local runs
# and tests use the docker-compose Postgres. Tables come only from supabase/migrations (production:
# `supabase db push`; local and tests: scripts/migrate.py), never from the app at runtime.
#   with db.connection() as conn: conn.execute(...)   # commits when the block ends, rolls back on an error
# =============================================================================

import os
import threading
from contextlib import contextmanager

_pool = None
_lock = threading.Lock()


def configured():
    return bool(os.environ.get("DATABASE_URL"))


def pool():
    global _pool
    with _lock:
        if _pool is None:
            from psycopg_pool import ConnectionPool  # only needed when the database is used
            # prepare_threshold=None: no server-side prepared statements, which the Supabase pooler can't share.
            _pool = ConnectionPool(os.environ["DATABASE_URL"], min_size=1, max_size=int(os.environ.get("DB_POOL_MAX", 5)),
                                   kwargs={"prepare_threshold": None}, timeout=10, open=True)
        return _pool


@contextmanager
def connection():
    """A connection from the pool, inside one transaction."""
    with pool().connection() as conn:
        yield conn


def query(sql, params=()):
    """All rows of one statement."""
    with connection() as conn:
        return conn.execute(sql, params).fetchall()


def reset():
    """Close the pool, so the next use connects to DATABASE_URL afresh (tests switch databases)."""
    global _pool
    with _lock:
        if _pool is not None:
            _pool.close()
            _pool = None
