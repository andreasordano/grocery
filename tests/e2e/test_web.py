"""Browser tests for the web app (web/: index.html, css/, js/) against the real API, with fake stores.

Needs Playwright (requirements-dev.txt) and a browser:
  pip install -r requirements-dev.txt && python -m playwright install chromium
  python -m pytest -q tests/e2e
PW_CHANNEL=chrome uses an installed Google Chrome instead of Playwright's Chromium.
Skipped when Playwright isn't installed.
"""
import os
import re
import socket
import threading
import time
import urllib.request

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

STORES = {"selver": 2.0, "rimi": 1.5, "barbora": 1.8}  # price level per store: Rimi is cheapest


def fake_fetch(store, query, size=40, refresh=False):
    """Two products per search, named after the query so free-text matching takes them."""
    word = query.strip().lower()
    base = STORES[store]
    return [
        {"store": store, "id": f"{store}-{word}-1", "name": f"{word.capitalize()} Test 500g", "price": base,
         "shelf": "Testriiul", "category": ["Testriiul"], "in_stock": True},
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


def receipt_lines(page):
    page.wait_for_selector(".r-line")
    return [t.replace("\n", " | ") for t in page.locator(".r-line").all_inner_texts()]


def test_first_visit_asks_for_a_name(base_url, page):
    page.goto(base_url + "/")
    page.locator("#hello").wait_for(state="visible")
    page.fill("#helloName", "Mari")
    page.click("#helloForm button[type=submit]")
    page.locator("#hello").wait_for(state="hidden")
    assert page.evaluate("JSON.parse(localStorage.getItem('pantryrun.name'))") == "Mari"


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
    page.wait_for_selector(".r-line")
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
    other.click("#saveShared")
    other.wait_for_selector(".sent >> text=Saved to Mine")
    other.click("[data-cat=mine]")
    assert other.locator(".dishes .mine .dish").inner_text().endswith("Testi pasta")


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
