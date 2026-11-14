"""Backfill provenance and conversion metadata for rows created before it existed.

Existing nutrition rows came from USDA FoodData Central under CC0 1.0. The
exact retrieval date was not stored, so the migration date is used as the date
the data entered this database. That is a lower bound on provenance, not an
invented source date. ``processed_at`` is backfilled the same way: it records
when this migration labelled an already-matched ingredient, not a guess at when
the original match happened.

The backfill only fills blanks. Re-running it after a reverse or a restore must
not overwrite provenance that was recorded more precisely when a row was
imported.
"""

import re

from django.db import migrations

USDA_SOURCE = "USDA FoodData Central"
USDA_LICENSE = "CC0 1.0"
USDA_ATTRIBUTION = (
    "U.S. Department of Agriculture, Agricultural Research Service. "
    "FoodData Central, 2019. fdc.nal.usda.gov."
)
# Frozen copies of the helpers in recipes.units and recipes.ingredient_cleanup
# as of migration 0011. A data migration must not import application code that
# is free to change later, so these are duplicated on purpose. Do not "fix" the
# duplication by importing the live helpers: that would silently change what
# this migration does on an old database.
US_CUSTOMARY = frozenset(
    {"cup", "tbsp", "tsp", "fl oz", "gill", "pint", "quart", "gallon", "oz", "lb"}
)
METRIC = frozenset({"ml", "l", "dl", "cl", "mg", "g", "kg"})
MASS = frozenset({"mg", "g", "kg", "oz", "lb"})
VOLUME = frozenset(
    {"ml", "l", "fl oz", "tsp", "tbsp", "cup", "gill", "pint", "quart", "gallon"}
)
PREPARATION_STATES = frozenset(
    {
        "raw",
        "cooked",
        "boiled",
        "steamed",
        "roasted",
        "baked",
        "grilled",
        "fried",
        "sauteed",
        "braised",
        "poached",
        "smoked",
        "dried",
        "canned",
        "frozen",
        "thawed",
        "pasteurized",
        "homemade",
        "commercial",
    }
)
# Words are matched the same way as recipes.ingredient_cleanup; splitting on
# whitespace instead would miss forms such as "pan-fried".
_PREPARATION_WORD = re.compile(r"[a-z]+")


def measurement_system(measure):
    if measure in US_CUSTOMARY:
        return "us"
    if measure in METRIC:
        return "metric"
    return "unspecified"


def conversion_confidence(measure):
    if measure in MASS:
        return 1.0
    if measure in VOLUME:
        return 0.9
    return 0.8


def preparation_state(text):
    found = []
    for word in _PREPARATION_WORD.findall(str(text or "").casefold()):
        if word in PREPARATION_STATES and word not in found:
            found.append(word)
    return ", ".join(found)[:50]


def backfill(apps, schema_editor):
    from django.utils import timezone

    Ingredient = apps.get_model("recipes", "Ingredient")
    IngredientMeasure = apps.get_model("recipes", "IngredientMeasure")
    IngredientNutrition = apps.get_model("recipes", "IngredientNutrition")

    now = timezone.now()

    # Fill only blanks. Ingredients already marked matched keep their original
    # processed_at, and a stale error on one of them is cleared.
    matched = Ingredient.objects.filter(nutrition__isnull=False).exclude(
        processing_status="matched"
    )
    matched.update(
        processing_status="matched",
        processing_error="",
        processed_at=now,
    )
    Ingredient.objects.filter(nutrition__isnull=False).exclude(
        processing_error=""
    ).update(processing_error="")

    nutrition = IngredientNutrition.objects.filter(source=USDA_SOURCE)
    nutrition.filter(license="").update(license=USDA_LICENSE)
    nutrition.filter(attribution="").update(attribution=USDA_ATTRIBUTION)
    nutrition.filter(retrieved_at__isnull=True).update(retrieved_at=now)

    # Which source produced each ingredient, so a measure is never labelled
    # "USDA foodPortions" when its ingredient came from somewhere else.
    sources = {}
    for ingredient_id, source in IngredientNutrition.objects.values_list(
        "ingredient_id", "source"
    ):
        sources.setdefault(ingredient_id, set()).add(source)

    def conversion_source(ingredient_id):
        names = sources.get(ingredient_id, ())
        if USDA_SOURCE in names:
            return f"{USDA_SOURCE} foodPortions"
        if names:
            return f"{sorted(names)[0]} foodPortions"
        return ""

    measures = []
    fields = [
        "measurement_system",
        "conversion_source",
        "confidence",
        "preparation_state",
    ]
    for measure in IngredientMeasure.objects.select_related("ingredient").iterator():
        before = (
            measure.measurement_system,
            measure.conversion_source,
            measure.confidence,
            measure.preparation_state,
        )
        system = measure.measurement_system
        if not system or system == "unspecified":
            measure.measurement_system = measurement_system(measure.measure)
        if not measure.conversion_source:
            measure.conversion_source = conversion_source(measure.ingredient_id)
        if measure.confidence is None:
            measure.confidence = conversion_confidence(measure.measure)
        if not measure.preparation_state:
            # The live importer reads the USDA description and portion label.
            # Historical rows only kept the ingredient name, so the label is
            # the closest surviving input; still closer than the name alone.
            measure.preparation_state = preparation_state(
                f"{measure.ingredient.name} {measure.source_label}"
            )
        after = (
            measure.measurement_system,
            measure.conversion_source,
            measure.confidence,
            measure.preparation_state,
        )
        if after != before:
            measures.append(measure)
    if measures:
        IngredientMeasure.objects.bulk_update(measures, fields, batch_size=1000)


def unbackfill(apps, schema_editor):
    # The added fields do not change existing nutrition arithmetic, so there is
    # nothing destructive to undo. Clearing them would lose provenance.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("recipes", "0011_remove_ingredientmeasure_ingredient_measure_valid_values_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
