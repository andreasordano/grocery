# =============================================================================
# RECIPE IMPORT  (a recipe page → a dinner someone can save as their own)
# Most big recipe sites publish schema.org Recipe data (JSON-LD) for search engines:
# name, servings, ingredient lines and a photo. That's read once, when someone pastes
# a link; the method is the site's own text and is never copied (the dinner keeps the
# link instead). Pages without Recipe data still give their title and photo, and the
# person types what to buy. No AI: it's structured data.
# The server fetches a URL someone typed, so only public web addresses are allowed,
# redirects are checked hop by hop, and the page is read up to a size limit.
# A recipe's text can be pasted too (an Instagram caption, a message; WEB-51): each line
# becomes an item the same way, and lines that name nothing the stores sell are set aside.
# =============================================================================

import functools
import ipaddress
import json
import os
import re
import socket
import unicodedata
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from core import catalog

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
    """A link to Instagram, Facebook or TikTok (WEB-50). Their posts aren't fetched: logged-out pages mostly show a
    login wall, Meta's API only reads business and creator accounts (and needs the poster's username), and automated
    collection is against their terms. The person pastes the post's text instead (WEB-51).
    `site` is for the log, which shows how often people try."""

    def __init__(self, site):
        self.site = site
        super().__init__(f"pantryrun can't open {site} posts. Copy the post's text and paste it here instead, "
                         "or the link to the recipe page if the post has one.")


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


def iso_minutes(iso):
    """90 from "PT1H30M"; None when there's no time."""
    m = re.fullmatch(r"P(?:T)?(?:(\d+)H)?(?:(\d+)M)?", str(iso or "").strip())
    return int(m[1] or 0) * 60 + int(m[2] or 0) if m and (m[1] or m[2]) else None


def _total_minutes(recipe):
    """The whole time a recipe's data gives: totalTime, else preparing and cooking added up."""
    total = iso_minutes(recipe.get("totalTime"))
    parts = [iso_minutes(recipe.get(k)) for k in ("prepTime", "cookTime")]
    total = total or (sum(p for p in parts if p) if any(parts) else None)
    return total if total and total <= 600 else None


def parse(html, url):
    """{name, servings, minutes, items, staples, image, link, partial}. partial: no Recipe data, only title and photo.
    staples: the items usually at home (admin's "From home")."""
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
        return {"name": name[:80], "servings": _servings(recipe.get("recipeYield")) or 2,
                "minutes": _total_minutes(recipe), "items": items[:60], "staples": [i for i in items[:60] if is_staple(i)],
                "image": _image(recipe.get("image")) or _image(meta("og:image")), "link": url, "partial": not items}
    name = " ".join((meta("og:title") or title).split())
    return {"name": name[:80], "servings": 2, "minutes": None, "items": [], "staples": [], "image": _image(meta("og:image")),
            "link": url, "partial": True}


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


# ── a recipe's text, pasted ──────────────────────────────────────────────────

VOCAB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "vocab.json")
MAX_TEXT = 10_000
MAX_WORDS = 8  # longer lines are sentences: the intro or a step of the method

# A line that starts a part of the recipe ("Ingredients:", "Kastmeks:", "Method"). After a method heading, lines are
# steps ("Prae sibul õlis" names sibul, but it's not a thing to buy) until the next ingredients heading.
_HEADING = re.compile(r"^([^:]{1,40}):\s*(.*)$")
_METHOD = re.compile(r"^(method|instructions?|directions?|steps?|preparation|how to( make( it)?)?|to make|"
                     r"valmistamine|valmistusviis|valmistusõpetus|valmistus|juhend|tegemine|nii teed|kuidas teha)$", re.I)
_INGREDIENTS = re.compile(r"^(ingredients?|you('ll)? need|what you need|koostisosad|koostis|vaja läheb|vaja on|"
                          r"sul läheb vaja|sul on vaja|ostunimekiri)\b", re.I)
_BULLET = re.compile(r"^(?:[-–—•*·▪►>+~]+|\d{1,2}[.)](?=\s+\D))\s*")  # "1. sibul" is a list; "1 sibul" is one onion
_SERVES = re.compile(r"\b(?:serves|servings|portions|yield|makes|portsjone|annuseid)\s*:?\s*(\d+)\b|"
                     r"\b(\d+)\s*(?:portsjonit?|portsjonile|inimesele|servings|portions|people)\b", re.I)


def _words(text):
    return re.findall(r"[a-zäöüõšž]+", text.lower())


@functools.lru_cache(maxsize=1)
def known_words():
    """Words that name products in the stores (web/vocab.json, scripts/build_vocab.py) and the ingredient rules'
    names."""
    words = {w for w, *_ in json.load(open(VOCAB, encoding="utf-8"))}
    for spec in catalog.load_recipes()["ingredients"].values():
        words.update(spec.get("aliases", []))
    return frozenset(words)


def buyable(item, known=None):
    """True when the stores sell it: it matches an ingredient rule, or one of its words is a word products are
    named with, whole or at the end of a compound ("sibul punane", "veisehakkliha" → "hakkliha"). Recipes say
    "400 g pastat", "100 g riivjuustu", "tomateid": a word also counts without its last few letters."""
    known = known_words() if known is None else known
    name, _ = catalog.parse_quantity(item)
    name = name.lower()
    if catalog.match_ingredient(name) or name in known:
        return True
    forms = {w[:len(w) - cut] for w in _words(name) if len(w) >= 4 for cut in range(4) if len(w) - cut >= 4}
    return any(f in known or any(f.endswith(k) for k in known if len(k) >= 5) for f in forms)


def _clean(line):
    """A pasted line without emoji, bullets and hashtags: "✅ 2 sibulat #easy" → "2 sibulat"."""
    line = "".join(c for c in line if unicodedata.category(c) not in ("So", "Sk", "Cf", "Co", "Cs"))
    line = re.sub(r"(?:^|\s)[#@]\S+", " ", line)
    return " ".join(_BULLET.sub("", line.strip()).split())


def _step(raw):
    """A line of the method as written, numbering kept, without emoji and hashtags."""
    line = "".join(c for c in raw if unicodedata.category(c) not in ("So", "Sk", "Cf", "Co", "Cs"))
    return " ".join(re.sub(r"(?:^|\s)[#@]\S+", " ", line).split())


def _title(raw):
    """The dinner's name in a line, up to its first emoji ("Kiire kanapasta 🍝 Ideaalne…" → "Kiire kanapasta"), or
    None when that's a sentence or a heading."""
    cut = next((i for i, c in enumerate(raw) if unicodedata.category(c) == "So"), len(raw))
    name = _clean(raw[:cut]).strip(" .!:–-")
    if not name or len(name.split()) > MAX_WORDS or len(name) > 80 or _INGREDIENTS.match(name) or _METHOD.match(name):
        return None
    return name


_AMOUNT = re.compile(r"^[\d½¼¾⅓⅔]")  # "200 g kodujuustu", "½ tl soola": an ingredient line
# Only a time the recipe gives for the whole dinner, never one step's ("Küpseta umbes 25 minutit").
_TIME = re.compile(r"\b(?:valmistusaeg|valmistamise aeg|aega kulub|kokku|valmib|total time|ready in|cooking time|"
                   r"time|takes)\s*:?\s*(?:umbes|u\.|about|~)?\s*(\d+)\s*(?:[-–]\s*\d+\s*)?"
                   r"(min|minutit|minutiga|minuti|minutes|mins|h|tund|tundi|tunniga|hours?)\b", re.I)


def _start(lines, raws):
    """(where the ingredients start, the dinner's name or None). After an "Ingredients" heading, or else at the first
    line with an amount when what comes before it is the title and an intro ("Valgurikas juustuleib" over
    "200 g kodujuustu"); a plain list without amounts is read from the top."""
    heading = next((i for i, line in enumerate(lines) if _INGREDIENTS.match(line)), None)
    if heading is not None:
        return heading, next((t for t in map(_title, raws[:heading]) if t), None)
    amounts = [i for i, line in enumerate(lines) if _AMOUNT.match(line)]
    if len(amounts) < 2:
        return 0, None
    before = [i for i in range(amounts[0]) if lines[i]]
    short = [i for i in before if len(lines[i].split()) <= MAX_WORDS]
    if len(short) > 1:
        return 0, None  # a list that starts without amounts ("sool", "pipar", "200 g hakkliha")
    return amounts[0], next((t for t in map(_title, [raws[i] for i in short + before]) if t), None)


# Bought once and kept at home: admin's and the store dinners' "From home", not priced.
STAPLES = ("sool", "pipar", "õli", "oliiviõli", "rapsiõli", "suhkur", "jahu", "nisujahu", "äädikas", "vesi", "vett", "puljong",
           "puljongikuubik", "maitseaine", "vürts", "paprikapulber", "küüslaugupulber", "loorber", "kaneel", "köömned",
           "vürtsisegu", "maitseainesegu", "pulber", "kurkum", "karri", "tšillihelbed", "majoraan", "pune", "oregano", "tüümian", "basiilik", "rosmariin", "muskaat",
           "petersell", "till", "koriander", "piparmünt", "münt", "murulauk", "salvei", "estragon", "ürdid",  # herbs
           "sinep", "ketšup", "majonees", "sojakaste", "mesi", "või", "riivsai", "tärklis", "sooda", "küpsetuspulber")
# ...and as recipes write them: "pulber" → "pulbrit", "kaneel" → "kaneeli" (the e drops before an ending)
_STAPLE_FORMS = STAPLES + tuple(s[:-2] + s[-1] for s in STAPLES if s.endswith(("er", "el")))


def is_staple(item):
    """Salt, oil, spices: assumed at home. "sool ja pipar", "kookosõli" (any word ending in a staple's name), also in
    a recipe's forms: "½ tl soola", "1 tl küpsetuspulbrit", "kuivatatud oreganot"."""
    name, _ = catalog.parse_quantity(item)
    ws = _words(name)
    ends = lambda w: any(w[:len(w) - cut].endswith(_STAPLE_FORMS) for cut in range(3) if len(w) - cut >= 3)
    return bool(ws) and (ends(ws[0]) or ends(ws[-1]) or ws[0] in ("jahvatatud", "kuivatatud"))  # ground, dried spices


def from_text(text):
    """A recipe's text, ready for the dinner editor: {name, servings, minutes, items, staples, skipped, method}.
    items: what the stores sell, as typed items (staples: the ones usually at home, for admin's "From home");
    skipped: short lines that name nothing pantryrun knows (an English word, a typo), for the person to add if they
    buy it; method: the steps as written. name, servings and minutes are None when the text doesn't say. The intro,
    links and hashtags are left out."""
    raws = (text or "")[:MAX_TEXT].splitlines()
    lines = [_clean(raw) for raw in raws]
    start, name = _start(lines, raws)
    time = _TIME.search(text or "")
    minutes = time and int(time[1]) * (60 if time[2].lower().startswith(("h", "tun")) else 1)
    items, skipped, steps, servings, method = [], [], [], None, False
    for raw, line in zip(raws[start:], lines[start:]):
        if method and not _INGREDIENTS.match(line):
            if not _METHOD.match(line.strip(" .:")):
                steps.append(_step(raw))
            continue
        serves = _SERVES.search(line)  # "Serves 4", "Koostisosad (4 portsjonit):"
        if serves:
            servings = servings or max(1, min(int(serves[1] or serves[2]), 12))
            line = _SERVES.sub("", line).replace("()", "").strip()
            if not line:
                continue
        heading = _HEADING.match(line)
        if heading and (_METHOD.match(heading[1].strip()) or _INGREDIENTS.match(heading[1]) or not heading[2]):
            # "Kastmeks:" or "Ingredients: 2 eggs": a part of the recipe, maybe with its first line after the colon
            method, line = bool(_METHOD.match(heading[1].strip())), heading[2]
            if method:
                steps += [heading[2]] if heading[2] else []
                continue
        elif heading:
            line = f"{heading[1]} {heading[2]}"  # "Kanafilee: 500 g"
        elif _METHOD.match(line.strip(" .")) or _INGREDIENTS.match(line):
            method = bool(_METHOD.match(line.strip(" .")))
            continue
        if not line or re.search(r"https?://|www\.", line):
            continue
        if len(line.split()) > MAX_WORDS:
            # A sentence: the intro before the ingredients, a step after them. The method starts there.
            if items or skipped:
                method = True
                steps.append(_step(raw))
            continue
        item = to_item(line)
        if item:
            (items if is_staple(item) or buyable(item) else skipped).append(item)
    items = list(dict.fromkeys(items))[:60]
    return {"name": name, "servings": servings, "minutes": minutes if minutes and minutes <= 600 else None,
            "items": items, "staples": [i for i in items if is_staple(i)], "skipped": list(dict.fromkeys(skipped))[:30],
            "method": "\n".join(s for s in steps if s)[:4000]}
