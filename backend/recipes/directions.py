"""Normalise recipe directions into clean, ordered cooking steps.

Sources hand us directions in three shapes: already-numbered Markdown steps,
PDF text where one logical step wraps across several physical lines, and
prose bullet lists. They also append material that is not an instruction: a
crediting block ("1 cup provides ..."), a printed nutrition panel
("Total Fat 8 g ..."), or a closing note.

The renderer draws an ordered list from one line per step, so this module is
the single place that turns any of those shapes into that list. It removes the
source's step numbers (the renderer adds its own), joins wrapped lines, and
stops at the first line that is clearly a footnote, crediting block or
nutrition panel rather than a cooking instruction.
"""

import re

# Lines that introduce non-instruction material. Once one of these appears the
# remaining lines belong to it, not to the method, until a numbered step
# resumes. Team Nutrition cards put the note and the crediting block after the
# last step, so this also protects against a wrapped note line being mistaken
# for a continuation of the final step.
NOTE_START = re.compile(
    r"^(?:note|notes|suggestion|suggestions|tip|tips|variation|variations|"
    r"source|sources|crediting|nutrition|nutrients)\b\s*:?",
    re.I,
)
YIELD_LINE = re.compile(
    r"^(?:makes?|serves?|yields?|for)\b.*\b"
    r"(?:servings?|portions?|people|persons|wraps?|cups?)\b",
    re.I,
)

# Nutrition-panel labels, matched case-insensitively. A line carrying one of
# these is the panel, not the method. "calories" is included because panels
# often break across lines and start a continuation with just the number plus
# the next label.
NUTRITION_LABEL = re.compile(
    r"\b(?:total\s+fat|saturated\s+fat|trans\s+fat|cholesterol|"
    r"dietary\s+(?:fiber|iron)|vitamin\s+[a-z]\b|"
    r"calcium\s*(?=\d)|iron\s*(?=\d)|calories|kcal|kilocalories)\b",
    re.I,
)

# Crediting language is specific to the USDA cards: "1 cup provides 2 oz
# equivalent meat/meat alternate". A bare "provides" inside a normal sentence
# is not enough, so require the crediting words to appear together or at the
# start of the line.
CREDITING = re.compile(
    r"(?:\bprovide[sd]?\b.*\bequivalents?\b|\bequivalents?\b.*\bprovide[sd]?\b|"
    r"^\s*provide[sd]?\b|\bcrediting\b)",
    re.I,
)

NUMBERED = re.compile(r"^\s*(?P<number>\d{1,3})\s*(?:[.)]\s*|\s+)(?P<text>.*)$")
BULLET = re.compile(r"^\s*[-*+]\s+(?P<text>.*)$")
MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
EMPHASIS = re.compile(r"(?<!\w)(\*{1,3}|_{1,3})(?=\S)(.+?)(?<=\S)\1(?!\w)")
HTML_TAG = re.compile(r"<[^>]+>")
TERMINAL = re.compile(r"[.!?;:]\s*$")
LOWERCASE_START = re.compile(r"^[a-z]")
# What is left after cutting a panel label can be a bare value fragment such
# as "6 g" or "0 mg". It is not an instruction.
TAIL_FRAGMENT = re.compile(
    r"^(?:[A-Z]|\d+(?:\.\d+)?|<)\s*"
    r"(?:g|mg|iu|mcg|kcal|%|calories|cal|cups?|tbsp|tsp|oz|"
    r"teaspoons?|tablespoons?|servings?)?$",
    re.I,
)
WRAPPED_LINE = 45


def _text(value):
    text = " ".join(str(value or "").split())
    text = MARKDOWN_LINK.sub(r"\1", text)
    text = EMPHASIS.sub(r"\2", text)
    text = HTML_TAG.sub("", text)
    return text.strip()


def _strip_tail(text):
    """Remove a nutrition panel or crediting tail from one line.

    Returns the instruction that precedes the tail, or an empty string when
    the whole line is tail material.
    """
    cuts = []
    for pattern in (NUTRITION_LABEL, CREDITING):
        match = pattern.search(text)
        if match:
            cuts.append(match.start())
    if not cuts:
        return text
    head = text[: min(cuts)].strip(" ,;:-–—")
    # A tail can begin after a complete sentence on the same line; keeping the
    # sentence before it is still useful. If nothing substantive is left,
    # drop the line.
    if not head or TAIL_FRAGMENT.match(head):
        return ""
    return head


def _is_tail_line(text):
    return bool(
        NOTE_START.match(text)
        or YIELD_LINE.match(text)
        or CREDITING.search(text)
        or NUTRITION_LABEL.search(text)
    )


def _step_matches(line):
    """Return ``(text, marked)`` for a line, stripping its list marker.

    ``marked`` is true when the source explicitly starts a new step with a
    number or a bullet. Bare PDF numbers ("1 Preheat the oven") count too,
    but only when the number is followed by a capital letter, so a wrapped
    line beginning "2 cups ..." is not mistaken for step 2.
    """
    numbered = NUMBERED.match(line)
    if numbered:
        rest = numbered.group("text").strip()
        if rest and (rest[0].isupper() or rest[0].isdigit() or not rest[0].isalpha()):
            return rest, True
        # "1 cup ..." has a measure at the head, not a step number.
    bullet = BULLET.match(line)
    if bullet:
        return bullet.group("text").strip(), True
    return line.strip(), False


def _clean_lines(lines):
    """Yield ``(text, marked)`` after removing tails and note blocks."""
    if isinstance(lines, str):
        lines = lines.splitlines()
    dropping = False
    for raw in lines or []:
        text = _text(raw)
        if not text:
            continue
        text, marked = _step_matches(text)
        if not text:
            continue
        if NOTE_START.match(text):
            dropping = True
            continue
        if dropping and not marked:
            continue
        # Crediting and nutrition-panel lines are unnumbered tails, so drop
        # them whole. A numbered line keeps the instruction before a tail.
        if not marked and _is_tail_line(text):
            continue
        text = _strip_tail(text)
        if not text:
            continue
        if _is_tail_line(text):
            # Yield lines and crediting blocks are not directions. A numbered
            # line that still matched a tail pattern is malformed; skip it
            # rather than showing panel text as a cooking step.
            continue
        if marked:
            dropping = False
        yield text, marked


def clean_directions(lines):
    """Return the clean steps in ``lines`` as a list of strings.

    ``lines`` may be a newline-separated string or an iterable of lines. The
    result never carries source step numbers; the detail page renders its own
    ordered list.
    """
    cleaned = list(_clean_lines(lines))
    if not cleaned:
        return []

    has_numbers = any(marked for _, marked in cleaned)
    steps = []
    for text, marked in cleaned:
        if marked:
            steps.append(text)
            continue
        if not steps:
            steps.append(text)
            continue
        previous = steps[-1]
        # In a numbered sequence every unnumbered line is a continuation of
        # the step above it. In unmarked prose the line break usually *is* the
        # step boundary: old cookbooks write one short instruction per line.
        # Only glue a line back when it looks like a wrapped paragraph -- the
        # previous line is long and unfinished and this one opens in lowercase.
        if has_numbers:
            steps[-1] = f"{previous} {text}"
        elif (
            not TERMINAL.search(previous)
            and len(previous) >= WRAPPED_LINE
            and LOWERCASE_START.match(text)
        ):
            steps[-1] = f"{previous} {text}"
        else:
            steps.append(text)

    # Collapse whitespace introduced by joining and discard empty results.
    return [" ".join(step.split()) for step in steps if step.strip()]


def directions_text(value):
    """Render ``value`` as the newline-separated directions string stored on a row."""
    return "\n".join(clean_directions(value))
