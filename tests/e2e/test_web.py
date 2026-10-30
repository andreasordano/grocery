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
import threading
import time
import urllib.error
import urllib.request

import psycopg
import pytest

from conftest import TABLES, rows
from core import db

sync_api = pytest.importorskip("playwright.sync_api")

STORES = {"selver": 2.0, "rimi": 1.5, "barbora": 1.8}  # price level per store: Rimi is cheapest
# a tall product photo, like Rimi's: it must stay inside the quick view's photo box
PHOTO = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='900'/%3E"


def fake_fetch(store, query, size=40, refresh=False):
    """Two products per search, named after the query so free-text matching takes them.
    Selver doesn't answer searches for "katki" (broken), and has prunes ("ploomid") cheaper with Partnerkaart."""
    word = query.strip().lower()
    if store == "selver" and word == "katki":
        raise RuntimeError("403 Forbidden")
    base = STORES[store]
    card = 1.2 if store == "selver" and word == "ploomid" else None
    return [
        {"store": store, "store_id": f"{store}-{word}-1", "name": f"{word.capitalize()} Test 500g", "price": base,
         "card_price": card, "shelf": "Testriiul", "category": ["Testriiul"], "in_stock": True,
         "image": PHOTO, "url": f"https://{store}.example/p/{word}-1"},
        {"store": store, "store_id": f"{store}-{word}-2", "name": f"{word.capitalize()}, kg", "price": base * 3, "unit": "kg",
         "shelf": "Testriiul", "category": ["Testriiul"], "in_stock": True},
    ]


@pytest.fixture(scope="module")  # the fake stores end with this module, so other tests see the real ones
def base_url(test_database_url):
    mp = pytest.MonkeyPatch()
    mp.setenv("DATABASE_URL", test_database_url)  # empty tables, then the app's own pool (conftest.py)
    with psycopg.connect(test_database_url) as conn:
        conn.execute(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE")
    db.reset()
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


class _Browser:
    """The browser, with every new context already past the one-tap usual-store question and the newsletter
    offer (test_first_visit… and test_newsletter… ask them on purpose)."""
    def __init__(self, browser):
        self._browser = browser

    def new_context(self, **kwargs):
        ctx = self._browser.new_context(**kwargs)
        ctx.add_init_script("localStorage.setItem('pantryrun.usualStore', JSON.stringify('selver'));"
                            "localStorage.setItem('pantryrun.newsletterAsked', 'true')")
        return ctx

    def __getattr__(self, name):
        return getattr(self._browser, name)


@pytest.fixture(scope="session")
def browser():
    with sync_api.sync_playwright() as pw:
        b = pw.chromium.launch(channel=os.environ.get("PW_CHANNEL") or None)
        yield _Browser(b)
        b.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context(permissions=["clipboard-read", "clipboard-write"])
    yield ctx.new_page()
    ctx.close()


def logged(type, user=None, wait=0):
    """The events of one type, oldest first: (user_id, data). With a user and wait=n, waits up to 3 s
    until that person has n of them: the page sends events in the background."""
    for _ in range(60 if wait else 1):
        found = list(rows("SELECT user_id, data FROM events WHERE type = %s ORDER BY id", (type,)))
        if sum(u == user for u, _ in found) >= wait:
            return found
        time.sleep(0.05)
    return found


def receipt_lines(page):
    page.wait_for_selector(".r-line")
    return [t.replace("\n", " | ") for t in page.locator(".r-line").all_inner_texts()]


def open_recipe(page, name):
    """A dinner's own page, from "Recipe" on it in the basket."""
    page.click(f".trip li:has-text('{name}') .open")
    page.wait_for_selector(".dp-recipe")


def test_first_visit_gets_an_anonymous_id_asks_the_name_and_logs_a_visit(base_url, page):
    page.add_init_script("if (!sessionStorage.getItem('asked')) { localStorage.removeItem('pantryrun.usualStore'); sessionStorage.setItem('asked', 1); }")
    page.goto(base_url + "/")
    page.locator("#hello").wait_for(state="visible")  # the name is asked on the first visit
    page.keyboard.press("Escape")
    assert page.locator("#hello").is_visible()  # and can't be skipped
    page.fill("#helloName", "  Mari   Maasikas ")
    page.click("#helloForm button[type=submit]")
    page.locator("#usual").wait_for(state="visible")  # then, one tap: the usual store
    page.click("#usualForm button[value=rimi]")
    page.wait_for_selector(".dish")
    person = page.evaluate("JSON.parse(localStorage.getItem('pantryrun.person'))")
    assert re.fullmatch(r"[0-9a-f-]{36}", person)
    assert [d["name"] for u, d in logged("hello", person, wait=1) if u == person] == ["Mari Maasikas"]
    usual = [d for u, d in logged("usual_store", person, wait=1) if u == person]
    assert [(d["store"], d["changed"]) for d in usual] == [("rimi", False)]
    assert usual[0]["country"] == "EE" and usual[0]["internal"] is False and usual[0]["app_version"]

    page.reload()
    page.wait_for_selector(".dish")
    assert not page.locator("#hello").is_visible() and not page.locator("#usual").is_visible()  # asked once
    assert page.evaluate("JSON.parse(localStorage.getItem('pantryrun.person'))") == person  # same person next time
    visits = [d for u, d in logged("visit", person, wait=2) if u == person]
    assert [v["first_visit"] for v in visits] == [True, False]
    assert visits[0]["from"] == "direct"


def test_tester_link_and_old_name_keep_their_id(base_url, browser):
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(base_url + "/?u=e2e-tester")
    page.wait_for_selector(".dish")
    assert page.evaluate("JSON.parse(localStorage.getItem('pantryrun.person'))") == "e2e-tester"
    assert [d["from"] for u, d in logged("visit", "e2e-tester", wait=1) if u == "e2e-tester"] == ["tester_link"]
    page.goto(base_url + "/")  # the plain link later: still the same person, and not asked for a name
    page.wait_for_selector(".dish")
    assert page.evaluate("JSON.parse(localStorage.getItem('pantryrun.person'))") == "e2e-tester"
    assert not page.locator("#hello").is_visible()
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
    page.fill("#item", "kohv, suvikõrvits 600g, kartul 1,2 kg")
    page.press("#item", "Enter")
    # a comma between digits is a decimal, not a new item
    assert page.locator(".items .it").all_inner_texts() == ["kohv", "suvikõrvits 600g", "kartul 1,2 kg"]
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
    assert not page.locator("#hello").is_visible()  # a tester link says who it is
    assert "Testi pasta for 2" in page.locator(".receipt").inner_text()
    assert page.locator(".dishes .mine .dc-name").inner_text() == "Testi pasta"

    open_recipe(page, "Testi pasta")
    page.click(".dinner-page [data-share]")
    page.wait_for_function("document.querySelector('.dinner-page .share-note').textContent.length > 0")
    link = page.evaluate("navigator.clipboard.readText()")
    assert "/?dinner=" in link

    other = browser.new_context().new_page()
    other.goto(link + "&u=e2e-ben")
    other.wait_for_selector(".sent")
    assert "Testi pasta" in other.locator(".sent").inner_text()
    assert "Testi pasta for 2" in other.locator(".receipt").inner_text()  # priced for the person who opened it
    assert [d["from"] for u, d in logged("visit", "e2e-ben", wait=1) if u == "e2e-ben"] == ["tester_link"]
    other.click("#saveShared")
    other.wait_for_selector(".sent >> text=Saved to Mine")
    other.click("[data-cat=mine]")
    assert other.locator(".dishes .mine .dc-name").inner_text() == "Testi pasta"


def test_answer_id_comes_from_the_server_and_goes_back_with_feedback(base_url, page):
    page.goto(base_url + "/?u=e2e-result")
    page.click("[data-mode=list]")
    page.fill("#item", "kohv")
    page.press("#item", "Enter")
    page.click("#find")
    receipt_lines(page)
    page.click("[data-store=selver]")
    page.click("[data-way=store]")  # "How will you get it?": in the store
    page.wait_for_selector("#wayNote:has-text('Have a good shop')")
    page.click("[data-way=online]")  # a change of mind isn't a second accept
    page.locator("#sheet").wait_for(state="visible")
    page.wait_for_timeout(300)  # events are sent without waiting

    basket = [d for u, d in logged("basket") if u == "e2e-result"][-1]
    assert re.fullmatch(r"[0-9a-f]{32}", basket["result_id"])
    for type in ("view_store", "accept", "way_change"):
        assert [d["result_id"] for u, d in logged(type) if u == "e2e-result"] == [basket["result_id"]], type
    [accept] = [d for u, d in logged("accept") if u == "e2e-result"]
    assert (accept["via"], accept["store"]) == ("store", "selver")
    assert [(d["via"], d["from"]) for u, d in logged("way_change") if u == "e2e-result"] == [("online", "store")]


def test_store_that_didnt_answer_is_named_not_missing(base_url, page):
    page.goto(base_url + "/?u=e2e-down")
    page.click("[data-mode=list]")
    page.fill("#item", "katki")
    page.press("#item", "Enter")
    page.click("#find")
    receipt_lines(page)
    receipt = page.locator(".receipt").inner_text()
    assert "Selver didn't answer, prices from Rimi and Barbora" in receipt
    assert page.locator(".r-missing").count() == 0  # a store that didn't answer isn't "missing" things
    assert [s.split("\n")[0] for s in page.locator(".stores .s").all_inner_texts()] == ["Rimi", "Maxima"]  # Barbora prices, shown as the Maxima store
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
    # the kinds of dinner scroll sideways in their own row; nothing else may stick out
    widest = page.evaluate("""Math.max(...[...document.querySelectorAll('#pick *')].filter(e => !e.closest('.cats') || e.matches('.cats'))
                                     .map(e => e.getBoundingClientRect().right))""")
    assert widest <= 390
    assert page.evaluate("document.documentElement.scrollWidth") <= 390
    ctx.close()


def test_a_phone_shows_one_step_at_a_time(base_url, browser):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
    page = ctx.new_page()
    page.goto(base_url + "/?u=e2e-steps")
    page.click("[data-mode=list]")
    page.fill("#item", "kohv")
    page.press("#item", "Enter")
    assert page.text_content(".stepbar .sb-info span") == "1 thing on your list"
    assert not page.locator(".printer").is_visible() and not page.locator("#find").is_visible()
    page.click(".stepbar [data-go='2']")  # "Find the store"
    receipt_lines(page)
    assert not page.locator("#pick").is_visible() and page.locator(".printer").is_visible()
    assert page.get_attribute(".steps [data-go='2']", "aria-current") == "step"
    page.click(".stepbar [data-go='3']")  # "How will you get it?"
    page.wait_for_selector("[data-way=store]")
    assert not page.locator(".printer").is_visible() and not page.locator(".stepbar").is_visible()
    page.click("[data-way=store]")
    page.click("#wayNote [data-go='2']")  # "See the list"
    assert page.locator(".printer").is_visible() and page.locator(".stamp").is_visible()
    page.click(".steps [data-go='1']")
    assert page.locator("#pick").is_visible() and "Cheapest at" in page.text_content(".stepbar")
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
    page.locator(".dish").first.click()  # its own page
    page.wait_for_selector(".dp-recipe")
    page.click("#addToTrip")
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
    photo, name = page.locator(".pk-photo img").bounding_box(), page.locator(".pk-name").bounding_box()
    assert photo["y"] + photo["height"] <= name["y"]  # the photo doesn't cover the name
    card, slot = page.locator("#peek").bounding_box(), page.locator(".slot").bounding_box()
    assert card["x"] + card["width"] <= slot["x"]  # nor the receipt printer's slot
    assert page.get_attribute("#pkOpen", "href") == "https://rimi.example/p/kohv-1"
    page.evaluate("document.querySelector('#pkOpen').addEventListener('click', e => e.preventDefault())")
    page.click("#pkOpen")
    assert [d["product"] for u, d in logged("open_product", "e2e-peek", wait=1) if u == "e2e-peek"] == ["Kohv Test 500g"]

    page.click("#pkChoose")  # from the quick look to the products to choose from
    page.locator("#sheet").wait_for(state="visible")
    assert not page.locator("#peek").evaluate("p => p.matches(':popover-open')")


def test_several_dinners_price_as_one_trip(base_url, page):
    for name, items in (("Testi pasta", ["spagetid 500g", "suvikõrvits 300g"]), ("Testi salat", ["suvikõrvits 200g"])):
        body = json.dumps({"user_id": "e2e-trip", "name": name, "servings": 2, "items": items}).encode()
        urllib.request.urlopen(urllib.request.Request(base_url + "/my-dinners", body, {"Content-Type": "application/json"}))
    page.goto(base_url + "/?u=e2e-trip")
    page.click("[data-cat=mine]")
    for name in ("Testi pasta", "Testi salat"):
        page.click(f".dish >> text={name}")
        page.click("#addToTrip")
    page.wait_for_function("document.querySelector('.r-what')?.textContent.startsWith('2 dinners')")
    assert [t.split("\n")[0] for t in page.locator(".trip li").all_inner_texts()] == ["Testi pasta", "Testi salat"]
    # what both dinners need is one line, added up: 300 g + 200 g of courgette
    lines = receipt_lines(page)
    assert any(l.startswith("suvikõrvits need 500 g") and "for Testi pasta, Testi salat" in l for l in lines)
    basket = [d for u, d in logged("basket") if u == "e2e-trip"][-1]
    assert basket["mission"] == "dinners" and basket["dinner_count"] == 2

    page.click("[data-unpick] >> nth=1")  # take the salad out: back to one dinner
    page.wait_for_function("document.querySelector('.r-what')?.textContent.startsWith('Testi pasta')")
    assert page.locator(".dc-add[aria-pressed=true]").count() == 1


def test_plus_on_a_card_adds_the_dinner_without_opening_it(base_url, page):
    page.goto(base_url + "/?u=e2e-plus")
    page.click("[data-cat=classics]")
    page.locator(".dc-add").first.click()
    page.wait_for_selector(".trip li")
    assert page.locator(".dinner-page").count() == 0  # still on the list
    assert page.locator(".dc-add[aria-pressed=true]").count() == 1
    page.click(".dc-add[aria-pressed=true]")  # the tick takes it out again
    page.wait_for_selector(".trip", state="detached")


def test_a_long_product_name_in_the_report_list_keeps_the_page_on_screen(base_url, browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    page.goto(base_url + "/?u=e2e-wrong")
    page.click("[data-mode=list]")
    page.fill("#item", "kohv")
    page.press("#item", "Enter")
    page.click("#find")
    page.click("#wrong")
    page.evaluate("() => { document.querySelector('#wrongItem option').textContent = 'broileri rinnafilee: '"
                  " + 'Broileri rinnafilee värske, A-klass, 500 g, jahutatud, pakendatud kaitsegaasi '.repeat(3); }")
    assert page.evaluate("document.documentElement.scrollWidth") == 1280  # the column didn't grow off the screen
    box = page.locator("#sendReport").bounding_box()
    assert box["x"] + box["width"] <= 1280
    ctx.close()


def test_a_line_left_out_with_x_comes_off_every_store_and_can_be_put_back(base_url, page):
    page.goto(base_url + "/?u=e2e-skip")
    page.click("[data-mode=list]")
    page.fill("#item", "kohv, tee")
    page.press("#item", "Enter")
    page.click("#find")
    page.wait_for_selector(".r-line")
    assert len(receipt_lines(page)) == 2
    page.click(".r-x[data-skip='text:tee']")
    page.wait_for_selector(".r-skipped")
    assert [l.split(" | ")[0] for l in receipt_lines(page)] == ["kohv"]
    page.click("[data-store=selver]")  # another store: left out there too
    page.wait_for_function("document.querySelectorAll('.r-line').length === 1")
    assert page.locator(".r-x").count() == 0  # the last line stays
    basket = [d for u, d in logged("basket", "e2e-skip", wait=2) if u == "e2e-skip"][-1]
    assert basket["skip"] == ["text:tee"]
    page.click("[data-unskip='text:tee']")  # put it back
    page.wait_for_function("document.querySelectorAll('.r-line').length === 2")
    assert page.locator(".r-skipped").count() == 0


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
    open_recipe(page, "Testi supp")
    assert page.locator(".rc-ing li").all_inner_texts() == ["suvikõrvits\n400 g"]
    assert page.locator(".rc-method li").all_inner_texts() == ["Tükelda.", "Keeda 20 min."]
    assert page.get_attribute(".rc-link", "href") == "https://nami-nami.ee/retseptid/1"


def test_hover_card_stays_while_the_mouse_goes_to_its_buttons(base_url, browser):
    page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    page.goto(base_url + "/?u=e2e-hover")
    page.click("[data-mode=list]")
    page.fill("#item", "kohv, tee, leib")
    page.press("#item", "Enter")
    page.click("#find")
    page.wait_for_selector("button.r-photo")
    # the receipt prints out of the slot; a line sliding under a still mouse isn't hovered
    page.wait_for_function("document.querySelector('.receipt').getAnimations().every(a => a.playState === 'finished')")
    first = page.locator(".r-items li").first.bounding_box()
    page.mouse.move(first["x"] + first["width"] / 2, first["y"] + first["height"] / 2, steps=5)
    page.wait_for_selector("#peek:popover-open")
    label = page.locator(".pk-for").inner_text()
    target = page.locator("#pkChoose").bounding_box()
    # the way there crosses the paper's edge and, when the card is lower, the other lines
    for steps in (15, 60):
        page.mouse.move(target["x"] + 5, target["y"] + 5, steps=steps)
        page.mouse.move(first["x"] + first["width"] / 2, first["y"] + first["height"] / 2, steps=5)
    page.mouse.move(target["x"] + 5, target["y"] + 5, steps=30)
    page.wait_for_timeout(600)
    assert page.locator(".pk-for").inner_text() == label and page.locator("#pkChoose").bounding_box() == target
    page.mouse.click(target["x"] + 5, target["y"] + 5)
    page.locator("#sheet").wait_for(state="visible")
    page.context.close()


def test_dinner_from_a_recipe_link(base_url, page, monkeypatch):
    from core import recipe_import
    page_html = """<html><head><script type="application/ld+json">{"@type": "Recipe", "name": "Testi kotletid",
      "recipeYield": "4", "image": "https://cdn.example/kotletid.jpg",
      "recipeIngredient": ["600 g Spagetid", "2 spl Tomatipasta", "Vesi"]}</script></head></html>"""
    monkeypatch.setattr(recipe_import, "fetch", lambda url: (url, page_html))
    page.goto(base_url + "/?u=e2e-import")
    page.click("[data-cat=mine]")
    page.click("#fromLinkDinner")
    page.fill("#dlinkImport", "rimi.ee/retseptid/testi-kotletid/1")  # as copied, without https://
    page.click("#readLink")
    page.wait_for_selector("#linkNote:text('Found 2 things')")
    assert page.input_value("#dname") == "Testi kotletid" and page.text_content("#dservings") == "4"
    assert page.locator(".items .it").all_inner_texts() == ["600 g spagetid", "tomatipasta"]
    page.click("#saveDinner")
    open_recipe(page, "Testi kotletid")
    assert page.locator(".dp-photo img").count() == 1
    assert page.text_content(".rc-link").startswith("Full recipe on rimi.ee")
    assert page.locator("[data-write]").count() == 0  # the method is on the page it links to
    assert [d for u, d in logged("recipe_import") if u == "e2e-import"][0]["items"] == 2

    page.click("#backToList")
    page.click("#newDinner")
    monkeypatch.setattr(recipe_import, "fetch", lambda url: (url, "<title>Security check required</title>"))
    page.fill("#dlinkImport", "https://nami-nami.ee/retseptid/1")
    page.click("#readLink")
    page.wait_for_selector("#linkNote:text(\"doesn't let pantryrun read\")")


def test_send_to_cart_asks_without_the_extension_and_fills_with_it(base_url, browser):
    def receipt(page):
        page.goto(base_url + "/?u=e2e-cart")
        page.click("[data-mode=list]")
        page.fill("#item", "kohv, suvikõrvits 1,2 kg")
        page.press("#item", "Enter")
        page.click("#find")
        page.wait_for_selector("[data-way=online]")

    page = browser.new_context().new_page()
    receipt(page)  # without the extension: the ways that work today, and would you use one tap?
    assert page.text_content("[data-way=online] b") == "Order online at Rimi"
    page.click("[data-way=online]")
    page.locator("#sheet").wait_for(state="visible")
    assert page.locator(".cart-links a").count() == 2  # each product's page
    assert page.get_attribute("#getExtension", "href") == "/extension.zip"
    page.click("[data-cart-answer=yes]")
    page.wait_for_selector("#cartAsk:has-text('Thanks')")
    assert [d["wants"] for u, d in logged("cart_interest", "e2e-cart", wait=1) if u == "e2e-cart"] == [True]
    page.context.close()

    page = browser.new_context().new_page()  # with it: the basket goes to the extension
    # what extension/pantryrun.js does; a test script runs before <html> exists, so mark it once the page has loaded
    page.add_init_script("""addEventListener('message', e => { if (e.data?.type === 'fill-cart') window.sentBasket = e.data; });
      addEventListener('DOMContentLoaded', () => { document.documentElement.dataset.pantryrunCart = 'rimi'; });""")
    receipt(page)
    page.click("[data-way=online]")
    page.wait_for_function("window.sentBasket")
    basket = page.evaluate("window.sentBasket")
    assert basket["store"] == "rimi" and {i["id"]: i["qty"] for i in basket["items"]} == {"rimi-kohv-1": 1, "rimi-suvikõrvits-1": 3}  # 3 × 500 g beat 1.2 kg loose
    assert "Opening Rimi" in page.text_content("#wayNote")
    page.context.close()


def test_the_extension_can_be_downloaded(base_url):
    import io, zipfile
    names = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(base_url + "/extension.zip").read())).namelist()
    assert "pantryrun-rimi/manifest.json" in names and "pantryrun-rimi/rimi.js" in names


def test_basket_refuses_huge_lists_and_ignores_unknown_stores(base_url):
    def post(body):
        req = urllib.request.Request(base_url + "/basket", json.dumps(body).encode(), {"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req).read())
    with pytest.raises(urllib.error.HTTPError) as e:
        post({"items": [f"asi {i}" for i in range(61)]})
    assert e.value.code == 400
    res = post({"items": ["kohv"], "stores": ["rimi", "rimi", "evil.example"]})
    assert [b["store"] for b in res["baskets"]] == ["rimi"]  # each known store once, the rest dropped


def test_barbora_prices_stand_for_a_maxima_store(base_url, page):
    page.goto(base_url + "/?u=e2e-maxima")
    page.click("[data-mode=list]")
    page.fill("#item", "kohv")
    page.press("#item", "Enter")
    page.click("#find")
    page.wait_for_selector(".stores [data-store=barbora]")
    assert page.locator(".stores [data-store=barbora] .s").inner_text() == "Maxima"
    page.click(".stores [data-store=barbora]")
    page.wait_for_selector(".r-store:text('Maxima')")
    assert "Prices from Barbora, Maxima's e-shop" in page.locator(".receipt").inner_text()
    assert page.text_content("#after .card-sub").startswith("Maxima,")
    assert page.text_content("[data-way=online] b") == "Order online at Barbora"


def test_totals_with_the_stores_loyalty_card(base_url, page):
    page.goto(base_url + "/?u=e2e-card")
    page.click("[data-mode=list]")
    page.fill("#item", "ploomid")
    page.press("#item", "Enter")
    page.click("#find")
    page.wait_for_selector(".stores [data-store=selver]")
    # Rimi is cheapest on shelf prices (1,50 €); Selver's 2,00 € is 1,20 € with its card, said under its total.
    assert page.locator(".r-store").inner_text() == "Rimi"
    assert page.locator(".stores [data-store=selver] .cv").inner_text().replace("\xa0", " ") == "1,20 € with Partnerkaart"
    assert page.locator(".stores [data-store=rimi] .cv").count() == 0
    assert page.locator(".r-card").count() == 0  # nothing cheaper with a card at Rimi
    page.click(".stores [data-store=selver]")
    page.wait_for_selector(".r-store:text('Selver')")
    assert page.locator(".r-total").inner_text().replace("\xa0", " ").split("\n") == ["Total", "2,00 €"]
    assert page.locator(".r-card").inner_text().replace("\xa0", " ").split("\n") == ["With Partnerkaart", "1,20 €"]
    assert "1,20 with Partnerkaart" in page.locator(".receipt").inner_text()


def test_privacy_page_takes_a_deletion_request(base_url, page):
    page.goto(base_url + "/?u=e2e-privacy")
    page.wait_for_selector(".dish")
    page.click(".foot a")
    page.wait_for_selector("h1:text('Your data')")
    page.click("#askDelete")
    page.wait_for_selector("#deleteNote:has-text('within 30 days')")
    assert [d["person"] for u, d in logged("delete_request", "e2e-privacy", wait=1) if u == "e2e-privacy"] == ["e2e-privacy"]


def test_usual_store_goes_with_the_answer_and_can_be_changed(base_url, page):
    page.goto(base_url + "/?u=e2e-usual")
    page.click("[data-mode=list]")
    page.fill("#item", "kohv")
    page.press("#item", "Enter")
    page.click("#find")
    receipt_lines(page)
    page.wait_for_selector("#footYou:has-text('Your usual store is Selver')")
    page.click("#changeUsual")
    page.click("#usualForm button[value=maxima]")
    page.wait_for_selector("#footYou:has-text('Your usual store is Maxima')")
    page.click("[data-way=store]")
    assert [d["usual_store"] for u, d in logged("accept", "e2e-usual", wait=1) if u == "e2e-usual"] == ["maxima"]
    assert [(d["store"], d["changed"]) for u, d in logged("usual_store", "e2e-usual", wait=1) if u == "e2e-usual"] == [("maxima", True)]


def test_a_dinner_for_six_opens_and_is_priced_for_six(base_url, page):
    from core import recipes as own
    own.save({"name": "Testi lasanje", "servings": 6, "minutes": 90, "tags": ["friends"], "status": "published",
              "ingredients": ["spagetid 500g", "suvikõrvits", "2 tomatipasta"]})
    own.forget()
    page.goto(base_url + "/?u=e2e-six")
    page.click("[data-cat=friends]")
    page.click(".dish:has-text('Testi lasanje')")
    page.wait_for_selector(".dp-recipe")
    assert page.text_content(".dinner-page #servings") == "6"  # the recipe's own number, not the headline's 2
    page.click("#addToTrip")  # back to the list, and priced
    page.wait_for_selector(".receipt:has-text('Testi lasanje for 6')")
    assert page.text_content("#heroText #servings") == "6" and "for 6" in page.locator(".trip").inner_text()
    page.click("#heroText [data-step='-1']")
    page.wait_for_selector(".receipt:has-text('Testi lasanje for 5')")
    page.click("[data-cat=classics]")
    page.click(".dc:has-text('Shakshuka') .dc-add")  # a classic: the headline's number, 5 now
    page.wait_for_selector(".receipt:has-text('2 dinners for 5')")
    page.click(".trip li:has-text('Shakshuka') .open")
    page.wait_for_selector(".dp-recipe")
    page.click(".dinner-page [data-step='-1']")  # only this dinner
    page.wait_for_selector(".receipt:has-text('2 dinners'):not(:has-text('2 dinners for'))")
    page.click("#backToList")
    assert not page.locator("#heroText #servings").count()  # they differ: each shows its own
    assert [t.split("for ")[-1] for t in page.locator(".trip-n").all_inner_texts()] == ["5", "4"]


def test_desserts_show_under_desserts_only(base_url, page):
    from core import recipes as own
    own.save({"name": "Testi kook", "servings": 8, "minutes": 20, "tags": ["dessert", "friends"], "status": "published",
              "ingredients": ["koor", "2 tomatipasta"]})
    own.forget()
    page.goto(base_url + "/?u=e2e-dessert")
    page.wait_for_selector(".dish")
    names = lambda: page.locator(".dc-name").all_inner_texts()
    for chip in ("ideas", "quick", "friends"):  # quick by its minutes, friends by its tag: still not there
        page.click(f"[data-cat={chip}]")
        assert "Testi kook" not in names(), chip
    page.click("[data-cat=dessert]")
    assert names() == ["Testi kook"]


def test_skipping_the_usual_store_isnt_asked_again(base_url, browser):
    ctx = browser.new_context()
    ctx.add_init_script("if (!sessionStorage.getItem('asked')) { localStorage.removeItem('pantryrun.usualStore'); sessionStorage.setItem('asked', 1); }")
    page = ctx.new_page()
    page.goto(base_url + "/?u=e2e-skip")
    page.click("#usualForm button[value=skip]")
    page.wait_for_selector(".dish")
    page.reload()
    page.wait_for_selector(".dish")
    assert not page.locator("#usual").is_visible()
    ctx.close()


def test_weekly_plan_link_loads_its_dinners_as_one_trip(base_url, page):
    from core import my_dinners, plans
    sent = "sh-" + my_dinners.share(None, None, "Testi kõrvitsasupp", 2, ["kõrvits 500g", "koor"])
    token = plans.create("Week 46", ["kanasupp", sent], featured=sent)
    page.goto(base_url + f"/?plan={token}&from=newsletter&u=e2e-plan")
    page.wait_for_selector(".sent >> text=This week's plan")
    assert "Week 46" in page.locator(".sent").inner_text()
    page.wait_for_function("document.querySelector('.r-what')?.textContent.startsWith('2 dinners')")
    trip = page.locator(".trip li").all_inner_texts()
    assert len(trip) == 2 and sum("FEATURED" in t.upper() for t in trip) == 1 and "Testi kõrvitsasupp" in trip[1]
    visit = [d for u, d in logged("visit", "e2e-plan", wait=1) if u == "e2e-plan"][0]
    assert (visit["from"], visit["plan"]) == ("newsletter", token)
    assert [d["from"] for u, d in logged("plan_opened") if u == "e2e-plan"] == ["newsletter"]

    page.click("#dropPlan")
    assert page.locator(".trip").count() == 0 and "plan=" not in page.url


def test_newsletter_is_offered_once_and_says_when_sign_up_isnt_open(base_url, page):
    page.add_init_script("if (!sessionStorage.getItem('nl')) { localStorage.removeItem('pantryrun.newsletterAsked'); sessionStorage.setItem('nl', 1); }")
    page.goto(base_url + "/?u=e2e-news")
    page.locator("#news").wait_for(state="visible")
    page.fill("#news input[name=email]", "mari@example.ee")
    page.check("#news input[name=consent]")
    page.click("#news button[type=submit]")
    page.wait_for_selector("#news .nl-note >> text=Sign-up isn't open yet")  # MailerLite isn't set up here
    page.click("#newsLater")
    assert not page.locator("#news").is_visible()
    assert [d["answer"] for u, d in logged("newsletter_offer", "e2e-news", wait=1) if u == "e2e-news"] == ["later"]
    page.reload()
    page.click("[data-mode=list]")
    page.fill("#item", "kohv")
    page.press("#item", "Enter")
    page.click("#find")
    receipt_lines(page)
    page.wait_for_selector("#newsletter-footer")  # still offered, in the foot
    assert not page.locator("#news").is_visible()  # but the dialog only once


def test_make_it_yours_copies_a_dinner_into_mine(base_url, page):
    body = json.dumps({"user_id": "e2e-author", "name": "Testi pasta", "servings": 2,
                       "items": ["spagetid 500g", "suvikõrvits 300g"], "method": "Keeda pasta."}).encode()
    made = json.load(urllib.request.urlopen(urllib.request.Request(base_url + "/my-dinners", body, {"Content-Type": "application/json"})))
    share = json.load(urllib.request.urlopen(urllib.request.Request(
        base_url + "/shares", json.dumps({"recipe_id": made["id"], "user_id": "e2e-author"}).encode(), {"Content-Type": "application/json"})))
    page.goto(base_url + share["path"] + "&u=e2e-copier")
    receipt_lines(page)
    open_recipe(page, "Testi pasta")
    page.click("[data-copy]")
    page.wait_for_selector("h1:has-text('Make it yours')")
    assert page.input_value("#dname") == "Testi pasta" and page.input_value("#dmethod") == "Keeda pasta."
    page.fill("#dname", "Minu pasta")
    page.fill("#item", "parmesan 50g")
    page.press("#item", "Enter")
    page.click("#saveDinner")
    page.wait_for_selector(".trip li:has-text('Minu pasta')")  # saved, and picked straight away
    page.click("[data-cat=mine]")
    assert "Minu pasta" in page.locator(".dishes .mine").inner_text()
    assert [d["from"] for u, d in logged("dinner_copy", "e2e-copier", wait=1) if u == "e2e-copier"] == ["sh-" + share["token"]]
    saved = [d for u, d in logged("my_dinner_saved", "e2e-copier", wait=1) if u == "e2e-copier"]
    assert saved[-1]["from_dinner"] == "sh-" + share["token"] and saved[-1]["items"] == 3


def test_delivery_is_asked_once_and_logged(base_url, page):
    page.add_init_script("if (!sessionStorage.getItem('dl')) { localStorage.removeItem('pantryrun.delivery'); sessionStorage.setItem('dl', 1); }")
    page.goto(base_url + "/?u=e2e-delivery")
    page.click("[data-mode=list]")
    page.fill("#item", "kohv")
    page.press("#item", "Enter")
    page.click("#find")
    receipt_lines(page)
    page.click("[data-way=delivery]")
    page.click("#after [data-delivery=wolt]")
    page.wait_for_selector("#after .delivery-ask >> text=Every yes helps us ask Wolt and Bolt")
    [(user, data)] = [(u, d) for u, d in logged("delivery_interest", "e2e-delivery", wait=1) if u == "e2e-delivery"]
    assert (data["service"], data["where"], data["store"]) == ("wolt", "receipt", "rimi") and data["result_id"]

    page.click("[data-way=online]")  # the sheet doesn't ask again
    page.wait_for_selector("#cartAsk")
    assert page.locator("#sheet [data-delivery]").count() == 0
    page.reload()
    page.click("[data-mode=list]")
    page.fill("#item", "kohv")
    page.press("#item", "Enter")
    page.click("#find")
    receipt_lines(page)
    page.click("[data-way=delivery]")
    page.wait_for_selector("#wayNote:has-text('Every yes helps')")
    assert page.locator("#after [data-delivery]").count() == 0  # nor the next answer


def test_tapping_a_dinner_shows_its_page_and_adds_only_on_request(base_url, page):
    body = json.dumps({"user_id": "e2e-look", "name": "Testi hautis", "servings": 2, "items": ["suvikõrvits 400g", "koor"],
                       "method": "Hauta 30 min."}).encode()
    urllib.request.urlopen(urllib.request.Request(base_url + "/my-dinners", body, {"Content-Type": "application/json"}))
    page.goto(base_url + "/?u=e2e-look")
    page.click("[data-cat=mine]")
    page.click(".dish >> text=Testi hautis")
    page.wait_for_selector(".dp-recipe")
    assert page.text_content(".dp-name") == "Testi hautis"
    assert page.locator(".dp-recipe .rc-ing li").count() == 2 and "Hauta 30 min." in page.text_content(".dp-recipe")
    assert page.locator(".trip").count() == 0  # looking doesn't add it
    assert [d["id"] for u, d in logged("dinner_view", "e2e-look", wait=1) if u == "e2e-look"][0].startswith("my-")

    page.click("#backToList")
    page.wait_for_selector(".dishes")
    page.click(".dish >> text=Testi hautis")
    page.click("#addToTrip")
    page.wait_for_selector(".trip li:has-text('Testi hautis')")
    receipt_lines(page)
    assert page.locator(".trip li:has-text('Testi hautis') .open").count() == 1  # its recipe, a tap away
    assert page.locator("#newsletter-footer").count() == 1
