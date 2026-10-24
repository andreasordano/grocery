"""Browser tests for the web app (web/: index.html, css/, js/) against the real API, with fake stores.

Needs Playwright (requirements-dev.txt) and a browser:
  pip install -r requirements-dev.txt && python -m playwright install chromium
  python -m pytest -q tests/e2e
PW_CHANNEL=chrome uses an installed Google Chrome instead of Playwright's Chromium.
Skipped when Playwright isn't installed.
"""
import json
import os
import re
import socket
import sqlite3
import threading
import time
import urllib.error
import urllib.request

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

STORES = {"selver": 2.0, "rimi": 1.5, "barbora": 1.8}  # price level per store: Rimi is cheapest
PHOTO = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10'/%3E"


def fake_fetch(store, query, size=40, refresh=False):
    """Two products per search, named after the query so free-text matching takes them.
    Selver doesn't answer searches for "katki" (broken)."""
    word = query.strip().lower()
    if store == "selver" and word == "katki":
        raise RuntimeError("403 Forbidden")
    base = STORES[store]
    return [
        {"store": store, "id": f"{store}-{word}-1", "name": f"{word.capitalize()} Test 500g", "price": base,
         "shelf": "Testriiul", "category": ["Testriiul"], "in_stock": True,
         "image": PHOTO, "url": f"https://{store}.example/p/{word}-1"},
        {"store": store, "id": f"{store}-{word}-2", "name": f"{word.capitalize()}, kg", "price": base * 3, "unit": "kg",
         "shelf": "Testriiul", "category": ["Testriiul"], "in_stock": True},
    ]


@pytest.fixture(scope="module")  # the fake stores end with this module, so other tests see the real ones
def base_url(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    mp.delenv("DATABASE_URL", raising=False)
    mp.setenv("EVENTS_DB", str(tmp_path_factory.mktemp("db") / "app.db"))
    mp.setenv("CACHE_WARMUP", "0")
    from core import catalog, fetch
    mp.setattr(fetch, "_cached_fetch", fake_fetch)
    mp.setattr(catalog, "_cached_fetch", fake_fetch)

    import uvicorn
    from api.service import app
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(url + "/health", timeout=1)
            break
        except OSError:
            time.sleep(0.05)
    yield url
    server.should_exit = True
    mp.undo()


@pytest.fixture(scope="session")
def browser():
    with sync_api.sync_playwright() as pw:
        b = pw.chromium.launch(channel=os.environ.get("PW_CHANNEL") or None)
        yield b
        b.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context(permissions=["clipboard-read", "clipboard-write"])
    yield ctx.new_page()
    ctx.close()


def logged(type):
    """The events of one type, oldest first: (user_id, data)."""
    rows = sqlite3.connect(os.environ["EVENTS_DB"]).execute(
        "SELECT user_id, data FROM events WHERE type = ? ORDER BY id", (type,)).fetchall()
    return [(u, json.loads(d)) for u, d in rows]


def receipt_lines(page):
    page.wait_for_selector(".r-line")
    return [t.replace("\n", " | ") for t in page.locator(".r-line").all_inner_texts()]


def test_first_visit_gets_an_anonymous_id_and_logs_a_visit(base_url, page):
    page.goto(base_url + "/")
    page.wait_for_selector(".dish")
    assert not page.locator("#hello").is_visible()  # no name asked until a dinner is saved
    person = page.evaluate("JSON.parse(localStorage.getItem('pantryrun.person'))")
    assert re.fullmatch(r"[0-9a-f-]{36}", person)

    page.reload()
    page.wait_for_selector(".dish")
    assert page.evaluate("JSON.parse(localStorage.getItem('pantryrun.person'))") == person  # same person next time
    visits = [d for u, d in logged("visit") if u == person]
    assert [v["first_visit"] for v in visits] == [True, False]
    assert visits[0]["from"] == "direct"


def test_tester_link_and_old_name_keep_their_id(base_url, browser):
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(base_url + "/?u=e2e-tester")
    page.wait_for_selector(".dish")
    assert page.evaluate("JSON.parse(localStorage.getItem('pantryrun.person'))") == "e2e-tester"
    assert [d["from"] for u, d in logged("visit") if u == "e2e-tester"] == ["tester_link"]
    page.goto(base_url + "/")  # the plain link later: still the same person
    page.wait_for_selector(".dish")
    assert page.evaluate("JSON.parse(localStorage.getItem('pantryrun.person'))") == "e2e-tester"
    ctx.close()

    ctx = browser.new_context()  # someone who typed a name before ids existed
    page = ctx.new_page()
    page.add_init_script("localStorage.setItem('pantryrun.name', JSON.stringify('Old Mari'))")
    page.goto(base_url + "/")
    page.wait_for_selector(".dish")
    assert page.evaluate("JSON.parse(localStorage.getItem('pantryrun.person'))") == "Old Mari"
    ctx.close()


def test_shopping_list_with_amounts_prints_one_store(base_url, page):
    page.goto(base_url + "/?u=e2e-list")
    page.click("[data-mode=list]")
    page.fill("#item", "kohv, suvikõrvits 600g")
    page.press("#item", "Enter")
    assert page.locator(".items .it").all_inner_texts() == ["kohv", "suvikõrvits 600g"]
    page.click("#find")
    lines = receipt_lines(page)
    assert "Rimi" in page.locator(".receipt").inner_text()      # cheapest store
    # The amount asked for, priced as 600 g of the loose one (0.6 × 4.50 €/kg) rather than two 500 g packs (3.00).
    assert any(l.startswith("suvikõrvits 600 g") and "2,70" in l for l in lines)


def test_tapping_an_item_changes_it(base_url, page):
    page.goto(base_url + "/?u=e2e-edit")
    page.click("[data-mode=list]")
    page.fill("#item", "kohv")
    page.press("#item", "Enter")
    page.click(".items .it")
    page.fill(".items input.edit", "2 kohv")
    page.press(".items input.edit", "Enter")
    assert page.locator(".items .it").all_inner_texts() == ["2 kohv"]


def test_suggestions_complete_the_word_and_keep_the_amount(base_url, page):
    page.goto(base_url + "/?u=e2e-suggest")
    page.click("[data-mode=list]")
    page.click("#item")
    page.keyboard.type("600g maapä", delay=20)
    page.wait_for_selector("#suggest li")
    first = page.locator("#suggest li").first.inner_text().split("\n")[0]
    assert first.startswith("maapähk")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    assert page.locator(".items .it").all_inner_texts() == [f"600g {first}"]


def test_own_dinner_is_saved_priced_and_sent_to_someone(base_url, browser, page):
    page.goto(base_url + "/?u=e2e-anna")
    page.click("[data-cat=mine]")
    page.click("#newDinner")
    page.fill("#dname", "Testi pasta")
    page.fill("#item", "spagetid 500g, suvikõrvits, 2 tomatipasta")
    page.press("#item", "Enter")
    page.click("#saveDinner")
    page.locator("#hello").wait_for(state="visible")  # the first dinner asks for a name
    page.fill("#helloName", "Anna")
    page.click("#helloForm button[value=save]")
    page.wait_for_selector(".r-line")
    assert page.evaluate("JSON.parse(localStorage.getItem('pantryrun.name'))") == "Anna"
    assert ("e2e-anna", {"name": "Anna"}) in logged("hello")
    assert "Testi pasta for 2" in page.locator(".receipt").inner_text()
    assert page.locator(".dishes .mine .dish").inner_text().endswith("Testi pasta")

    page.click("#share")
    page.wait_for_function("document.querySelector('#shareNote').textContent.length > 0")
    link = page.evaluate("navigator.clipboard.readText()")
    assert "/?dinner=" in link

    other = browser.new_context().new_page()
    other.goto(link + "&u=e2e-ben")
    other.wait_for_selector(".sent")
    assert "Testi pasta" in other.locator(".sent").inner_text()
    assert "Testi pasta for 2" in other.locator(".receipt").inner_text()  # priced for the person who opened it
    assert [d["from"] for u, d in logged("visit") if u == "e2e-ben"] == ["tester_link"]
    other.click("#saveShared")
    other.click("#helloForm button[value=skip]")  # the name can be skipped
    other.wait_for_selector(".sent >> text=Saved to Mine")
    assert other.evaluate("JSON.parse(localStorage.getItem('pantryrun.name'))") == ""
    other.click("[data-cat=mine]")
    assert other.locator(".dishes .mine .dish").inner_text().endswith("Testi pasta")


def test_answer_id_comes_from_the_server_and_goes_back_with_feedback(base_url, page):
    page.goto(base_url + "/?u=e2e-result")
    page.click("[data-mode=list]")
    page.fill("#item", "kohv")
    page.press("#item", "Enter")
    page.click("#find")
    receipt_lines(page)
    page.click("[data-store=selver]")
    page.click("[data-fb=accept]")
    page.wait_for_selector(".thanks")
    page.wait_for_timeout(300)  # events are sent without waiting

    basket = [d for u, d in logged("basket") if u == "e2e-result"][-1]
    assert re.fullmatch(r"[0-9a-f]{32}", basket["result_id"])
    for type in ("view_store", "accept"):
        assert [d["result_id"] for u, d in logged(type) if u == "e2e-result"] == [basket["result_id"]], type


def test_store_that_didnt_answer_is_named_not_missing(base_url, page):
    page.goto(base_url + "/?u=e2e-down")
    page.click("[data-mode=list]")
    page.fill("#item", "katki")
    page.press("#item", "Enter")
    page.click("#find")
    receipt_lines(page)
    receipt = page.locator(".receipt").inner_text()
    assert "Selver didn't answer, prices from Rimi and Barbora" in receipt
    assert "Not in the e-shop" not in receipt
    assert [s.split("\n")[0] for s in page.locator(".stores .s").all_inner_texts()] == ["Rimi", "Barbora"]
    statuses = {b["store"]: b.get("status") for b in [d for u, d in logged("basket") if u == "e2e-down"][-1]["baskets"]}
    assert statuses == {"rimi": "ok", "barbora": "ok", "selver": "no_answer"}


def test_broken_link_says_so(base_url, page):
    page.goto(base_url + "/?u=e2e-x&dinner=nope1234")
    page.wait_for_selector(".receipt >> text=This link doesn't lead to a dinner")


def test_dinner_screen_fits_a_phone(base_url, browser):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
    page = ctx.new_page()
    page.goto(base_url + "/?u=e2e-phone")
    page.click("[data-cat=soup]")
    widest = page.evaluate("Math.max(...[...document.querySelectorAll('#pick *')].map(e => e.getBoundingClientRect().right))")
    assert widest <= 390
    ctx.close()


def test_page_files_are_served(base_url):
    """Every stylesheet, script module (following imports from main.js) and the icon is served,
    with a type the browser accepts and a cache header that makes a deploy show at once."""
    def get(path):
        with urllib.request.urlopen(base_url + path, timeout=5) as res:
            return res.read().decode(), res.headers

    html, headers = get("/")
    assert headers["Cache-Control"] == "no-cache"
    files = re.findall(r'(?:href|src)="((?:css|js)/[^"]+|icon\.svg)"', html)
    assert "js/main.js" in files and "icon.svg" in files and len([f for f in files if f.startswith("css/")]) >= 5

    todo, seen = list(files), set()
    while todo:
        path = todo.pop()
        if path in seen:
            continue
        seen.add(path)
        body, headers = get("/" + path)
        assert headers["Cache-Control"] == "no-cache", path
        kind = {"css": "text/css", "js": "javascript", "svg": "image/svg+xml"}[path.rsplit(".", 1)[1]]
        assert kind in headers["Content-Type"], (path, headers["Content-Type"])
        if path.endswith(".js"):  # follow imports: every module the page loads must exist
            todo += ["js/" + m for m in re.findall(r'from "\./([\w-]+\.js)"', body)]
    assert len([f for f in seen if f.endswith(".js")]) > 10

    _, headers = get("/vocab.json")
    assert headers["Cache-Control"] == "public, max-age=86400"


def test_no_script_errors(base_url, page):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(base_url + "/?u=e2e-errors")
    page.click("[data-cat=classics]")
    page.locator(".dish").first.click()
    page.wait_for_function("!document.querySelector('.receipt').textContent.includes('Comparing prices')")
    page.click("[data-mode=list]")
    page.fill("#item", "kohv")
    page.press("#item", "Enter")
    page.click("#find")
    receipt_lines(page)
    page.click("[data-mode=dinner]")
    assert errors == []


def test_a_products_photo_opens_a_quick_look_with_its_store_page(base_url, page):
    page.goto(base_url + "/?u=e2e-peek")
    page.click("[data-mode=list]")
    page.fill("#item", "kohv")
    page.press("#item", "Enter")
    page.click("#find")
    page.wait_for_selector("button.r-photo")
    page.click("button.r-photo")
    page.wait_for_selector("#peek:popover-open")
    assert not page.locator("#sheet").is_visible()  # the photo isn't a tap on the line
    assert "Kohv Test 500g" in page.locator("#peek").inner_text()
    assert page.get_attribute("#pkOpen", "href") == "https://rimi.example/p/kohv-1"
    page.evaluate("document.querySelector('#pkOpen').addEventListener('click', e => e.preventDefault())")
    page.click("#pkOpen")
    time.sleep(0.3)  # the event is sent in the background
    assert [d["product"] for u, d in logged("open_product") if u == "e2e-peek"] == ["Kohv Test 500g"]

    page.click("#pkChoose")  # from the quick look to the products to choose from
    page.locator("#sheet").wait_for(state="visible")
    assert not page.locator("#peek").evaluate("p => p.matches(':popover-open')")


def test_several_dinners_price_as_one_trip(base_url, page):
    for name, items in (("Testi pasta", ["spagetid 500g", "suvikõrvits 300g"]), ("Testi salat", ["suvikõrvits 200g"])):
        body = json.dumps({"user_id": "e2e-trip", "name": name, "servings": 2, "items": items}).encode()
        urllib.request.urlopen(urllib.request.Request(base_url + "/my-dinners", body, {"Content-Type": "application/json"}))
    page.goto(base_url + "/?u=e2e-trip&trip=1")
    page.click("[data-cat=mine]")
    page.click(".dish >> text=Testi pasta")
    page.click(".dish >> text=Testi salat")
    page.wait_for_function("document.querySelector('.r-what')?.textContent.startsWith('2 dinners')")
    assert [t.split("\n")[0] for t in page.locator(".trip li").all_inner_texts()] == ["Testi pasta", "Testi salat"]
    # what both dinners need is one line, added up: 300 g + 200 g of courgette
    lines = receipt_lines(page)
    assert any(l.startswith("suvikõrvits need 500 g") and "for Testi pasta, Testi salat" in l for l in lines)
    basket = [d for u, d in logged("basket") if u == "e2e-trip"][-1]
    assert basket["mission"] == "dinners" and basket["dinner_count"] == 2

    page.click("[data-unpick] >> nth=1")  # take the salad out: back to one dinner
    page.wait_for_function("document.querySelector('.r-what')?.textContent.startsWith('Testi pasta')")
    assert page.locator(".dish[aria-pressed=true]").count() == 1


def test_too_many_dinners_in_one_trip_is_refused(base_url):
    body = json.dumps({"recipes": [{"id": f"d{i}"} for i in range(6)]}).encode()
    req = urllib.request.Request(base_url + "/basket", body, {"Content-Type": "application/json"})
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req)
    assert e.value.code == 400


def test_own_dinner_has_a_recipe_card_with_how_to_cook_it(base_url, page):
    page.goto(base_url + "/?u=e2e-cook")
    page.click("[data-cat=mine]")
    page.click("#newDinner")
    page.fill("#dname", "Testi supp")
    page.fill("#item", "suvikõrvits 400g")
    page.press("#item", "Enter")
    page.fill("#dmethod", "1. Tükelda.\n2. Keeda 20 min.")
    page.fill("#dlink", "https://nami-nami.ee/retseptid/1")
    page.click("#saveDinner")
    page.click("#helloForm button[value=skip]")
    page.wait_for_selector(".rc")
    if not page.evaluate("document.querySelector('.rc').open"):  # folded on narrow screens
        page.click(".rc summary")
    assert page.locator(".rc-ing li").all_inner_texts() == ["suvikõrvits\n400 g"]
    assert page.locator(".rc-method li").all_inner_texts() == ["Tükelda.", "Keeda 20 min."]
    assert page.get_attribute(".rc-link", "href") == "https://nami-nami.ee/retseptid/1"
