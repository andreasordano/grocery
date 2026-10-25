"""How the app asks the stores (core/fetch.py): one request per search however many people ask at once, a cap on
requests per store, and answers kept across restarts (search_cache)."""
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from conftest import rows
from core import db, fetch, price_log


@pytest.fixture
def store(monkeypatch):
    """A fake store that takes a moment to answer and counts its requests."""
    calls, busy, peak = [], [0], [0]
    lock = threading.Lock()

    def search(query, limit=40):
        with lock:
            calls.append(query)
            busy[0] += 1
            peak[0] = max(peak[0], busy[0])
        time.sleep(0.05)
        with lock:
            busy[0] -= 1
        return [{"store": "fake", "store_id": query, "name": f"{query} 500g", "price": 1.0}]

    monkeypatch.setattr(fetch, "connector", lambda s: search)
    monkeypatch.setattr(fetch, "max_concurrency", lambda s: 2)
    monkeypatch.setattr(fetch, "_limits", {})
    monkeypatch.setattr(price_log, "enabled", lambda: False)
    fetch._CACHE.clear()
    yield {"calls": calls, "peak": peak}
    fetch._CACHE.clear()


def run_together(n, target):
    threads = [threading.Thread(target=target, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def test_the_same_search_asked_at_once_goes_to_the_store_once(store):
    answers = []
    run_together(8, lambda i: answers.append(fetch._cached_fetch("fake", "piim")))
    assert store["calls"] == ["piim"] and len(answers) == 8 and all(a == answers[0] for a in answers)


def test_each_store_gets_at_most_its_limit_of_requests_at_once(store):
    run_together(8, lambda i: fetch._cached_fetch("fake", f"toode{i}"))
    assert len(store["calls"]) == 8 and store["peak"][0] == 2


def test_a_restart_starts_with_the_saved_answers(store, pg):
    now = datetime.now(timezone.utc)
    price_log.save_search("fake", " Piim ", "search", now, now, [{"store_id": "1", "name": "Piim 1 l", "price": 1.19}], None)
    price_log.save_search("fake", "piim", "refresh", now, now, [{"store_id": "2", "name": "Piim 2 l", "price": 2.0}], None)  # newer wins
    price_log.save_search("fake", "vana", "search", now - timedelta(days=2), now - timedelta(days=2), [{"store_id": "3"}], None)
    price_log.save_search("fake", "tühi", "search", now, now, [], None)  # empty answers aren't kept
    assert rows("SELECT retailer, query FROM search_cache ORDER BY query") == [("fake", "piim"), ("fake", "vana")]

    assert fetch.load_saved_searches() == 1  # the two-day-old one is past the cache's lifetime
    assert fetch._cached_fetch("fake", "piim") == [{"store_id": "2", "name": "Piim 2 l", "price": 2.0}]
    assert store["calls"] == []  # answered from the saved search


def test_saved_searches_are_skipped_without_the_table(store, pg, monkeypatch, capsys):
    monkeypatch.setattr(db, "query", lambda *a: (_ for _ in ()).throw(RuntimeError('relation "search_cache" does not exist')))
    assert fetch.load_saved_searches() == 0
    assert "saved searches not loaded" in capsys.readouterr().out
