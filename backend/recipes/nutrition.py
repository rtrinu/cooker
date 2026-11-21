"""Per-serving nutrition computed from a recipe's ingredient amounts.

Every line goes through one pipeline: parse the amount, convert it to grams,
then scale the ingredient's per-100 g nutrition record. A gram value can come
from an explicit mass on the line, a USDA measure for that food, or -- only
when neither exists -- a standard cooking weight. The first two are measured
data; the last is an estimate and is flagged so it can be audited.

Nothing here invents a missing value: a line with no parseable amount, no
nutrition record, or no conversion contributes nothing and is returned in the
report. A panel built from part of a recipe is published as a lower bound with
its coverage and confidence, never as if it were the whole dish.
"""

from collections import namedtuple
from dataclasses import dataclass

from .models import INGREDIENT_NUTRIENT_FIELDS, NUTRIENT_FIELDS
from .units import parse_quantity, resolve_grams

ComputedNutrition = namedtuple(
    "ComputedNutrition",
    (
        "per_serving",
        "totals",
        "lines_used",
        "lines_total",
        "unresolved",
        "weight_g",
        "confidence",
        "warnings",
        "lines",
    ),
)


@dataclass(frozen=True)
class LineResult:
    """What happened to one ingredient line during a panel calculation.

    ``grams`` and ``confidence`` describe the measurement conversion alone,
    so they remain useful even when the line has no nutrition record. Whether
    the line contributed to the panel is indicated by ``reason`` being empty.
    """

    ingredient: str
    quantity: str
    grams: float | None
    nutrition: object | None
    conversion: object | None
    reason: str
    confidence: float
    method: str = ""
    detail: str = ""


# Model fields filled from a :class:`LineResult`; kept in one place so a caller
# can bulk-update lines without repeating the mapping.
CONVERSION_FIELDS = ("grams", "grams_method", "grams_detail", "grams_confidence")


def apply_line_conversions(computed, rows):
    """Copy resolved grams and provenance from ``computed`` onto ``rows``.

    ``rows`` must be in the same order as the lines that produced ``computed``.
    Does not save; the caller owns the transaction and can bulk-update the
    returned field names.
    """
    for row, line in zip(rows, computed.lines):
        row.grams = line.grams
        row.grams_method = line.method
        row.grams_detail = line.detail[:200]
        row.grams_confidence = line.confidence if line.grams is not None else None
    return CONVERSION_FIELDS


# A computed panel is only trustworthy when nearly every ingredient line
# converted. Unresolved lines can only make a total too low, so a sum built
# from part of a recipe is not an estimate of that recipe -- it is the
# nutrition of a different, smaller dish. Anything below this share is
# reported rather than published as per-serving calories.
MIN_COVERAGE = 0.75
# Below this combined confidence the panel is kept as a lower bound but the
# UI says the estimate is weak.
MIN_CONFIDENCE = 0.60

# A generic USDA row is still the right food; verification affects how much we
# trust it, not whether it counts. Match confidence, when present, is stricter.
VERIFICATION_CONFIDENCE = {
    "verified": 1.0,
    "estimated": 0.95,
}
DEFAULT_NUTRITION_CONFIDENCE = 0.90


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
    return (
        bool(servings)
        and coverage(computed) >= minimum
        and computed.confidence >= MIN_CONFIDENCE
    )


def scale_nutrients(nutrition, grams):
    """Nutrients contained in ``grams`` of an ingredient.

    ``nutrition`` is an ``IngredientNutrition`` row whose values are for
    ``serving_size_g`` grams.
    """
    factor = grams / nutrition.serving_size_g
    return {
        field: (getattr(nutrition, field) or 0.0) * factor for field in NUTRIENT_FIELDS
    }


def _nutrition_rank(nutrition):
    """Ordering for choosing between several records for one ingredient."""
    verification = {"verified": 2, "estimated": 1}.get(
        nutrition.verification_status, 0
    )
    confidence = nutrition.confidence if nutrition.confidence is not None else -1.0
    completeness = sum(
        getattr(nutrition, field) is not None
        for field in INGREDIENT_NUTRIENT_FIELDS
    )
    return (verification, confidence, completeness, nutrition.pk or 0)


def best_nutrition(ingredient):
    """The most trustworthy nutrition record for ``ingredient``, or None.

    ``ingredient.nutrition.first()`` is database order, which can change. A
    verified record beats an estimate, a higher match confidence beats a lower
    one, and a complete record beats a sparse one. The primary key is only a
    final tie-break so the same data always produces the same figure.
    """
    rows = list(ingredient.nutrition.all())
    if not rows:
        return None
    return max(rows, key=_nutrition_rank)


def nutrition_confidence(nutrition):
    """How much to trust the nutrition record itself, 0..1."""
    if nutrition is None:
        return 0.0
    if nutrition.confidence is not None:
        return max(0.0, min(1.0, nutrition.confidence))
    return VERIFICATION_CONFIDENCE.get(
        nutrition.verification_status, DEFAULT_NUTRITION_CONFIDENCE
    )


def _line_parts(line):
    """Accept ``(ingredient, quantity)`` or ``(ingredient, quantity, context)``."""
    ingredient, quantity = line[0], line[1] if len(line) > 1 else ""
    context = line[2] if len(line) > 2 else ""
    return ingredient, quantity or "", context or ""


def _add_warning(warnings, warning):
    if warning not in warnings:
        warnings.append(warning)


def macro_kcal(totals):
    """Energy implied by the macros, using 4/4/9 kcal per gram."""
    return (
        totals.get("protein_g", 0.0) * 4
        + totals.get("carbs_g", 0.0) * 4
        + totals.get("fat_g", 0.0) * 9
    )


def panel_warnings(totals, weight_g=None):
    """Sanity checks that do not change the numbers, only flag them.

    A large gap between the recorded calories and the macro-derived energy
    usually means the wrong food was matched or the source row is incomplete.
    An energy density above pure fat is physically impossible.
    """
    warnings = []
    kcal = totals.get("kcal", 0.0)
    if kcal >= 20:
        derived = macro_kcal(totals)
        if abs(derived - kcal) / kcal > 0.30:
            warnings.append("macro-mismatch")
    if weight_g and kcal and kcal / weight_g * 100 > 900:
        warnings.append("implausible-energy-density")
    return warnings


def compute(lines, servings):
    """Per-serving nutrition across ``lines`` of ingredient amounts.

    Each line is ``(ingredient, quantity_text)`` or
    ``(ingredient, quantity_text, context)``. The context is the original
    recipe wording, used to choose between USDA measures such as "cup, sliced"
    and "cup, mashed".

    Returns a ``ComputedNutrition`` whose ``per_serving`` and ``totals`` are
    ``{field: float}`` dicts over the five tracked nutrients. ``unresolved``
    lists one entry per line that contributed nothing, phrased so the report
    can print it without further thought. ``confidence`` combines ingredient
    coverage with the trustworthiness of each gram conversion, and
    ``warnings`` names anything that needs a human look.
    """
    totals = dict.fromkeys(NUTRIENT_FIELDS, 0.0)
    unresolved = []
    warnings = []
    line_results = []
    used = 0
    total = 0
    weight_g = 0.0
    weighted_confidence = 0.0

    for line in lines:
        ingredient, quantity_text, context = _line_parts(line)
        total += 1
        nutrition = best_nutrition(ingredient)
        quantity = parse_quantity(quantity_text)
        conversion = None

        if quantity.amount is None:
            reason = "no amount"
        else:
            conversion = resolve_grams(
                ingredient, quantity, f"{ingredient.name} {context}"
            )
            # A line with no nutrition record is reported as such even when its
            # mass resolves: the missing nutrition is what costs the panel.
            if nutrition is None:
                reason = "no nutrition"
            elif conversion is None:
                reason = f"no {quantity.unit or 'unit'} measure"
            else:
                reason = None

        if conversion is None or reason is not None:
            line_results.append(
                LineResult(
                    ingredient.name,
                    quantity_text,
                    conversion.grams if conversion is not None else None,
                    nutrition,
                    conversion,
                    reason or "no conversion",
                    round(conversion.confidence, 3) if conversion is not None else 0.0,
                    conversion.method if conversion is not None else "",
                    conversion.detail if conversion is not None else "",
                )
            )
            unresolved.append(
                {
                    "ingredient": ingredient.name,
                    "quantity": quantity_text,
                    "reason": reason,
                }
            )
            continue

        for field, value in scale_nutrients(nutrition, conversion.grams).items():
            totals[field] += value
        used += 1
        weight_g += conversion.grams
        confidence = conversion.confidence * nutrition_confidence(nutrition)
        weighted_confidence += confidence * conversion.grams
        line_results.append(
            LineResult(
                ingredient.name,
                quantity_text,
                conversion.grams,
                nutrition,
                conversion,
                "",
                round(conversion.confidence, 3),
                conversion.method,
                conversion.detail,
            )
        )
        if conversion.ambiguous:
            _add_warning(warnings, "ambiguous-measure")
        if conversion.standard:
            _add_warning(warnings, "standard-weight")

    per_serving = {
        field: totals[field] / servings if servings else totals[field]
        for field in NUTRIENT_FIELDS
    }

    share = used / total if total else 0.0
    quality = weighted_confidence / weight_g if weight_g else 0.0
    confidence = round(share * quality, 3)

    if used < total:
        _add_warning(warnings, "partial")
    if total and confidence < MIN_CONFIDENCE:
        _add_warning(warnings, "low-confidence")
    for warning in panel_warnings(totals, weight_g):
        _add_warning(warnings, warning)

    return ComputedNutrition(
        per_serving,
        totals,
        used,
        total,
        unresolved,
        round(weight_g, 3),
        confidence,
        warnings,
        tuple(line_results),
    )
