# =============================================================================
# SCORING  (what a product is, and how well it fits what was typed)
# parse_price and pack_size read a store's product; the rest decides whether a product name is the typed
# thing ("Banaan, kg" for "banaan"), a near form, or only mentions it, for free-text items (core/fetch.py).
# =============================================================================

import os
import re
from difflib import SequenceMatcher

def parse_price(price_str):
    if price_str is None:
        return float("inf")
    if isinstance(price_str, (int, float)):
        return float(price_str)
    s = str(price_str).replace("€", "").replace(",", ".").strip()
    try:
        return float(s)
    except Exception:
        return float("inf")


_SIZE_RE = re.compile(r"(?:(\d+)\s*[x×]\s*)?(\d+(?:[.,]\d+)?)\s*(kg|g|ml|cl|l|tk|pcs)\b")
_BONUS_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|cl|l)\s*\+\s*(\d+(?:[.,]\d+)?)\s*(kg|g|ml|cl|l)\b")
_EGG_RE = re.compile(r"\b[SMLX]{1,2}(\d{1,2})\b")  # egg packs like "M10", "L6", "XL10"
_BASE = {"kg": (1000, "g"), "g": (1, "g"), "l": (1000, "ml"), "cl": (10, "ml"), "ml": (1, "ml"), "tk": (1, "pcs"), "pcs": (1, "pcs")}


def _base(value, unit):
    factor, base = _BASE[unit]
    return float(value.replace(",", ".")) * factor, base


def pack_size(name, volume=None):
    """(amount, unit) of a packaged product, unit g, ml or pcs; None when neither the store's size field
    nor the name says. Multipacks count whole ("4x125g" → 500 g), bonus packs too ("250 g + 50 g" → 300 g),
    and egg sizes give the count ("M10" → 10 pcs). The only pack-size reader: prices, ranking and the price log."""
    for text in (volume, name):
        if not text:
            continue
        t = str(text).lower()
        bonus = _BONUS_RE.search(t)
        if bonus:
            (a, unit), (b, other) = _base(bonus[1], bonus[2]), _base(bonus[3], bonus[4])
            if unit == other:
                return a + b, unit
        m = _SIZE_RE.search(t)
        if m:
            amount, unit = _base(m[2], m[3])
            return amount * (int(m[1]) if m[1] else 1), unit
        m = _EGG_RE.search(str(text))
        if m:
            return float(m[1]), "pcs"
    return None


def fold(text):
    """Spelling-tolerant form: "spaghetti" and "Spagetid" both become "spageti…"."""
    t = text.lower()
    t = re.sub(r"(?<=[gctp])h", "", t)   # spaghetti → spagetti
    return re.sub(r"(.)\1+", r"\1", t)  # double letters → single


_WORD_RE = re.compile(r"[^\W\d_]+(?:-[^\W\d_]*)*")  # letter words, hyphen groups kept: "roh.tee" → roh, tee


def _form(word, query):
    """3: the same word (õun, õunad), 2: a near form (õuna, maapähklivõie, a typo), 0: other."""
    if word == query:
        return 3
    if len(word) >= 3 and query.startswith(word) and len(query) - len(word) <= 2:
        # Typed a plural: "õun" is the thing, but "õuna" (= õunad minus d) is the "of apple" form.
        return 2 if query.endswith("d") and word == query[:-1] else 3
    if len(query) >= 3 and word == query + "d":  # typed singular, name has the plural
        return 3
    n = len(os.path.commonprefix([word, query]))
    if n >= 3 and n >= max(len(word), len(query)) - 2:
        return 2
    if len(query) >= 6 and SequenceMatcher(None, word, query).ratio() >= 0.85:
        return 2
    return 0


def word_match(word, query):
    """How a name word relates to a typed word (both folded).

    3: it *is* the thing: the same word or a compound ending in it (rukkileib → leib).
    2: a near form: "of X" (õuna mahl), a close variant (maapähklivõie) or a typo.
    1: it only mentions it: "with/without X" (maapähklivõiga), a hyphen prefix
       (maapähklivõi-proteiinibatoon) or X inside a longer word.
    0: unrelated.
    A word that is the last part of a typed compound is a near form: "kintsuliha" (Br.kintsuliha)
    for "kanakintsuliha", since Estonian compounds end in what the thing is.
    """
    parts = word.split("-")
    if len(parts) > 1:
        # In "mango-banaani" or "maapähkli- ja …" only the last part can be the thing itself.
        head = word_match(parts[-1], query) if parts[-1] else 0
        return head if head else (1 if any(word_match(p, query) for p in parts[:-1] if p) else 0)
    form = _form(word, query)
    if not form and len(query) >= 4:
        form = max((_form(word[i:], query) for i in range(3, len(word) - 2)), default=0)
    if not form and len(word) >= 5 and query.endswith(word) and len(query) - len(word) >= 3:
        form = 2
    if form:
        # Estonian comitative/abessive: "maapähklivõiga" = with peanut butter, not peanut butter.
        if word.endswith(("ga", "ta")) and len(word) > len(query) and not query.endswith(("ga", "ta")):
            return 1
        return form
    return 1 if query in word else 0


def _name_words(name):
    """Folded words of a product name. Brands are written in capitals ("Juust Eesti E-PIIM",
    "NATTY ORIGINAL") and don't say what the product is, so they are left out."""
    has_lower = any(c.islower() for c in name)
    return [fold(w) for w in _WORD_RE.findall(name) if not (has_lower and len(w) > 1 and w.isupper())]


# A match followed by one of these is not the thing: "tee jaoks" (for tea), "banaani maitseline" (banana-flavoured).
_NOT_THE_THING_AFTER = {"jaoks", "maitseline", "maitselised", "maitsega", "maitsestatud"}


def _word_matches(words, query):
    """word_match for each name word, with "for/flavoured" phrases capped at a mention."""
    out = []
    for i, w in enumerate(words):
        m = word_match(w, query)
        if m >= 2 and i + 1 < len(words) and words[i + 1] in _NOT_THE_THING_AFTER:
            m = 1
        out.append(m)
    return out


def _participle(word):
    """"hautatud", "kuivatatud", "külmutatud": how it was made, not what it is."""
    return len(word) > 5 and word.endswith(("tud", "dud"))


def head_weight(name, rules):
    """1 / position of the first word that is (nearly) the typed thing: "Banaan, kg" → 1,
    "Mahe õun" → 0.5, "Kakao segu: õun, banaan, …" → 0.25. Names of the thing itself
    tend to say it first; mixes and flavours list it later. Participles in front don't
    count ("Hautatud veiseliha" → 1)."""
    includes = [fold(kw) for kw in rules.get("include", []) if kw]
    words = _name_words(name)
    per_query = [_word_matches(words, q) for q in includes]
    position = 0
    for i, w in enumerate(words):
        if any(m[i] >= 2 for m in per_query):
            return 1 / (position + 1)
        if not _participle(w):
            position += 1
    return 0.0


def shares_stem(name, rules, letters=5):
    """True if a name word starts like a typed word for at least `letters` letters:
    "Maapähklikreem" for "maapähklivõi". Store search also returns look-alikes with nothing in
    common ("Tilsit" for "tilaapia", a lamp for "porru"); those don't."""
    includes = [fold(kw) for kw in rules.get("include", []) if kw]
    return any(len(os.path.commonprefix([w, q])) >= min(letters, len(q))
               for w in _name_words(name) for q in includes)


def relevance_score(name, rules):
    """How well a product name fits the typed words:
    0 unrelated, 1 some words mentioned, 2 all mentioned, 4 near forms, 5 it is the thing.
    """
    includes = [fold(kw) for kw in rules.get("include", []) if kw]
    if not includes:
        return 2

    words = _name_words(name)
    best = [max(_word_matches(words, q), default=0) for q in includes]
    worst = min(best)
    if worst == 3:
        return 5
    if worst == 2:
        return 4
    if worst == 1:
        return 2
    return 1 if any(best) else 0


def score(product):
    """Lower is better: the price per 100 g (or 100 ml, or per pack when the size is unknown), plus a penalty
    large enough that a worse match tier always ranks below a better one."""
    size = product.get("weight_g") or product.get("volume_ml")
    unit_price = product["price"] / (size / 100.0) if size else product["price"]
    return unit_price + max(0, 5 - product.get("relevance", 0)) * 100.0
