"""Normalize a simple product catalog into a structured list used by the
API fetcher and the DB loader.

Improvements over the original:
- Clean product names (collapse whitespace, trim punctuation).
- Generate unique, stable `product_id` slugs.
- Infer a coarse `category` from keyword matches.
"""

import json
import os
import re
import unicodedata
from typing import List, Dict


KEYWORD_CATEGORIES = {
    "Bread & Bakery": ["leib", "sai", "batoon", "croissant", "kukkel", "leiv"],
    "Dairy": ["piim", "juust", "jogurt", "või", "piimajook", "kefir", "mait"],
    "Meat & Poultry": ["hakkliha", "kana", "broiler", "sealiha", "vorst", "pihv", "kalkun"],
    "Fruit": ["õun", "banaan", "apelsin", "pirn", "marja", "viinamari", "õunad", "banaanid"],
    "Vegetables": ["kartul", "tomat", "kurk", "salat", "kurgi", "köögivili"],
    "Rice & Pasta": ["riis", "pasta", "spaget"],
    "Coffee & Tea": ["kohv", "tee", "cappuccino", "espresso"],
    "Beverages": ["jook", "limonaad", "siider", "õlu", "vein", "vesi"],
    "Snacks & Sweets": ["šokolaad", "küpsis", "krõps", "jäätis", "kook", "magus"],
}


def slugify(text: str) -> str:
    # Normalize unicode, remove diacritics, allow a-z0-9 and hyphens
    text = (unicodedata.normalize("NFKD", text) or "").encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "unknown"


def clean_name(name: str) -> str:
    # Collapse whitespace and strip stray punctuation
    if not isinstance(name, str):
        name = str(name or "")
    s = name.strip()
    s = re.sub(r"\s+", " ", s)
    # remove bracketed content, packaging info and sizes
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"\b\d+(?:[.,]\d+)?\s?(?:g|kg|ml|l)\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\b\d+x\d+\s?(?:g|ml)?\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(\d+\s?kg|\d+kg)\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(pp|pk|pack|pakend)\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"[^\w\säöüõšžÄÖÜÕŠŽ-]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[\s,;:]+$", "", s)
    return s.strip()


def infer_category(name: str) -> str:
    lower = name.lower()
    for cat, kws in KEYWORD_CATEGORIES.items():
        for kw in kws:
            if kw in lower:
                return cat
    return "uncategorized"


COMMON_REPLACEMENTS = {
    r"aurututd": "aurutatud",
    r"aurutöödeldud": "aurutatud",
    r"aurutöödeldud riis": "aurutatud riis",
    r"aurutö?tagud riis": "aurutatud riis",
    r"aurut.*riis": "aurutatud riis",
}


def canonicalize(name: str) -> str:
    s = name.lower()
    # apply simple replacements for common misspellings/patterns
    for pat, repl in COMMON_REPLACEMENTS.items():
        s = re.sub(pat, repl, s)
    # remove duplicate words (e.g., "riis riis")
    words = s.split()
    dedup = []
    for w in words:
        if not dedup or w != dedup[-1]:
            dedup.append(w)
    s = " ".join(dedup)
    s = s.strip()
    # capitalize first letter for display
    return s.capitalize() if s else s


def normalize_catalog(input_path: str = None, output_path: str = None) -> List[Dict]:
    if input_path is None:
        input_path = os.path.join(os.path.dirname(__file__), "catalog.json")

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items: List[str] = []
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, list):
                for name in v:
                    items.append(str(name))
    elif isinstance(data, list):
        items = [str(x) for x in data]

    normalized = []
    seen = {}
    for i, raw_name in enumerate(items):
        name = clean_name(raw_name)
        # canonicalize common patterns (turn misspelled variants into canonical display names)
        name = canonicalize(name)
        base_slug = slugify(name)
        count = seen.get(base_slug, 0)
        if count:
            uid = f"{base_slug}-{count}"
        else:
            uid = base_slug
        seen[base_slug] = count + 1

        rec = {
            "product_id": uid,
            "name": name,
            "price": None,
            "unit": None,
            "store": None,
            "category": infer_category(name),
            "metadata": {},
        }
        normalized.append(rec)

    if output_path is None:
        output_path = os.path.join(os.path.dirname(__file__), "normalized_catalog.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)

    print(f"Normalized {len(normalized)} products -> {output_path}")
    return normalized


if __name__ == "__main__":
    normalize_catalog()
