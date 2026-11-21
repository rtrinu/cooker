"""Convert recipe quantities to grams and split quantities out of lines.

Ingredient measures come from the USDA foodPortions table as ``amount`` units
weighing ``gram_weight`` grams, so a measured conversion is always
``amount_wanted * gram_weight / measure.amount``. A mass printed on the recipe
line wins over any portion, and only when the food has no usable measure do we
fall back to a standard cooking weight. Every path returns a confidence and a
short provenance string so a computed panel can say how it was built.
"""

import re
from dataclasses import dataclass

from .standard_weights import (
    SMALL_UNIT_GRAMS,
    grams_for_count,
    grams_for_unit,
    grams_for_volume,
)

# Canonical name for every unit spelling USDA writes in foodPortions. The word
# has to open the label because only then does it describe ``amount``: in
# "oz (approx 2/3 cup)" the amount is ounces, not cups.
MEASURE_SYNONYMS = {
    # volume
    "cup": "cup", "cups": "cup", "c": "cup", "cupful": "cup", "cupfuls": "cup",
    "tbsp": "tbsp", "tbs": "tbsp", "tb": "tbsp", "tbl": "tbsp",
    "tblsp": "tbsp", "tablespoon": "tbsp", "tablespoons": "tbsp",
    "tablespoonful": "tbsp", "tablespoonfuls": "tbsp",
    "spoon": "tbsp", "spoons": "tbsp", "spoonful": "tbsp",
    "spoonfuls": "tbsp", "spoonsful": "tbsp",
    "tsp": "tsp", "t": "tsp", "tspn": "tsp", "teaspoon": "tsp",
    "teaspoons": "tsp", "teaspoonful": "tsp", "teaspoonfuls": "tsp",
    "pint": "pint", "pints": "pint",
    "quart": "quart", "quarts": "quart", "qt": "quart",
    "gallon": "gallon", "gallons": "gallon",
    "gill": "gill", "gills": "gill",
    "fl oz": "fl oz", "fluid ounce": "fl oz", "fluid ounces": "fl oz",
    "ml": "ml", "milliliter": "ml", "milliliters": "ml",
    "l": "l", "liter": "l", "liters": "l", "litre": "l", "litres": "l",
    "dl": "dl", "deciliter": "dl", "deciliters": "dl",
    "decilitre": "dl", "decilitres": "dl",
    "cl": "cl", "centiliter": "cl", "centiliters": "cl",
    "centilitre": "cl", "centilitres": "cl",
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
    # Small count measures. They identify the unit so the name stays clean,
    # but they deliberately have no gram weight: only an exact USDA measure
    # for the ingredient can convert them.
    "pinch": "pinch", "pinches": "pinch",
    "dash": "dash", "dashes": "dash",
    "handful": "handful", "handfuls": "handful",
    "drop": "drop", "drops": "drop",
    "sprig": "sprig", "sprigs": "sprig",
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


VOLUME_UNITS = frozenset({
    "ml", "l", "dl", "cl", "fl oz", "tsp", "tbsp", "cup", "gill", "pint",
    "quart", "gallon",
})
MASS_UNITS = frozenset({"mg", "g", "kg", "oz", "lb"})

# The only units that convert to each other without a measure from the
# dataset: same dimension, standard sizes. A volume never turns into a mass
# through these tables.
VOLUME_IN_ML = {
    "ml": 1.0, "l": 1000.0, "dl": 100.0, "cl": 10.0, "fl oz": 29.5735,
    "tsp": 4.92892, "tbsp": 14.7868, "cup": 236.588, "gill": 118.294,
    "pint": 473.176, "quart": 946.353, "gallon": 3785.41,
}
MASS_IN_GRAMS = {
    "mg": 0.001, "g": 1.0, "kg": 1000.0, "oz": 28.3495, "lb": 453.592,
}

# Every canonical unit that is not a dimension. These are the units that need
# an ingredient-specific weight: "each", "clove", "slice", a size word, and the
# container words a recipe writes as a unit.
COUNT_UNITS = frozenset(
    set(MEASURE_SYNONYMS.values()) - VOLUME_UNITS - MASS_UNITS
)
CONTAINER_UNITS = frozenset({
    "can", "jar", "package", "stick", "loaf", "bunch", "head",
})
SIZE_UNITS = frozenset({"small", "medium", "large"})


@dataclass(frozen=True)
class Quantity:
    """A parsed recipe amount, including an exact mass stated on the line.

    ``amount`` is the value to compute with. For a printed range it is the
    midpoint, and ``low``/``high`` keep the original bounds. ``grams`` is a mass
    the line states outright, such as "¼ cup (1 oz)" or "2 (14 oz) cans"; when
    present it is more exact than any household measure and wins.
    """

    amount: float | None
    unit: str | None
    rest: str
    low: float | None = None
    high: float | None = None
    grams: float | None = None
    note: str = ""


@dataclass(frozen=True)
class Conversion:
    """The result of converting one recipe amount to grams."""

    grams: float
    confidence: float
    method: str
    detail: str = ""
    ambiguous: bool = False

    @property
    def standard(self):
        """Whether this conversion used a fallback rather than measured data."""
        return self.method.startswith("standard")

# USDA foodPortions use US customary volume units and metric mass units in the
# same file. Recording which system a conversion came from matters because a
# US cup is 236.588 ml while a metric cup is 250 ml.
US_CUSTOMARY_UNITS = frozenset({
    "cup", "tbsp", "tsp", "fl oz", "gill", "pint", "quart", "gallon", "oz", "lb",
})
METRIC_UNITS = frozenset({"ml", "l", "dl", "cl", "mg", "g", "kg"})


def measurement_system_for(measure):
    """Which measurement system a canonical unit belongs to."""
    if measure in US_CUSTOMARY_UNITS:
        return "us"
    if measure in METRIC_UNITS:
        return "metric"
    return "unspecified"


def conversion_confidence_for(measure):
    """Confidence in a USDA portion conversion, by unit kind.

    A mass portion is exact arithmetic. A volume portion relies on the density
    of that particular food, which USDA measured but which varies between
    samples. A count portion depends on the size of the item. Keeping these
    apart from nutrition-match confidence is the point of the field.
    """
    if measure in MASS_UNITS:
        return 1.0
    if measure in VOLUME_UNITS:
        return 0.9
    return 0.8



def _scaled(measure, amount):
    """Grams that ``amount`` of ``measure`` refers to."""
    return amount * measure.gram_weight / measure.amount


def _measure_confidence(measure):
    """Confidence stored on a measure, or the default for its unit kind."""
    confidence = getattr(measure, "confidence", None)
    if confidence is not None:
        return confidence
    return conversion_confidence_for(measure.measure)


def _measure_label(measure):
    label = getattr(measure, "source_label", "") or measure.measure
    return f"{measure.amount:g} {label} = {measure.gram_weight:g} g"


_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text):
    return set(_TOKEN.findall(str(text or "").casefold()))


def _choose_measure(candidates, unit, context=""):
    """Pick the measure that best fits the recipe line.

    USDA often has several portions for one unit: "cup, chopped" and "cup,
    sliced", or a small/medium/large egg. Matching preparation and shape words
    from the recipe line is the strongest signal. Confidence and USDA's
    portion order break the remaining ties. A tie between different weights is
    reported as ambiguous rather than hidden.
    """
    context_tokens = _tokens(context)
    scored = []
    for measure in candidates:
        label_tokens = _tokens(
            f"{getattr(measure, 'source_label', '')} "
            f"{getattr(measure, 'preparation_state', '')}"
        )
        overlap = context_tokens & label_tokens
        score = (
            _measure_confidence(measure) * 2
            + len(overlap) * 3
            + (5 if measure.measure == unit else 0)
            - getattr(measure, "sequence", 0) * 0.001
        )
        scored.append((score, measure))

    scored.sort(
        key=lambda item: (
            -item[0],
            getattr(item[1], "sequence", 0),
            getattr(item[1], "pk", 0) or 0,
        )
    )
    best_score, best = scored[0]
    ambiguous = any(
        score > best_score - 0.25
        and abs(measure.gram_weight - best.gram_weight) > 0.5
        for score, measure in scored[1:]
    )
    return best, ambiguous


def _convert_measures(measures, unit, amount, context=""):
    """Grams for ``amount`` of ``unit`` using only the ingredient's measures."""
    if not amount or amount <= 0:
        return None

    measures = list(measures)
    if unit in MASS_UNITS:
        return Conversion(
            amount * MASS_IN_GRAMS[unit], 1.0, "mass", f"{amount:g} {unit}"
        )

    if unit in VOLUME_UNITS:
        exact = [measure for measure in measures if measure.measure == unit]
        if exact:
            measure, ambiguous = _choose_measure(exact, unit, context)
            return Conversion(
                _scaled(measure, amount),
                min(1.0, _measure_confidence(measure)),
                "measure",
                _measure_label(measure),
                ambiguous,
            )
        volumes = [measure for measure in measures if measure.measure in VOLUME_UNITS]
        if volumes:
            measure, ambiguous = _choose_measure(volumes, unit, context)
            wanted_ml = amount * VOLUME_IN_ML[unit]
            # The measure carries USDA's own density for this food, so a
            # different volume unit still converts through it. A little
            # confidence is lost because the recipe did not ask for the
            # portion USDA measured.
            return Conversion(
                _scaled(measure, wanted_ml / VOLUME_IN_ML[measure.measure]),
                min(1.0, _measure_confidence(measure) * 0.95),
                "volume-measure",
                _measure_label(measure),
                ambiguous,
            )
        return None

    if unit is None:
        counts = [
            measure
            for measure in measures
            if measure.measure not in MASS_UNITS
            and measure.measure not in VOLUME_UNITS
        ]
        if counts:
            measure, ambiguous = _choose_measure(counts, unit, context)
            return Conversion(
                _scaled(measure, amount),
                min(1.0, _measure_confidence(measure) * 0.9),
                "count-measure",
                _measure_label(measure),
                ambiguous,
            )
        return None

    if unit in COUNT_UNITS:
        exact = [measure for measure in measures if measure.measure == unit]
        if exact:
            measure, ambiguous = _choose_measure(exact, unit, context)
            return Conversion(
                _scaled(measure, amount),
                min(1.0, _measure_confidence(measure)),
                "count-measure",
                _measure_label(measure),
                ambiguous,
            )
    return None


def grams_for(measures, unit, amount):
    """Grams for ``amount`` of ``unit`` from an iterable of measures.

    Measures are objects with ``measure``, ``amount`` and ``gram_weight``.
    Returns None when nothing converts. This is the strict, ingredient-level
    conversion used by callers that only have a measure list; the recipe
    calculator uses :func:`resolve_grams`, which can fall back to a standard
    cooking weight and carries confidence and provenance.
    """
    conversion = _convert_measures(measures, unit, amount)
    return conversion.grams if conversion is not None else None


def resolve_grams(ingredient, quantity, context=""):
    """Grams for ``quantity`` of ``ingredient``, with confidence and method.

    The order is deliberate: a mass printed on the recipe line, then a matching
    USDA measure, then a standard cooking weight. The first two are measured
    data. The last is an estimate and is flagged as one.
    """
    if quantity.grams is not None and quantity.grams > 0:
        return Conversion(
            quantity.grams,
            1.0,
            "stated",
            quantity.note or "mass stated on the line",
        )

    amount = quantity.amount
    if not amount or amount <= 0:
        return None

    measures = list(ingredient.measures.all())
    conversion = _convert_measures(measures, quantity.unit, amount, context)
    if conversion is not None:
        return conversion

    unit = quantity.unit
    name = ingredient.name
    if unit in VOLUME_UNITS:
        grams = grams_for_volume(name, context, amount * VOLUME_IN_ML[unit])
        if grams is not None:
            return Conversion(
                grams,
                0.55,
                "standard-density",
                "standard cooking density",
            )
    elif unit in SMALL_UNIT_GRAMS:
        grams = grams_for_unit(unit, amount)
        if grams is not None:
            return Conversion(
                grams,
                0.45,
                "standard-unit",
                f"standard {unit} weight",
            )
    elif (unit is None or unit in SIZE_UNITS or unit in COUNT_UNITS) and (
        unit not in CONTAINER_UNITS
    ):
        grams = grams_for_count(name, context, amount, unit)
        if grams is not None:
            return Conversion(
                grams,
                0.50,
                "standard-count",
                "standard item weight",
            )
    return None


UNICODE_FRACTIONS = {
    "⅛": " 1/8", "⅜": " 3/8", "⅝": " 5/8", "⅞": " 7/8",
    "⅕": " 1/5", "⅖": " 2/5", "⅗": " 3/5", "⅘": " 4/5",
    "⅙": " 1/6", "⅚": " 5/6", "⅐": " 1/7",
    "¼": " 1/4", "½": " 1/2", "¾": " 3/4",
    "⅓": " 1/3", "⅔": " 2/3",
}

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "dozen": 12, "half": 0.5, "quarter": 0.25,
}
NUMBER_NUMERIC = r"\d+\s+\d+\s*/\s*\d+|\d+\s*/\s*\d+|\d+(?:\.\d+)?|\.\d+"
NUMBER_WORD_TEXT = (
    r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve"
    r"|dozen|half|quarter"
)
NUMBER_TEXT = f"(?:{NUMBER_NUMERIC}|{NUMBER_WORD_TEXT})"
# Numeric amounts may run straight into a unit ("33cl"); word amounts must end
# at a word boundary so "onehalf" is not read as one.
QUANTITY = re.compile(
    r"^\s*(?P<number>(?:" + NUMBER_NUMERIC + r")|(?:" + NUMBER_WORD_TEXT + r")(?![a-z]))",
    re.I,
)
RANGE = re.compile(r"^\s*(?:-|–|—|\bto\b|\bor\b)\s*", re.I)
UNIT_WORD = re.compile(r"^\s*([A-Za-z]+)")
LEADING_FILLER = re.compile(
    r"^\s*(?:(?:about|approximately|approx\.?|around|roughly|circa)\s+|~|≈)+",
    re.I,
)

# A fraction printed with a hyphen ("1-1/2") is a mixed number, not a range.
# A range ("2-4 Tbsp") has no slash after the second number and is left alone.
HYPHEN_FRACTION = re.compile(r"(?<=\d)\s*[-–—]\s*(?=\d+\s*/\s*\d+)")

MASS_TOKEN = re.compile(
    r"(?P<value>" + NUMBER_TEXT + r")\s*[-–—]?\s*"
    r"(?P<unit>milligrams?|kilograms?|grams?|ounces?|pounds?|oz|lbs?|kg|mg|g)\b",
    re.I,
)
MASS_WORDS = {
    "mg": 0.001, "milligram": 0.001, "milligrams": 0.001,
    "g": 1.0, "gram": 1.0, "grams": 1.0,
    "kg": 1000.0, "kilogram": 1000.0, "kilograms": 1000.0,
    "oz": 28.3495, "ounce": 28.3495, "ounces": 28.3495,
    "lb": 453.592, "lbs": 453.592, "pound": 453.592, "pounds": 453.592,
}
PARENTHETICAL = re.compile(r"\(([^)]*)\)")
PER_ITEM = re.compile(r"\b(?:each|per)\b", re.I)
CONTAINER_AFTER = re.compile(
    r"^\s*(?:cans?|jars?|packages?|pkg|bags?|boxes?|cartons?|"
    r"containers?|bottles?|envelopes?|packets?|sticks?|loaves?|loaf)\b",
    re.I,
)
CONTAINER_AFTER_MASS = re.compile(
    r"^\s*[- ]?\s*(?:cans?|jars?|packages?|pkg|bags?|boxes?|cartons?|"
    r"containers?|bottles?|envelopes?|packets?|sticks?|loaves?|loaf)\b",
    re.I,
)

# Things a recipe uses to connect an amount to an ingredient, not measures.
ARTICLES = frozenset({"of", "a", "an"})


def _number(token):
    """Float value for a number token, or None when it is not one."""
    text = " ".join(str(token or "").split()).lower()
    if not text:
        return None
    if text in NUMBER_WORDS:
        return float(NUMBER_WORDS[text])
    if " " in text:
        whole, fraction = text.split(None, 1)
        try:
            return float(whole) + _number(fraction)
        except (TypeError, ValueError):
            return None
    if "/" in text:
        numerator, denominator = text.split("/", 1)
        try:
            denominator = float(denominator)
            return float(numerator) / denominator if denominator else None
        except ValueError:
            return None
    try:
        return float(text)
    except ValueError:
        return None


def _mass_token(token):
    value = _number(token.group("value"))
    if value is None:
        return None
    unit = token.group("unit").casefold()
    factor = MASS_WORDS.get(unit)
    return None if factor is None else value * factor


def _mass_grams(text):
    """Sum every mass phrase in ``text``; "1 lb 5 oz" is one compound mass."""
    total = None
    for token in MASS_TOKEN.finditer(str(text or "")):
        grams = _mass_token(token)
        if grams is None:
            continue
        total = grams if total is None else total + grams
    return total


def _mass_after_or(rest, _amount=None):
    match = re.search(r"\bor\b", rest, re.I)
    if not match:
        return None
    return _mass_grams(rest[match.end():])


def _mass_in_parentheses(rest, amount):
    for match in PARENTHETICAL.finditer(rest):
        grams = _mass_grams(match.group(1))
        if grams is None:
            continue
        after = rest[match.end():]
        per_item = bool(PER_ITEM.search(match.group(1))) or bool(
            CONTAINER_AFTER.match(after)
        )
        return grams * amount if per_item else grams
    return None


def _mass_with_each(rest, amount):
    for token in MASS_TOKEN.finditer(rest):
        if re.match(r"\s*(?:each|per)\b", rest[token.end():], re.I):
            grams = _mass_token(token)
            if grams is not None:
                return grams * amount
    return None


def _mass_after_multiplier(rest, amount):
    match = re.search(r"[x×]\s*", rest, re.I)
    if not match:
        return None
    grams = _mass_grams(rest[match.end():])
    return None if grams is None else grams * amount


def _mass_before_container(rest, amount):
    for token in MASS_TOKEN.finditer(rest):
        if CONTAINER_AFTER_MASS.match(rest[token.end():]):
            grams = _mass_token(token)
            if grams is not None:
                return grams * amount
    return None


def _explicit_grams(rest, amount, unit):
    """A mass the line states outright, in grams, and where it came from."""
    if unit in MASS_UNITS:
        # "1 lb 5 oz" is a compound mass: the first part is the parsed unit and
        # the rest continues the same measurement.
        extra = _mass_grams(rest)
        if extra is not None:
            return amount * MASS_IN_GRAMS[unit] + extra, "compound mass"

    for finder, note in (
        (_mass_after_or, "mass alternative"),
        (lambda text, count: _mass_in_parentheses(text, count), "mass in parentheses"),
        (_mass_with_each, "per-item mass"),
        (_mass_after_multiplier, "multiplied package mass"),
        (_mass_before_container, "container mass"),
    ):
        grams = finder(rest, amount)
        if grams is not None:
            return grams, note
    return None


def parse_quantity(text):
    """Parse the head of an ingredient line into a :class:`Quantity`.

    Handles numbers, fractions, unicode glyphs, ranges, count words, and a mass
    printed elsewhere on the line. A range becomes its midpoint, which keeps
    the estimate unbiased; the original bounds stay on the result. A line with
    no number, like "salt to taste", comes back with ``amount`` None so the
    caller can report it instead of inventing a serving.
    """
    if not text:
        return Quantity(None, None, "")

    expanded = str(text)
    for glyph, replacement in UNICODE_FRACTIONS.items():
        expanded = expanded.replace(glyph, replacement)
    expanded = HYPHEN_FRACTION.sub(" ", expanded)
    expanded = " ".join(expanded.split())
    expanded = LEADING_FILLER.sub("", expanded)

    match = QUANTITY.match(expanded)
    if not match:
        return Quantity(None, None, expanded)

    low = _number(match.group("number"))
    if low is None:
        return Quantity(None, None, expanded)

    rest = expanded[match.end():]
    high = low
    range_match = RANGE.match(rest)
    if range_match:
        end_match = QUANTITY.match(rest[range_match.end():])
        if end_match:
            end_high = _number(end_match.group("number"))
            if end_high is not None:
                high = end_high
                rest = rest[range_match.end() + end_match.end():]

    amount = (low + high) / 2
    note = "range midpoint" if high != low else ""

    unit = None
    while True:
        word = UNIT_WORD.match(rest)
        if not word:
            break
        token = word.group(1)
        following = UNIT_WORD.match(rest[word.end():])
        # A lone capital between the number and a real measure is a garbled
        # fraction glyph from a PDF, not a unit: "2 L cups" means two and a
        # fraction cups, and reading L as litres would multiply the amount
        # eightfold. The integer part is kept, which is a lower bound because
        # the missing glyph is a fraction between zero and one.
        if (
            len(token) == 1
            and token.isupper()
            and following
            and MEASURE_SYNONYMS.get(following.group(1).lower())
        ):
            rest = rest[word.end():]
            word = following
            token = word.group(1)
        canonical = MEASURE_SYNONYMS.get(token.lower())
        if canonical:
            unit = canonical
            rest = rest[word.end():]
            break
        # "half a cup" and "a pinch of salt" put a connector before the unit.
        if token.lower() in ARTICLES:
            rest = rest[word.end():]
            continue
        break

    explicit = _explicit_grams(rest, amount, unit)
    grams = None
    if explicit is not None:
        grams, mass_note = explicit
        note = f"{note}; {mass_note}" if note else mass_note

    words = rest.split()
    if words and words[0].lower() in ARTICLES and len(words) > 1:
        words = words[1:]
    return Quantity(
        amount,
        unit,
        " ".join(words),
        low=low,
        high=high,
        grams=grams,
        note=note,
    )


def parse_amount(text):
    """Split the head of an ingredient line into ``(amount, unit, rest)``."""
    quantity = parse_quantity(text)
    return quantity.amount, quantity.unit, quantity.rest
