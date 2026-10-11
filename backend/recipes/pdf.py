"""Extract recipes from the USDA Team Nutrition chapter PDFs.

The cards are set in two columns and the layout engine letter-spaces words,
scatters metadata, and overlaps the two columns in x, so a fixed seam cannot
separate them. Each page is split instead at half its width word by word (a
word belongs to the column its midpoint falls in) and the lines are rebuilt
per row: the ingredients read from the left stream, the directions from the
right stream, and the times and the servings from both. Headers are matched
with internal spaces collapsed, since "Ingredients" renders as "I ngredients".
The title is read from the unfiltered page text because heading lines never
interleave. Cover pages and the amount-free Look-and-Cook sheets have no
"Ingredients" header anywhere and report ``None``.
"""

import re
from collections import defaultdict

import pdfplumber

BANNER = "united states department of agriculture"
CREDITING = "crediting information"
PAGE_FOOTER = (
    "page 1 of",
    "page 2 of",
    "food and nutrition service",
    "usda is an equal opportunity",
    "teamnutrition.usda.gov",
    "recipes for healthy kids",
)

TIME_LABEL = re.compile(r"(preparation|cooking)\s+time\s*:$", re.I)
INLINE_TIME = re.compile(
    r"(preparation|cooking)\s+time\s*:?\s*(?:(?P<h>\d+)\s*(?:hours?|hrs?|h)\s*)?"
    r"(?:and\s+)?(?P<m>\d+)?\s*(?:minutes?|mins?|m)\b",
    re.I,
)
TIME_VALUE = re.compile(
    r"(?:(?P<h>\d+)\s*(?:hours?|hrs?|h)\s*)?(?:and\s+)?"
    r"(?P<m>\d+)?\s*(?:minutes?|mins?|m)\b",
    re.I,
)
MAKES = re.compile(r"(?:makes|yield)\s*:?\s*(\d+)\s+servings?", re.I)
SERVINGS = re.compile(r"\b(\d+)\s+servings?\b", re.I)
TITLE_SUFFIX = re.compile(
    r"\s*[-–—]\s*(?:cacfp\s+(?:home\s+childcare|adult\s+portion|childcare|cacfp))$",
    re.I,
)
FRACTION = re.compile(r"^[\d.\u00bd\u00bc\u00be\u2153\u2154\u215b\u215c\u215d\u215e]+$")

QUANTITY_TOKENS = frozenset({
    "or", "and", "about", "approx", "approximately", "to", "fl", "qt", "each",
    "whole", "serving", "servings",
    "cup", "cups", "tbsp", "tablespoon", "tablespoons", "tsp", "teaspoon",
    "teaspoons", "oz", "ounce", "ounces", "lb", "lbs", "pound", "pounds",
    "g", "gram", "grams", "kg", "ml", "l", "clove", "cloves", "slice",
    "slices", "piece", "pieces", "pinch", "dash", "can", "cans", "package",
    "packages", "bag", "bags", "head", "heads", "bunch", "bunches", "jar",
    "jars", "carton", "cartons", "container", "containers", "stalk", "stalks",
    "bundle", "bundle", "medium", "large",
})
CREDIT_WORDS = ("provides", "equivalent", "spoodle", "scoop", "crediting")
STOP_WORDS = (
    "meal components", "grain ingredients", "whole grain-rich",
    "ingredients used in this recipe", "ingredients must meet", "source:",
    "nutrient", "nutrition information", "critical control point:",
    "notes section:", "see marketing guide", "preparation time", "cooking time",
)
SKIP_TITLES = frozenset({
    "whole grains", "meat/meat alternate", "vegetables", "fruit", "grains",
})


def _drop_line(line):
    lowered = line.strip().lower()
    if not lowered:
        return True
    if lowered.startswith(BANNER):
        return True
    if any(lowered.startswith(t) for t in PAGE_FOOTER):
        return True
    if "fns.usda.gov" in lowered or re.search(r"\|\s*(20\d\d|\d{2})$", lowered):
        return True
    return False


def _is_quantity_token(token):
    lowered = token.strip("(),.„“”;:—–-*").lower()
    if not lowered:
        return True
    if lowered in QUANTITY_TOKENS:
        return True
    return bool(FRACTION.match(lowered))


def _looks_malformed(line):
    return sum(1 for token in line.split() if len(token) == 1) >= 3


def _minutes(hours, minutes):
    if hours is None and minutes is None:
        return None
    return (int(hours) if hours else 0) * 60 + (int(minutes) if minutes else 0)


def _clean_heading(line):
    line = re.sub(r"\s+", " ", line).strip()
    return TITLE_SUFFIX.sub("", line).strip(" ,-–—")


def _header(label):
    """Collapse the letter-spacing the layout engine introduces in labels."""
    return re.sub(r"(?<=(\w)) +(?=\w)", "", label.lower())


INGS_HEADERS = {
    "ingredients", "ingredientscontinued", "ingredientsdirections",
    "directionsingredients", "ingredientscontinueddirections",
}
DIRS_HEADERS = {
    "directions", "directionscontinued", "ingredientsdirections",
    "directionsingredients", "directionscontinuedingredients",
}


def split_quantity(line):
    """Split an ingredient line into the quantity and the ingredient name.

    The name is the stretch of the line without measure tokens, wherever they
    sit: the classic cards write "3 ½ cups or 1 lb 5 oz Canned, low sodium
    pinto beans" with the name trailing, while the Healthy Kids tables write
    "Brown rice, long grain, regular, dry 4 ¾ oz ¾ cup" with it leading.
    Returns ``("", "")`` when the line carries no measures.
    """
    tokens = line.split()
    content = [not _is_quantity_token(token) for token in tokens]
    indices = [i for i, keep in enumerate(content) if keep]
    if not indices:
        return "", ""
    first = indices[0]
    last = indices[-1]
    quantity = " ".join(tokens[:first] + tokens[last + 1:])
    name = " ".join(tokens[first:last + 1])
    return quantity, name


def _page_columns(page):
    """Return ``(left_lines, right_lines, whole_lines)`` for one page."""
    words = page.extract_words(x_tolerance=2)
    seam = page.width * 0.5
    left = defaultdict(list)
    right = defaultdict(list)
    for word in words:
        mid = (word["x0"] + word["x1"]) / 2
        bands = left if mid < seam else right
        bands[round(word["top"])].append((word["x1"], word["text"]))
    whole = (page.extract_text() or "").splitlines()

    def rows(bands):
        lines = []
        for top in sorted(bands):
            words = sorted(bands[top], key=lambda item: item[0])
            lines.append(" ".join(text for _, text in words))
        return lines

    return rows(left), rows(right), whole


def _title_match(line):
    """Score a whole-page line as a title candidate; higher is better."""
    if TITLE_SUFFIX.search(line):
        return 3, _clean_heading(line)
    lowered = line.lower()
    if (
        len(line.split()) <= 5
        and lowered not in SKIP_TITLES
        and not _looks_malformed(line)
        and not FRACTION.match(line.replace(" ", ""))
    ):
        return 1, _clean_heading(line)
    return 0, None


def _pick_title(whole_lines):
    titles = []
    for raw in whole_lines:
        line = raw.strip()
        if not line or _drop_line(line):
            continue
        score, candidate = _title_match(line)
        if candidate:
            titles.append((score, candidate))
    if not titles:
        return None
    return max(titles, key=lambda item: item[0])[1]


def parse_pdf(path):
    """Parse one recipe PDF into a recipe dict, or None when it does not fit."""
    with pdfplumber.open(path) as pdf:
        pages = [_page_columns(page) for page in pdf.pages]
    return extract_recipe(pages)


def extract_recipe(pages):
    """Parse ``[(left_lines, right_lines, whole_lines)]`` into a recipe dict."""
    first_ing = None
    for index, (left, _, _) in enumerate(pages):
        if any(_header(line) in INGS_HEADERS for line in left):
            first_ing = index
            break
    if first_ing is None:
        return None

    left_stream = []
    right_stream = []
    whole_stream = []
    for index, (left, right, whole) in enumerate(pages):
        if index < first_ing:
            continue
        left_stream.extend(left)
        right_stream.extend(right)
        whole_stream.extend(whole)

    title = _pick_title(whole_stream)

    ingredients = []
    in_ingredients = False
    stop = False
    pending = ""
    for raw in left_stream:
        line = raw.strip()
        if not line or _drop_line(line):
            continue
        lowered = line.lower()
        if _header(line) in INGS_HEADERS:
            in_ingredients = True
            stop = False
            continue
        if lowered.startswith(CREDITING) or any(w in lowered for w in STOP_WORDS):
            in_ingredients = False
            stop = True
            continue
        if in_ingredients and not stop:
            quantity, name = split_quantity(line)
            if any(word in lowered for word in CREDIT_WORDS):
                continue
            if name in ("weight measure weight", "weight measure"):
                continue
            if quantity and name:
                if pending:
                    line = f"{pending} {line}"
                    pending = ""
                if split_quantity(line)[1] != title:
                    ingredients.append(line)
            elif name and not quantity:
                pending = f"{pending} {line}".strip()
            elif quantity and not name and pending:
                ingredients.append(f"{pending} {line}")
                pending = ""

    prep_mins = cook_mins = servings = None
    directions = []
    in_directions = False
    lines = right_stream
    for index, raw in enumerate(lines):
        line = raw.strip()
        if not line or _drop_line(line):
            continue
        lowered = line.lower()

        if prep_mins is None or cook_mins is None:
            inline = INLINE_TIME.search(lowered)
            if inline:
                minutes = _minutes(inline.group("h"), inline.group("m"))
                if inline.group(1).lower() == "preparation":
                    prep_mins = minutes
                else:
                    cook_mins = minutes
                continue
            label = TIME_LABEL.search(lowered)
            if label:
                for probe in lines[max(0, index - 2):index + 3]:
                    strict = TIME_VALUE.fullmatch(probe.strip().lower())
                    if strict and (strict.group("h") or strict.group("m")):
                        minutes = _minutes(strict.group("h"), strict.group("m"))
                        if label.group(1).lower() == "preparation":
                            prep_mins = minutes
                        else:
                            cook_mins = minutes
                        break
                continue
        if servings is None:
            match = MAKES.search(lowered)
            if match:
                servings = int(match.group(1))
                continue

        if _header(line) in DIRS_HEADERS:
            in_directions = True
            continue
        if any(w in lowered for w in STOP_WORDS):
            in_directions = False
            continue
        if in_directions and not lowered.startswith(CREDITING):
            directions.append(line)

    if servings is None:
        for raw in left_stream + right_stream:
            match = SERVINGS.search(raw)
            if match and not MAKES.match(raw):
                servings = int(match.group(1))
                break

    if not ingredients:
        return None

    return {
        "title": title,
        "description": "",
        "servings": servings,
        "prep_mins": prep_mins,
        "cook_mins": cook_mins,
        "ingredients": ingredients,
        "directions": directions,
    }