"""English ingredient names in Estonian (core/english.py, WEB-51), without the internet."""
import pytest

from core import catalog, english
from core.recipe_import import from_text, to_item


@pytest.mark.parametrize("line, item", [
    ("1 lb ground beef", "450 g veisehakkliha"),           # pounds and ounces in grams
    ("8 oz mushrooms", "230 g šampinjonid"),
    ("2 large red onions, diced", "2 punane sibul"),         # describing words and plurals
    ("2 boneless skinless chicken thighs", "2 kanakintsuliha"),
    ("5 chopped cloves Garlic", "5 küüslauk"),
    ("1/2 tsp Cloves", "nelk"),                              # the spice, as a name of its own
    ("1 (14 oz) can chickpeas, drained", "1 kikerherned"),   # a can is one pack
    ("400g can chopped tomatoes", "400g tükeldatud tomatid"),
    ("1 ½ tbsp Red Wine Vinegar", "veiniäädikas"),
    ("1 1/2 cups Flour", "jahu"),                            # cups: one pack
    ("175g/6oz plain flour", "175g nisujahu"),
    ("For frying Vegetable Oil", "rapsiõli"),
    ("Salt and pepper to taste", "sool ja pipar"),
    ("chicken or turkey", "kana või kalkun"),                # alternatives stay alternatives
    ("All-purpose flour", "nisujahu"),
    ("1 litre hot Vegetable Stock", "1 l köögiviljapuljong"),
    ("1 lb Fish fillet", "450 g fish fillet"),               # not on the list: the amount still in grams
    ("almond milk", "mandlijook"),
    ("coconut water", "coconut water"),                      # never a part of the name: that would be vesi
    ("Water", None),
])
def test_english_lines_become_estonian_items(line, item):
    assert to_item(line) == item


@pytest.mark.parametrize("line", ["500 g kanafilee", "2 sibulat", "paprika", "1 sibul", "või", "pasta"])
def test_estonian_stays_as_it_is(line):
    assert to_item(line) == line


def test_a_typed_english_item_keeps_its_name_and_is_found_in_estonian():
    recipes = catalog.load_recipes()
    need = catalog.to_need("chicken breast 1 lb", recipes)
    assert need["label"] == "chicken breast" and need["rule"] == "kanafilee" and need["amount"] == 450
    need = catalog.to_need("coconut milk", recipes)
    assert need["label"] == "coconut milk" and need["text"] == "kookospiim"


def test_a_pasted_english_caption_gives_what_to_buy():
    found = from_text("Creamy chicken pasta 🍝\nServes 4\nIngredients:\n- 1 lb chicken breast\n- 2 cups penne\n"
                      "- 1 cup heavy cream\n- 3 cloves garlic, minced\n- Salt and pepper\n- 1 cup dulce de leche\n"
                      "Method:\n1. Cook the pasta.")
    assert found["name"] == "Creamy chicken pasta" and found["servings"] == 4
    assert found["items"] == ["450 g kanafilee", "penne", "vahukoor", "küüslauk", "sool ja pipar"]
    assert found["skipped"] == ["dulce de leche"]   # not on the list: the person adds it
    assert found["english"] == 4  # "penne" is the same in both


def test_the_word_list_is_written_the_way_it_is_read():
    for name, words in english.names().items():
        assert name == name.lower().strip() and words and words == words.strip(), name
        assert not catalog.match_ingredient(name), f"{name} is an Estonian ingredient: it would never be read"
