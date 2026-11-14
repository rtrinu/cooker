"""Ingredient naming and cleanup shared by the import commands.

USDA descriptions are written for a database, not a pantry: ``Alcoholic
Beverage, wine, table, red, Barbera`` is a red wine, and its category is
``Beverages``. This module rewrites those names into the item-first form the
finder and the ingredient list use, and identifies the USDA categories that
are not cooking ingredients at all.
"""

import re

from .units import MEASURE_SYNONYMS

UNWANTED_CATEGORIES = frozenset({"Restaurant Foods", "Fast Foods", "Baby Foods"})
ALCOHOLIC_CATEGORY = "Alcoholic Beverage"
ALCOHOLIC_PREFIX = re.compile(r"^alcoholic beverages?\s*,?\s*", re.I)
PROOF = re.compile(r"\b(?P<proof>\d+)\s*proof\b", re.I)

# Things a recipe lists in its equipment, not its ingredients. The names are
# matched whole so "red pepper flakes" and "string beans" are not caught.
EQUIPMENT = frozenset({
    "aluminum foil", "tin foil", "foil", "silver foil",
    "parchment paper", "baking paper", "baking parchment", "wax paper",
    "greaseproof paper", "white paper",
    "plastic wrap", "cling film", "cling wrap", "saran wrap",
    "cheesecloth", "cheese cloth", "muslin", "muslin cloth",
    "skewer", "skewers", "wooden skewer", "wooden skewers",
    "metal skewer", "metal skewers", "bamboo skewer", "bamboo skewers",
    "toothpick", "toothpicks", "cocktail stick", "cocktail sticks",
    "kitchen twine", "twine", "string",
    "thermometer", "cheese recipient", "thermos",
    "kitchen thermometer", "probe thermometer",
    "glass jar", "glass jars", "glass marbles", "pie weights",
})
EQUIPMENT_PREFIX = re.compile(
    r"^(?:aluminum|tin|silver)\s+foil\b"
    r"|^(?:parchment|baking|wax|greaseproof)\s+paper\b"
    r"|^(?:wooden|metal|bamboo)?\s*skewers?\b"
    r"|^find\s+sieve\b",
    re.I,
)

# A leading amount or grade that leaked into the name after parsing:
# "/500g liver", "3 large turnips", "00 or 0 flour".
_NUMBER = r"(?:\d+\s+\d+/\d+|\d+(?:\.\d+)?/\d+|\d+/\d+|\d+(?:\.\d+)?|\.\d+)"
_WORD_NUMBER = (
    r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)"
)
_SIZE = r"(?:large|small|medium|big|whole)"
# Count words that name a food, not a measure. Treating "onions" as a unit
# would reduce "or three onions" to an empty name.
_FOOD_UNITS = frozenset({
    "egg", "eggs", "steak", "steaks", "roll", "rolls", "muffin", "muffins",
    "biscuit", "biscuits", "pancake", "pancakes", "tortilla", "tortillas",
    "bun", "buns", "waffle", "waffles", "pizza", "pizzas", "chop", "chops",
    "roast", "roasts", "tomato", "tomatoes", "banana", "bananas", "onion",
    "onions", "olive", "olives", "cookie", "cookies", "drumstick",
    "drumsticks",
})
_UNIT = "|".join(
    sorted(
        {re.escape(unit) for unit in MEASURE_SYNONYMS}
        - {re.escape(unit) for unit in _FOOD_UNITS}
        | {_SIZE},
        key=len,
        reverse=True,
    )
)
LEADING_AMOUNT = re.compile(
    r"^(?:[/~≈]\s*)?"
    r"(?:(?:around|about|roughly|nearly|approximately|approx\.?|up to|"
    r"less than|a few|few|some)\s+)?"
    r"(?:" + _NUMBER + r"|" + _WORD_NUMBER + r")"
    r"(?:\s*(?:-|\u2013|\u2014|to|or)\s*(?:" + _NUMBER + r"|" + _WORD_NUMBER + r"))?"
    r"\s*(?:" + _UNIT + r")\b\.?\s*(?:of\s+)?",
    re.I,
)
# "or three onions": a connector left in front of a leaked count.
LEADING_CONNECTOR_AMOUNT = re.compile(
    r"^(?:or|and)\s+(?:" + _NUMBER + r"|" + _WORD_NUMBER + r")"
    r"(?:\s*(?:-|\u2013|\u2014|to|or)\s*(?:" + _NUMBER + r"|" + _WORD_NUMBER + r"))?"
    r"\s*(?:(?:" + _UNIT + r")\b)?\.?\s*(?:of\s+)?",
    re.I,
)
# "3 onions": a leaked count with no unit left behind.
BARE_COUNT = re.compile(
    r"^(?:" + _NUMBER + r"|" + _WORD_NUMBER + r")"
    r"(?:\s*(?:-|\u2013|\u2014|to|or)\s*(?:" + _NUMBER + r"|" + _WORD_NUMBER + r"))?"
    r"\s+(?=[^\W\d_])",
    re.I,
)
# A leftover connector: "or less of Xanthan Gum", "and two ounces".
ORPHAN_CONNECTOR = re.compile(
    r"^(?:or|and)\s+(?:(?:more|less)\s*,?\s*)?(?:of\s+)?", re.I
)
# A measure word that survived without a number: "spoon ginger powder".
_MEASURE_WORD = (
    r"(?:pinch(?:es)?|dash(?:es)?|spoonfuls?|spoonsful|spoons?|handfuls?|"
    r"slices?|branches?|bit|pieces?)"
)
BARE_MEASURE = re.compile(
    r"^(?:" + _MEASURE_WORD + r"\s+(?:of\s+)?|glass(?:es)?\s+of\s+)", re.I
)
APPROXIMATION_HEAD = re.compile(r"^(?:a few|few|some)\s+", re.I)
# A fat or alcohol grade: "18% sour cream", "95% ABV grain alcohol".
PERCENT_HEAD = re.compile(
    r"^\d+(?:\.\d+)?(?:\s*[-\u2013]\s*\d+(?:\.\d+)?)?\s*%\s*"
    r"(?:a\.?\s?b\.?\s?v\.?\s*|abv\s*)?",
    re.I,
)
MEASURE_PAREN = re.compile(
    r"^(?:" + _MEASURE_WORD + r"|glass(?:es)?)\s+of\s+\((?P<list>.+)\)\s*$",
    re.I,
)
GRADE_HEAD = re.compile(
    r"^(?:0{1,2}|t\d{2})(?:\s*(?:or|/)\s*(?:0{1,2}|t\d{2}))?\s+(?=[a-z])",
    re.I,
)
_NOTE_WORDS = (
    r"or|etc|optional|recommended|preferably|prefer|if|alternative|substitute|"
    r"about|around|approx|approximately|roughly|you|your|i|"
    r"any\s+(?:type|kind|amount)|soak|whatever|this\s+is|"
    r"doesn'?t\s+matter|to\s+taste|to\s+your|adjust|preference"
)
NOTE_PAREN = re.compile(
    r"\s*\([^()]*(?:\b(?:" + _NOTE_WORDS + r")\b|e\.g\.|~|≈)[^()]*\)",
    re.I,
)
# A note in parentheses whose closing bracket was lost in the source, such as
# "Apricot jam (about".
UNCLOSED_NOTE_PAREN = re.compile(
    r"\s*\((?=[^()]*(?:\b(?:" + _NOTE_WORDS + r")\b|e\.g\.|~|≈))[^()]*$",
    re.I,
)
# "sardines (~4oz)": a measure or note marked with a tilde.
TILDE_PAREN = re.compile(r"\s*\([^()]*(?:~|≈)[^()]*\)")
TRAILING_MEASURE = re.compile(
    r",\s+\d+(?:\.\d+)?(?:\s*[-\u2013]\s*\d+(?:\.\d+)?)?\s*"
    r"(?:inches?|in\.?|cm|mm|centimet(?:er|re)s?|millimet(?:er|re)s?|"
    r"g|kg|ml|l|lb|oz)\b\.?\s*$",
    re.I,
)
TRAILING_PROSE = re.compile(r",\s+I\s+(?:don't|do not|didn't|did not)\b.*$", re.I)
TRAILING_WEIGHT = re.compile(r"\s+weighing\s+.*$", re.I)
TRAILING_THAT_WEIGHS = re.compile(r"\s+(?:that|which)\s+weighs?\b.*$", re.I)
TRAILING_BY_WEIGHT = re.compile(r"\s+by\s+[a-z ]+?\s+weight\s*$", re.I)
TRAILING_ALTERNATIVE = re.compile(r",\s+or\s+.*$", re.I)
TRAILING_ANY = re.compile(r"\s+or\s+any\b.*$", re.I)
TRAILING_WITH = re.compile(r"\s+with\s+(?:their|its|the)\b.*$", re.I)
# A recipe that points at another recipe instead of naming an ingredient:
# "1 recipe of your favorite tuna salad" is a tuna salad.
LEADING_RECIPE = re.compile(
    r"^(?:a\s+)?recipes?\s+(?:of|for)\s+(?:your\s+)?(?:favou?rite\s+)?", re.I
)
# An amount or serving note written after the food: "Kefir about 150-300 ml
# per serving", "rennet about two inches square".
TRAILING_ABOUT = re.compile(
    r",?\s+(?:about|around|approx\.?|approximately|roughly|circa)\b.*$", re.I
)
TRAILING_OR_APPROX = re.compile(
    r"\s+or\s+(?:about|around|approx\.?|approximately|roughly)\b.*$", re.I
)
TRAILING_OF_CHOICE = re.compile(
    r",?\s+of\s+(?:your\s+)?(?:choice|favou?rite(?:\s+variety)?|"
    r"any\s+(?:kind|type|variety))\b.*$",
    re.I,
)
TRAILING_ANY_KIND = re.compile(r",?\s+any\s+(?:kind|type|variety)\b.*$", re.I)
TRAILING_PREFERABLY = re.compile(r",?\s+preferably\b.*$", re.I)
TRAILING_TO_TASTE = re.compile(
    r",?\s+to\s+(?:your\s+)?(?:taste|palate|preference)\b.*$", re.I
)
TRAILING_IF_YOU = re.compile(r",?\s+if\s+you\b.*$", re.I)
TRAILING_AS_YOU_WANT = re.compile(r"\s+as\s+you\s+want\b.*$", re.I)
# A trailing preparation note with no comma: "Black pepper freshly grounded".
TRAILING_FRESHLY = re.compile(
    r"\s+freshly\s+(?:ground|grounded|grated|cracked|chopped)\s*$", re.I
)
# A preparation after a comma: "yolks, beaten until thick", or a bare
# trailing preparation: "yellow onion diced", "potatoes, peeled and cubed".
_PREP_WORD = (
    r"(?:chopped|diced|minced|sliced|grated|shredded|beaten|whisked|melted|"
    r"softened|peeled|seeded|crushed|divided|cubed|quartered)"
)
_PREP_ADVERB = r"(?:thinly|finely|coarsely|roughly|lightly|well|very|freshly)"
_PREP_PHRASE = (
    r"(?:(?:" + _PREP_ADVERB + r")\s+)*" + _PREP_WORD +
    r"(?:\s+(?:and|or)\s+(?:(?:" + _PREP_ADVERB + r")\s+)*" + _PREP_WORD + r")*"
)
TRAILING_PREPARATION = re.compile(
    r",\s+(?:[^,]*\s)?" + _PREP_PHRASE + r"(?:\s+(?:until|to)\b.*)?\s*$", re.I
)
TRAILING_PREP_WORD = re.compile(r"\s+" + _PREP_PHRASE + r"\s*$", re.I)
LEADING_AS_MUCH = re.compile(r"^as\s+much\s+", re.I)
LEADING_OPTIONAL = re.compile(r"^(?:optional|opt\.?)\s+", re.I)
LEADING_GOOD_BIT = re.compile(r"^(?:a\s+)?good\s+bit\s+of\s+", re.I)
# "glasses wine": a measure whose "of" was dropped.
BARE_GLASS = re.compile(
    r"^glass(?:es)?\s+(?!of\b)(?=[^\W\d_])", re.I
)
# A name that is only an author's aside, not a food.
VAGUE_NAME = re.compile(
    r"^(?:really\s+)?(?:whatever|anything|everything)\b"
    r"|^(?:really\s+)?as\s+(?:much|many)\s+as\s+you\s+(?:like|want)\b"
    r"|^to\s+your\s+(?:taste|palate)\s*$",
    re.I,
)
# A line that only describes a preparation ("finely diced") has no food left.
_PREP_ONLY = r"(?:" + _PREP_ADVERB + r"|" + _PREP_WORD + r")"
PURE_PREPARATION = re.compile(
    r"^" + _PREP_ONLY + r"(?:\s+" + _PREP_ONLY + r")*$", re.I
)


def is_equipment(name):
    """Whether ``name`` is kitchen equipment listed as an ingredient."""
    text = " ".join(str(name or "").split()).casefold()
    if not text:
        return False
    if text in EQUIPMENT:
        return True
    return bool(EQUIPMENT_PREFIX.match(text))


# Preparation states that change nutrient density, especially water loss and
# fat uptake. They are stored on conversions so raw and cooked forms of the
# same food never share a gram conversion silently.
PREPARATION_STATES = frozenset({
    "raw", "cooked", "boiled", "steamed", "roasted", "baked", "grilled",
    "fried", "sauteed", "braised", "poached", "smoked", "dried", "canned",
    "frozen", "thawed", "pasteurized", "homemade", "commercial",
})
_PREPARATION_WORD = re.compile(r"[a-z]+")


def detect_preparation_state(text):
    """Return the preparation states named in ``text``, most specific first.

    A USDA description can mention more than one form ("cooked, drained"), so
    every match is kept in the order it appears, truncated to the model field.
    """
    lowered = " ".join(str(text or "").casefold().split())
    found = []
    for word in _PREPARATION_WORD.findall(lowered):
        if word in PREPARATION_STATES and word not in found:
            found.append(word)
    return ", ".join(found)[:50]


def canonical_ingredient_name(name):
    """Reduce a parsed name to the ingredient a pantry would stock.

    Removes the mechanical junk that survives a recipe line: a second measure
    glued to the front ("/500g liver"), a leading grade ("00 or 0 flour"), a
    size word and count ("3 large turnips"), and parenthetical alternatives
    ("flour (0 or 00)"). Descriptive words that identify the food itself are
    kept, so "rye flour" stays "rye flour".
    """
    text = " ".join(str(name or "").split())
    if not text:
        return ""
    text = re.sub(r"\*+", "", text)
    text = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"\1", text)
    # "pinches of (Mozzarella, Oaxaca, or Montery Jack cheese)": the food is
    # in the parentheses, and the last alternative carries the head noun.
    measure = MEASURE_PAREN.match(text)
    if measure:
        alternatives = re.split(r"\s*(?:,|\bor\b)\s*", measure.group("list"))
        text = alternatives[-1]
    text = NOTE_PAREN.sub("", text)
    text = TILDE_PAREN.sub("", text)
    text = UNCLOSED_NOTE_PAREN.sub("", text)
    text = LEADING_RECIPE.sub("", text)
    text = LEADING_CONNECTOR_AMOUNT.sub("", text)
    text = LEADING_AMOUNT.sub("", text)
    text = ORPHAN_CONNECTOR.sub("", text)
    text = BARE_COUNT.sub("", text)
    text = PERCENT_HEAD.sub("", text)
    text = APPROXIMATION_HEAD.sub("", text)
    text = BARE_MEASURE.sub("", text)
    text = LEADING_AS_MUCH.sub("", text)
    text = LEADING_OPTIONAL.sub("", text)
    text = LEADING_GOOD_BIT.sub("", text)
    text = BARE_GLASS.sub("", text)
    text = re.sub(r"^the\s+", "", text, flags=re.I)
    text = GRADE_HEAD.sub("", text)
    if VAGUE_NAME.match(text):
        return ""
    text = TRAILING_MEASURE.sub("", text)
    text = TRAILING_PROSE.sub("", text)
    text = TRAILING_WEIGHT.sub("", text)
    text = TRAILING_THAT_WEIGHS.sub("", text)
    text = TRAILING_BY_WEIGHT.sub("", text)
    text = TRAILING_ALTERNATIVE.sub("", text)
    text = TRAILING_ANY.sub("", text)
    text = TRAILING_WITH.sub("", text)
    text = TRAILING_OR_APPROX.sub("", text)
    text = TRAILING_ABOUT.sub("", text)
    text = TRAILING_OF_CHOICE.sub("", text)
    text = TRAILING_ANY_KIND.sub("", text)
    text = TRAILING_PREFERABLY.sub("", text)
    text = TRAILING_TO_TASTE.sub("", text)
    text = TRAILING_IF_YOU.sub("", text)
    text = TRAILING_AS_YOU_WANT.sub("", text)
    text = TRAILING_FRESHLY.sub("", text)
    text = TRAILING_PREPARATION.sub("", text)
    text = TRAILING_PREP_WORD.sub("", text)
    if PURE_PREPARATION.match(text):
        return ""
    text = re.sub(r"^[\s,;:./\-]+", "", text)
    text = re.sub(r"[\s,;:.\-]+$", "", text)
    return " ".join(text.split())


def should_skip_category(category):
    return str(category or "").strip() in UNWANTED_CATEGORIES


def _title(value):
    text = " ".join(str(value or "").split())
    if not text:
        return ""
    # Keep already-mixed-case variety names such as "Pinot Gris (Grigio)"
    # readable without shouting all-caps USDA brand entries.
    if text.isupper():
        text = text.title()
    return text[:1].upper() + text[1:]


def _proof(parts):
    match = PROOF.search(", ".join(parts))
    return f"{match.group('proof')} proof" if match else ""


def _wine(parts):
    rest = [part for part in parts if part.casefold() not in {"wine", "table"}]
    night = [part.casefold() for part in rest]
    if "rose" in night:
        return "Rose wine"
    if "cooking" in night:
        return "Cooking wine"
    if "light" in night:
        return "Light wine"
    if "dessert" in night:
        return "Sweet dessert wine" if "sweet" in night else (
            "Dry dessert wine" if "dry" in night else "Dessert wine"
        )
    color = next((part for part in rest if part.casefold() in {"red", "white"}), "")
    if not color:
        if "all" in night:
            return "Table wine"
        return "Wine"
    variety = [
        part
        for part in rest
        if part.casefold() not in {"red", "white", "all", "late harvest"}
    ]
    name = " ".join(_title(part) for part in variety).strip()
    if "late harvest" in night:
        name = f"Late harvest {name}".strip()
    if name:
        return f"{name} ({color.casefold()} wine)"
    return f"{color.title()} wine"


def _beer(parts):
    rest = [part for part in parts if part.casefold() != "beer"]
    night = [part.casefold() for part in rest]
    if any("hard lemonade" in part for part in night):
        return "Hard lemonade"
    brand = [
        part
        for part in rest
        if part.casefold() not in {"light", "regular", "all", "higher alcohol", "low carb"}
    ]
    name = " ".join(_title(part) for part in brand).strip()
    if "light" in night:
        if name:
            return f"{name} (light beer)"
        if "higher alcohol" in night:
            return "High-alcohol light beer"
        if "low carb" in night:
            return "Low-carb light beer"
        return "Light beer"
    if "higher alcohol" in night:
        return f"{name} (higher alcohol)".strip() if name else "Beer (higher alcohol)"
    if name:
        return f"{name} (beer)"
    return "Beer"


def _distilled(parts):
    proof = _proof(parts)
    rest = [part for part in parts if part.casefold() != "distilled"]
    spirit = next(
        (
            part
            for part in rest
            if part.casefold() in {"rum", "vodka", "whiskey", "whisky", "gin"}
        ),
        "",
    )
    if spirit:
        name = f"{_title(spirit)}"
    else:
        name = "Distilled spirits"
    return f"{name} ({proof})" if proof else name


def _liqueur(parts):
    proof = _proof(parts)
    rest = [part for part in parts if part.casefold() != "liqueur"]
    flavour = ", ".join(part for part in rest if not PROOF.search(part))
    if "coffee with cream" in flavour.casefold():
        name = "Coffee cream liqueur"
    elif "coffee" in flavour.casefold():
        name = "Coffee liqueur"
    else:
        name = f"{_title(flavour)} liqueur".strip()
    return f"{name} ({proof})" if proof else name


def _cocktail(parts, name):
    suffix = " ".join(parts[1:]).casefold()
    if "canned" in suffix:
        return f"Canned {name}"
    return name


def normalize_alcoholic_name(name):
    """Return the item-first name for a USDA alcoholic description.

    Non-alcoholic descriptions are returned unchanged. The replacements cover
    the USDA shapes present in the dataset; an unrecognised suffix keeps its
    words after the item instead of being dropped.
    """
    text = " ".join(str(name or "").split())
    match = ALCOHOLIC_PREFIX.match(text)
    if not match:
        return text
    body = text[match.end():].strip(" ,")
    if not body:
        return text
    parts = [part.strip() for part in body.split(",") if part.strip()]
    if not parts:
        return text
    head = parts[0].casefold()
    if head == "wine":
        return _wine(parts)
    if head == "beer":
        return _beer(parts)
    if head == "distilled":
        return _distilled(parts)
    if head == "liqueur":
        return _liqueur(parts)
    if head.startswith("rice") and "sake" in body.casefold():
        return "Sake"
    if head == "daiquiri":
        return _cocktail(parts, "Daiquiri")
    if head == "pina colada":
        return _cocktail(parts, "Pina colada")
    if head == "tequila sunrise":
        return _cocktail(parts, "Tequila sunrise")
    if head == "whiskey sour":
        return "Whiskey sour"
    if head == "malt beer":
        return "Hard lemonade" if "lemonade" in body.casefold() else "Malt beer"
    proof = _proof(parts)
    if proof:
        return f"{_title(' '.join(parts[:-1]))} ({proof})"
    suffix = ", ".join(_title(part) for part in parts[1:])
    return f"{_title(parts[0])} ({suffix})" if suffix else _title(parts[0])


def normalize_ingredient(name, category=""):
    """Return ``(name, category)`` with alcoholic rows made item-first."""
    text = " ".join(str(name or "").split())
    normalized = normalize_alcoholic_name(text)
    if normalized != text:
        return normalized, ALCOHOLIC_CATEGORY
    lowered = text.casefold()
    if lowered == "beverages, amber, hard cider":
        return "Hard cider", ALCOHOLIC_CATEGORY
    if lowered == "rice (sake)":
        return "Sake", ALCOHOLIC_CATEGORY
    if lowered == "beverages, malt liquor beverage":
        return "Malt liquor", ALCOHOLIC_CATEGORY
    if lowered == "beverages, wine, non-alcoholic":
        return "Non-alcoholic wine", category
    if lowered.startswith("beverages, whiskey sour mix"):
        if lowered.endswith("bottled"):
            return "Whiskey sour mix (bottled)", category
        if lowered.endswith("powder"):
            return "Whiskey sour mix (powder)", category
    return text, category
