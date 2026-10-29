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
    if not form and len(query) >= 7 and query.endswith("liha") and word == query[:-4]:
        form = 2  # "Veise kaelaliha" for veiseliha: stores name the animal, then the cut
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
        if m < 2 and i + 1 < len(words) and len(w) >= 3:
            # Typed as one word, written as two: "hiinakapsa" for "Hiina kapsas, kg".
            m = max(m, min(word_match(w + words[i + 1], query), 3 if query.startswith(w) else 0))
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


# Words that say a product is made from the typed thing, not the thing itself: tinned or marinated, chopped or
# dried, a sauce, tea, crisps, dumplings, baby food, pet food. Free-text items leave such products out unless the
# person typed the word too ("marineeritud šampinjonid", "piparmünditee"). Found anywhere in the name, or (the
# second list) at the end of a word: "piparmünditee", "õunamahl", "tomatipasta".
_MADE_FROM = ("marin", "soolvees", "õlis", "omas mahlas", "hautatud", "kauaküp", "teriyaki", "purustatud", "tükeldatud",
              "hakitud", "granuleeritud", "kuiv", "vinnut", "konserv", "krõps", "pelmeen", "pür", "pehmik", "smuuti",
              "galett", "puljong", "kaste", "kastme", "kast.", "borš", "hommikueine", "liköör", "šok", "jäätis", "koera", "kassi", "lemmiklooma",
              # and as the stores shorten them, and more things made with it
              "mar.", "kauak", "maits.", "paneer", "siider", "jook", "batoon", "krutoon", "majonees", "pirukas", "pitsa",
              "pesto", "friikartul", "vesi", "mineraal", "kokt",
              # smoked fish isn't the fresh fish a recipe means ("Kuumsuitsu meriahven" for meriahven)
              "kuumsuits", "külmsuits", "kuums.", "külms.", "suitsutatud", "soolatud", "snack", "snäkk",
              # minced, a dairy product or a pickle made with it, more pet food
              "hakkliha", "jogurt", "kimchi", "kiisu", "kasside", "koerte",
              # ready to cook or eat, and what's sold to season it
              "burger", "šašlõkk", "puding", "vürtsid", "maitseaine",
              # ready-made salads, not salad leaves
              "kartulisalat", "pastasalat", "toorsalat", "coleslaw")
_MADE_FROM_END = ("tee", "mahl", "supp", "pasta", "vorst", "roog")
_BABY_AGE = re.compile(r"\d\s?k\.?\+?(?![\w])")  # baby food is sold by age: "120g4k", "7k.+"


def made_from(name, typed):
    """True when the name says it's made from the thing ("Küüslauk ürtidega päevalilleõlis") and `typed`
    didn't ask for that."""
    # A brand written straight after a word is a word of its own: "…piparmün.mahlKADARBIKU250ml" is mahl + KADARBIKU.
    words = re.findall(r"[^\W\d_]+", re.sub(r"(?<=[a-zäöüõšž])(?=[A-ZÄÖÜÕŠŽ]{2})", " ", name).lower())
    name, typed = name.lower(), typed.lower()
    found = [m for m in _MADE_FROM if m in name] + [m for m in _MADE_FROM_END if any(w.endswith(m) for w in words)]
    # "…veiselihast" (elative: from beef) names something made from it: "Vürtsiliha veiselihast", "Pihvid kanalihast".
    from_it = any(w == t + "st" for t in re.findall(r"[^\W\d_]+", typed) if len(t) >= 4 for w in words)
    return any(m not in typed for m in found) or from_it or bool(_BABY_AGE.search(name))


# Words that describe the thing rather than name it: "punane sibul", "küpsetatud pardiliha", "kooritud mandel".
_DESCRIBES = ("ne", "line", "lised", "tud", "dud", "ga", "ta", "värske", "mahe", "suur", "väike")


def misses_the_thing(name, typed):
    """For an item of several words: True when the name has neither the first nor the last word that names the
    thing ("Keedusalaami" for "parma juust", "Kooritud kreeka pähklid" for "kooritud mandel"). Rimi's recipes
    write the noun first ("juust feta", "sibul punane"), most people last, so either will do."""
    typed_words = [fold(w) for w in _WORD_RE.findall(typed.lower()) if len(w) > 1]
    if len(typed_words) < 2:
        return False
    naming = [w for w in typed_words if not w.endswith(_DESCRIBES)] or typed_words
    words = _name_words(name)
    if not any(max(_word_matches(words, q), default=0) >= 2 for q in {naming[0], naming[-1]}):
        return True
    # "lamba kintsuliha" is lamb: chicken thighs ("Broileri kintsuliha") have the right cut of the wrong animal.
    # Anywhere in a word for the longer names: "Suitsukana kintsuliha" is chicken.
    has = lambda w, forms: w.startswith(forms) or any(len(f) >= 4 and f in w for f in forms)
    asked = {a for a, forms in _ANIMALS.items() if any(has(w, forms) for w in typed_words)}
    named = {a for a, forms in _ANIMALS.items() if any(has(w, forms) for w in words)}
    return bool(asked) and bool(named) and not asked & named


_ANIMALS = {"lamb": ("lamba", "lammas"), "pork": ("sea",), "beef": ("veise", "veis"), "chicken": ("kana", "broiler", "br"),
            "turkey": ("kalkun",), "duck": ("pardi", "part")}


def relevance_score(name, rules):
    """How well a product name fits the typed words:
    0 unrelated, 1 some words mentioned, 2 all mentioned, 4 near forms, 5 it is the thing.
    """
    includes = [fold(kw) for kw in rules.get("include", []) if kw]
    if not includes:
        return 2

    words = _name_words(name)
    if len(includes) > 1 and fold("".join(includes)) in words:
        return 5  # "Hiinakapsas, kg" for "hiina kapsas"
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
