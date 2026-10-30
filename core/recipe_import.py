# =============================================================================
# RECIPE IMPORT  (a recipe page → a dinner someone can save as their own)
# Most big recipe sites publish schema.org Recipe data (JSON-LD) for search engines:
# name, servings, ingredient lines and a photo. That's read once, when someone pastes
# a link; the method is the site's own text and is never copied (the dinner keeps the
# link instead). Pages without Recipe data still give their title and photo, and the
# person types what to buy. No AI: it's structured data.
# The server fetches a URL someone typed, so only public web addresses are allowed,
# redirects are checked hop by hop, and the page is read up to a size limit.
# =============================================================================

import ipaddress
import json
import re
import socket
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

MAX_BYTES = 3_000_000
MAX_REDIRECTS = 3
TIMEOUT = 10
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "et,en;q=0.8",
}


class PageError(Exception):
    """A page that can't be read; the message is for the person."""


class SocialPost(PageError):
    """A link to Instagram, Facebook or TikTok (WEB-50). Their posts aren't fetched: Meta's APIs don't give other
    people's captions, logged-out pages mostly show a login wall, and automated collection is against their terms.
    `site` is for the log, which shows how often people try (that decides WEB-51, pasting a recipe's text)."""

    def __init__(self, site):
        self.site = site
        super().__init__(f"pantryrun can't open {site} posts. If the post links to a recipe page, paste that link "
                         "here. Otherwise type what you buy for it below.")


# host (and its subdomains) → the name people know it by; short links included
SOCIAL = {"instagram.com": "Instagram", "instagr.am": "Instagram", "facebook.com": "Facebook", "fb.com": "Facebook",
          "fb.me": "Facebook", "fb.watch": "Facebook", "threads.net": "Threads", "threads.com": "Threads",
          "tiktok.com": "TikTok"}


def _social(host):
    """"Instagram" for www.instagram.com, None for a recipe site."""
    host = host.lower().rstrip(".")
    return next((name for domain, name in SOCIAL.items() if host == domain or host.endswith("." + domain)), None)


# ── fetching a page someone typed ────────────────────────────────────────────

def _public(host):
    """True when every address the host resolves to is on the public internet."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    return bool(infos) and all(ipaddress.ip_address(i[4][0]).is_global for i in infos)


def fetch(url):
    """(final URL, HTML) of a public web page, or PageError."""
    for _ in range(MAX_REDIRECTS + 1):
        parts = urlparse(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise PageError("That doesn't look like a web address. Copy the link from the recipe page.")
        if _social(parts.hostname):  # checked every hop: a short link can lead to a post
            raise SocialPost(_social(parts.hostname))
        if not _public(parts.hostname):
            raise PageError("pantryrun can only open public web pages.")
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=False, stream=True)
        except requests.RequestException:
            raise PageError("Couldn't reach that page. Check the link and try again.")
        if r.is_redirect:
            url = urljoin(url, r.headers.get("Location", ""))
            r.close()
            continue
        if r.status_code != 200:
            raise PageError(f"The page answered with an error ({r.status_code}).")
        body = b""
        for chunk in r.iter_content(65536):
            body += chunk
            if len(body) > MAX_BYTES:
                raise PageError("That page is too big to read.")
        r.encoding = r.encoding or "utf-8"
        return url, body.decode(r.encoding, errors="replace")
    raise PageError("That link redirects too many times.")


# ── reading the recipe ───────────────────────────────────────────────────────

def _find_recipe(node):
    """The first schema.org Recipe in JSON-LD (top level, a list, @graph or mainEntity)."""
    if isinstance(node, list):
        return next((r for r in map(_find_recipe, node) if r), None)
    if isinstance(node, dict):
        kinds = node.get("@type")
        if "Recipe" in (kinds if isinstance(kinds, list) else [kinds]):
            return node
        for key in ("@graph", "mainEntity"):
            if key in node:
                found = _find_recipe(node[key])
                if found:
                    return found
    return None


def _image(value):
    """A photo URL from schema.org's many shapes: a string, a list, an ImageObject."""
    if isinstance(value, list):
        return next((u for u in map(_image, value) if u), None)
    if isinstance(value, dict):
        return _image(value.get("url") or value.get("contentUrl"))
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        return value
    return None


def _servings(value):
    """4 from 4, "4", "4 portsjonit", ["4", "4 servings"]; None when there's no number."""
    if isinstance(value, list):
        return next((s for s in map(_servings, value) if s), None)
    m = re.search(r"\d+", str(value or ""))
    return max(1, min(int(m.group()), 12)) if m else None


_FRACTIONS = {"½": ".5", "¼": ".25", "¾": ".75", "⅓": ".33", "⅔": ".67"}
# Amounts that mean "a bit of something you buy once": the line keeps only the name (one pack).
_SMALL = r"(?:spl|sl|tls|tl|tsp|tbsp|tbs|näputäis|näpuotsatäis|natuke|veidi|küünt|küüs|oksa|oks|tass|tassi|klaas|klaasi|cup|cups|pinch)\b\.?"
_SKIP = {"vesi", "vett", "keeduvesi", "keeva vett", "külma vett", "sooja vett", "water", "jää", "jääkuubikud"}


def to_item(line):
    """A recipe's ingredient line as a typed item, or None for what isn't bought (water).
    "500 g Maasikad" → "500 g maasikad"; "2 spl oliiviõli" → "oliiviõli"; "1 sibul, hakitud" → "1 sibul"."""
    text = " ".join(BeautifulSoup(str(line), "html.parser").get_text(" ").split())
    for k, v in _FRACTIONS.items():
        text = re.sub(rf"(\d?){k}", lambda m: (m.group(1) or "0") + v, text)
    text = re.sub(r"\([^)]*\)", "", text)                      # notes in brackets
    text = re.split(r",\s|;\s| – | - ", text)[0]               # "…, peeneks hakitud"
    text = re.sub(r"\b(maitse järgi|soovi korral|to taste|optional)\b", "", text, flags=re.I)
    text = re.sub(r"^\s*\d+(?:[.,/]\d+)?\s*-\s*", "", text)    # "2-3 tk" keeps the 3
    text = re.sub(rf"^\s*(?:\d+(?:[.,/]\d+)?\s*)?{_SMALL}\s*", "", text, flags=re.I)
    text = re.sub(r"^\s*(\d+)/(\d+)\s*", lambda m: f"{int(m.group(1)) / int(m.group(2)):g} ", text)
    text = re.sub(r"^\s*(\d+(?:[.,]\d+)?)\s*(pakk|pk|purk|purki|pakki)\b\.?\s*", r"\1 ", text, flags=re.I)
    text = " ".join(text.split()).strip(" .:")
    if not text or text.lower() in _SKIP or len(text) < 2:
        return None
    # "Pruun suhkur" → "pruun suhkur"; brand names in capitals stay ("WELL DONE")
    return " ".join(w.lower() if w[:1].isupper() and not w.isupper() else w for w in text.split())


def parse(html, url):
    """{name, servings, items, image, link, partial}. partial: no Recipe data, only title and photo."""
    soup = BeautifulSoup(html, "html.parser")
    recipe = None
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            recipe = _find_recipe(json.loads(script.string or script.get_text() or ""))
        except ValueError:
            continue
        if recipe:
            break
    meta = lambda prop: (soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop}) or {}).get("content")
    title = (soup.title.string if soup.title and soup.title.string else "") or ""
    if recipe:
        lines = recipe.get("recipeIngredient") or recipe.get("ingredients") or []
        items = list(dict.fromkeys(i for i in map(to_item, lines if isinstance(lines, list) else [lines]) if i))
        name = " ".join(str(recipe.get("name") or meta("og:title") or title).split())
        return {"name": name[:80], "servings": _servings(recipe.get("recipeYield")) or 2, "items": items[:60],
                "image": _image(recipe.get("image")) or _image(meta("og:image")), "link": url, "partial": not items}
    name = " ".join((meta("og:title") or title).split())
    return {"name": name[:80], "servings": 2, "items": [], "image": _image(meta("og:image")), "link": url, "partial": True}


def import_recipe(url):
    """The recipe behind a link, ready to fill in the dinner editor, or PageError."""
    url = (url or "").strip()
    if "://" not in url:
        url = "https://" + url  # "rimi.ee/retseptid/…" as typed
    final, html = fetch(url)
    if re.search(r"<title>[^<]*(security check|captcha|just a moment|attention required)", html[:5000], re.I):
        raise PageError("That site doesn't let pantryrun read its pages. Type what you buy for it instead.")
    found = parse(html, final)
    if not found["name"] and not found["items"]:
        raise PageError("Couldn't read a recipe on that page.")
    return found
