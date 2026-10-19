"""Convert recipe quantities to grams and split quantities out of lines.

Ingredient measures come from the USDA foodPortions table as ``amount`` units
weighing ``gram_weight`` grams, so grams are always
``amount_wanted * gram_weight / measure.amount``. That is the only way a
volume becomes a mass here: nothing assumes a density, because the guess work
is exactly what would make the per-serving figure worthless.
"""

import re

# Canonical name for every unit spelling USDA writes in foodPortions. The word
# has to open the label because only then does it describe ``amount``: in
# "oz (approx 2/3 cup)" the amount is ounces, not cups.
MEASURE_SYNONYMS = {
    # volume
    "cup": "cup", "cups": "cup",
    "tbsp": "tbsp", "tablespoon": "tbsp", "tablespoons": "tbsp",
    "tsp": "tsp", "teaspoon": "tsp", "teaspoons": "tsp",
    "pint": "pint", "pints": "pint",
    "quart": "quart", "quarts": "quart",
    "gallon": "gallon", "gallons": "gallon",
    "fl oz": "fl oz", "fluid ounce": "fl oz", "fluid ounces": "fl oz",
    "ml": "ml", "milliliter": "ml", "milliliters": "ml",
    "l": "l", "liter": "l", "liters": "l", "litre": "l", "litres": "l",
    # mass
    "oz": "oz", "ounce": "oz", "ounces": "oz",
    "lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb",
    "g": "g", "gram": "g", "grams": "g",
    "kg": "kg", "kilogram": "kg", "kilograms": "kg",
    "mg": "mg", "milligram": "mg", "milligrams": "mg",
    # count
    "each": "each",
    "slice": "slice", "slices": "slice",
    "piece": "piece", "pieces": "piece",
    "clove": "clove", "cloves": "clove",
    "can": "can", "cans": "can",
    "jar": "jar", "jars": "jar",
    "package": "package", "packages": "package", "pkg": "package",
    "stick": "stick", "sticks": "stick",
    "ear": "ear", "ears": "ear",
    "stalk": "stalk", "stalks": "stalk",
    "bunch": "bunch", "bunches": "bunch",
    "egg": "egg", "eggs": "egg",
    "large": "large", "medium": "medium", "small": "small",
    "wedge": "wedge", "wedges": "wedge",
    "fillet": "fillet", "fillets": "fillet",
    "steak": "steak", "steaks": "steak",
    "link": "link", "links": "link",
    "bar": "bar", "bars": "bar",
    "head": "head", "heads": "head",
    "roll": "roll", "rolls": "roll",
    "spear": "spear", "spears": "spear",
    "scoop": "scoop", "scoops": "scoop",
    "crust": "crust", "crusts": "crust",
    "loaf": "loaf", "loaves": "loaf",
    "muffin": "muffin", "muffins": "muffin",
    "biscuit": "biscuit", "biscuits": "biscuit",
    "pancake": "pancake", "pancakes": "pancake",
    "tortilla": "tortilla", "tortillas": "tortilla",
    "bun": "bun", "buns": "bun",
    "waffle": "waffle", "waffles": "waffle",
    "pizza": "pizza", "pizzas": "pizza",
    "chop": "chop", "chops": "chop",
    "roast": "roast", "roasts": "roast",
    "tomato": "tomato", "tomatoes": "tomato",
    "banana": "banana", "bananas": "banana",
    "onion": "onion", "onions": "onion",
    "olive": "olive", "olives": "olive",
    "cookie": "cookie", "cookies": "cookie",
    "drumstick": "drumstick", "drumsticks": "drumstick",
}

# These spellings keep into a standard unit only when they open a label.
LEADING_UNIT = re.compile(r"([a-z]+(?:\s+[a-z]+)?)")


def normalize_measure(label):
    """Map free-text measure wording onto a canonical unit name, or None.

    USDA records the unit in a different field per dataset -- ``modifier`` in
    SR Legacy, ``measureUnit`` in Foundation, ``portionDescription`` in API
    responses -- so all of them arrive here as text such as "cup, chopped" or
    "tbsp". The unit has to open the label: when it does not, the label is
    describing a portion rather than stating one, as in "serving 1/2 cup"
    where the dataset's ``amount`` is 0.12 rather than 0.5. Reading that as
    half a cup would overstate the weight tenfold, so such portions are
    dropped instead of guessed at.
    """
    if not label:
        return None
    text = " ".join(str(label).split()).lower()
    match = LEADING_UNIT.match(text)
    if not match:
        return None
    phrase = match.group(1)
    return MEASURE_SYNONYMS.get(phrase) or MEASURE_SYNONYMS.get(phrase.split()[0])


VOLUME_UNITS = frozenset({"ml", "l", "fl oz", "tsp", "tbsp", "cup", "pint", "quart", "gallon"})
MASS_UNITS = frozenset({"mg", "g", "kg", "oz", "lb"})

# The only units that convert to each other without a measure from the
# dataset: same dimension, standard sizes. A volume never turns into a mass
# through these tables.
VOLUME_IN_ML = {
    "ml": 1.0, "l": 1000.0, "fl oz": 29.5735,
    "tsp": 4.92892, "tbsp": 14.7868, "cup": 236.588,
    "pint": 473.176, "quart": 946.353, "gallon": 3785.41,
}
MASS_IN_GRAMS = {
    "mg": 0.001, "g": 1.0, "kg": 1000.0, "oz": 28.3495, "lb": 453.592,
}


def _scaled(measure, amount):
    """Grams that ``amount`` of ``measure`` refers to."""
    return amount * measure.gram_weight / measure.amount


def grams_for(measures, unit, amount):
    """Grams for ``amount`` of ``unit`` from an iterable of measures.

    Measures are objects with ``measure``, ``amount`` and ``gram_weight``.
    Returns None when nothing converts, which is the signal to report the line
    rather than to invent a number: count words and empty units only convert
    on an exact measure of the same unit, and a volume needs a volume measure
    for this ingredient.
    """
    if not amount or amount <= 0:
        return None
    measures = list(measures)
    for measure in measures:
        if measure.measure == unit:
            return _scaled(measure, amount)
    if unit in MASS_UNITS:
        return amount * MASS_IN_GRAMS[unit]
    if unit in VOLUME_UNITS:
        wanted_ml = amount * VOLUME_IN_ML[unit]
        for measure in measures:
            if measure.measure in VOLUME_UNITS:
                return _scaled(measure, wanted_ml / VOLUME_IN_ML[measure.measure])
    return None


UNICODE_FRACTIONS = {
    "⅛": " 1/8", "⅜": " 3/8", "⅝": " 5/8", "⅞": " 7/8",
    "⅕": " 1/5", "⅖": " 2/5", "⅗": " 3/5", "⅘": " 4/5",
    "⅙": " 1/6", "⅚": " 5/6", "⅐": " 1/7",
    "¼": " 1/4", "½": " 1/2", "¾": " 3/4",
    "⅓": " 1/3", "⅔": " 2/3",
}

QUANTITY = re.compile(
    r"""^\s*
 (?:
      (?P<integer>\d+)\s+(?P<mixed>\d+)\s*/\s*(?P<mixed_den>\d+)
    | (?P<numerator>\d+)\s*/\s*(?P<denominator>\d+)
    | (?P<decimal>\d+(?:\.\d+)?)
    )
    """,
    re.VERBOSE,
)
UNIT_WORD = re.compile(r"^\s*([A-Za-z]+)")

# Things a recipe uses to connect an amount to an ingredient, not measures.
ARTICLES = frozenset({"of"})


def parse_amount(text):
    """Split the head of an ingredient line into ``(amount, unit, rest)``.

    Reads the number first -- integers, decimals and fractions, whether ASCII
    or the unicode glyphs recipes are written in -- then the next word when it
    names a measure. Lines without a number, like "salt to taste", come back
    as ``(None, None, line)`` and are reported rather than guessed at.
    """
    if not text:
        return None, None, ""
    expanded = str(text)
    for glyph, replacement in UNICODE_FRACTIONS.items():
        expanded = expanded.replace(glyph, replacement)
    expanded = " ".join(expanded.split())
    match = QUANTITY.match(expanded)
    if not match:
        return None, None, expanded

    if match.group("integer") is not None:
        numerator = int(match.group("mixed"))
        denominator = int(match.group("mixed_den"))
        amount = int(match.group("integer")) + (
            numerator / denominator if denominator else 0.0
        )
    elif match.group("numerator") is not None:
        numerator = int(match.group("numerator"))
        denominator = int(match.group("denominator"))
        amount = numerator / denominator if denominator else 0.0
    else:
        amount = float(match.group("decimal"))

    rest = expanded[match.end():]
    unit = None
    word = UNIT_WORD.match(rest)
    if word:
        canonical = MEASURE_SYNONYMS.get(word.group(1).lower())
        if canonical:
            unit = canonical
            rest = rest[word.end():]

    words = rest.split()
    if words and words[0].lower() in ARTICLES and len(words) > 1:
        words = words[1:]
    return amount, unit, " ".join(words)
