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


def relevance_score(name, rules):
    """Keyword-based relevance. Returns an integer 0..5; higher = more relevant.

    Behavior:
      - If any `exclude` token matches as a whole word -> return -1 to drop product.
      - If the full include phrase appears verbatim in the product name -> return 5.
      - Otherwise combine whole-word token overlap and a fuzzy ratio into 0..5.
    """
    name_l = name.lower()

    # Exclude matches -> drop product
    for w in rules.get("exclude", []):
        if not w:
            continue
        if re.search(r"\b" + re.escape(w.lower()) + r"\b", name_l):
            return -1

    includes = [kw.lower() for kw in rules.get("include", []) if kw]
    # If no include keywords provided, return neutral relevance
    if not includes:
        return 2

    # If full include phrase appears, treat as perfect match
    full_query = " ".join(includes)
    if full_query and full_query in name_l:
        return 5

    # Count whole-word token matches
    matched = 0
    for kw in includes:
        if re.search(r"\b" + re.escape(kw) + r"\b", name_l):
            matched += 1

    token_fraction = matched / len(includes)

    # Fuzzy similarity between query and product name (helps when tokens are reordered)
    ratio = SequenceMatcher(None, name_l, full_query).ratio()

    # Require at least some whole-word overlap unless the fuzzy ratio is very high.
    if matched == 0 and ratio < 0.72:
        return 0

    # Combine signals into 0..5 scale, giving stronger weight to token overlap.
    score_float = token_fraction * 4.5 + ratio * 1.0
    score = int(round(min(5.0, score_float)))

    if score < 0:
        score = 0
    return score


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
      2. Relevance penalty             →  products with low keyword match score worse
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

    # Tuneable weights
    RELEVANCE_WEIGHT = 3.0

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