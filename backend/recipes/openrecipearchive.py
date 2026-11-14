"""Parse recipes from the Open Recipe Archive JSONL corpus.

The archive stores each recipe as a Markdown ``body`` with an ``## Ingredients``
list and a numbered ``## Directions`` list. The English collections use that
shape consistently, so parsing is deliberately narrow: headings are read, the
bullets and step numbers are stripped, and the ingredient lines are rewritten
into the canonical quantity form the rest of the app already understands.

Historical cookbooks write amounts in words and units that no modern parser
recognises (``nine large pippin apples``, ``three table-spoonfuls of flour``,
``a quarter of a pound of white sugar``). :func:`parse_ingredient` front-loads
those spellings into a normal ``<amount> <unit> <name>`` line and keeps the
original wording in ``raw`` for the report and for a later human cleanup. A
line whose amount cannot be read is not guessed at: it keeps the whole line as
its name and gets an empty quantity, exactly like ``salt to taste``.
"""

import hashlib
import re
from collections import namedtuple

from .ingredient_cleanup import (
    GRADE_HEAD,
    canonical_ingredient_name,
    is_equipment,
)
from .models import Ingredient, RecipeIngredient
from .units import MEASURE_SYNONYMS, UNICODE_FRACTIONS, parse_amount

SOURCE = "openrecipearchive"

# The nine collections whose recipes are written in English. The rest of the
# archive is French, German, Spanish, etc.; the headings and prose differ, so
# they are left for a later multilingual pass.
ENGLISH_COLLECTIONS = frozenset({
    "australian-table",
    "canadian-kitchen",
    "filipino-kitchen",
    "indian-kitchen",
    "jewish-kitchen",
    "louisiana-creole",
    "victorian-britain",
    "west-indies",
    "ye-old-american",
})

NAME_MAX_LENGTH = Ingredient._meta.get_field("name").max_length
QUANTITY_MAX_LENGTH = RecipeIngredient._meta.get_field("quantity_text").max_length
TITLE_MAX_LENGTH = 200
SLUG_MAX_LENGTH = 200
SOURCE_ID_MAX_LENGTH = 200

ParsedIngredient = namedtuple("ParsedIngredient", ("quantity", "name", "raw"))
ParsedRecipe = namedtuple(
    "ParsedRecipe",
    (
        "title",
        "slug",
        "source_id",
        "collection",
        "ingredients",
        "directions",
        "servings",
        "servings_note",
        "first_instruction",
        "contributor",
        "source_title",
        "source_year",
        "license",
        "attribution",
        "source_url",
        "tags",
        "category",
    ),
)

HEADING = re.compile(r"^#{2,4}\s+(?P<name>.+?)\s*$", re.M)
LIST_MARKER = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
DIRECTION_MARKER = re.compile(r"^\s*(?:\d+[.)]|[-*+])\s*(?P<text>.*)$")

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}
FRACTION_WORDS = {
    "half": "1/2",
    "quarter": "1/4",
    "third": "1/3",
    "fourth": "1/4",
    "eighth": "1/8",
    "sixteenth": "1/16",
}

# Unit spellings that are specific to old cookbooks. The modern spellings are
# already in ``MEASURE_SYNONYMS``; these are merged on top for head-of-line
# canonicalisation only.
EXTRA_UNIT_ALIASES = {
    "table spoon": "tbsp", "table spoons": "tbsp",
    "table spoonful": "tbsp", "table spoonfuls": "tbsp",
    "table-spoon": "tbsp", "table-spoons": "tbsp",
    "table-spoonful": "tbsp", "table-spoonfuls": "tbsp",
    "tablespoonful": "tbsp", "tablespoonfuls": "tbsp",
    "tb": "tbsp", "tbl": "tbsp", "tspn": "tsp",
    "teacup": "cup", "teacups": "cup",
    "teacupful": "cup", "teacupfuls": "cup",
    "coffee cup": "cup", "coffee cups": "cup",
    "coffee-cup": "cup", "coffee-cups": "cup",
    "coffee cupful": "cup", "coffee cupfuls": "cup",
    "coffee-cupful": "cup", "coffee-cupfuls": "cup",
    "tea spoon": "tsp", "tea spoons": "tsp",
    "tea spoonful": "tsp", "tea spoonfuls": "tsp",
    "tea-spoon": "tsp", "tea-spoons": "tsp",
    "tea-spoonful": "tsp", "tea-spoonfuls": "tsp",
    "teaspoonful": "tsp", "teaspoonfuls": "tsp",
    "cupful": "cup", "cupfuls": "cup",
    "tbls": "tbsp", "tblsp": "tbsp", "tbsps": "tbsp",
    "tsps": "tsp", "ozs": "oz", "lbs": "lb",
    "pt": "pint", "pts": "pint", "qt": "quart", "qts": "quart",
    "gal": "gallon", "gals": "gallon",
}
UNIT_ALIASES = {**MEASURE_SYNONYMS, **EXTRA_UNIT_ALIASES}

# Count units that are also the food when nothing follows them ("seven eggs",
# "four cloves"). A bare measure such as "1 cup" or "1 can" has no ingredient
# name and is not a usable recipe line.
FOOD_COUNT_UNITS = frozenset({
    "egg", "tomato", "banana", "onion", "olive", "cookie", "drumstick", "clove",
})

# Longest first so "table-spoonful" wins over "table".
_UNIT_PHRASES = sorted(UNIT_ALIASES, key=len, reverse=True)
UNIT_HEAD = re.compile(
    r"^(?P<unit>" + "|".join(re.escape(phrase) for phrase in _UNIT_PHRASES) + r")"
    r"\.?(?=[\s,;/]|$)",
    re.I,
)
SINGLE_LETTER_UNIT = re.compile(r"^(?P<unit>[TtCc])\.(?=[\s,;]|$)")

AMOUNT_HEAD = re.compile(r"^\s*(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?|\.\d+)")
NUMERIC_AMOUNT = r"(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?|\.\d+)"
RANGE_HEAD = re.compile(
    r"^(?P<low>" + NUMERIC_AMOUNT + r")\s*(?:[-\u2013\u2014]|or)\s*"
    r"(?P<high>" + NUMERIC_AMOUNT + r")\s*"
    r"(?P<unit>" + "|".join(re.escape(phrase) for phrase in _UNIT_PHRASES) + r")?"
    r"\.?\s+(?:of\s+)?(?P<name>.+)$",
    re.I,
)
APPROXIMATION = re.compile(
    r"^(?:up to|less than|about|around|approximately|approx\.?|nearly|"
    r"roughly|almost|<)\s*",
    re.I,
)
WORD_RANGE = re.compile(
    r"^(?P<low>one|two|three|four|five|six|seven|eight|nine|ten|eleven|"
    r"twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
    r"twenty)\s+(?:to|or)\s+"
    r"(?P<high>one|two|three|four|five|six|seven|eight|nine|ten|eleven|"
    r"twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
    r"twenty)\b",
    re.I,
)
# "50-70% dark chocolate" and "4% sea salt" describe the product, not an
# amount to cook with; the leading number must stay in the name.
PERCENT_HEAD = re.compile(
    r"^\d+(?:\.\d+)?(?:\s*[-\u2013\u2014]\s*\d+(?:\.\d+)?)?\s*%"
)
TRAILING_AMOUNT = re.compile(
    r"^(?P<name>.+?)\s*(?:(?:,|;)\s*|\s+[-\u2013\u2014]\s+|\s+)"
    r"~?\s*(?P<amount>" + NUMERIC_AMOUNT + r")\s*"
    r"(?P<unit>" + "|".join(re.escape(phrase) for phrase in _UNIT_PHRASES) + r")\b"
    r"(?:\s*\([^)]*\))?(?:\s*[,;].*)?$",
    re.I,
)
TRAILING_ALTERNATIVE = re.compile(
    r"^(?P<name>.+?)\s*(?:(?:,|;)\s*|\s+[-\u2013\u2014]\s+|\s+)"
    r"(?P<amount>" + NUMERIC_AMOUNT + r")\s*"
    r"(?P<unit1>" + "|".join(re.escape(phrase) for phrase in _UNIT_PHRASES) + r")"
    r"\s*/\s*"
    r"(?P<unit2>" + "|".join(re.escape(phrase) for phrase in _UNIT_PHRASES) + r")"
    r"\.?\s*$",
    re.I,
)
# A measure inside an alternative name ("ketchup or 3 Tbsp tomato sauce") is
# not part of the ingredient name when the line already stated its amount.
EMBEDDED_AMOUNT = (
    r"(?:\d+(?:\.\d+)?\s+\d+/\d+|\d+(?:\.\d+)?/\d+|\d+/\d+|\d+(?:\.\d+)?)"
)
EMBEDDED_ALTERNATIVE = re.compile(
    r"\s+(?P<join>or|\+)\s+" + EMBEDDED_AMOUNT + r"\s*"
    r"(?:" + "|".join(re.escape(phrase) for phrase in _UNIT_PHRASES) + r")\b"
    r"\s*(?:of\s+)?",
    re.I,
)
# "2 heaped tbsp", "1/2 metric cup": a qualifier belongs to the measure.
QUALIFIED_UNIT = re.compile(
    r"^(?P<qualifier>heaped|heaping|overfilled|generous|level|rounded|scant|"
    r"packed|metric)"
    r"\s+(?P<unit>" + "|".join(re.escape(phrase) for phrase in _UNIT_PHRASES) + r")\b",
    re.I,
)
CONTAINER = re.compile(
    r"^(?:(?:large|small|medium|big)\s+)?"
    r"(?P<container>cans?|jars?|packs?|packages?|bottles?|tins?|boxes?|packets?)"
    r"\b(?:\s+of\s+)?",
    re.I,
)
ALTERNATIVE = re.compile(r"^\s*(?:/|\||or)\s*", re.I)
LEADING_UNIT_OF = re.compile(
    r"^(?:(?:heaped|heaping|overfilled|generous|level|rounded|scant|packed|"
    r"metric)\s+)?"
    r"(?P<unit>" + "|".join(re.escape(phrase) for phrase in _UNIT_PHRASES) + r")"
    r"\.?\s+of\s+(?P<name>.+)$",
    re.I,
)
LEADING_QUALIFIED_UNIT = re.compile(
    r"^(?P<qualifier>heaped|heaping|overfilled|generous|level|rounded|scant|"
    r"packed)\s+"
    r"(?P<unit>" + "|".join(re.escape(phrase) for phrase in _UNIT_PHRASES) + r")"
    r"\.?\s+(?P<name>.+)$",
    re.I,
)
NUMERIC_MIXED = re.compile(
    r"^(?P<whole>\d+)\s+and\s+(?P<frac>\d+/\d+)\b",
    re.I,
)
LEADING_TENS = re.compile(
    r"^(?P<num>(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)"
    r"(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine))?)\b",
    re.I,
)
LEADING_WORD_NUMBER = re.compile(
    r"^(?P<num>one|two|three|four|five|six|seven|eight|nine|ten|eleven|"
    r"twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
    r"twenty)\b",
    re.I,
)
LEADING_ARTICLE = re.compile(r"^(?:a|an)\s+(?=[A-Za-z])", re.I)
LEADING_UNIT_HALF = re.compile(
    r"^(?P<unit>"
    + "|".join(re.escape(phrase) for phrase in _UNIT_PHRASES)
    + r")\s+and\s+a\s+half\b",
    re.I,
)

# Compound fractions that appear before a unit ("a quarter of a pound").
COMPOUND_FRACTIONS = (
    (re.compile(r"^(?:a|an)\s+three\s+quarters?\s+(?:of\s+)?(?:a\s+)?", re.I), "3/4 "),
    (re.compile(r"^(?:a|an)\s+two\s+thirds?\s+(?:of\s+)?(?:a\s+)?", re.I), "2/3 "),
    (re.compile(r"^(?:a|an)\s+one\s+half\s+(?:of\s+)?(?:a\s+)?", re.I), "1/2 "),
    (re.compile(r"^(?:a|an)\s+one\s+quarter\s+(?:of\s+)?(?:a\s+)?", re.I), "1/4 "),
    (re.compile(r"^(?:a|an)\s+quarter\s+(?:of\s+)?(?:a\s+)?", re.I), "1/4 "),
    (re.compile(r"^(?:a|an)\s+third\s+(?:of\s+)?(?:a\s+)?", re.I), "1/3 "),
    (re.compile(r"^(?:a|an)\s+half\s+(?:of\s+)?(?:a\s+)?", re.I), "1/2 "),
    (re.compile(r"^three\s+quarters?\s+(?:of\s+)?(?:a\s+)?", re.I), "3/4 "),
    (re.compile(r"^two\s+thirds?\s+(?:of\s+)?(?:a\s+)?", re.I), "2/3 "),
    (re.compile(r"^one\s+half\s+(?:of\s+)?(?:a\s+)?", re.I), "1/2 "),
    (re.compile(r"^one\s+quarter\s+(?:of\s+)?(?:a\s+)?", re.I), "1/4 "),
    (re.compile(r"^quarter\s+(?:of\s+)?(?:a\s+)?", re.I), "1/4 "),
    (re.compile(r"^half\s+(?:of\s+)?(?:a\s+)?", re.I), "1/2 "),
)
FRACTION_AT_HEAD = (
    (re.compile(r"^one[-\s]half\b", re.I), "1/2"),
    (re.compile(r"^one[-\s]quarter\b", re.I), "1/4"),
    (re.compile(r"^one[-\s]third\b", re.I), "1/3"),
    (re.compile(r"^two[-\s]thirds?\b", re.I), "2/3"),
    (re.compile(r"^three[-\s]quarters?\b", re.I), "3/4"),
)
MIXED_NUMBER = re.compile(
    r"^(?P<whole>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+and\s+"
    r"(?:a\s+)?(?P<frac>one[-\s]?half|half|one[-\s]?quarter|quarter|"
    r"one[-\s]?third|third|two[-\s]?thirds?|three[-\s]?quarters?)\b",
    re.I,
)
# "a pint and a half" puts the fraction after the unit. The "and" is required:
# without it, an ingredient whose name merely starts with "half" (as in
# "half and half") would be eaten as a fraction and its amount inflated.
TRAILING_HALF = re.compile(
    r"^\s*and\s+(?:a\s+)?(?:one[-\s])?half\b",
    re.I,
)
PARENTHETICAL_ONLY = re.compile(r"^\([^)]*\)\s*$")


def _expand_fractions(text):
    text = text.replace("\u2044", "/")
    for glyph, replacement in UNICODE_FRACTIONS.items():
        text = text.replace(glyph, replacement)
    return text


def _word_number(word):
    text = word.strip().lower()
    if text.isdigit():
        return int(text)
    parts = re.split(r"[-\s]+", text)
    if len(parts) == 2 and parts[0] in NUMBER_WORDS and parts[1] in NUMBER_WORDS:
        return NUMBER_WORDS[parts[0]] + NUMBER_WORDS[parts[1]]
    return NUMBER_WORDS.get(text)


def _replace_compound_fraction(text):
    for pattern, replacement in COMPOUND_FRACTIONS:
        if pattern.match(text):
            return pattern.sub(replacement, text, count=1)
    return text


def _replace_mixed_number(text):
    match = NUMERIC_MIXED.match(text)
    if match:
        return (
            f"{match.group('whole')} {match.group('frac')}"
            + text[match.end():]
        )
    match = MIXED_NUMBER.match(text)
    if not match:
        return text
    whole = _word_number(match.group("whole"))
    if whole is None:
        return text
    fraction_text = match.group("frac").lower()
    if "two" in fraction_text:
        fraction = "2/3"
    elif "three" in fraction_text:
        fraction = "3/4"
    elif "half" in fraction_text:
        fraction = "1/2"
    elif "quarter" in fraction_text:
        fraction = "1/4"
    else:
        fraction = "1/3"
    return f"{whole} {fraction}" + text[match.end():]


def _replace_leading_fraction(text):
    for pattern, replacement in FRACTION_AT_HEAD:
        if pattern.match(text):
            return pattern.sub(replacement, text, count=1)
    return text


def _replace_leading_number(text):
    match = LEADING_TENS.match(text)
    if match:
        value = _word_number(match.group("num"))
        if value is not None:
            return f"{value}" + text[match.end():]
    match = LEADING_WORD_NUMBER.match(text)
    if match:
        return f"{NUMBER_WORDS[match.group('num').lower()]}" + text[match.end():]
    article = LEADING_ARTICLE.match(text)
    if article:
        rest = text[article.end():]
        if SINGLE_LETTER_UNIT.match(rest) or UNIT_HEAD.match(rest):
            return f"1 {rest}"
    return text


def _canonicalise_head_unit(text):
    amount = AMOUNT_HEAD.match(text)
    if not amount:
        return text
    remainder = text[amount.end():]
    leading = remainder[: len(remainder) - len(remainder.lstrip())]
    rest = remainder.lstrip()
    match = SINGLE_LETTER_UNIT.match(rest)
    if match:
        unit = {"T": "tbsp", "t": "tsp", "C": "cup", "c": "cup"}[match.group("unit")]
        return f"{text[:amount.end()]}{leading}{unit}" + rest[match.end():]
    match = UNIT_HEAD.match(rest)
    if match:
        unit = UNIT_ALIASES[match.group("unit").casefold()]
        return f"{text[:amount.end()]}{leading}{unit}" + rest[match.end():]
    return text


def _format_amount(amount):
    if amount is None:
        return ""
    if abs(amount - round(amount)) < 1e-9:
        return str(int(round(amount)))
    whole = int(amount)
    fraction = round(amount - whole, 6)
    glyphs = {
        0.125: "1/8", 0.25: "1/4", 1 / 3: "1/3", 0.375: "3/8",
        0.5: "1/2", 5 / 6: "5/6", 0.625: "5/8", 2 / 3: "2/3",
        0.75: "3/4", 0.875: "7/8",
    }
    for value, text in glyphs.items():
        if abs(fraction - value) < 0.01:
            return f"{whole} {text}" if whole else text
    return f"{amount:g}"


def _replace_word_range(text):
    """Rewrite a word range ("three to four turnips") as numbers."""
    match = WORD_RANGE.match(text)
    if not match:
        return text
    low = _word_number(match.group("low"))
    high = _word_number(match.group("high"))
    if low is None or high is None:
        return text
    return f"{low}-{high}" + text[match.end():]


def _clean_name(name):
    text = " ".join(str(name or "").split())
    text = re.sub(r"^[\s,;:.]+", "", text)
    text = re.sub(r"[\s,;:.]+$", "", text)
    text = re.sub(r"^(?:\([^)]*\)\s*)+", "", text)
    text = re.sub(r"^(?:of|the)\s+", "", text, flags=re.I)
    text = re.sub(r"^(?:a|an)\s+", "", text, flags=re.I)
    text = re.sub(
        r"^(?:bit|piece|pinch|dash|handful)\s+of\s+",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"\s+(?:to taste|to your taste|as needed|for garnish|for serving|"
        r"if desired|optional)\s*$",
        "",
        text,
        flags=re.I,
    )
    text = canonical_ingredient_name(text)
    if is_equipment(text):
        return ""
    return text[:NAME_MAX_LENGTH].strip()


def normalize_name(name):
    """Ingredient name clipped to the model field and stripped of noise."""
    return _clean_name(name)


def _quantity_text(amount, unit):
    text = f"{_format_amount(amount)} {unit or ''}".strip()
    return text[:QUANTITY_MAX_LENGTH]


def _strip_approximation(text):
    """Drop "about"/"nearly" when a real amount follows, keeping the number."""
    match = APPROXIMATION.match(text)
    if not match:
        return text
    rest = text[match.end():]
    if (
        AMOUNT_HEAD.match(rest)
        or LEADING_TENS.match(rest)
        or LEADING_WORD_NUMBER.match(rest)
    ):
        return rest
    return text


def _range_quantity(low, high, unit):
    return " ".join(
        part for part in (f"{low}-{high}", (unit or "").casefold()) if part
    )


def _parse_range(text):
    """Parse ``1/4-1/2 cup`` style ranges, preserving both bounds."""
    match = RANGE_HEAD.match(text)
    if not match:
        return None
    unit = UNIT_ALIASES.get((match.group("unit") or "").casefold(), match.group("unit") or "")
    name = _clean_name(match.group("name"))
    if not name:
        return None
    quantity = _range_quantity(
        match.group("low"), match.group("high"), unit
    )
    return quantity[:QUANTITY_MAX_LENGTH], name


def _parse_compound(text):
    """Parse lines that state two amounts, such as ``1 cup + 2 tbsp``."""
    amount, unit, rest = parse_amount(text)
    if amount is None or not unit:
        return None
    rest = rest.lstrip()
    if not rest.startswith("+"):
        return None
    second_text = _canonicalise_head_unit(rest[1:].lstrip())
    second_amount, second_unit, second_rest = parse_amount(second_text)
    if second_amount is None or not second_unit:
        return None
    name = _clean_name(second_rest)
    if not name:
        return None
    quantity = (
        f"{_quantity_text(amount, unit)} + "
        f"{_quantity_text(second_amount, second_unit)}"
    )
    return quantity[:QUANTITY_MAX_LENGTH], name


def _parse_trailing_amount(text):
    """Move a measure written at the end of the line into the quantity.

    Modern recipe sites often put the amount after the ingredient
    (``All-purpose flour 3 cups``), sometimes after a dash
    (``Salt - 1 1/2 teaspoons``). Only a recognised measure is moved, so a
    name that merely ends in a number is left alone.
    """
    match = TRAILING_AMOUNT.match(text)
    if not match:
        alternative = TRAILING_ALTERNATIVE.match(text)
        if not alternative:
            return None
        unit = UNIT_ALIASES.get(alternative.group("unit1").casefold())
        second_unit = UNIT_ALIASES.get(alternative.group("unit2").casefold())
        if not unit or not second_unit:
            return None
        amount, _, _ = parse_amount(
            f"{alternative.group('amount')} {unit}"
        )
        if amount is None:
            return None
        name = _clean_name(alternative.group("name"))
        if not name:
            return None
        quantity = (
            f"{_quantity_text(amount, unit)} / "
            f"{_quantity_text(amount, second_unit)}"
        )
        return quantity[:QUANTITY_MAX_LENGTH], name
    unit = UNIT_ALIASES.get(match.group("unit").casefold())
    if not unit:
        return None
    amount, _, _ = parse_amount(f"{match.group('amount')} {unit}")
    if amount is None:
        return None
    name = _clean_name(match.group("name"))
    if not name:
        return None
    return _quantity_text(amount, unit), name


def _container_rest(rest):
    """Split a leading container word (``can``, ``jars of``) off the name."""
    text = rest.lstrip()
    match = CONTAINER.match(text)
    if not match:
        return "", text
    return match.group("container").casefold(), text[match.end():]


def _parse_package_count(amount, rest):
    """Parse ``1 15 oz can tomatoes`` as a count plus a package size."""
    second_text = _canonicalise_head_unit(rest.lstrip())
    second_amount, second_unit, second_rest = parse_amount(second_text)
    if second_amount is None or not second_unit:
        return None
    container, after = _container_rest(second_rest)
    name = _clean_name(after)
    if not name:
        return None
    quantity = (
        f"{_format_amount(amount)} {_quantity_text(second_amount, second_unit)}"
    )
    if container:
        quantity = f"{quantity} {container}"
    return quantity[:QUANTITY_MAX_LENGTH], name


def _parse_qualified_unit(amount, rest):
    """Parse a measure with a qualifier, such as ``2 heaped tbsp``."""
    text = rest.lstrip()
    match = QUALIFIED_UNIT.match(text)
    if not match:
        return None
    qualifier = match.group("qualifier").casefold()
    unit_text = text[match.start("unit"):]
    second_amount, unit, second_rest = parse_amount(
        f"{_format_amount(amount)} {unit_text}"
    )
    if second_amount is None or not unit:
        return None
    container, after = _container_rest(second_rest)
    name = _clean_name(after)
    if not name:
        return None
    quantity = f"{_format_amount(amount)} {qualifier} {unit}"
    if container:
        quantity = f"{quantity} {container}"
    return quantity[:QUANTITY_MAX_LENGTH], name


def _parse_alternative(amount, unit, rest):
    """Parse dual measures, such as ``100 g / 1/2 cup`` or ``600 g or 5 cups``."""
    match = ALTERNATIVE.match(rest)
    if not match:
        return None
    second_text = _canonicalise_head_unit(rest[match.end():].lstrip("~≈ "))
    second_amount, second_unit, second_rest = parse_amount(second_text)
    if second_amount is None and second_unit is None:
        # "1 clove/teaspoon garlic" states the second measure without a number.
        second_amount, second_unit, second_rest = parse_amount(
            f"1 {second_text}"
        )
    if second_amount is None or not second_unit:
        return None
    container, after = _container_rest(second_rest)
    name = _clean_name(after)
    if not name:
        return None
    quantity = (
        f"{_quantity_text(amount, unit)} / "
        f"{_quantity_text(second_amount, second_unit)}"
    )
    if container:
        quantity = f"{quantity} {container}"
    return quantity[:QUANTITY_MAX_LENGTH], name


def parse_ingredient(line):
    """Return ``(quantity_text, name, raw_text)`` for one ingredient line."""
    raw = LIST_MARKER.sub("", " ".join(str(line or "").split())).strip()
    if not raw:
        return None
    text = _strip_approximation(_expand_fractions(raw).strip())
    text = _replace_compound_fraction(text)
    text = _replace_mixed_number(text)
    text = _replace_leading_fraction(text)
    text = _replace_word_range(text)
    text = _replace_leading_number(text)
    if LEADING_UNIT_HALF.match(text):
        text = f"1 {text}"
    text = _canonicalise_head_unit(text)

    if PERCENT_HEAD.match(text) or GRADE_HEAD.match(text):
        name = _clean_name(text)
        return ("", name, raw) if name else None

    ranged = _parse_range(text)
    if ranged:
        quantity, name = ranged
        return quantity, name, raw

    compound = _parse_compound(text)
    if compound:
        quantity, name = compound
        return quantity, name, raw

    amount, unit, rest = parse_amount(text)
    if amount is not None:
        if unit is None:
            packaged = _parse_package_count(amount, rest)
            if packaged:
                quantity, name = packaged
                return quantity, name, raw
            qualified = _parse_qualified_unit(amount, rest)
            if qualified:
                quantity, name = qualified
                return quantity, name, raw
        else:
            alternative = _parse_alternative(amount, unit, rest)
            if alternative:
                quantity, name = alternative
                return quantity, name, raw
        # A parenthetical pack size in front of the real unit is common in old
        # lines ("1 (14-ounce) can tomatoes"); look past it once.
        if unit is None and rest.startswith("("):
            stripped = re.sub(r"^\([^)]*\)\s*", "", rest)
            if stripped != rest:
                amount, unit, rest = parse_amount(f"{amount} {stripped}")
        # "one-half a cupful" leaves the article between the fraction and unit.
        if unit is None:
            article = re.match(r"^(?:a|an)\s+", rest, re.I)
            if article:
                candidate = rest[article.end():]
                if SINGLE_LETTER_UNIT.match(candidate) or UNIT_HEAD.match(candidate):
                    amount, unit, rest = parse_amount(f"{amount} {candidate}")
        # "a pint and a half" states the half after the unit.
        trailing = TRAILING_HALF.match(rest)
        if trailing:
            amount += 0.5
            rest = rest[trailing.end():]
            rest = re.sub(r"^(?:of|the)\s+", "", rest, flags=re.I)
        if unit is None:
            # ``parse_amount`` reports "large" as a unit; keep that behaviour,
            # but do not let a dangling article become the name.
            rest = re.sub(r"^(?:of|the)\s+", "", rest, flags=re.I)
        container, rest = _container_rest(rest)
        if PARENTHETICAL_ONLY.match(rest.strip()) and unit in FOOD_COUNT_UNITS:
            return _quantity_text(amount, None), unit, raw
        name = _clean_name(rest)
        if not name:
            if unit in FOOD_COUNT_UNITS:
                return _quantity_text(amount, None), unit, raw
            return None
        quantity = _quantity_text(amount, unit)
        if container:
            quantity = f"{quantity} {container}"
        return quantity[:QUANTITY_MAX_LENGTH], name, raw

    name = _clean_name(text)
    if not name:
        return None
    leading_unit = LEADING_UNIT_OF.match(text)
    if leading_unit:
        unit = UNIT_ALIASES.get(leading_unit.group("unit").casefold())
        unit_name = _clean_name(leading_unit.group("name"))
        if unit and unit_name:
            return _quantity_text(1, unit), unit_name, raw
    qualified_unit = LEADING_QUALIFIED_UNIT.match(text)
    if qualified_unit:
        unit = UNIT_ALIASES.get(qualified_unit.group("unit").casefold())
        unit_name = _clean_name(qualified_unit.group("name"))
        if unit and unit_name:
            return (
                _quantity_text(
                    1, f"{qualified_unit.group('qualifier').casefold()} {unit}"
                ),
                unit_name,
                raw,
            )
    trailing = _parse_trailing_amount(text)
    if trailing:
        quantity, trailing_name = trailing
        return quantity, trailing_name, raw
    return "", name, raw


def _section_lines(body):
    """Split a Markdown body into ``{heading: [lines]}``."""
    sections = {}
    matches = list(HEADING.finditer(body))
    for index, match in enumerate(matches):
        key = match.group("name").strip().strip(":").casefold()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections.setdefault(key, []).extend(body[match.end():end].splitlines())
    return sections


def parse_ingredients(body):
    lines = _section_lines(body).get("ingredients", [])
    parsed = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        item = parse_ingredient(line)
        if item is not None:
            parsed.append(ParsedIngredient(*item))
    return parsed


YIELD_LINE = re.compile(
    r"^(?:makes|serves?|yields?|for)\b.*\b(?:servings?|portions?|people|persons)\b",
    re.I,
)


def parse_directions(body):
    lines = _section_lines(body).get("directions", [])
    steps = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = DIRECTION_MARKER.match(line)
        text = match.group("text").strip() if match else line
        if not text or YIELD_LINE.match(text):
            continue
        if match or not steps:
            steps.append(text)
        else:
            # A wrapped continuation line belongs to the previous step.
            steps[-1] = f"{steps[-1]} {text}"
    return "\n".join(steps)


SERVINGS_PATTERNS = (
    re.compile(r"\bserves?\s+(?P<n>\d+|[a-z]+(?:[-\s][a-z]+)?)\b", re.I),
    re.compile(r"\b(?P<n>\d+|[a-z]+(?:[-\s][a-z]+)?)\s+(?:servings?|portions?)\b", re.I),
    re.compile(r"\bfor\s+(?P<n>\d+|[a-z]+(?:[-\s][a-z]+)?)\s+(?:persons?|people)\b", re.I),
    re.compile(r"\byield(?:s|ed)?\s*:?\s*(?P<n>\d+)\s+(?:servings?|portions?)\b", re.I),
)


def _serving_number(value):
    value = value.strip().lower()
    if value.isdigit():
        return int(value)
    return _word_number(value)


def parse_servings(text):
    """Return ``(servings, note)``; ``servings`` is None when not stated."""
    for pattern in SERVINGS_PATTERNS:
        for match in pattern.finditer(text):
            number = _serving_number(match.group("n"))
            if number is not None and 1 <= number <= 1000:
                return number, f'matched "{match.group(0).strip()}"'
    return None, "no yield statement"


def _slug_for(collection, slug):
    base = f"ora-{collection}-{slug}" if collection else f"ora-{slug}"
    if len(base) <= SLUG_MAX_LENGTH:
        return base
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]
    return f"{base[:SLUG_MAX_LENGTH - 13]}-{digest}"


def _attribution(record):
    author = str(record.get("author") or "").strip()
    title = str(record.get("source_title") or "").strip()
    year = str(record.get("source_year") or "").strip()
    url = str(record.get("source_url") or "").strip()
    source = f"{title} ({year})" if title and year else title or year
    return " — ".join(part for part in (author, source, url) if part)


def _tags(record, collection):
    tags = record.get("tags")
    if not isinstance(tags, list):
        tags = []
    tags = [str(tag) for tag in tags if str(tag).strip()]
    for value in (collection, record.get("culture")):
        value = str(value or "").strip()
        if value and value not in tags:
            tags.append(value)
    return tags


def parse_record(record):
    """Convert one JSONL record into a :class:`ParsedRecipe`, or None."""
    body = record.get("body")
    if not isinstance(body, str) or not body.strip():
        return None
    collection = str(record.get("collection") or "").strip()
    title = " ".join(str(record.get("title") or "").split()) or "Untitled recipe"
    slug = str(record.get("slug") or "").strip()
    if not slug:
        slug = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-") or "recipe"
    source_id = f"{collection}/{slug}" if collection else slug
    ingredients = parse_ingredients(body)
    directions = parse_directions(body)
    if not ingredients or not directions:
        return None

    note_text = f"{title}\n{directions}\n{body}"
    servings, servings_note = parse_servings(note_text)
    first_instruction = directions.splitlines()[0][:240] if directions else ""
    author = str(record.get("author") or "").strip()
    culture = str(record.get("culture") or "").strip()

    return ParsedRecipe(
        title=title[:TITLE_MAX_LENGTH],
        slug=_slug_for(collection, slug),
        source_id=source_id[:SOURCE_ID_MAX_LENGTH],
        collection=collection[:100],
        ingredients=ingredients,
        directions=directions,
        servings=servings,
        servings_note=servings_note,
        first_instruction=first_instruction,
        contributor=author[:100],
        source_title=str(record.get("source_title") or "")[:300],
        source_year=str(record.get("source_year") or "")[:20],
        license=str(record.get("license") or "")[:50],
        attribution=_attribution(record),
        source_url=str(record.get("source_url") or ""),
        tags=_tags(record, collection),
        category=culture[:50],
    )
