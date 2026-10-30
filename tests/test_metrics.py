"""The validation metric views (DATA-6) and the analyst role (DATA-5), on a small made-up test group.
Needs a real Postgres: set TEST_DATABASE_URL, e.g. the docker-compose db."""

import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from core import events

MIGRATIONS = Path(__file__).resolve().parent.parent / "supabase" / "migrations"
VIEWS = MIGRATIONS / "20261025170000_metrics_views.sql"
ROLE = MIGRATIONS / "20261025170100_analyst_role.sql"

DAY0 = datetime.now(timezone.utc).replace(hour=9, minute=0, second=0, microsecond=0) - timedelta(days=10)


def basket(result_id, totals, latency=2.0, mission="dinner"):
    """A basket event's data: totals is {store: price or None (store can't make it)}."""
    return {"result_id": result_id, "mission": mission, "latency_s": latency,
            "recommended_store": min((s for s in totals if totals[s] is not None), key=totals.get, default=None),
            "baskets": [{"store": s, "status": "ok" if t is not None else "no_answer", "total_price": t}
                        for s, t in totals.items()]}


# (days after DAY0, user, type, data). anna comes back on her own; ben only through the newsletter;
# cara after a reminder; dan never gets an answer; eve's only answer has no viable store; andrea is internal.
STORY = [
    (0, "anna", "visit", {"from": "tester_link"}),
    (0, "anna", "usual_store", {"store": "rimi"}),
    (0, "anna", "basket", basket("a1", {"rimi": 10.0, "selver": 12.0, "barbora": 11.0}, latency=1.0)),
    (0, "anna", "accept", {"store": "rimi", "result_id": "a1"}),
    (2, "anna", "basket", basket("a2", {"rimi": 5.0, "selver": 5.5}, latency=3.0, mission="dinners")),
    (0, "ben", "usual_store", {"store": "rimi"}),
    (0, "ben", "basket", basket("b1", {"rimi": 8.0, "selver": 7.0}, latency=2.0)),
    (0, "ben", "accept", {"store": "selver", "result_id": "b1"}),
    (1, "ben", "visit", {"from": "newsletter"}),
    (1, "ben", "basket", basket("b2", {"selver": 4.0}, latency=2.0)),
    (0, "cara", "basket", basket("c1", {"rimi": 6.0}, latency=4.0, mission="list")),
    (3, "cara", "basket", basket("c2", {"rimi": 6.0}, latency=5.0)),
    (0, "dan", "visit", {"from": "tester_link"}),
    (0, "eve", "usual_store", {"store": "maxima"}),
    (0, "eve", "basket", basket("e1", {"rimi": None, "selver": None}, latency=9.0)),
    (0, "eve", "accept", {"store": "barbora", "result_id": "e1"}),
    (0, "andrea", "basket", basket("x1", {"rimi": 1.0})),
    (5, "andrea", "basket", basket("x2", {"rimi": 1.0})),
]


@pytest.fixture
def pg():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    import psycopg
    schema = f"test_metrics_{uuid.uuid4().hex[:8]}"
    conn = psycopg.connect(url)
    conn.execute(f"CREATE SCHEMA {schema}")
    conn.execute(f"SET search_path TO {schema}")
    conn.execute("CREATE TABLE events (id BIGSERIAL PRIMARY KEY, ts TIMESTAMPTZ NOT NULL, user_id TEXT, session_id TEXT, "
                 "type TEXT NOT NULL, data JSONB)")  # as in the first migration
    for days, user, type_, data in STORY:
        at = DAY0 + timedelta(days=days, minutes=len(conn.execute("SELECT 1 FROM events").fetchall()))
        conn.execute("INSERT INTO events (ts, user_id, type, data) VALUES (%s, %s, %s, %s::jsonb)",
                     (at, user, type_, json.dumps({**data, "internal": events.is_internal(user)})))
    # the views live in their own schema on Supabase; here everything goes into the test schema
    conn.execute(re.sub(r"\bmetrics\b", schema, VIEWS.read_text()))
    conn.execute(f"SET search_path TO {schema}")
    conn.execute("INSERT INTO nudges (ts, user_id, channel) VALUES (%s, 'cara', 'whatsapp')", (DAY0 + timedelta(days=1),))
    conn.commit()
    yield conn, schema
    conn.rollback()
    conn.execute(f"DROP SCHEMA {schema} CASCADE")
    conn.commit()
    conn.close()


def row(conn, view):
    cur = conn.execute(f"SELECT * FROM {view}")
    return {c.name: float(v) if isinstance(v, Decimal) else v for c, v in zip(cur.description, cur.fetchone())}


def test_internal_people_are_left_out(pg):
    conn, _ = pg
    assert {r[0] for r in conn.execute("SELECT user_id FROM testers")} == {"anna", "ben", "cara", "dan", "eve"}
    assert conn.execute("SELECT count(*) FROM answers WHERE user_id = 'andrea'").fetchone()[0] == 0


def test_activation(pg):
    assert row(pg[0], "activation") == {"testers": 5, "activated": 4, "share": pytest.approx(0.8)}


def test_return_counts_only_unprompted_answers_on_a_later_day(pg):
    conn, _ = pg
    per = {r[0]: r[1:] for r in conn.execute("SELECT user_id, returned_unprompted, returned_any FROM return_7d")}
    assert per == {"anna": (True, True), "ben": (False, True), "cara": (False, True), "eve": (False, False)}
    band = row(conn, "return_7d_band")
    assert (band["activated_complete"], band["returned"], band["band"]) == (4, 1, "EXTEND TO 50 TESTERS")


def test_band_waits_for_complete_windows(pg):
    conn, _ = pg
    conn.execute("UPDATE events SET ts = ts + interval '8 days'")
    assert row(conn, "return_7d_band")["band"] == "NO DATA YET"


def test_acceptance_store_switch_and_no_result(pg):
    conn, _ = pg
    assert row(conn, "acceptance") == {"answers": 7, "accepted": 3, "share": pytest.approx(0.429)}
    # anna stays at Rimi, ben switches from Rimi to Selver, eve's Barbora answer stands for her usual Maxima
    assert row(conn, "store_switch") == {"accepts_with_usual_store": 3, "switched": 1, "share": pytest.approx(0.333)}
    assert row(conn, "no_result") == {"answers": 7, "no_result": 1, "share": pytest.approx(0.143)}


def test_answer_time_gap_and_entry_point(pg):
    conn, _ = pg
    t = row(conn, "answer_time")
    assert (t["answers"], t["median_s"]) == (7, 3.0)
    gap = row(conn, "store_gap")
    assert (gap["answers"], float(gap["median_gap_eur"])) == (3, 1.0)  # gaps: anna 1.0 and 0.5, ben 1.0
    assert dict(conn.execute("SELECT mission, answers FROM entry_point")) == {"dinner": 5, "dinners": 1, "list": 1}


def test_weekly_cohorts_count_each_tester_once_per_week(pg):
    conn, _ = pg
    rows = conn.execute("SELECT week_n, sum(active_testers) FROM weekly_cohorts GROUP BY week_n ORDER BY week_n").fetchall()
    assert rows[0][1] == 4 and sum(r[1] for r in rows) >= 4


def test_analyst_reads_the_views_and_writes_nothing(pg):
    conn, schema = pg
    conn.execute(re.sub(r"\bmetrics\b", schema, ROLE.read_text()))
    conn.execute("SET ROLE analyst")
    assert row(conn, "activation")["testers"] == 5
    import psycopg
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("INSERT INTO nudges (user_id, channel) VALUES ('x', 'y')")


def test_analyst_can_read_every_table(test_database_url):
    """A new table needs its own grant and policy for the analyst (as in the plans migration), or pgweb can't read it."""
    import psycopg
    with psycopg.connect(test_database_url) as conn:
        missing = [r[0] for r in conn.execute(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relrowsecurity "
            "AND NOT (has_table_privilege('analyst', c.oid, 'SELECT') AND EXISTS ("
            "    SELECT FROM pg_policies p WHERE p.schemaname = 'public' AND p.tablename = c.relname "
            "    AND p.policyname = 'analyst_reads'))")]
    assert missing == []
