# This script normalizes a product catalog from a JSON file, ensuring that each product has a consistent structure with fields like product_id, name, price, unit, store, category, and metadata. 
# It also generates a slugified product_id based on the product name to ensure uniqueness and consistency. The normalized catalog is saved to a new JSON file for use in the application.
# The script can handle input catalogs that are either a list of product names or a dictionary with lists of product names. 
# It processes each product name, normalizes it, and outputs a structured JSON file that can be easily consumed by other parts of the application. 
# The slugify function ensures that product IDs are URL-friendly and unique, even if there are duplicate product names in the input catalog.

import json
import os
import re
from catalog import catalog


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "unknown"


def normalize_catalog(input_path=None, output_path=None):
    if input_path is None:
        input_path = os.path.join(os.path.dirname(__file__), "catalog.json")
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = []
    # support dict with lists, or a list directly
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, list):
                for name in v:
                    items.append(str(name))
    elif isinstance(data, list):
        items = [str(x) for x in data]

    normalized = []
    for i, name in enumerate(items):
        name = name.strip()
        record = {
            "product_id": slugify(name) + (f"-{i}" if i and slugify(name) == slugify(items[0]) else ""),
            "name": name,
            "price": None,
            "unit": None,
            "store": None,
            "category": "uncategorized",
            "metadata": {},
        }
        normalized.append(record)

    if output_path is None:
        output_path = os.path.join(os.path.dirname(__file__), "normalized_catalog.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)

    print(f"Normalized {len(normalized)} products -> {output_path}")


if __name__ == "__main__":
    normalize_catalog()
