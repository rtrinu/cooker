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
    r"\.?(?=[\s,;]|$)",
    re.I,
)
SINGLE_LETTER_UNIT = re.compile(r"^(?P<unit>[TtCc])\.(?=[\s,;]|$)")

AMOUNT_HEAD = re.compile(r"^\s*(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)")
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
TRAILING_HALF = re.compile(
    r"^\s*(?:and\s+)?(?:a\s+)?(?:one[-\s])?half\b",
    re.I,
)
PARENTHETICAL_ONLY = re.compile(r"^\([^)]*\)\s*$")


def _expand_fractions(text):
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


def _clean_name(name):
    text = " ".join(str(name or "").split())
    text = re.sub(r"^[\s,;:.]+", "", text)
    text = re.sub(r"[\s,;:.]+$", "", text)
    text = re.sub(r"^(?:of|the)\s+", "", text, flags=re.I)
    text = re.sub(r"^(?:a|an)\s+", "", text, flags=re.I)
    text = re.sub(
        r"^(?:bit|piece|pinch|dash|handful)\s+of\s+",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"\s+(?:to taste|as needed|for garnish|for serving|optional)\s*$",
        "",
        text,
        flags=re.I,
    )
    return text[:NAME_MAX_LENGTH].strip()


def normalize_name(name):
    """Ingredient name clipped to the model field and stripped of noise."""
    return _clean_name(name)


def _quantity_text(amount, unit):
    text = f"{_format_amount(amount)} {unit or ''}".strip()
    return text[:QUANTITY_MAX_LENGTH]


def parse_ingredient(line):
    """Return ``(quantity_text, name, raw_text)`` for one ingredient line."""
    raw = LIST_MARKER.sub("", " ".join(str(line or "").split())).strip()
    if not raw:
        return None
    text = _expand_fractions(raw)
    text = _replace_compound_fraction(text)
    text = _replace_mixed_number(text)
    text = _replace_leading_fraction(text)
    text = _replace_leading_number(text)
    if LEADING_UNIT_HALF.match(text):
        text = f"1 {text}"
    text = _canonicalise_head_unit(text)

    amount, unit, rest = parse_amount(text)
    if amount is not None:
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
        if PARENTHETICAL_ONLY.match(rest.strip()) and unit in FOOD_COUNT_UNITS:
            return _quantity_text(amount, None), unit, raw
        name = _clean_name(rest)
        if not name:
            if unit in FOOD_COUNT_UNITS:
                return _quantity_text(amount, None), unit, raw
            return None
        return _quantity_text(amount, unit), name, raw

    name = _clean_name(text)
    if not name:
        return None
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
