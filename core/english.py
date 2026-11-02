# =============================================================================
# ENGLISH INGREDIENT NAMES  (WEB-51: "chicken breast" → kanafilee)
# Most recipes people find on Instagram are in English, and expats type their list in English, but the stores name
# their products in Estonian. The country pack's fixed list (countries/ee/english.yaml) gives the Estonian word for
# common ingredients; pounds and ounces become grams. A name that isn't on the list stays as it was. No AI.
# =============================================================================

import os
import re

from core import catalog

# The stores' country. Another country gets its own countries/<code>/english.yaml (see the multi-country plan).
PACK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "countries", "ee", "english.yaml")

# Words that describe an ingredient rather than name it: "2 large ripe tomatoes", "boneless skinless chicken thighs".
# A name is looked up whole first, so "ground beef" and "crushed tomatoes" keep theirs.
_DESCRIBING = {
    "fresh", "frozen", "dried", "dry", "raw", "cooked", "chopped", "finely", "roughly", "coarsely", "thinly", "diced",
    "sliced", "minced", "grated", "shredded", "crushed", "ground", "peeled", "deseeded", "halved", "quartered", "cubed",
    "trimmed", "rinsed", "drained", "softened", "melted", "beaten", "large", "medium", "small", "big", "ripe",
    "boneless", "skinless", "organic", "lean", "unsalted", "salted", "cold", "warm", "room", "temperature", "good",
    "quality", "thick", "thin", "about", "approx", "approximately", "of", "a", "an", "the", "some", "and", "plus",
    "more", "extra", "for", "serving", "garnish", "to", "taste", "optional", "handful", "bunch", "pinch", "x", "leaf",
    "leaves", "clove", "cloves", "stick", "sticks", "sprig", "sprigs", "mashed", "new", "separated", "seperated",
    "whole", "plain", "pitted", "smoked", "toasted", "roasted", "boiled", "hot", "free", "range", "topping", "dusting",
    "drizzle", "sprinkling", "shaved", "crusty", "floury", "strips", "strip", "bulb", "nut", "nuts",
}
# "1 lb", "8 oz": grams
_WEIGHT = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(lbs?|pounds?|oz|ounces?)\b\.?\s*", re.I)
_WEIGHT_AFTER = re.compile(r"\s(\d+(?:[.,]\d+)?)\s*(lbs?|pounds?|oz|ounces?)\.?\s*$", re.I)  # "chicken breast 1 lb"
_LITRES = re.compile(r"^(\s*\d+(?:[.,]\d+)?)\s*(?:litres?|liters?)\b", re.I)
# "1 can chickpeas", "400 g can of tomatoes", "2 packs of tofu": the number of packs is the amount
_PACK = re.compile(r"^(\s*(?:\d+(?:[.,]\d+)?\s*(?:kg|g|ml|l)?\s+)?)(?:cans?|tins?|jars?|tubs?|packages?|packets?|packs?|"
                   r"bags?|boxes?|bottles?)\b\s*(?:of\s+)?", re.I)
# "chicken or turkey", "salt and pepper": each name on its own, joined the Estonian way
_JOIN = re.compile(r"\s+(or|and|&|/)\s+", re.I)
_JOINED = {"or": " või ", "/": " või ", "and": " ja ", "&": " ja "}


def names():
    """English name → Estonian search words, from the country pack."""
    return catalog.load_yaml(PACK)["names"]


def _names_spaced():
    return {k.replace("-", " "): v for k, v in names().items()}


def _singular(word):
    """The forms an English plural can come from: "tomatoes" → tomato, "berries" → berry, "leaves" → leaf."""
    forms = [word]
    if word.endswith("ies"):
        forms.append(word[:-3] + "y")
    if word.endswith("ves"):
        forms.append(word[:-3] + "f")
    if word.endswith("es"):
        forms.append(word[:-2])
    if word.endswith("s") and not word.endswith("ss"):
        forms.append(word[:-1])
    return forms


def _lookup(words, known):
    if not words:
        return None
    for last in _singular(words[-1]):
        found = known.get(" ".join(words[:-1] + [last]))
        if found:
            return found
    return None


def estonian(name):
    """The Estonian words for an English ingredient name ("Boneless chicken thighs" → kanakintsuliha), or None when
    it isn't on the list or already names an ingredient pantryrun knows."""
    if catalog.match_ingredient(name):
        return None
    known = _names_spaced()
    words = re.findall(r"[a-z]+", name.lower().replace("’", "'").replace("'s", ""))  # "all-purpose" = "all purpose"
    return _lookup(words, known) or _lookup([w for w in words if w not in _DESCRIBING], known)


def _grams(m):
    """450 for "1 lb", 230 for "8 oz": rounded the way a recipe would say it."""
    grams = float(m[1].replace(",", ".")) * (28.35 if m[2].lower().startswith("o") else 453.6)
    return round(grams / 10) * 10 if grams >= 100 else round(grams / 5) * 5 or 5


def metric(item):
    """Pounds and ounces as grams, litres as l, a can or a pack as the number of them: "1 lb ground beef" → "450 g ground beef",
    "1 can chickpeas" → "1 chickpeas"."""
    m = _WEIGHT.match(item)
    if m:
        item = f"{_grams(m)} g {item[m.end():]}"
    m = _WEIGHT_AFTER.search(item)
    if m:
        item = f"{item[:m.start()]} {_grams(m)} g"
    item = _LITRES.sub(r"\1 l", item)
    return _PACK.sub(lambda m: m[1] or "1 ", item, count=1).strip()


def translate(item):
    """A typed item or recipe line with its English name in Estonian, the amount kept ("2 large onions" → "2 sibul",
    "chicken or turkey" → "kana või kalkun"), or None when it isn't English pantryrun knows."""
    item = metric(item)
    lead = re.match(r"^\s*(?:\d+(?:[.,]\d+)?\s*(?:kg|g|dl|cl|ml|l|tk)?\s+)?", item, re.I)
    trail = re.search(r"(?:\s+\d+(?:[.,]\d+)?\s*(?:kg|g|dl|cl|ml|l|tk)?)?\s*$", item[lead.end():], re.I)
    amount, name, after = item[:lead.end()], item[lead.end():][:trail.start()], trail[0]  # "chicken breast 500g"
    parts = _JOIN.split(name)  # names, with the words between them at the odd places
    found = [estonian(p) if i % 2 == 0 else _JOINED[p.lower()] for i, p in enumerate(parts)]
    if not all(found):
        return None
    return amount + "".join(found) + after
