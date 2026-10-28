"""Build data/store_recipes.yaml from Rimi's recipe pages (rimi.ee/retseptid).

Rimi publishes about a thousand recipes with schema.org Recipe data for search engines: name,
photo, time, servings, categories, ingredient lines. This keeps weeknight dinners people
recognise: a main course or dinner, at most an hour and a half, a handful of things to buy,
each of them a word the stores sell (web/vocab.json) or an ingredient rule. Ingredient lines
become typed items, as when someone pastes a recipe link (core/recipe_import.to_item); spoonfuls
and staples go under "from home". The photo is hotlinked and the method stays on Rimi's page
(the dinner keeps the link), as with a pasted link.

Generated file; don't edit dinners by hand. Re-run every few months to pick up new recipes:

  python -m scripts.import_rimi_recipes              # download and write data/store_recipes.yaml
  python -m scripts.import_rimi_recipes --cache DIR  # keep the downloads in DIR (for re-runs)
  python -m scripts.import_rimi_recipes --report     # also list why recipes were left out
"""

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import requests
import yaml
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import catalog, recipe_import  # noqa: E402

SITEMAP = "https://www.rimi.ee/sitemaps/recipes.xml"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "store_recipes.yaml")
VOCAB = os.path.join(ROOT, "web", "vocab.json")
HEADERS = {"User-Agent": "pantryrun recipe index (pantryrun.ee)"}

# The same kinds of dinner as data/dishes.yaml, so the chips stay. First match wins, on the name and
# what's bought. Soups by name or Rimi's category.
CATEGORIES = [
    {"id": "soup", "name": "Soups", "emoji": "🍲", "words": ["supp", "borš", "soljanka", "puljong"]},
    {"id": "fish", "name": "Fish", "emoji": "🐟", "words": ["kala", "lõhe", "tursk", "forell", "räim", "heik", "tuun",
                                                           "krevet", "kilu", "makrell", "pangaasius", "tilaapia", "ahven"]},
    {"id": "chicken", "name": "Chicken", "emoji": "🍗", "words": ["kana", "broiler", "kalkun", "koib", "tiib"]},
    {"id": "mince", "name": "Mince", "emoji": "🥘", "words": ["hakkliha", "hakk", "frikadell", "kotlet", "lihapall"]},
    {"id": "meat", "name": "Meat", "emoji": "🥩", "words": ["sealiha", "veise", "sea", "peekon", "vorst", "sink", "singi",
                                                           "prosciutto", "karbonaad", "ribi", "lamba", "guljašš", "pardi"]},
    {"id": "veggie", "name": "Veggie", "emoji": "🥦", "words": []},
]
PER_CATEGORY = 30   # the best few per kind of dinner: fewest things to buy, then quickest
MAX_MINUTES = 90
MIN_BUY, MAX_BUY = 3, 9

DINNER = ("pearoog", "õhtusöök", "lõunasöök")
NOT_DINNER = ("magustoit", "küpsetis", "hommikusöök", "jook", "kook", "suupiste", "salat", "kaste", "grill",
              "pidulaud", "jõulu", "laste", "smuuti", "vahepala", "eelroog", "leib")
NOT_DINNER_NAME = ("salat", "kaste", "dip", "tort", "kook", "muffin", "pirukas", "võileib", "burger", "smuuti", "jook",
                   "kokteil", "pannkook", "vahvl", "küpsis", "mousse", "parfee", "austr", "tapas", "suupiste",
                   "hommikusöök", "jäätis", "pulga", "puder")
# Bought once and kept at home: listed under "from home" instead of priced.
STAPLES = ("sool", "pipar", "õli", "oliiviõli", "rapsiõli", "suhkur", "jahu", "nisujahu", "äädikas", "vesi", "vett", "puljong",
           "puljongikuubik", "maitseaine", "vürts", "paprikapulber", "küüslaugupulber", "loorber", "kaneel", "köömned",
           "vürtsisegu", "kurkum", "karri", "tšillihelbed", "majoraan", "pune", "tüümian", "basiilik", "rosmariin", "muskaat",
           "sinep", "ketšup", "majonees", "sojakaste", "mesi", "või", "riivsai", "tärklis", "sooda", "küpsetuspulber")
BRANDS = re.compile(r"\b(rimi(\s+(smart|basic|eco|selection))?|smart|basic|i love eco|food ?studio|forte)\b", re.I)
# What it's for, not what it is: "praadimiseks õli", "serveerimiseks laim".
PURPOSE = re.compile(r"\b\w+(?:miseks|mseks)\b\s*", re.I)
# Kitchen measures the stores don't sell by: the item is bought as one pack ("4 peotäis pasta" → "pasta").
MEASURE = re.compile(r"^\s*(?:\d+(?:[.,]\d+)?\s*|paar\s+)?(?:peotäi\w*|punt\w*|viil\w*|ok\w*|lehte?|kimp\w*)\s+", re.I)


def minutes(iso):
    """90 from "PT1H30M"; None when there's no time."""
    m = re.fullmatch(r"P(?:T)?(?:(\d+)H)?(?:(\d+)M)?", str(iso or "").strip())
    return int(m[1] or 0) * 60 + int(m[2] or 0) if m and (m[1] or m[2]) else None


def _get(url, cache):
    """The page's schema.org Recipe (a dict), or None. Cached by URL."""
    f = os.path.join(cache, re.sub(r"\W", "_", url.split("/retseptid/")[-1]) + ".json") if cache else None
    if f and os.path.exists(f):
        return json.load(open(f, encoding="utf-8"))
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except requests.RequestException:
        return None
    recipe = None
    for script in BeautifulSoup(r.text, "html.parser").select('script[type="application/ld+json"]'):
        try:
            recipe = recipe_import._find_recipe(json.loads(script.string or script.get_text() or ""))
        except ValueError:
            continue
        if recipe:
            break
    time.sleep(0.5)  # be gentle with Rimi's site
    if f:
        json.dump(recipe, open(f, "w", encoding="utf-8"), ensure_ascii=False)
    return recipe


def recipe_urls():
    xml = requests.get(SITEMAP, headers=HEADERS, timeout=30).text
    return [u for u in re.findall(r"<loc>([^<]+)</loc>", xml) if re.search(r"/retseptid/[^/]+/\d+$", u)]


def _words(text):
    return re.findall(r"[a-zäöüõšž]+", text.lower())


def known_words(vocab):
    """Words that name products in the stores, and the ingredient rules' names."""
    words = {w for w, *_ in vocab}
    recipes = catalog.load_recipes()
    for spec in recipes["ingredients"].values():
        words.update(spec.get("aliases", []))
    return words


def buyable(item, known):
    """True when the stores sell it: it matches an ingredient rule, or one of its words is a word products are
    named with, whole or at the end of a compound ("sibul punane", "veisehakkliha" → "hakkliha")."""
    name, _ = catalog.parse_quantity(item)
    name = name.lower()
    if catalog.match_ingredient(name) or name in known:
        return True
    return any(w in known or any(w.endswith(k) for k in known if len(k) >= 5)
               for w in _words(name) if len(w) >= 4)


def is_staple(item):
    """Salt, oil, spices: assumed at home. "sool ja pipar", "kookosõli" (any word ending in a staple's name)."""
    name, _ = catalog.parse_quantity(item)
    ws = _words(name)
    return bool(ws) and (ws[0].endswith(STAPLES) or ws[-1].endswith(STAPLES))


def category(name, items):
    text = " ".join([name, *(i for i in items if "muna" not in i)]).lower()  # kanamunad aren't chicken
    for c in CATEGORIES:
        if any(w in text for w in c["words"]):
            return c["id"]
    return "veggie"


def place(url, recipe, known):
    """A dinner for data/store_recipes.yaml, or (None, why it's left out)."""
    if not recipe:
        return None, "no recipe data"
    name = " ".join(str(recipe.get("name") or "").split())
    cats = str(recipe.get("recipeCategory") or "").lower()
    if not any(c in cats for c in DINNER):
        return None, "not a dinner"
    if any(c in cats for c in NOT_DINNER) and "pearoog" not in cats:
        return None, "not a dinner"
    if any(w in name.lower() for w in NOT_DINNER_NAME):
        return None, "not a dinner"
    image = recipe_import._image(recipe.get("image"))
    if not image:
        return None, "no photo"
    mins = minutes(recipe.get("totalTime")) or minutes(recipe.get("cookTime"))
    if mins and mins > MAX_MINUTES:
        return None, "too long"
    lines = recipe.get("recipeIngredient") or []
    items = (recipe_import.to_item(MEASURE.sub("", PURPOSE.sub("", BRANDS.sub("", str(x))))) for x in lines)
    items = list(dict.fromkeys(" ".join(i.split()) for i in items if i))
    pantry = [catalog.parse_quantity(i)[0] for i in items if is_staple(i) and not {"vesi", "vett"} & set(_words(i))]
    buy = [i for i in items if not is_staple(i)]
    if not MIN_BUY <= len(buy) <= MAX_BUY:
        return None, "too few or too many things to buy"
    odd = [i for i in buy if not buyable(i, known)]
    if odd:
        return None, f"can't price {odd[0]}"
    steps = recipe.get("recipeInstructions") or []
    return {"id": "rm-" + url.rstrip("/").rsplit("/", 1)[-1], "name": name[:80], "category": category(name, buy),
            "servings": recipe_import._servings(recipe.get("recipeYield")) or 4, "minutes": mins,
            "steps": len(steps) if isinstance(steps, list) else None,
            "ingredients": buy, "pantry": list(dict.fromkeys(pantry)), "image": image, "link": url}, None


def build(cache=None, report=False):
    known = known_words(json.load(open(VOCAB, encoding="utf-8")))
    kept, why = [], Counter()
    urls = recipe_urls()
    with ThreadPoolExecutor(4) as pool:  # a few at a time: Rimi's pages take a few seconds each
        pages = pool.map(lambda u: _get(u, cache), urls)
        for n, (url, recipe) in enumerate(zip(urls, pages), 1):
            dinner, reason = place(url, recipe, known)
            if dinner:
                kept.append(dinner)
            else:
                why[reason if not reason.startswith("can't") else "can't price an ingredient"] += 1
                if report and reason.startswith("can't"):
                    print(f"  {reason:40} {url}")
            if n % 100 == 0:
                print(f"{n}/{len(urls)} read, {len(kept)} kept", file=sys.stderr)
    # One per name (Rimi has a few twice), then the simplest few per kind of dinner.
    by_name = {}
    for d in kept:
        by_name.setdefault(d["name"].lower(), d)
    best = []
    for c in CATEGORIES:
        mine = [d for d in by_name.values() if d["category"] == c["id"]]
        mine.sort(key=lambda d: (len(d["ingredients"]), d["minutes"] or 60))
        best += sorted(mine[:PER_CATEGORY], key=lambda d: d["name"])
    if report:
        print("Left out: " + ", ".join(f"{k} {v}" for k, v in why.most_common()))
    return best


def write(dinners):
    cats = [{k: c[k] for k in ("id", "name", "emoji")} for c in CATEGORIES]
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("# Generated by scripts/import_rimi_recipes.py. Don't edit by hand; re-run the script.\n"
                "# Source: Rimi's recipes (rimi.ee/retseptid). Photos are hotlinked and the method stays on Rimi's page.\n"
                "# `ingredients` are typed items for `servings` people; `pantry` is assumed at home.\n")
        yaml.safe_dump({"categories": cats, "dinners": dinners}, f, allow_unicode=True, sort_keys=False, width=120)
    counts = Counter(d["category"] for d in dinners)
    print(f"{len(dinners)} dinners → {OUT}: " + ", ".join(f"{c['name']} {counts[c['id']]}" for c in CATEGORIES))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cache", help="directory to keep downloads in")
    ap.add_argument("--report", action="store_true", help="list why recipes were left out")
    args = ap.parse_args()
    if args.cache:
        os.makedirs(args.cache, exist_ok=True)
    write(build(args.cache, args.report))


if __name__ == "__main__":
    main()
