# This module provides functionality to load the product catalog from a JSON file.

import json
import os


def load_catalog():
    """Load a product catalog suitable for the Streamlit UI.

    Priority:
    - If `normalized_catalog.json` exists, load it and return a mapping
      category -> [product names].
    - Otherwise fall back to the legacy `catalog.json` (keeps existing shape).
    """
    base = os.path.dirname(__file__)
    normalized_path = os.path.join(base, "normalized_catalog.json")
    legacy_path = os.path.join(base, "catalog.json")

    if os.path.exists(normalized_path):
        with open(normalized_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        mapping = {}
        for rec in data:
            cat = rec.get("category") or "uncategorized"
            mapping.setdefault(cat, []).append(rec.get("name") or "")
        return mapping

    if os.path.exists(legacy_path):
        with open(legacy_path, "r", encoding="utf-8") as f:
            return json.load(f)

    return {}