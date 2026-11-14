"""Per-serving nutrition computed from a recipe's ingredient amounts.

USDA nutrients are published per 100 g; an ingredient amount is converted to
grams and scaled from there. Nothing in this module invents a missing value:
a line with no parseable amount, no measure, or no nutrition row contributes
zero and is returned in the report, because a figure built from half a recipe
would be silently wrong.
"""

from collections import namedtuple

from .models import NUTRIENT_FIELDS
from .units import grams_for, parse_amount

ComputedNutrition = namedtuple(
    "ComputedNutrition",
    ("per_serving", "totals", "lines_used", "lines_total", "unresolved"),
)

# A computed panel is only trustworthy when nearly every ingredient line
# converted. Unresolved lines can only make a total too low, so a sum built
# from part of a recipe is not an estimate of that recipe -- it is the
# nutrition of a different, smaller dish. Anything below this share is
# reported rather than published as per-serving calories.
MIN_COVERAGE = 0.75


def coverage(computed):
    """Share of ingredient lines that contributed to ``computed``, 0..1."""
    if not computed.lines_total:
        return 0.0
    return computed.lines_used / computed.lines_total


def is_reliable(computed, servings, minimum=MIN_COVERAGE):
    """Whether ``computed`` is complete enough to publish as per serving.

    A recipe with no known serving count cannot produce a per-serving figure
    at all: dividing by an invented ``1`` silently turns a whole dish into one
    serving.
    """
    return bool(servings) and coverage(computed) >= minimum


def scale_nutrients(nutrition, grams):
    """Nutrients contained in ``grams`` of an ingredient.

    ``nutrition`` is an ``IngredientNutrition`` row whose values are for
    ``serving_size_g`` grams.
    """
    factor = grams / nutrition.serving_size_g
    return {
        field: (getattr(nutrition, field) or 0.0) * factor for field in NUTRIENT_FIELDS
    }


def compute(lines, servings):
    """Per-serving nutrition across ``lines`` of ``(ingredient, quantity_text)``.

    Returns a ``ComputedNutrition`` where ``per_serving`` and ``totals`` are
    ``{field: float}`` dicts over the five tracked nutrients and ``unresolved``
    lists one entry per line that contributed nothing, phrased so the report
    can print it without further thought.
    """
    totals = dict.fromkeys(NUTRIENT_FIELDS, 0.0)
    unresolved = []
    used = 0
    total = 0
    for ingredient, quantity_text in lines:
        total += 1
        nutrition = ingredient.nutrition.first()
        amount, unit, _ = parse_amount(quantity_text)
        grams = None
        reason = None
        if amount is None:
            reason = "no amount"
        elif nutrition is None:
            reason = "no nutrition"
        else:
            grams = grams_for(ingredient.measures.all(), unit, amount)
            if grams is None:
                reason = f"no {unit or 'unit'} measure"
        if grams is None:
            if reason is None:
                reason = "no conversion"
            unresolved.append(
                {"ingredient": ingredient.name, "quantity": quantity_text, "reason": reason}
            )
            continue
        for field, value in scale_nutrients(nutrition, grams).items():
            totals[field] += value
        used += 1

    per_serving = {
        field: totals[field] / servings if servings else totals[field]
        for field in NUTRIENT_FIELDS
    }
    return ComputedNutrition(per_serving, totals, used, total, unresolved)
