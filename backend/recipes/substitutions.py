"""Suggest practical substitutes for a missing ingredient.

The finder is only useful if a near-match can become dinner. This module holds
a curated, deliberately conservative substitution table for common pantry
items. It is not a nutrition database: a suggestion says what to reach for and
the ratio to use, and the UI marks suggestions the cook already has.

Matching is token-based so it works across the many wordings in the corpus:
``Butter, without salt``, ``unsalted butter`` and ``salted butter`` all reach
the butter rule, while ``peanut butter`` and ``cocoa butter`` hit their own
more specific rules first.
"""

from dataclasses import dataclass

from .finder import terms_touch
from .matching import significant, tokenize


@dataclass(frozen=True)
class Substitute:
    name: str
    note: str


def _key(text):
    return tuple(tokenize(text))


# Order matters only for equally specific keys; matching tries the longest key
# first, so "peanut butter" wins over "butter" and "red wine vinegar" wins over
# "red wine".
RULES = (
    ("peanut butter", (
        Substitute("Almond butter", "1:1"),
        Substitute("Sunflower seed butter", "1:1"),
        Substitute("Tahini", "1:1, loosen with a little water"),
    )),
    ("almond butter", (
        Substitute("Peanut butter", "1:1"),
        Substitute("Cashew butter", "1:1"),
        Substitute("Tahini", "1:1"),
    )),
    ("cocoa butter", (
        Substitute("Coconut oil", "1:1 in baking"),
        Substitute("Vegetable shortening", "1:1"),
    )),
    ("unsalted butter", (
        Substitute("Salted butter", "1:1; omit any added salt"),
        Substitute("Margarine", "1:1"),
        Substitute("Olive oil", "¾ cup oil per cup butter"),
    )),
    ("butter", (
        Substitute("Margarine", "1:1"),
        Substitute("Olive oil", "¾ cup oil per cup butter"),
        Substitute("Coconut oil", "1:1"),
    )),
    ("buttermilk", (
        Substitute("Milk + lemon juice", "1 tbsp lemon juice per cup; rest 5 min"),
        Substitute("Plain yogurt + milk", "¾ cup yogurt + ¼ cup milk per cup"),
        Substitute("Sour cream + milk", "¾ cup sour cream + ¼ cup milk"),
    )),
    ("heavy cream", (
        Substitute("Milk + melted butter", "¾ cup milk + ¼ cup butter per cup"),
        Substitute("Evaporated milk", "1:1; do not boil"),
        Substitute("Full-fat coconut milk", "1:1"),
    )),
    ("whipping cream", (
        Substitute("Heavy cream", "1:1"),
        Substitute("Full-fat coconut milk", "Chill and whip; 1:1"),
        Substitute("Evaporated milk", "1:1; do not boil"),
    )),
    ("half and half", (
        Substitute("Milk + cream", "½ cup milk + ½ cup cream"),
        Substitute("Evaporated milk", "1:1"),
    )),
    ("sour cream", (
        Substitute("Plain yogurt", "1:1"),
        Substitute("Milk + lemon juice", "1 cup milk + 1 tbsp lemon juice"),
        Substitute("Crème fraîche", "1:1"),
    )),
    ("cream cheese", (
        Substitute("Mascarpone", "1:1"),
        Substitute("Greek yogurt", "Drain well; 1:1"),
        Substitute("Cottage cheese", "Blend smooth; 1:1"),
    )),
    ("evaporated milk", (
        Substitute("Milk", "Reduce by half over low heat"),
        Substitute("Powdered milk + water", "Follow the packet ratio"),
    )),
    ("condensed milk", (
        Substitute("Evaporated milk + sugar", "1 cup milk + 1¼ cups sugar; heat"),
        Substitute("Coconut milk + sugar", "For a dairy-free version"),
    )),
    ("coconut milk", (
        Substitute("Evaporated milk", "1:1"),
        Substitute("Heavy cream + coconut extract", "1:1; add extract to taste"),
        Substitute("Cashew cream", "1:1"),
    )),
    ("oat milk", (
        Substitute("Soy milk", "1:1"),
        Substitute("Almond milk", "1:1"),
        Substitute("Dairy milk", "1:1"),
    )),
    ("soy milk", (
        Substitute("Oat milk", "1:1"),
        Substitute("Almond milk", "1:1"),
        Substitute("Dairy milk", "1:1"),
    )),
    ("almond milk", (
        Substitute("Oat milk", "1:1"),
        Substitute("Soy milk", "1:1"),
        Substitute("Dairy milk", "1:1"),
    )),
    ("yogurt", (
        Substitute("Sour cream", "1:1"),
        Substitute("Buttermilk", "1:1; thin with milk if needed"),
        Substitute("Mayonnaise", "1:1 in dressings"),
    )),
    ("egg white", (
        Substitute("Aquafaba", "3 tbsp per egg white"),
        Substitute("Flax egg", "1 tbsp ground flax + 3 tbsp water"),
    )),
    ("egg yolk", (
        Substitute("Silken tofu", "2 tbsp blended tofu per yolk"),
        Substitute("Flax egg", "For binding only"),
    )),
    ("egg", (
        Substitute("Flax egg", "1 tbsp ground flax + 3 tbsp water per egg"),
        Substitute("Chia egg", "1 tbsp chia + 3 tbsp water per egg"),
        Substitute("Silken tofu", "¼ cup blended tofu per egg"),
    )),
    ("cake flour", (
        Substitute("All-purpose flour + cornstarch", "1 cup minus 2 tbsp flour + 2 tbsp cornstarch"),
        Substitute("All-purpose flour", "1:1; slightly less tender"),
    )),
    ("bread flour", (
        Substitute("All-purpose flour", "1:1; slightly less chewy"),
        Substitute("Whole wheat flour", "Replace up to half"),
    )),
    ("whole wheat flour", (
        Substitute("All-purpose flour", "1:1"),
        Substitute("White whole wheat flour", "1:1"),
    )),
    ("self-rising flour", (
        Substitute("All-purpose flour + baking powder", "1 cup + 1½ tsp baking powder + ¼ tsp salt"),
        Substitute("All-purpose flour", "Add leavening separately"),
    )),
    ("all-purpose flour", (
        Substitute("Whole wheat flour", "1:1; add a little liquid"),
        Substitute("Bread flour", "1:1; expect more chew"),
        Substitute("Gluten-free flour blend", "1:1 with a binder"),
    )),
    ("flour", (
        Substitute("Whole wheat flour", "1:1; add a little liquid"),
        Substitute("Gluten-free flour blend", "1:1 with a binder"),
        Substitute("Oat flour", "1:1 by weight"),
    )),
    ("cornstarch", (
        Substitute("All-purpose flour", "2 tbsp flour per tbsp cornstarch"),
        Substitute("Arrowroot", "1:1"),
        Substitute("Tapioca starch", "1:1"),
    )),
    ("baking powder", (
        Substitute("Baking soda + cream of tartar", "¼ tsp soda + ½ tsp cream of tartar per tsp"),
        Substitute("Self-rising flour", "Adjust the flour and salt"),
    )),
    ("baking soda", (
        Substitute("Baking powder", "Use 3 times as much; omit added salt"),
    )),
    ("yeast", (
        Substitute("Sourdough starter", "1 cup starter per ¼ oz yeast; adjust flour"),
        Substitute("Baking powder + baking soda", "For quick breads only"),
    )),
    ("powdered sugar", (
        Substitute("Granulated sugar + cornstarch", "Blend 1 cup sugar + 1 tsp cornstarch"),
        Substitute("Caster sugar", "Blend until fine"),
    )),
    ("brown sugar", (
        Substitute("White sugar + molasses", "1 cup sugar + 1 tbsp molasses"),
        Substitute("Coconut sugar", "1:1"),
    )),
    ("caster sugar", (
        Substitute("Granulated sugar", "1:1"),
        Substitute("Powdered sugar", "Not for creaming"),
    )),
    ("sugar", (
        Substitute("Honey", "¾ cup per cup; reduce liquid"),
        Substitute("Maple syrup", "¾ cup per cup; reduce liquid"),
        Substitute("Coconut sugar", "1:1"),
    )),
    ("honey", (
        Substitute("Maple syrup", "1:1"),
        Substitute("Agave syrup", "1:1"),
    )),
    ("maple syrup", (
        Substitute("Honey", "1:1"),
        Substitute("Agave syrup", "1:1"),
    )),
    ("molasses", (
        Substitute("Honey", "Use a little more; milder"),
        Substitute("Brown sugar + water", "For colour and sweetness"),
    )),
    ("vanilla extract", (
        Substitute("Vanilla bean paste", "1:1"),
        Substitute("Maple syrup", "Use half the amount"),
    )),
    ("soy sauce", (
        Substitute("Tamari", "1:1; gluten-free"),
        Substitute("Coconut aminos", "1:1; sweeter and less salty"),
        Substitute("Worcestershire sauce", "Use less; adjust salt"),
    )),
    ("tamari", (
        Substitute("Soy sauce", "1:1"),
        Substitute("Coconut aminos", "1:1"),
    )),
    ("worcestershire", (
        Substitute("Soy sauce + vinegar", "2 parts soy sauce + 1 part vinegar"),
        Substitute("Balsamic vinegar", "Use less; sweeter"),
    )),
    ("balsamic vinegar", (
        Substitute("Red wine vinegar + sugar", "1 tbsp sugar per ½ cup vinegar"),
        Substitute("Apple cider vinegar", "1:1; sharper"),
    )),
    ("red wine vinegar", (
        Substitute("White wine vinegar", "1:1"),
        Substitute("Apple cider vinegar", "1:1"),
        Substitute("Lemon juice", "1:1"),
    )),
    ("white wine vinegar", (
        Substitute("Red wine vinegar", "1:1"),
        Substitute("Apple cider vinegar", "1:1"),
        Substitute("Lemon juice", "1:1"),
    )),
    ("apple cider vinegar", (
        Substitute("White wine vinegar", "1:1"),
        Substitute("Lemon juice", "1:1"),
    )),
    ("vinegar", (
        Substitute("Lemon juice", "1:1"),
        Substitute("Lime juice", "1:1"),
        Substitute("White wine", "1:1 in cooking"),
    )),
    ("lemon juice", (
        Substitute("Lime juice", "1:1"),
        Substitute("White wine vinegar", "Use half the amount"),
        Substitute("Lemon zest + water", "1 tsp zest + 1 tbsp water per tbsp"),
    )),
    ("lime juice", (
        Substitute("Lemon juice", "1:1"),
        Substitute("Rice vinegar", "Use half the amount"),
    )),
    ("lemon", (
        Substitute("Lime", "1:1; sharper"),
        Substitute("Orange", "1:1; sweeter"),
    )),
    ("lime", (
        Substitute("Lemon", "1:1"),
        Substitute("Orange", "1:1; sweeter"),
    )),
    ("white wine", (
        Substitute("Chicken or vegetable stock", "1:1"),
        Substitute("Dry vermouth", "1:1"),
        Substitute("Apple juice + vinegar", "1:1; add vinegar to taste"),
    )),
    ("red wine", (
        Substitute("Beef stock", "1:1"),
        Substitute("Grape juice + vinegar", "1:1; add vinegar to taste"),
        Substitute("Pomegranate juice", "1:1; sweeter"),
    )),
    ("wine", (
        Substitute("Stock", "1:1"),
        Substitute("Grape juice + vinegar", "1:1; add vinegar to taste"),
        Substitute("Water + lemon juice", "For deglazing"),
    )),
    ("beer", (
        Substitute("Stock", "1:1"),
        Substitute("Apple cider", "1:1; sweeter"),
        Substitute("Ginger ale", "1:1; sweeter"),
    )),
    ("chicken stock", (
        Substitute("Vegetable stock", "1:1"),
        Substitute("Water + bouillon", "Follow the packet ratio"),
        Substitute("Mushroom stock", "1:1; deeper flavour"),
    )),
    ("chicken broth", (
        Substitute("Vegetable stock", "1:1"),
        Substitute("Water + bouillon", "Follow the packet ratio"),
    )),
    ("beef stock", (
        Substitute("Chicken stock", "1:1; lighter"),
        Substitute("Vegetable stock", "1:1"),
        Substitute("Water + bouillon", "Follow the packet ratio"),
    )),
    ("beef broth", (
        Substitute("Chicken stock", "1:1; lighter"),
        Substitute("Vegetable stock", "1:1"),
    )),
    ("vegetable stock", (
        Substitute("Chicken stock", "1:1"),
        Substitute("Water + bouillon", "Follow the packet ratio"),
        Substitute("Mushroom stock", "1:1"),
    )),
    ("vegetable broth", (
        Substitute("Chicken stock", "1:1"),
        Substitute("Water + bouillon", "Follow the packet ratio"),
    )),
    ("stock", (
        Substitute("Water + bouillon", "Follow the packet ratio"),
        Substitute("Vegetable stock", "1:1"),
    )),
    ("broth", (
        Substitute("Water + bouillon", "Follow the packet ratio"),
        Substitute("Stock", "1:1"),
    )),
    ("mayonnaise", (
        Substitute("Greek yogurt", "1:1"),
        Substitute("Sour cream", "1:1"),
        Substitute("Avocado", "Mash; 1:1 in sandwiches"),
    )),
    ("dijon mustard", (
        Substitute("Yellow mustard", "1:1; sharper"),
        Substitute("Whole-grain mustard", "1:1"),
    )),
    ("mustard", (
        Substitute("Dijon mustard", "1:1"),
        Substitute("Dry mustard + water", "1 tsp powder + 1 tbsp water"),
    )),
    ("ketchup", (
        Substitute("Tomato paste + vinegar + sugar", "1 cup paste + 2 tbsp vinegar + 2 tbsp sugar"),
        Substitute("Tomato sauce + sugar + vinegar", "Cook down to thicken"),
    )),
    ("tomato paste", (
        Substitute("Tomato sauce", "Reduce by half"),
        Substitute("Crushed tomatoes", "Reduce until thick"),
    )),
    ("tomato sauce", (
        Substitute("Crushed tomatoes", "Blend smooth"),
        Substitute("Tomato paste + water", "Thin to the needed consistency"),
    )),
    ("crushed tomato", (
        Substitute("Diced tomatoes", "Blend briefly"),
        Substitute("Tomato sauce", "1:1; thinner"),
    )),
    ("canned tomato", (
        Substitute("Diced tomatoes", "Blend briefly"),
        Substitute("Tomato sauce", "1:1; thinner"),
    )),
    ("tomato", (
        Substitute("Canned tomatoes", "Drain well"),
        Substitute("Red pepper", "In cooked dishes, for colour"),
    )),
    ("olive oil", (
        Substitute("Canola oil", "1:1"),
        Substitute("Avocado oil", "1:1"),
        Substitute("Melted butter", "1:1; lower smoke point"),
    )),
    ("sesame oil", (
        Substitute("Toasted sesame oil", "Use less; stronger"),
        Substitute("Peanut oil", "1:1"),
        Substitute("Vegetable oil", "1:1; less flavour"),
    )),
    ("coconut oil", (
        Substitute("Butter", "1:1"),
        Substitute("Vegetable oil", "1:1"),
    )),
    ("canola oil", (
        Substitute("Vegetable oil", "1:1"),
        Substitute("Sunflower oil", "1:1"),
    )),
    ("vegetable oil", (
        Substitute("Canola oil", "1:1"),
        Substitute("Sunflower oil", "1:1"),
        Substitute("Olive oil", "1:1; stronger flavour"),
    )),
    ("oil", (
        Substitute("Melted butter", "1:1"),
        Substitute("Margarine", "1:1; melt first"),
    )),
    ("parmesan", (
        Substitute("Pecorino Romano", "1:1; saltier"),
        Substitute("Gran Padano", "1:1"),
        Substitute("Nutritional yeast", "For a dairy-free version"),
    )),
    ("mozzarella", (
        Substitute("Provolone", "1:1"),
        Substitute("Cheddar", "1:1; sharper"),
    )),
    ("cheddar", (
        Substitute("Gruyère", "1:1"),
        Substitute("Colby", "1:1; milder"),
        Substitute("Monterey Jack", "1:1; milder"),
    )),
    ("ricotta", (
        Substitute("Cottage cheese", "Drain well; 1:1"),
        Substitute("Mascarpone", "1:1; richer"),
    )),
    ("mascarpone", (
        Substitute("Cream cheese", "1:1"),
        Substitute("Greek yogurt", "Drain well; 1:1"),
    )),
    ("cream", (
        Substitute("Evaporated milk", "1:1"),
        Substitute("Full-fat coconut milk", "1:1"),
        Substitute("Milk + butter", "¾ cup milk + ¼ cup butter per cup"),
    )),
    ("panko", (
        Substitute("Breadcrumbs", "1:1"),
        Substitute("Crushed crackers", "1:1"),
    )),
    ("breadcrumb", (
        Substitute("Crushed crackers", "1:1"),
        Substitute("Rolled oats", "Blend fine; 1:1"),
        Substitute("Panko", "1:1"),
    )),
    ("bread", (
        Substitute("Tortillas", "For wraps and sandwiches"),
        Substitute("Lettuce leaves", "For wraps"),
        Substitute("Crackers", "For crumbs"),
    )),
    ("spaghetti", (
        Substitute("Linguine", "1:1"),
        Substitute("Penne", "1:1"),
        Substitute("Zucchini noodles", "Gluten-free; cook briefly"),
    )),
    ("pasta", (
        Substitute("Rice", "Gluten-free"),
        Substitute("Zucchini noodles", "Gluten-free"),
        Substitute("Quinoa", "Gluten-free"),
    )),
    ("rice", (
        Substitute("Quinoa", "1:1; adjust cooking time"),
        Substitute("Couscous", "1:1; not gluten-free"),
        Substitute("Cauliflower rice", "Low-carb"),
    )),
    ("quinoa", (
        Substitute("Rice", "1:1"),
        Substitute("Bulgur", "1:1; not gluten-free"),
        Substitute("Millet", "1:1"),
    )),
    ("sweet potato", (
        Substitute("Butternut squash", "1:1"),
        Substitute("Potato", "1:1"),
        Substitute("Carrot", "1:1; sweeter"),
    )),
    ("potato", (
        Substitute("Sweet potato", "1:1"),
        Substitute("Cauliflower", "For mash"),
        Substitute("Parsnip", "1:1"),
    )),
    ("shallot", (
        Substitute("Onion", "1:1"),
        Substitute("Leek", "1:1; milder"),
    )),
    ("leek", (
        Substitute("Onion", "1:1"),
        Substitute("Shallot", "1:1; milder"),
    )),
    ("onion", (
        Substitute("Shallot", "1:1"),
        Substitute("Leek", "1:1"),
        Substitute("Onion powder", "1 tsp per small onion"),
    )),
    ("garlic", (
        Substitute("Garlic powder", "⅛ tsp per clove"),
        Substitute("Garlic paste", "1:1"),
        Substitute("Shallot", "Milder; 1:1"),
    )),
    ("ginger", (
        Substitute("Ground ginger", "¼ tsp per tbsp fresh"),
        Substitute("Galangal", "1:1"),
    )),
    ("parsley", (
        Substitute("Cilantro", "1:1"),
        Substitute("Celery leaves", "1:1"),
    )),
    ("cilantro", (
        Substitute("Parsley", "1:1"),
        Substitute("Thai basil", "1:1; different aroma"),
    )),
    ("basil", (
        Substitute("Oregano", "1:1"),
        Substitute("Thyme", "Use less"),
    )),
    ("oregano", (
        Substitute("Marjoram", "1:1"),
        Substitute("Thyme", "1:1"),
    )),
    ("thyme", (
        Substitute("Oregano", "1:1"),
        Substitute("Savory", "1:1"),
    )),
    ("rosemary", (
        Substitute("Thyme", "1:1"),
        Substitute("Sage", "Use less"),
    )),
    ("sage", (
        Substitute("Rosemary", "Use less"),
        Substitute("Thyme", "1:1"),
    )),
    ("bay leaf", (
        Substitute("Thyme", "A pinch"),
        Substitute("Oregano", "A pinch"),
    )),
    ("nutmeg", (
        Substitute("Mace", "1:1"),
        Substitute("Cinnamon", "Use less; different flavour"),
    )),
    ("cinnamon", (
        Substitute("Allspice", "1:1; similar warmth"),
        Substitute("Nutmeg", "Use less"),
    )),
    ("smoked paprika", (
        Substitute("Paprika + liquid smoke", "A few drops of smoke"),
        Substitute("Chipotle powder", "Use less; spicier"),
    )),
    ("paprika", (
        Substitute("Smoked paprika", "Use less; stronger"),
        Substitute("Cayenne + sweet pepper", "For colour and heat"),
    )),
    ("cayenne", (
        Substitute("Chili powder", "Use more; milder"),
        Substitute("Hot sauce", "Adjust for salt"),
    )),
    ("chili powder", (
        Substitute("Paprika + cumin + cayenne", "1 tsp + 1 tsp + ¼ tsp per tbsp"),
        Substitute("Cayenne", "Use much less"),
    )),
    ("cumin", (
        Substitute("Coriander", "1:1; different flavour"),
        Substitute("Caraway", "Use less"),
    )),
    ("coriander", (
        Substitute("Cumin", "1:1; different flavour"),
        Substitute("Caraway", "Use less"),
    )),
    ("turmeric", (
        Substitute("Saffron", "For colour; use a pinch"),
        Substitute("Ginger", "Different flavour"),
    )),
    ("saffron", (
        Substitute("Turmeric", "For colour; use less"),
    )),
    ("sesame seed", (
        Substitute("Sunflower seed", "1:1"),
        Substitute("Poppy seed", "Different texture"),
    )),
    ("raisin", (
        Substitute("Dried cranberry", "1:1"),
        Substitute("Chopped date", "1:1"),
    )),
    ("walnut", (
        Substitute("Pecan", "1:1"),
        Substitute("Almond", "1:1"),
    )),
    ("almond", (
        Substitute("Cashew", "1:1"),
        Substitute("Walnut", "1:1"),
    )),
    ("pecan", (
        Substitute("Walnut", "1:1"),
        Substitute("Almond", "1:1"),
    )),
    ("chocolate", (
        Substitute("Cocoa powder + butter", "3 tbsp cocoa + 1 tbsp butter per oz"),
        Substitute("Carob chips", "1:1; caffeine-free"),
    )),
    ("cocoa powder", (
        Substitute("Unsweetened chocolate", "Melt; reduce sugar"),
        Substitute("Carob powder", "1:1"),
    )),
    ("tofu", (
        Substitute("Paneer", "1:1; not vegan"),
        Substitute("Tempeh", "1:1"),
        Substitute("Chicken", "1:1"),
    )),
    ("tempeh", (
        Substitute("Tofu", "1:1"),
        Substitute("Seitan", "1:1; not gluten-free"),
    )),
    ("chicken", (
        Substitute("Turkey", "1:1"),
        Substitute("Tofu", "1:1; press and marinate"),
        Substitute("Jackfruit", "Shredded; for saucy dishes"),
    )),
    ("beef", (
        Substitute("Lamb", "1:1"),
        Substitute("Mushrooms", "For texture; use less"),
        Substitute("Lentils", "For ground beef dishes"),
    )),
    ("pork", (
        Substitute("Chicken", "1:1"),
        Substitute("Turkey", "1:1"),
    )),
    ("bacon", (
        Substitute("Pancetta", "1:1"),
        Substitute("Smoked turkey", "1:1; leaner"),
        Substitute("Tempeh bacon", "1:1; vegetarian"),
    )),
    ("shrimp", (
        Substitute("Scallops", "1:1"),
        Substitute("Firm white fish", "1:1"),
        Substitute("Chicken", "1:1; cook through"),
    )),
    ("fish", (
        Substitute("Chicken", "1:1"),
        Substitute("Tofu", "1:1"),
        Substitute("Hearts of palm", "For a vegan texture"),
    )),
    ("mushroom", (
        Substitute("Zucchini", "1:1"),
        Substitute("Eggplant", "1:1"),
        Substitute("Soy sauce", "For umami; use less"),
    )),
    ("spinach", (
        Substitute("Kale", "1:1"),
        Substitute("Swiss chard", "1:1"),
    )),
    ("kale", (
        Substitute("Spinach", "1:1"),
        Substitute("Swiss chard", "1:1"),
        Substitute("Collard greens", "1:1"),
    )),
    ("broccoli", (
        Substitute("Cauliflower", "1:1"),
        Substitute("Romanesco", "1:1"),
    )),
    ("cauliflower", (
        Substitute("Broccoli", "1:1"),
        Substitute("Potato", "For mash"),
    )),
    ("carrot", (
        Substitute("Parsnip", "1:1"),
        Substitute("Sweet potato", "1:1"),
        Substitute("Butternut squash", "1:1"),
    )),
    ("celery", (
        Substitute("Fennel", "1:1"),
        Substitute("Celery seed", "A pinch"),
    )),
    ("zucchini", (
        Substitute("Yellow squash", "1:1"),
        Substitute("Eggplant", "For roasting"),
    )),
    ("eggplant", (
        Substitute("Zucchini", "1:1"),
        Substitute("Mushroom", "1:1"),
        Substitute("Portobello", "1:1"),
    )),
    ("chickpea", (
        Substitute("White bean", "1:1"),
        Substitute("Lentil", "1:1"),
    )),
    ("lentil", (
        Substitute("Split pea", "1:1"),
        Substitute("Bean", "1:1"),
    )),
    ("bean", (
        Substitute("Chickpea", "1:1"),
        Substitute("Lentil", "1:1"),
    )),
    ("pea", (
        Substitute("Edamame", "1:1"),
        Substitute("Fava bean", "1:1"),
    )),
    ("cabbage", (
        Substitute("Napa cabbage", "1:1"),
        Substitute("Brussels sprouts", "Shred; 1:1"),
    )),
    ("cucumber", (
        Substitute("Zucchini", "1:1; raw"),
        Substitute("Celery", "For crunch"),
    )),
    ("avocado", (
        Substitute("Hummus", "For sandwiches"),
        Substitute("Greek yogurt", "For creamy dishes"),
    )),
    ("salt", (
        Substitute("Sea salt", "1:1 by volume"),
        Substitute("Kosher salt", "Use a little more by volume"),
        Substitute("Soy sauce", "Use less; add liquid"),
    )),
    ("pepper", (
        Substitute("White pepper", "1:1; milder"),
        Substitute("Cayenne", "Use much less"),
    )),
)

# Longest key first so a specific rule beats a broader one.
RULES = tuple(
    sorted(
        ((_key(name), substitutes) for name, substitutes in RULES),
        key=lambda rule: len(rule[0]),
        reverse=True,
    )
)


def _ingredient_tokens(name):
    return set(tokenize(name))


def _substitute_tokens(name):
    tokens = set(significant(tokenize(name)))
    return tokens or _ingredient_tokens(name)


def _in_pantry(name, pantry_terms):
    tokens = _substitute_tokens(name)
    return any(terms_touch(term.tokens, tokens) for term in pantry_terms or [])


def suggest(ingredient, pantry_terms=None):
    """Return substitute dictionaries for one ingredient name.

    Suggestions already represented in the pantry are listed first so the UI
    can point at something the cook can use immediately.
    """
    tokens = _ingredient_tokens(ingredient)
    if not tokens:
        return []
    for keys, substitutes in RULES:
        if all(key in tokens for key in keys):
            items = [
                {
                    "name": substitute.name,
                    "note": substitute.note,
                    "in_pantry": _in_pantry(substitute.name, pantry_terms),
                }
                for substitute in substitutes
            ]
            items.sort(key=lambda item: not item["in_pantry"])
            return items
    return []


def suggestions_for_recipe(ingredients, pantry_terms=None):
    """Return ``[{"ingredient": ..., "substitutes": [...]}, ...]``.

    Ingredients with no curated rule are omitted; an empty section is more
    honest than inventing a swap.
    """
    results = []
    seen = set()
    for ingredient in ingredients or []:
        key = " ".join(str(ingredient).split()).casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        substitutes = suggest(ingredient, pantry_terms)
        if substitutes:
            results.append(
                {"ingredient": " ".join(str(ingredient).split()), "substitutes": substitutes}
            )
    return results
