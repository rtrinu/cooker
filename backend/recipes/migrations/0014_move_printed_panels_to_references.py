"""Move printed nutrition panels beside the computed figure.

Before this change a printed panel was the published ``Nutrition`` row with
``method="source"``. Nutrition is now always computed from ingredients, so the
printed values become a ``NutritionReference`` used only as validation ground
truth. The old source rows are removed so nothing keeps serving a printed panel
as if it were calculated; run ``recompute_nutrition`` afterwards to republish
every recipe's computed panel.

The copy is lossless for the five tracked nutrients. Only rows that can be
identified as printed panels are touched.
"""

from django.db import migrations

PRINTED_METHOD = "source"
NUTRIENT_FIELDS = ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g")


def move_to_references(apps, schema_editor):
    Nutrition = apps.get_model("recipes", "Nutrition")
    NutritionReference = apps.get_model("recipes", "NutritionReference")

    for row in Nutrition.objects.filter(method=PRINTED_METHOD):
        NutritionReference.objects.update_or_create(
            recipe_id=row.recipe_id,
            defaults={field: getattr(row, field) or 0.0 for field in NUTRIENT_FIELDS},
        )
        row.delete()


def move_back_to_nutrition(apps, schema_editor):
    Nutrition = apps.get_model("recipes", "Nutrition")
    NutritionReference = apps.get_model("recipes", "NutritionReference")

    for reference in NutritionReference.objects.all():
        Nutrition.objects.update_or_create(
            recipe_id=reference.recipe_id,
            defaults={
                **{
                    field: getattr(reference, field) or 0.0
                    for field in NUTRIENT_FIELDS
                },
                "method": PRINTED_METHOD,
            },
        )
        reference.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("recipes", "0013_nutritionreference_nutrition_confidence_and_more"),
    ]

    operations = [
        migrations.RunPython(move_to_references, move_back_to_nutrition),
    ]
