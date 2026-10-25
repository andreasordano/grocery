"""Selver's search request (api/selver_api.py), without the internet."""
import pytest

from api import selver_api


@pytest.mark.parametrize("typed, sent", [
    ("sai/leib", r"sai\/leib"),          # Selver answered HTTP 500 for these (WEB-23)
    ("tomat (kirss", r"tomat \(kirss"),
    ("piim 2,5%", "piim 2,5%"),          # ordinary text is left alone
])
def test_query_syntax_characters_are_escaped(typed, sent, monkeypatch):
    seen = {}

    class Answer:
        def raise_for_status(self): pass
        def json(self): return {"hits": {"hits": []}}

    monkeypatch.setattr(selver_api.requests, "post", lambda url, json, **k: seen.update(json) or Answer())
    selver_api.search_selver(typed)
    assert seen["query"]["query_string"]["query"] == sent
