# =============================================================================
# EVENTS  (validation data)
# Append-only log of what users do: requests, recommendations, accept/reject.
# One table: events(id, ts, user_id, session_id, type, data JSON), in Postgres (core/db.py).
# log_event only queues the event; a background writer stores them in batches, so a request never
# waits for the database. Logging must never break a user request, so failures are swallowed.
# Every event's data also says `country`, `app_version` (git commit) and `internal`
# (the founder or Claude: leave those out of every metric).
# =============================================================================

import json
import os
import queue
import subprocess
import threading
import time
from datetime import datetime, timezone

from core import db

COUNTRY = "EE"

# Every event the app logs, and what it means. tests/test_core.py checks the code uses only these.
EVENT_TYPES = {
    # visits and people
    "visit": "a page load (from: tester_link, shared_dinner, plan, direct, or a link's ?from= tag such as "
             "newsletter or instagram; plan: the weekly plan's token; first_visit; referrer)",
    "hello": "the name typed on the first visit",
    "usual_store": "the store someone usually shops at (store, or null for skip)",
    "delete_request": "someone asked for their data to be deleted",
    # answers and what people did with them
    "basket": "a recommendation: every store's basket, with a result_id",
    "accept": "a way to get it picked under an answer (via: store, online or delivery); once per store's receipt "
              "of an answer. Before Oct 2026: \"I'll go to <store>\"",
    "way_change": "another way to get it picked after the first, under the same answer (via, from)",
    "reject": "\"Not for me\" under an answer",
    "view_store": "looking at another store's receipt",
    "wrong_product": "reporting a wrong product",
    "preference": "choosing another product or typing preference words",
    "add_pantry": "adding a have-at-home item to the basket",
    "line_removed": "× on a receipt line or a missing item: left out at every store (key, store looked at, result_id)",
    "line_restored": "a line left out with × put back (key, result_id)",
    "quick_view": "tapping a product's photo",
    "open_product": "opening a product in the store's e-shop (from: quick_view, chooser, cart)",
    "recipe_open": "unfolding a recipe card (the cards left the page in Oct 2026)",
    "dinner_view": "a dinner's own page opened from the list (id)",
    # choosing dinners and items
    "dinner_category": "picking a kind of dinner",
    "dinner_shuffle": "\"Show me others\"",
    "trip_change": "a dinner added to or taken out of the trip (dinners: how many now)",
    "item_added": "an item added to a list (how: typed or suggestion)",
    "item_changed": "an item edited",
    # people's own dinners and sharing
    "my_dinner_saved": "a dinner of one's own saved (from_share, from_dinner: what it was copied from)",
    "dinner_copy": "\"Make it yours\": a dinner opened in the editor as a copy (from: its id)",
    "my_dinner_deleted": "a dinner of one's own deleted",
    "recipe_import": "reading a recipe link (site and items, or why it failed)",
    "recipe_text": "a recipe's text pasted into the editor (lines, items found, and the lines it didn't recognise: "
                   "what the English ingredient names of WEB-51 should cover); the text itself isn't logged",
    "share_created": "a link made to send a dinner",
    "share_opened": "a sent dinner opened",
    # shopping online
    "cart_click": "\"Order online at <store>\" without the extension",
    "cart_interest": "the answer to \"would you use one tap?\" (wants)",
    "cart_send": "a basket sent to the Rimi extension",
    "extension_download": "the Rimi extension downloaded",
    "delivery_interest": "\"Get it delivered instead?\", asked once per person (service: wolt, bolt or none; "
                         "where: receipt, i.e. after \"Delivered by Wolt or Bolt\", or sheet)",
    # the weekly plan newsletter (WEB-37)
    "newsletter_offer": "the answer to the sign-up offered after the first-visit questions (answer: later, signed_up)",
    "newsletter_signup": "an email sent to MailerLite for the weekly plan (ok, where); the address isn't logged",
    "plan_opened": "a weekly plan link opened (plan token, from)",
    "cooked": "a \"Did you cook it?\" link in the plan email (plan, dinner, answer)",
}


def _app_version():
    """The deployed git commit (Render sets RENDER_GIT_COMMIT), else the local one, else "dev"."""
    commit = os.environ.get("RENDER_GIT_COMMIT")
    if not commit:
        try:
            commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=2,
                                    cwd=os.path.dirname(os.path.abspath(__file__))).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            commit = ""
    return commit[:7] or "dev"


APP_VERSION = _app_version()


def is_internal(user_id=None, name=None):
    """The founder (tester link or name "andrea") or Claude's checks: not real testers.
    A stranger who types exactly "Andrea" would be counted as internal too."""
    uid = (user_id or "").strip().lower()
    return uid == "andrea" or uid.startswith(("claude", "internal-")) or (name or "").strip().lower() == "andrea"

_queue = queue.Queue(maxsize=10000)
_started = False
_start_lock = threading.Lock()
BATCH = 100  # events per insert


def log_event(type: str, data: dict | None = None, user_id: str | None = None, session_id: str | None = None,
              name: str | None = None):
    """Queue one event for the background writer. True if queued; never raises, never waits.
    name: the person's name, only to tell whether they're internal; it isn't stored."""
    data = {**(data or {}), "country": COUNTRY, "app_version": APP_VERSION, "internal": is_internal(user_id, name)}
    if not db.configured():
        return False
    try:
        row = (datetime.now(timezone.utc), user_id, session_id, type, json.dumps(data, ensure_ascii=False, default=str))
        _ensure_writer()
        _queue.put_nowait(row)
        return True
    except Exception as exc:  # a full queue (the database has been down a long while), or data that won't serialise
        print(f"event logging failed ({type}): {exc}")
        return False


def flush(timeout=10.0):
    """Wait until every queued event is written (tests, shutdown). False if it took longer than timeout."""
    deadline = time.monotonic() + timeout
    while _queue.unfinished_tasks:
        if time.monotonic() > deadline:
            return False
        time.sleep(0.02)
    return True


def _ensure_writer():
    global _started
    if _started:
        return
    with _start_lock:
        if not _started:
            threading.Thread(target=_writer, name="events", daemon=True).start()
            _started = True


def _writer():
    while True:
        rows = [_queue.get()]
        while len(rows) < BATCH:
            try:
                rows.append(_queue.get_nowait())
            except queue.Empty:
                break
        try:
            with db.connection() as conn, conn.cursor() as cur:
                cur.executemany("INSERT INTO events (ts, user_id, session_id, type, data) VALUES (%s, %s, %s, %s, %s::jsonb)", rows)
        except Exception as exc:
            print(f"event logging failed ({len(rows)} events): {exc}")
        finally:
            for _ in rows:
                _queue.task_done()
