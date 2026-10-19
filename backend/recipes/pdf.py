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

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20,
    "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90,
}
NUMBER_RE = re.compile(
    r"\b(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen)\b",
    re.I,
)


def _parse_number(s):
    if not s:
        return None
    s = s.strip().lower()
    m = re.match(r"(\d+)", s)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    m = NUMBER_RE.search(s)
    if m:
        return NUMBER_WORDS.get(m.group(0).lower())
    return None

MAKES = re.compile(
    r"(?:makes|yields?|yield)\s*:?\s*"
    r"(\d+|[a-z]+)",
    re.I,
)
SERVINGS = re.compile(r"\b(\d+)\s+servings?\b", re.I)
SERVINGS_HEADING = re.compile(
    r"\d+\s+servings?(?:\s+\d+\s+servings?)+\s*$", re.I
)
TITLE_SUFFIX = re.compile(
    r"\s*[-–—]\s*(?:cacfp\s+(?:home\s+childcare|adult\s+portion|childcare|cacfp))$",
    re.I,
)
FRACTION = re.compile(r"^[\d.\u00bd\u00bc\u00be\u2153\u2154\u215b\u215c\u215d\u215e]+$")

# These single letters are what a broken WhitneyNumeric font emits for the
# common fractions on some home cards. Only K, N and O could be matched to a
# named fraction glyph by exact outline equality, so only they are decoded;
# the other letters stay as-is and make their quantity unresolvable rather
# than being guessed. The printed nutrient panel supplies calories regardless.
FRACTION_GLYPHS = frozenset({"L", "V", "W", "O", "K", "X", "M", "N"})
FRACTION_GLYPH_VALUES = {"K": "½", "N": "¼", "O": "¾"}

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

SERVING_SIZE = re.compile(
    r"(?:serving\s+size|makes?|yield|portion)\s*:?\s*([^()\n]*?)(?:\)|\(|$)", re.I
)
NUTRIENTS_HEADING = "nutrients per serving"
NUTRIENT_KEYS = {
    "calories": "kcal",
    "protein": "protein_g",
    "carbohydrate": "carbs_g",
    "total fat": "fat_g",
    "dietary fiber": "fiber_g",
}
NUTRIENT_NUMBER = re.compile(r"([0-9]+(?:\.[0-9]+)?)")

# A second ingredient hides in a merged row when a number and a measure word
# follow a finished name, as in "... Salt 1 dash Ground black pepper".
MERGED_QUANTITY = re.compile(
    r"(?<=[A-Za-z])\s+(?:\d+(?:\.\d+)?|[\u00bd\u00bc\u00be\u2150-\u215e]|[LVWOKMXNT])"
    r"\s+(?:tsp|tbsp|cup|cups|oz|lb|dash|Tbsp|Tsp|g|kg|ml|pinch)\b"
)



def _serving_count(lowered):
    """Number of servings from a "Makes N servings" style line."""
    match = MAKES.search(lowered)
    if not match:
        return None
    return _parse_number(match.group(1))


def _serving_size(lowered):
    """The portion wording attached to a "Makes ..." line, when there is one.

    "Makes six 1-cup servings" becomes "1-cup"; "Makes 36 Tots (serving size:
    6 tots)" becomes "6 tots"; "Makes 12 wraps (two wraps per serving)"
    becomes "2 wraps". A bare "Makes six servings" yields ``None``.
    """
    inner = re.search(r"serving\s+size\s*:?\s*([\w\u00bd\u00bc\u00be][^)]*)", lowered)
    if inner:
        return _decode_glyphs(_number_word(inner.group(1).strip(" .")))
    per_serving = re.search(r"\(([^)]+?)\s+per\s+serving", lowered)
    if per_serving:
        return _decode_glyphs(_number_word(per_serving.group(1).strip()))
    match = MAKES.search(lowered)
    if not match:
        return None
    after = re.sub(r"\s+", " ", lowered[match.end():]).strip(" .)")
    portion = re.split(
        r"\(|\bservings?\b|\bprovide|(?<=\s)\d+\.\s|"
        r"\s(?:about|and|then|to|combine|place|add|mix|stir|heat|cook|bake|serve)\b",
        after,
        maxsplit=1,
    )[0].strip(" ,.:;–-")
    portion = _decode_glyphs(_number_word(portion))
    if portion and not portion.isdigit() and not NUMBER_RE.fullmatch(portion):
        return portion
    return None


def _number_word(portion):
    """Rewrite a leading number word ("six", "two") as its digit."""
    match = NUMBER_RE.match(portion)
    if not match:
        return portion
    value = _parse_number(match.group(0))
    if value is None:
        return portion
    return f"{value}{portion[match.end():]}"


def _decode_glyphs(text):
    def decode(token):
        if token in FRACTION_GLYPH_VALUES:
            return FRACTION_GLYPH_VALUES[token]
        head, sep, tail = token.partition("-")
        if head.upper() in FRACTION_GLYPH_VALUES and len(head) == 1:
            return FRACTION_GLYPH_VALUES[head.upper()] + sep + tail
        return token
    return " ".join(decode(token) for token in text.split())


def _clean_ingredient_name(name):
    """Strip the artifacts the layout engine leaves on a name.

    The quantity column can overflow into the name (``"Salt 1 dash"``), and
    footnote markers and dangling fragments ride along (``"*Oil"``,
    ``"cranberries, chopped (1 L No."``). Only the leading quantity is
    removed here; the name itself is left as the card prints it.
    """
    text = " ".join(str(name or "").split()).strip()
    text = text.lstrip("*").strip()
    text = re.sub(r"\s+[M]\s*$", "", text).strip()
    text = re.sub(r"\s*\([^)]*$", "", text).strip(" ,;–-")
    return text


def _split_ingredient_row(line):
    """Split a row that holds two ingredient names.

    The measure and name columns sometimes merge, so a line reads
    ``"V tsp Salt 1 dash Ground black pepper"``. The split point is a
    quantity followed by a unit in the middle of the line; the first piece
    keeps everything before it, the second carries on from it.
    """
    matches = []
    for match in MERGED_QUANTITY.finditer(line):
        before = line[: match.start()].rstrip()
        after = line[match.end():].strip()
        if before.lower().endswith(" or"):
            continue
        if before and _is_quantity_token(before.split()[-1]):
            continue
        if not after or _is_quantity_token(after.split()[0]):
            continue
        matches.append(match)
    if not matches:
        return [line]
    pieces = []
    start = 0
    for match in matches:
        pieces.append(line[start:match.start()].strip())
        start = match.start()
    pieces.append(line[start:].strip())
    return [piece for piece in pieces if piece]


def _continues_previous(ingredients, name):
    """Whether ``name`` is the tail of the previous ingredient line.

    A name that wrapped onto the next line is a fragment like ``"cubed ¾”"``
    or ``"(chickpeas), with liquid"``: the previous line ends with a comma or
    the fragment opens lowercase or in parentheses, so it is glued back rather
    than added as an ingredient of its own.
    """
    if not ingredients:
        return False
    if not name:
        return False
    if name[0] == "(":
        return True
    previous_quantity, previous_name = split_quantity(ingredients[-1])
    if name[0].islower():
        # A complete ingredient on these cards always opens with a quantity,
        # so a lowercase fragment continues the previous line whether or not
        # that line ended on a comma ("...low moisture, part" / "skim, ...").
        return bool(previous_quantity) or previous_name.rstrip().endswith(",")
    return False


def _join_wrapped(lines):
    """Glue a "serving size:" fragment onto the row that closes it.

    The "Makes 36 Tots (serving size:" wording wraps in the column layout, so
    the closing "6 tots)" lands on the next row. Only that shape is joined, so
    prose with stray parentheses is left alone.
    """
    joined = []
    pending = ""
    for line in lines:
        current = f"{pending} {line}".strip() if pending else line
        if re.search(r"\(\s*serving\s+size\s*:?\s*$", current, re.I):
            pending = current
            continue
        pending = ""
        joined.append(current)
    if pending:
        joined.append(pending)
    return joined


def _parse_nutrients(lines):
    """Printed "Nutrients Per Serving" panel as ``{field: float}``.

    The panel is a single line on the home cards, so the numbers are read
    label by label; only the five tracked fields are kept. Returns an empty
    dict when the card carries no panel.
    """
    panel = ""
    for raw in lines:
        lowered = raw.lower()
        if NUTRIENTS_HEADING in lowered:
            panel = lowered.split(NUTRIENTS_HEADING, 1)[1]
            break
    if not panel:
        return {}
    nutrients = {}
    for label, field in NUTRIENT_KEYS.items():
        match = re.search(re.escape(label) + r"[^0-9]*([0-9]+(?:\.[0-9]+)?)", panel)
        if match:
            nutrients[field] = float(match.group(1))
    return nutrients


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
    if token.strip("(),.„“”;:—–-*") in FRACTION_GLYPHS:
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
    head = [FRACTION_GLYPH_VALUES.get(token, token) for token in tokens[:first]]
    tail = [FRACTION_GLYPH_VALUES.get(token, token) for token in tokens[last + 1:]]
    quantity = " ".join(head + tail)
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
    if SERVINGS_HEADING.search(line) or FRACTION.match(line.replace(" ", "")):
        return 0, None
    if (
        len(line.split()) <= 10
        and lowered not in SKIP_TITLES
        and not _looks_malformed(line)
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
            pending = ""
            continue
        if lowered.startswith(CREDITING) or any(w in lowered for w in STOP_WORDS):
            in_ingredients = False
            stop = True
            continue
        if not (in_ingredients and not stop):
            continue
        if any(word in lowered for word in CREDIT_WORDS):
            continue
        if lowered.startswith("optional:"):
            continue
        for piece in _split_ingredient_row(line):
            quantity, name = split_quantity(piece)
            name = _clean_ingredient_name(name)
            if not name:
                if quantity and pending:
                    ingredients.append(f"{pending} {piece}".strip())
                    pending = ""
                continue
            if name.lower() in ("weight measure weight", "weight measure"):
                continue
            if quantity:
                joined = f"{pending} {piece}".strip() if pending else piece
                pending = ""
                joined_name = _clean_ingredient_name(split_quantity(joined)[1])
                if joined_name == title:
                    continue
                if _continues_previous(ingredients, joined_name):
                    ingredients[-1] = f"{ingredients[-1]} {joined_name}".strip()
                    continue
                ingredients.append(joined)
            elif _continues_previous(ingredients, name):
                # A wrapped name fragment with no quantity -- "(chickpeas),
                # with liquid" under "Canned low-sodium garbanzo beans" --
                # belongs to the previous ingredient, not to the next line.
                ingredients[-1] = f"{ingredients[-1]} {name}".strip()
            else:
                pending = f"{pending} {piece}".strip()
    if pending:
        pending = _clean_ingredient_name(pending)
        if pending and pending != title:
            ingredients.append(pending)

    prep_mins = cook_mins = servings = None
    serving_size = None
    directions = []
    in_directions = False
    lines = _join_wrapped(right_stream)
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
                servings = _serving_count(lowered)
                serving_size = _serving_size(lowered)
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
        for raw in _join_wrapped(whole_stream) + _join_wrapped(left_stream) + _join_wrapped(right_stream):
            lowered = raw.lower()
            match = MAKES.search(lowered)
            if match:
                servings = _serving_count(lowered)
                serving_size = _serving_size(lowered)
                break
            match = SERVINGS.search(lowered)
            if match:
                try:
                    servings = int(match.group(1))
                except ValueError:
                    servings = _parse_number(lowered)
                break

    if serving_size is None:
        for raw in left_stream + right_stream + whole_stream:
            candidate = _serving_size(raw.lower())
            if candidate:
                serving_size = candidate
                break

    nutrients = _parse_nutrients(left_stream + right_stream + whole_stream)

    if not ingredients:
        return None

    return {
        "title": title,
        "description": "",
        "servings": servings,
        "serving_size": serving_size or "",
        "prep_mins": prep_mins,
        "cook_mins": cook_mins,
        "ingredients": ingredients,
        "directions": directions,
        "nutrients": nutrients,
    }