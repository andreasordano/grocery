"""Build data/dishes.yaml from NutriData, the Estonian food composition database
(tka.nutridata.ee, Tervise Arengu Instituut).

NutriData lists ~800 main courses and soups with their ingredients in grams. This keeps one
variant per dish ("Hakklihakaste, segahakklihast, õliga" → "Hakklihakaste"), turns each
ingredient into something the app can price (an ingredient rule key, or a word for free-text
search) and scales amounts to 2 servings. Dishes with an ingredient it can't place are left out.

Generated file; don't edit dishes by hand. Re-run rarely (NutriData changes slowly):

  python -m scripts.import_nutridata              # download and write data/dishes.yaml
  python -m scripts.import_nutridata --cache DIR  # keep the downloads in DIR (for re-runs)
  python -m scripts.import_nutridata --report     # also list ingredient names it couldn't place
"""

import argparse
import json
import os
import re
import sys
import time
from collections import Counter

import requests
import urllib3
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import catalog  # noqa: E402
from core.scoring import fold  # noqa: E402

API = "https://tka.nutridata.ee/api-foods"
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "dishes.yaml")

# NutriData food groups → app categories. Offal dishes are left out.
CATEGORIES = [
    {"id": "mince", "name": "Mince", "emoji": "🥘", "groups": ["Hakkliharoad"]},
    {"id": "chicken", "name": "Chicken", "emoji": "🍗", "groups": ["Road linnulihast"]},
    {"id": "fish", "name": "Fish", "emoji": "🐟", "groups": ["Kalaroad"]},
    {"id": "meat", "name": "Meat", "emoji": "🥩", "groups": ["Keedetud ja hautatud liharoad", "Praetud liharoad",
                                                             "Road lihatoodetest", "Muud liha sisaldavad road"]},
    {"id": "veggie", "name": "Veggie", "emoji": "🥦", "groups": ["Lihata põhiroad", "Munaroad"]},
    {"id": "soup", "name": "Soups", "emoji": "🍲", "groups": ["Muud supid", "Püreesupid"]},
]
PORTION_G = {"soup": 350}  # raw ingredient weight per serving, water included
DEFAULT_PORTION_G = 400
# Free-text ingredients needing less than this for 2 (2 g chilli, 4 g ginger, a few basil leaves) are
# treated as at home: searching for them mostly finds the wrong thing, and nobody buys 2 g.
PANTRY_BELOW_G = 10

# Not bought: water, salt, ice.
SKIP = ("vesi", "sool", "jää", "keeduvesi")

# Assumed at home, shown as "Have at home" (tap to add). Matched on the start of the name.
PANTRY = {
    "rapsiõli": "õli", "õli": "õli", "päevalilleõli": "õli", "oliiviõli": "oliiviõli", "seesamiseemneõli": "seesamiõli",
    "nisujahu": "jahu", "suhkur": "suhkur", "must pipar": "pipar", "valge pipar": "pipar", "puljong": "puljong",
    "riivsai": "riivsai", "maitseainesegu": "maitseained", "köömned": "köömned", "kurkum": "kurkum",
    "tüümian": "tüümian", "kaneel": "kaneel", "kardemon": "kardemon", "pune": "pune", "koriandriseemned": "koriander",
    "cayenne": "cayenne pipar", "nelk": "nelk", "sinepiseemned": "sinepiseemned", "loorber": "loorberileht",
    "äädikas": "äädikas", "õunaäädikas": "äädikas", "palsamiäädikas": "äädikas", "suši äädikas": "riisiäädikas",
    "maitsepärm": "maitsepärm", "paprika, jahvatatud": "paprikapulber", "karri": "karri", "muskaat": "muskaat",
    "küüslaugupulber": "küüslaugupulber", "vürts": "vürtsid", "majoraan": "majoraan", "rosmariin, kuivatatud": "rosmariin",
    "basiilik, kuivatatud": "basiilik", "till, kuivatatud": "till", "petersell, kuivatatud": "petersell",
    "tšillipulber": "tšilli", "ingver, jahvatatud": "ingver", "kartulitärklis": "tärklis", "maisitärklis": "tärklis",
    "küpsetuspulber": "küpsetuspulber", "sooda": "sooda", "pärm": "pärm", "vanilli": "vanillisuhkur", "mesi": "mesi",
    "worcestershire kaste": "worcestershire kaste", "maapähkliõli": "õli", "segujahu": "jahu", "muskaatpähkel": "muskaat",
    "sidrunhein": "sidrunhein", "kookosrasv": "kookosõli",
    "sojakaste": "sojakaste", "sinep": "sinep", "ketšup": "ketšup", "majonees": "majonees",
}

# What to search for when the name before the first comma isn't how stores say it.
# Matched on the start of the full lowercase name; the longest match wins.
RENAME = {
    "mugulsibul": "sibul", "muna": "munad", "kartul": "kartul", "segahakkliha": "hakkliha",
    "seahakkliha": "seahakkliha", "veisehakkliha": "veisehakkliha", "broilerihakkliha": "kanahakkliha",
    "kalkunihakkliha": "kalkunihakkliha", "peakapsas": "kapsas", "porrulauk": "porru", "suvikõrvits": "suvikõrvits",
    "odrakruubid": "kruubid", "kaalikas": "kaalikas", "läätsed": "läätsed", "valge kala": "kalafilee",
    "ingverijuur": "ingver", "basiilik": "basiilik", "parmesani juust": "parmesan", "juurseller": "seller",
    "varsseller": "varsseller", "juurpetersell": "juurpetersell", "roheline sibul": "roheline sibul",
    "räim": "räim", "baklažaan": "baklažaan", "sulatatud juust": "sulatatud juust", "ahven": "ahven",
    "keedusink": "sink", "soolakurk": "hapukurk", "kurk, konserveeritud": "hapukurk", "murulauk": "murulauk",
    "pastinaak": "pastinaak", "külmutatud köögiviljad": "köögiviljasegu", "rukkijahu": "rukkijahu",
    "segaseened": "seened", "mozzarella": "mozzarella", "rukola": "rukola",
    "külmutatud herned": "herned", "külmutatud porgand": "porgand", "nuikapsas": "nuikapsas",
    "munakollane": "munad", "kalkunihakklihasegu": "kalkunihakkliha", "searibid": "searibid",
    "kanaliha, rinnafilee": "kanafilee", "kanaliha, kintsuliha": "kanakintsuliha", "kanaliha": "kanafilee",
    "tomat, purustatud": "purustatud tomatid", "tomat, konserveeritud": "purustatud tomatid", "tomat": "tomat",
    "sidrunimahl": "sidrun", "laimimahl": "laim", "piim": "piim", "juust": "juust", "või": "või",
    "riis": "riis", "makaronid": "makaronid", "spagetid": "spagetid", "tatar": "tatar", "kohvikoor": "kohvikoor",
    "vahukoor": "vahukoor", "toidukoor": "toidukoor", "hapukoor": "hapukoor", "kohupiim": "kohupiim",
    "kodujuust": "kodujuust", "toorjuust": "toorjuust", "jogurt": "jogurt", "herned": "herned",
    "aedoad": "aedoad", "oad": "oad", "kikerherned": "kikerherned", "šampinjonid": "šampinjonid",
    "tšillipipar": "tšilli", "paprika": "paprika", "peet": "peet", "brokoli": "brokoli", "lillkapsas": "lillkapsas",
    "spinat": "spinat", "till": "till", "petersell": "petersell", "koriander": "koriander", "küüslauk": "küüslauk",
    "porgand": "porgand", "lõhe": "lõhefilee", "tursk": "tursafilee", "heik": "heik", "tuunikala": "tuunikala",
    "krevetid": "krevetid", "vikerforell": "forell", "tilaapia": "tilaapia", "veiseliha": "veiseliha",
    "sealiha": "sealiha", "lambaliha": "lambaliha", "kalkuniliha": "kalkunifilee", "pardiliha": "pardifilee",
    "veisemaks": "veisemaks", "viiner": "viinerid", "frikadellid": "frikadellid", "suitsusink": "sink",
    # Canned coconut milk: shops name it "Kookosjook" on the cooking shelf (searching "kookospiim" finds
    # shower gel and body cream); the shelf vote leaves out coconut *drinks* (Alpro) on the plant-milk shelf.
    "kookosjook": "kookosjook", "kõrvits": "kõrvits", "bataat": "bataat", "mais": "mais", "ananass": "ananass",
    "avokaado": "avokaado", "õun": "õun", "seesamiseemned": "seesamiseemned", "tofu": "tofu",
    "tomatipüree": "tomatipüree", "tomatipasta": "tomatipasta", "vein": "vein", "kaerajahu": "kaerajahu",
    "kaerahelbed": "kaerahelbed", "manna": "manna", "munanuudlid": "munanuudlid", "riisinuudlid": "riisinuudlid",
    "tšillikaste": "tšillikaste", "hapukapsas": "hapukapsas", "keeduvorst": "keeduvorst", "sai": "sai",
    "sidrun": "sidrun", "kurk": "kurk", "sink": "sink", "peekon": "peekon", "oliivid": "oliivid",
    "suitsukala": "suitsukala", "cheddar juust": "cheddar", "teriyaki kaste": "teriyaki", "täidetud pasta": "tortellini",
    "röstsai": "röstsai", "broilerihakklihasegu": "kanahakkliha", "seapekk": "seapekk", "hirsitangud": "hirss",
    "türgi jogurt": "türgi jogurt", "kookoshelbed": "kookoshelbed", "mandlijahu": "mandlijahu",
    "kalapulgad": "kalapulgad", "india pähklid": "india pähklid", "suhkruherned": "suhkruherned", "keefir": "keefir",
    "kukeseened": "kukeseened", "kõrvitsaseemned": "kõrvitsaseemned", "poolsuitsuvorst": "suitsuvorst",
    "halloumi juust": "halloumi", "lehtsalat": "salat", "piiniaseemned": "piiniaseemned", "pelmeenid": "pelmeenid",
    "siig": "siig", "sinkvorst": "sinkvorst", "vasikaliha": "vasikaliha", "hiina kapsas": "hiina kapsas",
    "gouda juust": "gouda", "tortilja": "tortilja", "toorgrillvorst": "grillvorst",
}

# Dishes that need special kit or shopping the app can't do well.
SKIP_DISH_WORDS = ("suši", "sushi", "vetikal")


def _get(path, cache):
    if cache:
        f = os.path.join(cache, re.sub(r"\W", "_", path) + ".json")
        if os.path.exists(f):
            return json.load(open(f, encoding="utf-8"))
    # NutriData's server doesn't send its intermediate certificate, so verification fails outside
    # browsers. Read-only public data, and the result is reviewed in git, so it's skipped here.
    r = requests.get(f"{API}/{path}", timeout=30, verify=False)
    r.raise_for_status()
    data = r.json()
    time.sleep(0.15)  # be gentle with a public service
    if cache:
        json.dump(data, open(f, "w", encoding="utf-8"), ensure_ascii=False)
    return data


def _lookup(table, name):
    """Value for the longest key the lowercase name starts with, or None."""
    n = name.lower().strip()
    hits = [k for k in table if n == k or n.startswith(k + ",") or n.startswith(k + " ") or n.startswith(k + "/")]
    return table[max(hits, key=len)] if hits else None


def place(name, recipes):
    """("skip"|"pantry"|"item"|"text", value) for one NutriData ingredient name."""
    n = name.lower().strip()
    if any(n == s or n.startswith(s + ",") or n.startswith(s + " ") for s in SKIP):
        return "skip", None
    pantry = _lookup(PANTRY, n)
    if pantry:
        return "pantry", pantry
    word = _lookup(RENAME, n)
    if not word:
        return None, n.split(",")[0].split("/")[0].strip()
    key = catalog.match_ingredient(word, recipes)
    return ("item", key) if key else ("text", word)


# Names that say too little on their own ("Lõhe", "Supp"): the dish keeps NutriData's next part ("Lõhe, ahjus küpsetatud").
GENERIC = {"supp", "pasta", "hautis", "ahjuroog", "pajaroog", "vormiroog", "kotlet", "vokk", "raguu", "risoto",
           "omlett", "šnitsel", "karbonaad", "kalafilee", "broilerifilee", "broileriliha", "spagetid", "makaronid",
           "täisteramakaronid", "räimefilee", "forell", "vikerforell", "tilaapia", "siig", "searibid", "romsteek",
           "strooganov", "kodupraad", "lahtine pirukas", "täidetud pasta", "keedetud veiseliha", "keedetud kaunviljad"}
# Parts that only say how it was prepared or how much fat was used, not what the dish is.
_PREP_NOTES = ("õliga", "võiga", "lisatud rasvaineta", "rasvata", "keskmiselt", "puhastatud", "kondiga", "kondita",
               "luudega", "nahata", "nahaga", "toores", "praetud", "keedetud", "ahjus", "rinnafilee", "kintsuliha",
               "kintsulihast", "filee")


def clean_name(name):
    """Short dish name: "Hakklihakaste, segahakklihast, õliga" → "Hakklihakaste",
    but "Lõhe, ahjus küpsetatud, õliga" → "Lõhe, ahjus küpsetatud"."""
    parts = [p.strip() for p in re.sub(r"\s*\([^)]*\)", "", name).split(",") if p.strip()]
    base = parts[0]
    generic = base.lower() in GENERIC or _lookup(RENAME, base) or _lookup(PANTRY, base)
    detail = next((p for p in parts[1:] if not p.lower().startswith(_PREP_NOTES)), None)
    if generic and detail:
        base = f"{base}, {detail}"
    return base[:1].upper() + base[1:]


def build(cache=None, report=False):
    recipes = catalog.load_recipes()
    groups = {g["id"]: g for g in _get("food-groups", cache)}
    category_of = {grp: c["id"] for c in CATEGORIES for grp in c["groups"]}
    foods = _get("recipes/tka", cache)

    unplaced = Counter()
    by_name = {}
    for food in foods:
        group = groups.get(food["foodGroupId"])
        cat = category_of.get(group["nameEst"]) if group else None
        if food["type"] != "R" or not cat or any(w in food["nameEst"].lower() for w in SKIP_DISH_WORDS):
            continue
        parts = _get(f"recipes/tka/{food['id']}/tka/subrecipes", cache) or []
        placed = [(place(p["nameEst"], recipes), p.get("weightNet") or 0) for p in parts]
        missing = [v for (kind, v), _ in placed if kind is None]
        unplaced.update(missing)
        bought = [(k, v, g) for (k, v), g in placed if k in ("item", "text") and g > 0]
        if missing or len(bought) < 2:
            continue

        total = sum(g for _, g in placed if g > 0)
        portions = max(1.0, total / PORTION_G.get(cat, DEFAULT_PORTION_G))
        ingredients = {}
        for kind, value, grams in bought:
            amount = grams * catalog.BASE_SERVINGS / portions
            if kind == "item":
                spec = recipes["ingredients"][value]
                if spec["unit"] == "pcs":
                    amount = max(1, round(amount / (spec.get("piece_g") or 55)))  # eggs ≈ 55 g
                prev = ingredients.get(value, {"item": value, "amount": 0})
            else:
                prev = ingredients.get(value, {"text": value, "amount": 0})
            prev["amount"] = prev["amount"] + amount
            ingredients[value] = prev
        small = [k for k, ing in ingredients.items() if "text" in ing and ing["amount"] < PANTRY_BELOW_G]
        for k in small:
            del ingredients[k]
        if len(ingredients) < 2:
            continue
        for ing in ingredients.values():
            ing["amount"] = int(round(ing["amount"])) or 1

        dish = {
            "id": f"nd-{food['id']}",
            "name": clean_name(food["nameEst"]),
            "category": cat,
            "ingredients": list(ingredients.values()),
            "pantry": sorted({v for (k, v), _ in placed if k == "pantry"} | set(small)),
            "_source": food["nameEst"],
        }
        # "Kanaliha, rinnafilee, praetud" is cooked meat, not a dish: an ingredient name with little else.
        if _lookup(RENAME, food["nameEst"].split(",")[0]) and len(bought) <= 2:
            continue
        # One dish per name: prefer the plain "…, õliga" variant, then the shortest name.
        rank = ("'" in food["nameEst"], "õliga" not in food["nameEst"], len(food["nameEst"]))  # no chef-named variants
        best = by_name.get(dish["name"])
        if not best or rank < best[0]:
            by_name[dish["name"]] = (rank, dish)

    dishes = sorted((d for _, d in by_name.values()), key=lambda d: (d["category"], d["name"]))
    if report:
        print("Ingredient names it couldn't place (add to RENAME or PANTRY):", file=sys.stderr)
        for name, n in unplaced.most_common(40):
            print(f"  {n:3} {name}", file=sys.stderr)
    return dishes


def write(dishes):
    cats = [{k: c[k] for k in ("id", "name", "emoji")} for c in CATEGORIES]
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("# Generated by scripts/import_nutridata.py. Don't edit by hand; re-run the script.\n"
                "# Source: NutriData toidu koostise andmebaas, Tervise Arengu Instituut (tka.nutridata.ee).\n"
                "# Amounts are for 2 servings, in grams (pieces for eggs and lemons). `item` = ingredient rule,\n"
                "# `text` = free-text search word. `source` is NutriData's own name for the variant used.\n")
        yaml.safe_dump({"categories": cats,
                        "dishes": [{**{k: v for k, v in d.items() if k != "_source"}, "source": d["_source"]}
                                   for d in dishes]},
                       f, allow_unicode=True, sort_keys=False, width=120)
    counts = Counter(d["category"] for d in dishes)
    print(f"{len(dishes)} dishes → {OUT}: " + ", ".join(f"{c['name']} {counts[c['id']]}" for c in CATEGORIES))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cache", help="directory to keep downloads in")
    ap.add_argument("--report", action="store_true", help="list ingredient names it couldn't place")
    args = ap.parse_args()
    if args.cache:
        os.makedirs(args.cache, exist_ok=True)
    write(build(args.cache, args.report))


if __name__ == "__main__":
    main()
