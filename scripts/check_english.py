"""Check countries/ee/english.yaml (WEB-51): each Estonian word must find the thing at the stores.

Words the stores name products with (web/vocab.json, built from Selver's catalog) pass as they are. The others are
searched at Rimi and Barbora, and the ones with no exact match are listed: change the word, or take the name out.
Run it after adding names.

  python -m scripts.check_english
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import english  # noqa: E402
from core.fetch import fetch_all, spec_for  # noqa: E402
from core.recipe_import import buyable  # noqa: E402

STORES = ["rimi", "barbora"]  # Selver's search is geoblocked outside Estonia; vocab.json stands in for it


def main():
    words = sorted({w for w in english.names().values() if not buyable(w)})
    found, warnings = fetch_all({w: spec_for(w) for w in words}, STORES)
    for w in warnings:
        print("search failed:", w)
    missing = 0
    for word in words:
        exact = [p for p in found.get(word, []) if p.get("relevance", 0) >= 4]
        print(f"{'ok' if exact else 'NOT FOUND':10} {word:24} {exact[0]['store'] + ': ' + exact[0]['name'] if exact else ''}")
        missing += not exact
    print(f"\n{len(words)} words searched, {missing} not found")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
