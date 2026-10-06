import os
import re
from difflib import SequenceMatcher

# =============================================================================
# Score products based on price, relevance, and size. The scoring is designed to reward larger packs (lower unit price), 
# penalize products that don't match keywords, and enforce a minimum size.
# It runs after the initial parsing and before the optimization phase, which selects the best combination of products based on these scores.
# =============================================================================

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


def extract_weight_volume(name, extras=None, max_weight_g: float = 10000.0, max_volume_ml: float = 10000.0):
    """Extract weight/volume from product name plus optional hint strings.

    Values above the given max thresholds are discarded to avoid bogus parses
    (e.g., loose produce mistakenly parsed as tens of kilograms).
    """
    text = name.lower()
    if extras:
        text += " " + " ".join(str(x).lower() for x in extras if x)
    matches = re.findall(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l)\b", text)
    weight = volume = None
    for value, unit in matches:
        v = float(value.replace(",", "."))
        if unit == "kg":
            weight = v * 1000
        elif unit == "g":
            weight = v
        elif unit == "l":
            volume = v * 1000
        elif unit == "ml":
            volume = v

    if weight and weight > max_weight_g:
        weight = None
    if volume and volume > max_volume_ml:
        volume = None

    return weight, volume


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
    """
    parts = word.split("-")
    if len(parts) > 1:
        # In "mango-banaani" or "maapähkli- ja …" only the last part can be the thing itself.
        head = word_match(parts[-1], query) if parts[-1] else 0
        return head if head else (1 if any(word_match(p, query) for p in parts[:-1] if p) else 0)
    form = _form(word, query)
    if not form and len(query) >= 4:
        form = max((_form(word[i:], query) for i in range(3, len(word) - 2)), default=0)
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


def head_weight(name, rules):
    """1 / position of the first word that is (nearly) the typed thing: "Banaan, kg" → 1,
    "Mahe õun" → 0.5, "Kakao segu: õun, banaan, …" → 0.25. Names of the thing itself
    tend to say it first; mixes and flavours list it later."""
    includes = [fold(kw) for kw in rules.get("include", []) if kw]
    words = _name_words(name)
    per_query = [_word_matches(words, q) for q in includes]
    for i in range(len(words)):
        if any(m[i] >= 2 for m in per_query):
            return 1 / (i + 1)
    return 0.0


def relevance_score(name, rules):
    """How well a product name fits the typed words:
    -1 excluded, 0 unrelated, 1 some words mentioned, 2 all mentioned, 4 near forms, 5 it is the thing.
    """
    name_l = name.lower()

    for w in rules.get("exclude", []):
        if w and re.search(r"\b" + re.escape(w.lower()) + r"\b", name_l):
            return -1

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


def build_rules(spec):
    """Merge user-provided preferences into a single rules dict."""
    extra_inc = [kw.strip() for kw in spec.get("extra_include", "").split(",") if kw.strip()]
    extra_exc = [kw.strip() for kw in spec.get("extra_exclude", "").split(",") if kw.strip()]
    unit = spec.get("unit", "g")
    rules = {
        "include": list(spec.get("include", [])) + extra_inc,
        "exclude": list(spec.get("exclude", [])) + extra_exc,
        "unit": unit,
    }
    if unit == "ml":
        rules["min_volume_ml"] = spec.get("user_min", 0)
    else:
        rules["min_weight_g"] = spec.get("user_min", 0)
    return rules


def compute_product_score(product, rules):
    """
    Lower score = better. Components:
      1. Unit price per 100g or 100ml  →  rewards larger packs naturally
      2. Relevance penalty             →  a worse match tier always ranks below a better one
      3. Hard size penalty (+100)      →  if below the user's minimum size
    Returns (score, explanation_dict).
    """
    price = product.get("price", float("inf"))
    weight = product.get("weight_g")
    volume = product.get("volume_ml")
    relevance = product.get("relevance", 0)
    unit = rules.get("unit", "g")

    if unit == "ml" and volume:
        size = volume
        unit_label = "100ml"
    elif unit in ("g", "kg") and weight:
        size = weight
        unit_label = "100g"
    else:
        size = None
        unit_label = "unit"

    unit_price = (price / (size / 100.0)) if size else price

    # Large enough that unit price only orders products within the same match tier.
    RELEVANCE_WEIGHT = 100.0

    relevance_penalty = max(0, 5 - relevance) * RELEVANCE_WEIGHT

    size_penalty = 0.0
    user_min = rules.get("min_volume_ml" if unit == "ml" else "min_weight_g", 0)
    if user_min and size and size < user_min:
        size_penalty = 100.0

    final_score = unit_price + relevance_penalty + size_penalty

    return final_score, {
        "unit_price": round(unit_price, 3),
        "unit_label": unit_label,
        "size": size,
        "relevance": relevance,
        "relevance_penalty": relevance_penalty,
        "size_penalty": size_penalty,
        "final_score": round(final_score, 3),
    }