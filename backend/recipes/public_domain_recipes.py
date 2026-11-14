"""Parse recipes from the Public Domain Recipes Markdown collection.

The collection (https://publicdomainrecipes.com) is a Hugo site whose recipe
files are plain Markdown with YAML-style front matter. It is released under
the Unlicense, so the recipes can be used commercially without attribution
obligations. Files contain an ``## Ingredients`` list and one or more
direction sections, sometimes with their own sub-headings.

The site's ingredient syntax is freer than the USDA cards and the historical
corpus: amounts may lead or trail the name (``Spaghetti: 320 g | 11 oz``),
include ranges and mixed fractions, or be expressed as ``A few``. The parser
below normalises those into the ``(quantity, name)`` pairs that
:func:`recipes.recipe_import.save_recipe` stores.
"""

import html
import re
from collections import namedtuple
from pathlib import Path

from .cuisines import cuisine_for_tags, normalize_tags
from .directions import clean_directions
from .ingredient_cleanup import canonical_ingredient_name, is_equipment
from .models import Ingredient, RecipeIngredient
from .openrecipearchive import parse_ingredient

SOURCE = "public-domain-recipes"
COLLECTION = "public-domain-recipes"
SOURCE_TITLE = "Public Domain Recipes"
LICENSE = "Unlicense"
SITE_URL = "https://publicdomainrecipes.com"
NAME_MAX_LENGTH = Ingredient._meta.get_field("name").max_length
QUANTITY_MAX_LENGTH = RecipeIngredient._meta.get_field("quantity_text").max_length

PublicDomainRecipe = namedtuple(
    "PublicDomainRecipe",
    (
        "slug",
        "source_id",
        "title",
        "description",
        "ingredients",
        "directions",
        "servings",
        "prep_mins",
        "cook_mins",
        "tags",
        "cuisine",
        "author",
        "source_year",
        "source_url",
    ),
)

FRONTMATTER = re.compile(r"^---\s*\n(?P<body>.*?)\n---\s*\n", re.S)
TAG_LINE = re.compile(r"^tags\s*:\s*\[(?P<tags>.*?)\]\s*$", re.M | re.I)
SCALAR = re.compile(r"^(?P<key>[A-Za-z_]+)\s*:\s*(?P<value>.*)$", re.M)
HEADING = re.compile(r"^(?P<level>#{1,6})\s+(?P<name>.+?)\s*$")
LIST_MARKER = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
STRONG = re.compile(r"\*\*(.+?)\*\*")
EMPHASIS = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
HTML_TAG = re.compile(r"<[^>]+>")
OPTIONAL_SUFFIX = re.compile(
    r"\s*\(?(?:optional|as needed|to taste|to your taste|if desired|"
    r"if you like|or more|or less)\)?\s*$",
    re.I,
)
OPTIONAL_PAREN = re.compile(
    r"\([^()]*\b(?:optional|to taste|to your taste|as needed|if desired|"
    r"or more|or less|to serve|for serving|if you can)\b[^()]*\)",
    re.I,
)
VAGUE_START = re.compile(r"^any\b", re.I)
LEADING_PAREN = re.compile(r"^(?:\([^)]*\)\s*)+")
MEASURE_PAREN = re.compile(
    r"\s*\([^)]*\d[^)]*\b(?:gal|gallon|oz|ounce|lb|pound|g|gram|kg|ml|"
    r"litre|liter|cup|tbsp|tsp|teaspoon|tablespoon)s?\b[^)]*\)",
    re.I,
)
SPACED_DASH = re.compile(r"\s+[-\u2013]\s+.*$")
OPTIONAL_PREFIX = re.compile(r"^\((?:optional|as needed)\)\s*", re.I)
MIXED_NUMBER = re.compile(r"^(?P<whole>\d+)\s*-\s*(?P<fraction>\d+/\d+)\b")
RANGE_HEAD = re.compile(
    r"^(?P<amount>\d+(?:\.\d+)?\s*[-–]\s*\d+(?:\.\d+)?)\s*"
    r"(?P<unit>tablespoons?|tbsp|teaspoons?|tsp|cups?|cans?|cloves?|"
    r"slices?|pieces?|ounces?|oz|pounds?|lbs?|grams?|g|kilograms?|kg|"
    r"millilit(?:er|re)s?|ml|lit(?:er|re)s?|l|pinch(?:es)?|dash(?:es)?|"
    r"heads?|bunch(?:es)?|stalks?|packs?|packages?)?\s+"
    r"(?:of\s+)?(?P<name>.+)$",
    re.I,
)
A_FEW = re.compile(
    r"^(?P<amount>a\s+few|a\s+pinch|a\s+dash|a\s+handful|a\s+splash|"
    r"a\s+little|a\s+bit)\s+(?:of\s+)?(?P<name>.+)$",
    re.I,
)
TRAILING_PIPE = re.compile(r"\s*\|.*$")
LEADING_AMOUNT = re.compile(
    r"^(?:\d|a\s+(?:few|pinch|dash|handful|splash|little|bit)\b|"
    r"one\b|two\b|three\b|half\b|quarter\b)",
    re.I,
)
UNIT_JOIN = re.compile(
    r"^(?P<amount>\d+(?:\.\d+)?)\s*(?P<unit>ml|lt|l|g|kg|oz|lb|lbs)\b",
    re.I,
)
RANGE_UNIT_JOIN = re.compile(
    r"^(?P<amount>\d+(?:\.\d+)?\s*[-\u2013]\s*\d+(?:\.\d+)?)\s*"
    r"(?P<unit>ml|lt|l|g|kg|oz|lb|lbs)\b",
    re.I,
)
# Parenthetical asides longer than this are commentary, not a preparation note
# such as "(grated)" or "(optional)".
LONG_PAREN = re.compile(r"\s*\((?=[^)]{55})[^)]*\)")
COMMENTARY_START = re.compile(
    r"^(?:note|side note|tip|suggestion|if you|for example|i |ingredients in this|"
    r"spoon the|you can|this recipe)\b",
    re.I,
)
COMMENTARY_WORDS = 22
TIME = re.compile(
    r"(?P<label>prep(?:aration)?|cook(?:ing)?)\s*time\s*:\s*"
    r"(?P<amount>\d+(?:\s*[-–]\s*\d+)?)\s*"
    r"(?P<unit>hours?|hrs?|h|minutes?|mins?|m)?",
    re.I,
)
NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
# A yield is only read when it is a number, a number word, or a count of
# dozens. Free text such as "Depends" or "A batch like this" must stay
# unknown rather than being coerced into a serving count.
SERVINGS = re.compile(
    r"(?:servings?|serves?|yields?)\s*:?\s*(?P<amount>"
    r"\d+(?:\s*[-–]\s*\d+)?"
    r"|(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
    r"(?:\s*[-–\s]\s*dozens?)?"
    r"|dozens?"
    r")",
    re.I,
)
EQUIPMENT = frozenset({
    "thermometer", "cheesecloth", "cheese recipient", "thermos",
    "kitchen thermometer", "probe thermometer",
})
DIRECTION_WORDS = ("direction", "method", "procedure", "instruction", "steps")
INGREDIENT_WORDS = ("ingredient",)
NOTE_WORDS = (
    "note",
    "tip",
    "variation",
    "storage",
    "equipment",
    "utensil",
    "dish",
    "story",
    "closing",
    "extra",
    "consumption",
    "recommendation",
    "serving size",
    "served with",
    "accompaniment",
    "about",
)
GROUP_LABEL = re.compile(
    r"^(?:for\s+(?:the\s+)?[^:]{0,60}:?|"
    r"[^:]{0,50}\b(?:ingredients?|optional|stuffing|filling|topping|sauce|"
    r"dough|crust|batter|spices?|vegetables?|seafood|choose from)\b[^:]{0,30}:)$",
    re.I,
)
WRAP_TAIL = re.compile(r"[,(\u2013-]$")


def _markdown(value):
    text = html.unescape(str(value or ""))
    text = IMAGE.sub("", text)
    text = LINK.sub(r"\1", text)
    text = STRONG.sub(r"\1", text)
    text = EMPHASIS.sub(r"\1", text)
    text = HTML_TAG.sub("", text)
    text = text.replace("`", "")
    return " ".join(text.split()).strip()


def _frontmatter(text):
    match = FRONTMATTER.match(text)
    if not match:
        return {}, text
    body = match.group("body")
    values = {}
    for key, value in SCALAR.findall(body):
        values[key.casefold()] = _markdown(value.strip().strip("\"'"))
    tag_match = TAG_LINE.search(body)
    if tag_match:
        values["tags"] = [
            _markdown(tag.strip().strip("\"'"))
            for tag in tag_match.group("tags").split(",")
            if tag.strip()
        ]
    values.setdefault("tags", [])
    return values, text[match.end():]


def _section_lines(body):
    """Return ``(ingredient_lines, direction_lines, description)``.

    Headings do not always alternate cleanly: an ``## Ingredients`` section
    can contain ``### Filling`` and ``### Crust`` sub-headings, and a
    ``## Directions`` section can contain ``### Prepare the dough``. An
    unrecognised sub-heading therefore keeps the current mode instead of
    dropping everything under it. Recognised note/utensil headings stop the
    mode so their prose is not mistaken for a recipe instruction.
    """
    ingredients = []
    directions = []
    description = []
    mode = None
    seen_heading = False

    for raw in body.splitlines():
        line = raw.strip()
        heading = HEADING.match(line)
        if heading:
            seen_heading = True
            level = len(heading.group("level"))
            name = heading.group("name").strip().casefold()
            is_note = any(word in name for word in NOTE_WORDS)
            if level <= 2:
                if any(word in name for word in INGREDIENT_WORDS):
                    mode = "ingredients"
                elif any(word in name for word in DIRECTION_WORDS):
                    mode = "directions"
                elif is_note:
                    mode = None
                # An unknown top-level heading (``## Spice Blend`` between
                # ingredients and directions) belongs to the current section.
            else:
                if any(word in name for word in DIRECTION_WORDS):
                    mode = "directions"
                elif any(word in name for word in INGREDIENT_WORDS):
                    mode = "ingredients"
                elif is_note:
                    mode = None
            continue

        if not line or line.startswith("<!--"):
            continue
        if mode == "ingredients":
            # Keep indentation: a two-space bullet is either a grouped
            # ingredient or a note under the previous one.
            ingredients.append(raw.rstrip())
        elif mode == "directions":
            directions.append(raw.rstrip())
        elif not seen_heading:
            description.append(line)

    return ingredients, directions, description


def _ingredient_candidates(lines):
    """Collapse an ingredient section into one string per ingredient.

    Group labels (``For the bechamel``, ``Spices:``) are not ingredients, and
    an indented bullet under one is a grouped ingredient. An indented bullet
    under a real ingredient is the author's note about that ingredient and is
    dropped. Plain lines are wrapped text or commentary; only a line that
    continues the previous ingredient (lowercase continuation or an open
    bracket/comma) is appended.
    """
    candidates = []
    grouped = False

    for raw in lines:
        line = raw.rstrip()
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" \t"))
        bullet = re.match(r"^(?:[-*+]|\d+[.)])\s+", text)
        if bullet:
            content = text[bullet.end():].strip()
            if not content:
                continue
            if indent >= 2:
                if grouped:
                    candidates.append(content)
                continue
            grouped = bool(GROUP_LABEL.match(content))
            if not grouped:
                candidates.append(content)
            continue

        if grouped or not candidates:
            continue
        previous = candidates[-1]
        if previous.endswith(("(", "[", ",")) or text[:1].islower():
            candidates[-1] = f"{previous} {text}"

    return candidates


def _append_step(step, text):
    """Join a nested line onto its parent, adding a sentence break if needed."""
    if not step:
        return text
    if step[-1] in ".!?;:":
        return f"{step} {text}"
    return f"{step}. {text}"


def _flatten_directions(lines):
    """Join indented sub-steps onto the top-level step above them.

    The detail page renders one ordered list; a nested ``1. Preparation:``
    followed by ``1. Preheat ...`` would otherwise become a dozen tiny steps
    and a bare ``Sauce:`` heading. The parent label stays at the head of the
    joined step. List markers are removed here because every top-level PDR
    item is a step, including lowercase ones such as ``1. cut the orange``.
    A bullet is put back on each finished step so the shared cleaner keeps
    lowercase steps separate instead of treating them as wrapped prose.
    """
    has_markers = any(
        LIST_MARKER.match(raw.strip()) for raw in lines if raw.strip()
    )
    steps = []
    for raw in lines:
        line = raw.rstrip()
        text = line.strip()
        if not text or text.startswith("<!--"):
            continue
        indent = len(line) - len(line.lstrip(" \t"))
        marker = LIST_MARKER.match(text)
        content = LIST_MARKER.sub("", text).strip()
        if not content:
            continue
        if marker and indent < 2:
            steps.append(content)
        elif indent >= 2 or (has_markers and not marker and steps):
            # A nested item or a wrapped paragraph under a numbered step.
            steps[-1] = _append_step(steps[-1], content)
        else:
            steps.append(content)
    return [f"- {step}" for step in steps]


def _normalise_amount(text):
    text = MIXED_NUMBER.sub(lambda m: f"{m.group('whole')} {m.group('fraction')}", text)

    def unit(match):
        value = match.group("unit").lower()
        if value == "lt":
            value = "l"
        return f"{match.group('amount')} {value}"

    text = RANGE_UNIT_JOIN.sub(unit, text)
    return UNIT_JOIN.sub(unit, text)


TRAILING_CLAUSE = re.compile(
    r"\s*,\s*(?:if|but|though|unless|since|which|you can|i (?:did|prefer|use)|"
    r"don't|do not)\b.*$",
    re.I,
)


def _strip_trailing_clause(text):
    """Cut a prose aside beginning at a top-level comma.

    The same words can appear inside a preparation note ("... chopped (fine,
    but not dry)"), so only cut a comma that is not nested in parentheses.
    """
    for match in TRAILING_CLAUSE.finditer(text):
        head = text[: match.start()]
        if head.count("(") == head.count(")"):
            return head
    return text


def _sentences(text):
    """Split at sentence endings, ignoring periods inside parentheses."""
    parts = []
    depth = 0
    start = 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        elif char in ".!?" and depth == 0 and (
            index + 1 == len(text) or text[index + 1].isspace()
        ):
            parts.append(text[start:index + 1].strip())
            start = index + 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts or [text]


def _clean_name(name):
    text = _markdown(name)
    text = OPTIONAL_PAREN.sub("", text)
    text = OPTIONAL_SUFFIX.sub("", text)
    text = MEASURE_PAREN.sub("", text)
    text = LONG_PAREN.sub("", text)
    text = SPACED_DASH.sub("", text)
    text = LEADING_PAREN.sub("", text)
    text = _strip_trailing_clause(text)
    text = re.sub(r"^\s*of\s+", "", text, flags=re.I)
    # "tortillas. Any brand works ..." is an ingredient followed by an
    # author's aside. Keep the first short sentence.
    sentences = _sentences(text)
    if len(sentences) > 1 and len(sentences[0].split()) <= 10:
        text = sentences[0]
    # A long first sentence followed by more prose is an author's note, not
    # an ingredient description. Keep the ingredient, drop the essay.
    if len(text.split()) > COMMENTARY_WORDS:
        first = _sentences(text)[0]
        if len(first.split()) <= COMMENTARY_WORDS:
            text = first
    text = re.sub(r"\s+", " ", text).strip(" ,;:-–—.+")
    text = canonical_ingredient_name(text)
    return text[:NAME_MAX_LENGTH].strip()


def parse_ingredient_line(line):
    """Return ``{"quantity", "name"}`` for one Markdown ingredient line, or None."""
    text = _markdown(LIST_MARKER.sub("", line))
    text = text.lstrip("~≈ ").strip()
    if not text or text.startswith("#") or text.lower().startswith("for the "):
        return None
    if text.endswith(":") and not re.search(r"\d", text):
        return None
    if COMMENTARY_START.match(text):
        return None
    # "Any extra herbs or spices to your taste" is a shopping suggestion, not
    # an ingredient; importing it adds prose to the pantry index.
    if VAGUE_START.match(text):
        return None

    # Some recipes put the ingredient first and the amount after a colon:
    # "Spaghetti: 320 g | 11 oz". Only treat the left side as a name when the
    # right side really starts with an amount.
    if ":" in text:
        name_part, amount_part = text.split(":", 1)
        amount_part = TRAILING_PIPE.sub("", amount_part).strip()
        if LEADING_AMOUNT.match(amount_part):
            text = f"{amount_part} {name_part.strip()}"
        elif name_part.strip():
            # "Mace (Optional): Mace is a dried flower ..." is a name followed
            # by commentary, not an amount.
            text = name_part.strip()
    text = TRAILING_PIPE.sub("", text).strip()
    text = OPTIONAL_PREFIX.sub("", text)
    text = _normalise_amount(text)

    few = A_FEW.match(text)
    if few:
        return {
            "quantity": few.group("amount")[:QUANTITY_MAX_LENGTH],
            "name": _clean_name(few.group("name")),
        }

    ranged = RANGE_HEAD.match(text)
    if ranged:
        quantity = " ".join(
            part for part in (ranged.group("amount"), ranged.group("unit") or "") if part
        )
        name = _clean_name(ranged.group("name"))
        if name and not _is_equipment(name):
            return {"quantity": quantity[:QUANTITY_MAX_LENGTH], "name": name}

    parsed = parse_ingredient(text)
    if parsed is None:
        return None
    quantity, name, _raw = parsed
    quantity = quantity.rstrip("+ ").strip()
    name = _clean_name(name)
    if not name or len(name.split()) > COMMENTARY_WORDS:
        return None
    if _is_equipment(name):
        return None
    return {"quantity": quantity[:QUANTITY_MAX_LENGTH], "name": name}


def _is_equipment(name):
    lowered = name.casefold().strip()
    if is_equipment(name):
        return True
    if lowered in EQUIPMENT:
        return True
    return lowered.startswith("thermos")


def _minutes(amount, unit):
    try:
        value = int(re.match(r"\d+", amount).group(0))
    except (AttributeError, TypeError, ValueError):
        return None
    if (unit or "").casefold() in {"hour", "hours", "hr", "hrs", "h"}:
        value *= 60
    return value


def _number(text):
    text = text.strip().casefold()
    if text.isdigit():
        return int(text)
    if text in NUMBER_WORDS:
        return NUMBER_WORDS[text]
    match = re.match(r"\d+", text)
    return int(match.group(0)) if match else None


def _servings(amount):
    text = " ".join(str(amount or "").split()).casefold()
    dozen = re.fullmatch(r"(?:(?P<count>[a-z]+|\d+)[\s-]+)?dozens?", text)
    if dozen:
        count = dozen.group("count")
        if count is None:
            return 12
        value = _number(count)
        return None if value is None else value * 12
    return _number(text)


def _recipe_description(lines):
    for line in lines:
        text = _markdown(line)
        if not text:
            continue
        if text.startswith(("- ", "⏲", "🍳", "🍽", "|")):
            continue
        if TIME.search(text) or SERVINGS.search(text):
            continue
        return text[:600]
    return ""


def _slug_for(name):
    stem = str(name or "").strip().removesuffix(".md")
    slug = re.sub(r"[^a-z0-9]+", "-", stem.casefold()).strip("-") or "recipe"
    return f"pdr-{slug}"


def parse_recipe(text, filename="recipe.md"):
    """Parse one Markdown recipe file into a :class:`PublicDomainRecipe`."""
    meta, body = _frontmatter(text)
    title = _markdown(meta.get("title") or Path(filename).stem.replace("-", " ").title())
    ingredient_lines, direction_lines, description_lines = _section_lines(body)

    ingredients = [
        parsed
        for line in _ingredient_candidates(ingredient_lines)
        if (parsed := parse_ingredient_line(line)) is not None
    ]
    directions = clean_directions(_flatten_directions(direction_lines))
    if not ingredients or not directions:
        return None

    body_text = "\n".join(
        line for line in body.splitlines() if line.strip() and not line.startswith("#")
    )
    times = {}
    for match in TIME.finditer(body_text):
        label = match.group("label").casefold()
        key = "prep_mins" if label.startswith("prep") else "cook_mins"
        if key not in times:
            times[key] = _minutes(match.group("amount"), match.group("unit"))

    servings = None
    match = SERVINGS.search(body_text)
    if match:
        servings = _servings(match.group("amount"))

    tags = normalize_tags(meta.get("tags") or [])
    cuisine = cuisine_for_tags(tags)
    date = str(meta.get("date") or "")
    source_year = date[:4] if re.match(r"\d{4}", date) else ""
    source_id = Path(filename).stem
    author = _markdown(meta.get("author") or "")

    return PublicDomainRecipe(
        slug=_slug_for(filename),
        source_id=source_id,
        title=title[:200],
        description=_recipe_description(description_lines),
        ingredients=ingredients,
        directions=directions,
        servings=servings,
        prep_mins=times.get("prep_mins"),
        cook_mins=times.get("cook_mins"),
        tags=tags,
        cuisine=cuisine,
        author=author,
        source_year=source_year,
        source_url=f"{SITE_URL}/{source_id}/",
    )


def parse_directory(content_dir):
    """Yield ``(path, parsed)`` for every parseable Markdown file in ``content_dir``."""
    for path in sorted(Path(content_dir).glob("*.md")):
        if path.name.startswith("_"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        parsed = parse_recipe(text, path.name)
        if parsed is not None:
            yield path, parsed


def as_recipe_data(parsed):
    """Convert a :class:`PublicDomainRecipe` into ``save_recipe`` input."""
    return {
        "title": parsed.title,
        "description": parsed.description,
        "servings": parsed.servings,
        "serving_size": "",
        "prep_mins": parsed.prep_mins,
        "cook_mins": parsed.cook_mins,
        "ingredients": parsed.ingredients,
        "directions": parsed.directions,
        "tags": parsed.tags,
        "cuisine": parsed.cuisine,
    }


def as_metadata(parsed):
    attribution = f"{parsed.author} — {SOURCE_TITLE}" if parsed.author else SOURCE_TITLE
    attribution = f"{attribution}. Released under the Unlicense."
    return {
        "source": SOURCE,
        "source_id": parsed.source_id,
        "source_title": SOURCE_TITLE,
        "source_year": parsed.source_year,
        "license": LICENSE,
        "attribution": attribution,
        "collection": COLLECTION,
        "category": "modern",
        "contributor": parsed.author[:100],
        "source_url": parsed.source_url,
        "cuisine": parsed.cuisine,
    }
