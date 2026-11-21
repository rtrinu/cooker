"""Common household weights used only when USDA has no measure for an ingredient.

A gram conversion should come from the ingredient itself: an exact mass on the
recipe line, or a USDA ``foodPortions`` entry for that food. Those are measured
values and always win. This module is the last resort for the remaining lines,
where a recipe says "1 cup flour" and the imported food happens to have no cup
portion. Refusing every one of those lines turns a whole recipe into a lower
bound; using a standard cooking weight keeps the estimate useful.

The values below are ordinary culinary references (a cup of all-purpose flour is
about 125 g, a large egg about 50 g), not measurements of any particular sample.
They are deliberately coarse, and every conversion that uses one is labelled
low-confidence so it can be audited instead of mistaken for measured data.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class StandardWeight:
    """One named fallback rule, matched against the ingredient wording."""

    name: str
    pattern: re.Pattern
    grams_per_ml: float | None = None
    grams_each: float | None = None


# Order matters: specific phrases ("brown sugar", "olive oil") must be tried
# before the generic word they contain.
RULES = (
    StandardWeight("brown sugar", re.compile(r"\bbrown sugar\b"), grams_per_ml=0.72),
    StandardWeight("powdered sugar", re.compile(r"\b(powdered|confectioners?) sugar\b"), grams_per_ml=0.56),
    StandardWeight("granulated sugar", re.compile(r"\bsugar\b"), grams_per_ml=0.85),
    StandardWeight("olive oil", re.compile(r"\bolive oil\b"), grams_per_ml=0.91),
    StandardWeight("oil", re.compile(r"\b(oil|shortening)\b"), grams_per_ml=0.92),
    StandardWeight("honey", re.compile(r"\b(honey|molasses|syrup)\b"), grams_per_ml=1.40),
    StandardWeight("peanut butter", re.compile(r"\bpeanut butter\b"), grams_per_ml=1.09),
    StandardWeight("mayonnaise", re.compile(r"\bmayonnaise\b"), grams_per_ml=0.91),
    StandardWeight("vinegar", re.compile(r"\bvinegar\b"), grams_per_ml=1.01),
    StandardWeight("soy sauce", re.compile(r"\bsoy sauce\b"), grams_per_ml=1.16),
    StandardWeight("ketchup", re.compile(r"\bketchup\b"), grams_per_ml=1.10),
    StandardWeight("juice", re.compile(r"\bjuice\b"), grams_per_ml=1.04),
    StandardWeight("milk", re.compile(r"\b(milk|buttermilk)\b"), grams_per_ml=1.03),
    StandardWeight("yogurt", re.compile(r"\byogurt\b"), grams_per_ml=1.03),
    StandardWeight("cream", re.compile(r"\b(cream|half and half)\b"), grams_per_ml=1.01),
    StandardWeight("broth", re.compile(r"\b(broth|stock|water)\b"), grams_per_ml=1.00),
    StandardWeight("all-purpose flour", re.compile(r"\bflour\b"), grams_per_ml=0.53),
    StandardWeight("cornmeal", re.compile(r"\b(cornmeal|polenta)\b"), grams_per_ml=0.55),
    StandardWeight("cornstarch", re.compile(r"\b(cornstarch|corn starch)\b"), grams_per_ml=0.54),
    StandardWeight("cocoa", re.compile(r"\bcocoa\b"), grams_per_ml=0.42),
    StandardWeight("rolled oats", re.compile(r"\boats?\b"), grams_per_ml=0.41),
    StandardWeight("uncooked rice", re.compile(r"\brice\b"), grams_per_ml=0.85),
    StandardWeight("dry pasta", re.compile(r"\bpasta\b"), grams_per_ml=0.42),
    StandardWeight("breadcrumbs", re.compile(r"\b(bread ?crumbs?|panko)\b"), grams_per_ml=0.45),
    StandardWeight("shredded cheese", re.compile(r"\bcheese\b"), grams_per_ml=0.38),
    StandardWeight("salt", re.compile(r"\bsalt\b"), grams_per_ml=1.20),
    StandardWeight("leavening", re.compile(r"\b(baking powder|baking soda|bicarbonate)\b"), grams_per_ml=0.90),
    StandardWeight("dried fruit", re.compile(r"\b(raisins?|currants?|cranberries|dried fruit)\b"), grams_per_ml=0.60),
    StandardWeight("chocolate chips", re.compile(r"\b(chocolate chips?|chips)\b"), grams_per_ml=0.60),
    StandardWeight("nuts", re.compile(r"\b(nuts?|almonds?|walnuts?|pecans?|peanuts?)\b"), grams_per_ml=0.60),
    StandardWeight("egg", re.compile(r"\begg\b"), grams_each=50.0),
    StandardWeight("garlic clove", re.compile(r"\bgarlic\b"), grams_each=3.0),
    StandardWeight("onion", re.compile(r"\bonions?\b"), grams_each=110.0),
    StandardWeight("potato", re.compile(r"\bpotato(es)?\b"), grams_each=170.0),
    StandardWeight("tomato", re.compile(r"\btomato(es)?\b"), grams_each=123.0),
    StandardWeight("carrot", re.compile(r"\bcarrots?\b"), grams_each=61.0),
    StandardWeight("celery stalk", re.compile(r"\bcelery\b"), grams_each=40.0),
    StandardWeight("lemon", re.compile(r"\blemons?\b"), grams_each=58.0),
    StandardWeight("lime", re.compile(r"\blimes?\b"), grams_each=44.0),
    StandardWeight("apple", re.compile(r"\bapples?\b"), grams_each=182.0),
    StandardWeight("banana", re.compile(r"\bbananas?\b"), grams_each=118.0),
    StandardWeight("avocado", re.compile(r"\bavocados?\b"), grams_each=150.0),
    StandardWeight("bread slice", re.compile(r"\b(bread|toast)\b"), grams_each=28.0),
    StandardWeight("tortilla", re.compile(r"\btortillas?\b"), grams_each=45.0),
)

# Units whose weight is too small or too irregular for a density rule, but
# which still appear in recipes. Used only when the ingredient has no matching
# USDA measure of its own.
SMALL_UNIT_GRAMS = {
    "pinch": 0.36,   # about 1/16 tsp of a fine seasoning
    "dash": 0.60,    # about 1/8 tsp
    "drop": 0.05,
    "sprig": 2.0,
    "handful": 30.0,
}

# A size word changes a count weight, but only roughly. Kept small so the
# warning the converter attaches still means something.
SIZE_FACTORS = {"small": 0.8, "medium": 1.0, "large": 1.2}


def _text(name, context):
    return f"{name or ''} {context or ''}".casefold()


def rule_for(name, context=""):
    """The first fallback rule that describes ``name``/``context``, or None."""
    text = _text(name, context)
    for rule in RULES:
        if rule.pattern.search(text):
            return rule
    return None


def grams_for_volume(name, context, millilitres):
    """Estimated grams for ``millilitres`` of the named ingredient."""
    rule = rule_for(name, context)
    if rule is None or rule.grams_per_ml is None:
        return None
    return millilitres * rule.grams_per_ml


def grams_for_count(name, context, count, unit=None):
    """Estimated grams for ``count`` items of the named ingredient."""
    rule = rule_for(name, context)
    if rule is None or rule.grams_each is None:
        return None
    factor = SIZE_FACTORS.get(unit or "", 1.0)
    return count * rule.grams_each * factor


def grams_for_unit(unit, amount):
    """Estimated grams for a small measure such as a pinch or a dash."""
    per_unit = SMALL_UNIT_GRAMS.get(unit or "")
    if per_unit is None:
        return None
    return amount * per_unit
