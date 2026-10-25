# =============================================================================
# MAILERLITE  (the weekly plan newsletter's subscribers, WEB-37)
# Sign-ups from the app go to the group MAILERLITE_GROUP_NEW as "unconfirmed": MailerLite sends the
# double opt-in email (turn on "Double opt-in for API and integrations" in its settings) and handles
# unsubscribing. After a subscriber's first 7 days with pantryrun, scripts/weekly_plan.py moves them to
# MAILERLITE_GROUP_WEEKLY, the group each edition is sent to: no reminders in a tester's first week (PROD-5).
# Each subscriber carries the custom field pantryrun_id (their person id), so newsletter links can open the
# app as the same person. The email address is kept only in MailerLite, never in our database.
# On the free plan the API can't set an email's content, so editions are pasted into MailerLite's editor.
# =============================================================================

import os
import re

import requests

API = "https://connect.mailerlite.com/api"
TIMEOUT = 10
ID_FIELD = "pantryrun_id"
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class MailerLiteError(Exception):
    pass


def configured():
    return all(os.environ.get(k) for k in ("MAILERLITE_API_KEY", "MAILERLITE_GROUP_NEW", "MAILERLITE_GROUP_WEEKLY"))


def _call(method, path, **kwargs):
    try:
        r = requests.request(method, API + path, timeout=TIMEOUT, **kwargs, headers={
            "Authorization": f"Bearer {os.environ['MAILERLITE_API_KEY']}", "Accept": "application/json"})
    except requests.RequestException as exc:
        raise MailerLiteError(str(exc)) from exc
    if r.status_code >= 400:
        raise MailerLiteError(f"{r.status_code}: {r.text[:200]}")
    return r.json() if r.content else None


def subscribe(email, person_id, name=None):
    """Add someone to the new-subscribers group; MailerLite asks them to confirm."""
    fields = {ID_FIELD: person_id, **({"name": name} if name else {})}
    _call("POST", "/subscribers", json={"email": email, "fields": fields, "status": "unconfirmed",
                                        "groups": [os.environ["MAILERLITE_GROUP_NEW"]]})


def group_subscribers(group_id):
    """Every confirmed (active) subscriber in a group: [{id, email, created_at, fields}]."""
    found, cursor = [], None
    while True:
        page = _call("GET", f"/groups/{group_id}/subscribers",
                     params={"filter[status]": "active", "limit": 1000, **({"cursor": cursor} if cursor else {})})
        found += page["data"]
        cursor = page.get("meta", {}).get("next_cursor")
        if not cursor:
            return found


def move(subscriber_id, from_group, to_group):
    _call("POST", f"/subscribers/{subscriber_id}/groups/{to_group}")
    _call("DELETE", f"/subscribers/{subscriber_id}/groups/{from_group}")
