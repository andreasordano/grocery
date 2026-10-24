"""Reading a recipe page into a dinner (core/recipe_import.py), without the internet."""
import socket

import pytest

from core import recipe_import
from core.recipe_import import PageError, import_recipe, parse, to_item

RECIPE_PAGE = """<html><head><title>Kana-nuudliroog | Rimi</title>
<meta property="og:image" content="https://cdn.example/og.jpg">
<script type="application/ld+json">{"@context": "https://schema.org", "@graph": [
  {"@type": "WebPage", "name": "x"},
  {"@type": ["Recipe"], "name": "Kana-nuudliroog mangokastmes", "recipeYield": ["4", "4 portsjonit"],
   "image": [{"@type": "ImageObject", "url": "https://cdn.example/kana.jpg"}],
   "recipeIngredient": ["500 g Kanafilee", "2 spl õli", "1 sibul, hakitud", "Vesi", "500 g Kanafilee"],
   "recipeInstructions": [{"@type": "HowToStep", "text": "The site's own text"}]}]}</script>
</head><body></body></html>"""

ARTICLE_PAGE = """<html><head><title>Piimapuding</title><meta property="og:title" content="Lihtne piimapuding">
<meta property="og:image" content="https://cdn.example/puding.jpg">
<script type="application/ld+json">{"@type": "NewsArticle", "headline": "x"}</script></head></html>"""


@pytest.mark.parametrize("line, item", [
    ("500 g Maasikad", "500 g maasikad"),
    ("2 spl oliiviõli", "oliiviõli"),            # spoonfuls: one pack of it
    ("2 tls Vahtrasiirup", "vahtrasiirup"),
    ("1 sibul, peeneks hakitud", "1 sibul"),      # the note after the comma goes
    ("1 purk purustatud tomateid (400 g)", "1 purustatud tomateid"),
    ("sool maitse järgi", "sool"),
    ("1/2 kg kartuleid", "0.5 kg kartuleid"),
    ("½ tk sidrun", "0.5 tk sidrun"),
    ("200 g WELL DONE hakkliha", "200 g WELL DONE hakkliha"),  # brand names in capitals stay
    ("Vesi", None),                               # not bought
])
def test_ingredient_line_becomes_a_typed_item(line, item):
    assert to_item(line) == item


def test_recipe_data_fills_the_dinner_but_not_the_method():
    found = parse(RECIPE_PAGE, "https://www.rimi.ee/retseptid/kana/1")
    assert found["name"] == "Kana-nuudliroog mangokastmes" and found["servings"] == 4
    assert found["items"] == ["500 g kanafilee", "õli", "1 sibul"]  # water out, duplicates once
    assert found["image"] == "https://cdn.example/kana.jpg" and found["link"] == "https://www.rimi.ee/retseptid/kana/1"
    assert not found["partial"] and "The site's own text" not in str(found)


def test_page_without_recipe_data_gives_its_title_and_photo():
    found = parse(ARTICLE_PAGE, "https://example.ee/puding")
    assert (found["name"], found["image"], found["items"], found["partial"]) == \
        ("Lihtne piimapuding", "https://cdn.example/puding.jpg", [], True)


@pytest.mark.parametrize("url", [
    "http://localhost:8000/", "http://127.0.0.1/", "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.5/", "ftp://example.ee/x",
])
def test_only_public_web_pages_are_fetched(url, monkeypatch):
    monkeypatch.setattr(recipe_import.requests, "get", lambda *a, **k: pytest.fail("fetched " + url))
    with pytest.raises(PageError):
        import_recipe(url)


def test_a_redirect_to_a_private_address_is_refused(monkeypatch):
    class Redirect:
        is_redirect, status_code, headers = True, 302, {"Location": "http://127.0.0.1/admin"}
        def close(self): pass
    public = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    real = socket.getaddrinfo
    monkeypatch.setattr(recipe_import.socket, "getaddrinfo", lambda host, *a: public if host == "example.ee" else real(host, *a))
    calls = []
    monkeypatch.setattr(recipe_import.requests, "get", lambda url, **k: calls.append(url) or Redirect())
    with pytest.raises(PageError, match="public"):
        import_recipe("https://example.ee/r")
    assert calls == ["https://example.ee/r"]  # the private address was never asked


def test_captcha_page_says_the_site_blocks_reading(monkeypatch):
    monkeypatch.setattr(recipe_import, "fetch", lambda url: (url, "<html><title>Security check required</title></html>"))
    with pytest.raises(PageError, match="doesn't let"):
        import_recipe("nami-nami.ee/retseptid/1")
