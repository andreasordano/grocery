"""Reading a recipe page into a dinner (core/recipe_import.py), without the internet."""
import socket

import pytest

from core import recipe_import
from core.recipe_import import PageError, SocialPost, buyable, from_text, import_recipe, parse, to_item

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


@pytest.mark.parametrize("url, site", [
    ("https://www.instagram.com/p/C8abc123/", "Instagram"), ("instagram.com/reel/C8abc123", "Instagram"),
    ("https://m.facebook.com/story.php?id=1", "Facebook"), ("https://fb.watch/abc/", "Facebook"),
    ("https://vm.tiktok.com/ZMabc/", "TikTok"), ("https://www.threads.net/@cook/post/1", "Threads"),
])
def test_social_posts_are_never_fetched(url, site, monkeypatch):
    """WEB-50: their posts aren't read, so say what to do instead of trying (paste the text, WEB-51)."""
    monkeypatch.setattr(recipe_import.requests, "get", lambda *a, **k: pytest.fail("fetched " + url))
    with pytest.raises(SocialPost, match=f"can't open {site} posts") as refused:
        import_recipe(url)
    assert refused.value.site == site and isinstance(refused.value, PageError)


def test_a_short_link_to_a_social_post_is_refused_at_the_hop(monkeypatch):
    class Redirect:
        is_redirect, status_code, headers = True, 301, {"Location": "https://www.instagram.com/p/C8abc123/"}
        def close(self): pass
    public = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    monkeypatch.setattr(recipe_import.socket, "getaddrinfo", lambda host, *a: public)
    calls = []
    monkeypatch.setattr(recipe_import.requests, "get", lambda url, **k: calls.append(url) or Redirect())
    with pytest.raises(SocialPost):
        import_recipe("https://bit.ly/x")
    assert calls == ["https://bit.ly/x"]


def test_lookalike_hosts_are_ordinary_sites():
    assert recipe_import._social("notinstagram.com") is None and recipe_import._social("instagram.com.evil.ee") is None
    assert recipe_import._social("WWW.Facebook.com.") == "Facebook"


def test_a_social_link_is_logged_as_social(monkeypatch):
    from fastapi import HTTPException
    from api import service
    logged = []
    monkeypatch.setattr(service.events, "log_event", lambda kind, data, user_id=None: logged.append((kind, data, user_id)))
    with pytest.raises(HTTPException) as refused:
        service.import_recipe(service.RecipeImportRequest(url="https://www.instagram.com/p/C8abc123/", user_id="anna"))
    assert refused.value.status_code == 422 and "Instagram" in refused.value.detail
    assert logged == [("recipe_import", {"ok": False, "reason": "social", "site": "Instagram"}, "anna")]


def test_captcha_page_says_the_site_blocks_reading(monkeypatch):
    monkeypatch.setattr(recipe_import, "fetch", lambda url: (url, "<html><title>Security check required</title></html>"))
    with pytest.raises(PageError, match="doesn't let"):
        import_recipe("nami-nami.ee/retseptid/1")


# ── a recipe's text, pasted (WEB-51) ─────────────────────────────────────────

CAPTION = """Kiire kanapasta kooreses kastmes 🍝 Ideaalne nädalaõhtuks, valmib 20 minutiga!

Koostisosad (4 portsjonit):
✅ 400 g pastat
✅ 500 g kanafileed
• 1 sibul, hakitud
- 1 spl oliiviõli
- 2 küüslauguküünt
- sool ja pipar maitse järgi
Kastmeks:
1 purk purustatud tomateid
Vesi
Valmistamine:
1. Keeda pasta pakendil oleva juhendi järgi.
2. Prae kana ja sibul õlis.
Retsept: https://example.ee/kanapasta
#kanapasta #õhtusöök @kokk"""


def test_a_pasted_caption_gives_what_to_buy():
    found = from_text(CAPTION)
    assert found["items"] == ["400 g pastat", "500 g kanafileed", "1 sibul", "oliiviõli", "sool ja pipar",
                              "1 purustatud tomateid"]
    assert found["skipped"] == ["2 küüslauguküünt"]   # no product is named like that: the person adds it
    assert found["servings"] == 4


def test_the_title_intro_and_method_are_not_things_to_buy():
    found = from_text(CAPTION)
    everything = " ".join(found["items"] + found["skipped"])
    assert "kanapasta" not in everything and "keeda" not in everything and "prae" not in everything
    assert "#" not in everything and "http" not in everything and "vesi" not in everything


def test_text_without_headings_reads_every_short_line():
    found = from_text("hakkliha 500g\n2 porgandit\nMa teen seda igal reedel, sest lapsed armastavad seda väga\nfoo bar")
    assert found["items"] == ["hakkliha 500g", "2 porgandit"]
    assert found["skipped"] == ["foo bar"]  # the sentence is left out quietly; a short unknown line is offered


@pytest.mark.parametrize("text, servings", [
    ("Serves 2\nhakkliha", 2), ("Ingredients (for 6 people):\nhakkliha", 6), ("hakkliha", None),
    ("Portsjone: 40\nhakkliha", 12),
])
def test_servings_come_from_the_text(text, servings):
    assert from_text(text)["servings"] == servings


def test_an_amount_after_a_colon_stays_with_its_item():
    assert from_text("Kanafilee: 500 g")["items"] == ["kanafilee 500 g"]


@pytest.mark.parametrize("item, known", [
    ("400 g pastat", True), ("100 g riivjuustu", True), ("veisehakkliha", True), ("purustatud tomateid", True),
    ("2 porgandit", True), ("xyzzy", False),
])
def test_recipe_words_are_known_in_their_recipe_forms(item, known):
    assert buyable(item) is known


def test_pasted_text_is_logged_without_the_text(monkeypatch):
    from api import service
    logged = []
    monkeypatch.setattr(service.events, "log_event", lambda kind, data, user_id=None: logged.append((kind, data, user_id)))
    found = service.read_recipe_text(service.RecipeTextRequest(text="400 g pastat\nfoo bar\nMinu salajane retsept, mida ema tegi meile igal pühapäeval",
                                                               user_id="anna"))
    assert found["items"] == ["400 g pastat"]
    assert logged == [("recipe_text", {"lines": 3, "items": 1, "skipped": ["foo bar"]}, "anna")]


# ── Rimi's recipes as store dinners (scripts/import_rimi_recipes.py) ─────────

from scripts import import_rimi_recipes as rimi  # noqa: E402

RIMI = {"@type": "Recipe", "name": "Kartuli-liha ahjuvorm", "recipeCategory": "Toidukord, Pearoog, Õhtusöök, Ahjuroad",
        "image": ["https://res.cloudinary.com/rimibaltic-web/image/upload/w_1200/R1.jpg"], "totalTime": "PT1H10M",
        "recipeYield": 6, "recipeInstructions": ["Koori.", "Küpseta."],
        "recipeIngredient": ["1 kg Kartul", "1 tl Sool", "300 ml Vahukoor", "400 g Hakkliha",
                             "1 spl Universaalne vürtsisegu Rimi Smart", "150 g Riivjuust"]}
KNOWN = {"kartul", "vahukoor", "hakkliha", "riivjuust"}


def test_a_rimi_dinner_keeps_what_to_buy_and_leaves_staples_at_home():
    d, why = rimi.place("https://www.rimi.ee/retseptid/kartuli-liha-ahjuvorm/15847", RIMI, KNOWN)
    assert why is None
    assert d["id"] == "rm-15847" and d["category"] == "mince" and d["minutes"] == 70 and d["steps"] == 2
    assert d["ingredients"] == ["1 kg kartul", "300 ml vahukoor", "400 g hakkliha", "150 g riivjuust"]
    assert "sool" in d["pantry"] and d["servings"] == 6


@pytest.mark.parametrize("change, why", [
    ({"recipeCategory": "Magustoidud"}, "not a dinner"),
    ({"name": "Kana-avokaadosalat"}, "not a dinner"),
    ({"totalTime": "PT3H"}, "too long"),
    ({"image": []}, "no photo"),
    ({"recipeIngredient": ["1 kg Kartul", "200 g Austerservikud", "400 g Hakkliha"]}, "can't price 200 g austerservikud"),
])
def test_rimi_recipes_that_are_not_weeknight_dinners_are_left_out(change, why):
    assert rimi.place("https://www.rimi.ee/retseptid/x/1", {**RIMI, **change}, KNOWN) == (None, why)
