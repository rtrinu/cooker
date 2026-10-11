import json
import zipfile
from collections import namedtuple
from datetime import date
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from .management.commands.import_usda import (
    NAME_MAX_LENGTH,
    USDADataError,
    disambiguated_name,
    name_is_claimed,
    preview_name,
    resolve_ingredient,
    sync_measures,
)
from .management.commands.usda_bulk import (
    iter_foods,
    open_dataset,
    parse_bulk_food,
    parse_portions,
)
from .models import (
    Ingredient,
    IngredientMeasure,
    IngredientNutrition,
    Nutrition,
    Recipe,
    RecipeIngredient,
)
from .nutrition import compute, scale_nutrients
from .pdf import extract_recipe, split_quantity
from .units import grams_for, normalize_measure, parse_amount

Measure = namedtuple("Measure", ("measure", "amount", "gram_weight"))


class NutritionFactoryMixin:
    """Creates nutrition rows against ``self.ingredient`` unless one is passed."""

    def create_nutrition(self, ingredient=None, **overrides):
        values = {
            "kcal": 389,
            "protein_g": 16.9,
            "carbs_g": 66.3,
            "fat_g": 6.9,
            "serving_size_g": 100,
            "source": "USDA",
            "source_id": "123",
        }
        values["ingredient"] = ingredient or self.ingredient
        values.update(overrides)
        return IngredientNutrition.objects.create(**values)


class DisambiguatedNameTests(NutritionFactoryMixin, TestCase):
    def claimed(self, name="Kale, raw"):
        ingredient = Ingredient.objects.create(name=name)
        self.create_nutrition(ingredient=ingredient)
        return ingredient

    def test_suffixes_the_fdc_id(self):
        self.assertEqual(
            disambiguated_name("Hummus, commercial", 174289),
            "Hummus, commercial (FDC 174289)",
        )

    def test_truncates_to_the_name_limit(self):
        name = disambiguated_name("x" * NAME_MAX_LENGTH, 174289)

        self.assertEqual(len(name), NAME_MAX_LENGTH)
        self.assertTrue(name.endswith("(FDC 174289)"))

    def test_truncation_does_not_leave_a_trailing_space(self):
        name = disambiguated_name("y" * (NAME_MAX_LENGTH - 10) + "  ", 1)

        self.assertFalse(name[: -len(" (FDC 1)")].endswith(" "))

    def test_name_is_claimed_only_once_nutrition_exists(self):
        ingredient = Ingredient.objects.create(name="Kale, raw")

        self.assertFalse(name_is_claimed("Kale, raw"))

        self.create_nutrition(ingredient=ingredient)
        self.assertTrue(name_is_claimed("Kale, raw"))

    def test_resolve_ingredient_creates_a_new_name(self):
        self.assertEqual(resolve_ingredient("Kale, raw", 1).name, "Kale, raw")

    def test_resolve_ingredient_reuses_a_nutrition_free_ingredient(self):
        existing = Ingredient.objects.create(name="Kale, raw")

        self.assertEqual(resolve_ingredient("Kale, raw", 1), existing)

    def test_resolve_ingredient_suffixes_a_claimed_name(self):
        self.claimed()

        self.assertEqual(resolve_ingredient("Kale, raw", 2).name, "Kale, raw (FDC 2)")

    def test_resolve_ingredient_is_stable_across_repeated_calls(self):
        self.claimed()
        resolve_ingredient("Kale, raw", 2)

        self.assertEqual(resolve_ingredient("Kale, raw", 2).name, "Kale, raw (FDC 2)")
        self.assertEqual(Ingredient.objects.count(), 2)

    def test_preview_name_matches_what_a_write_would_store(self):
        self.assertEqual(preview_name("Kale, raw", 1), "Kale, raw")
        self.assertEqual(
            preview_name("Kale, raw", 1), resolve_ingredient("Kale, raw", 1).name
        )

    def test_preview_name_sees_a_claimed_name(self):
        self.claimed()

        self.assertEqual(preview_name("Kale, raw", 2), "Kale, raw (FDC 2)")

    def test_preview_name_accounts_for_names_planned_this_run(self):
        self.assertEqual(preview_name("Kale, raw", 2), "Kale, raw")
        self.assertEqual(
            preview_name("Kale, raw", 2, {"Kale, raw"}), "Kale, raw (FDC 2)"
        )


class IngredientNutritionTests(NutritionFactoryMixin, TestCase):
    def setUp(self):
        self.ingredient = Ingredient.objects.create(name="Oats")

    def test_nutrition_is_available_from_ingredient(self):
        nutrition = self.create_nutrition()

        self.assertEqual(self.ingredient.nutrition.get(), nutrition)

    def test_duplicate_source_record_is_rejected(self):
        self.create_nutrition()

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_nutrition()

    def test_negative_nutrition_is_rejected_by_model_validation(self):
        nutrition = IngredientNutrition(
            ingredient=self.ingredient,
            kcal=-1,
            protein_g=1,
            carbs_g=1,
            fat_g=1,
            serving_size_g=100,
            source="USDA",
            source_id="123",
        )

        with self.assertRaises(ValidationError):
            nutrition.full_clean()

    def test_invalid_nutrition_is_rejected_by_database_constraint(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_nutrition(serving_size_g=0)


class NormalizeMeasureTests(TestCase):
    def test_reads_the_unit_that_opens_the_label(self):
        self.assertEqual(normalize_measure("cup, chopped"), "cup")
        self.assertEqual(normalize_measure("tbsp"), "tbsp")

    def test_prefers_the_opening_unit_over_a_later_approximation(self):
        self.assertEqual(normalize_measure("oz (approx 2/3 cup)"), "oz")
        self.assertEqual(normalize_measure("cup (8 fl oz)"), "cup")

    def test_reads_a_two_word_unit(self):
        self.assertEqual(normalize_measure("fluid ounce"), "fl oz")
        self.assertEqual(normalize_measure("fl oz"), "fl oz")

    def test_normalizes_plural_spellings(self):
        self.assertEqual(normalize_measure("tablespoons"), "tbsp")
        self.assertEqual(normalize_measure("slices"), "slice")

    def test_drops_a_reference_amount(self):
        self.assertIsNone(normalize_measure("RACC"))

    def test_drops_a_label_that_opens_with_no_unit(self):
        self.assertIsNone(normalize_measure("unit (yield from 1 lb chicken)"))
        self.assertIsNone(normalize_measure("breast, bone and skin removed"))

    def test_drops_a_label_describing_a_portion_rather_than_a_measure(self):
        # The dataset reports amount=0.12 for this portion, not 0.5, so reading
        # it as half a cup would overstate the weight tenfold.
        self.assertIsNone(normalize_measure("serving 1/2 cup"))

    def test_does_not_strip_a_leading_quantity(self):
        # Only a unit opening the label can be trusted to describe ``amount``.
        self.assertIsNone(normalize_measure("1/2 cup"))
        self.assertIsNone(normalize_measure("5.3 oz"))

    def test_handles_blank_labels(self):
        self.assertIsNone(normalize_measure(""))
        self.assertIsNone(normalize_measure(None))


class ParsePortionsTests(TestCase):
    def portions(self, **overrides):
        portion = {
            "amount": 1.0,
            "gramWeight": 152.0,
            "sequenceNumber": 2,
            "modifier": "",
            "portionDescription": "",
            "measureUnit": {"id": 1000, "name": "cup", "abbreviation": "cup"},
        }
        portion.update(overrides)
        return {"foodPortions": [portion]}

    def test_reads_the_unit_from_the_measure_unit(self):
        record = parse_portions(self.portions())[0]

        self.assertEqual(record["measure"], "cup")
        self.assertEqual(record["source_label"], "cup")
        self.assertEqual(record["amount"], 1.0)
        self.assertEqual(record["gram_weight"], 152.0)
        self.assertEqual(record["sequence"], 2)

    def test_reads_the_unit_from_the_sr_modifier(self):
        record = parse_portions(
            self.portions(
                modifier="tbsp",
                portionDescription=None,
                measureUnit={"id": 1001, "name": "undetermined", "abbreviation": None},
            )
        )[0]

        self.assertEqual(record["measure"], "tbsp")
        self.assertEqual(record["source_label"], "tbsp")

    def test_reads_the_unit_from_the_portion_description(self):
        record = parse_portions(
            self.portions(modifier=None, portionDescription="1 cup")
        )[0]

        self.assertEqual(record["measure"], "cup")

    def test_drops_the_reference_amount(self):
        portions = self.portions(
            modifier=None,
            portionDescription=None,
            measureUnit={"id": 1121, "name": "RACC", "abbreviation": "RACC"},
        )

        self.assertEqual(parse_portions(portions), [])

    def test_drops_a_portion_without_a_gram_weight(self):
        self.assertEqual(parse_portions(self.portions(gramWeight=None)), [])

    def test_drops_a_portion_without_a_positive_amount(self):
        self.assertEqual(parse_portions(self.portions(amount=0.0)), [])
        self.assertEqual(parse_portions(self.portions(amount=-2.0)), [])

    def test_drops_a_portion_with_a_non_numeric_amount(self):
        self.assertEqual(parse_portions(self.portions(amount=None)), [])
        self.assertEqual(parse_portions(self.portions(amount="1")), [])

    def test_keeps_several_measures_for_one_food(self):
        food = {
            "foodPortions": [
                self.portions()["foodPortions"][0],
                self.portions(amount=2.0, gramWeight=33.9, sequenceNumber=1)[
                    "foodPortions"
                ][0],
            ]
        }

        records = parse_portions(food)

        self.assertEqual([record["measure"] for record in records], ["cup", "cup"])
        self.assertEqual([record["sequence"] for record in records], [2, 1])

    def test_falls_through_to_the_measure_unit_when_the_modifier_is_no_unit(self):
        record = parse_portions(self.portions(modifier="shredded"))[0]

        self.assertEqual(record["measure"], "cup")
        self.assertEqual(record["source_label"], "cup")

    def test_returns_no_measures_for_a_food_without_portions(self):
        self.assertEqual(parse_portions({"description": "Rolled oats"}), [])
        self.assertEqual(parse_portions({"foodPortions": None}), [])

    def test_ignores_entries_that_are_not_objects(self):
        self.assertEqual(parse_portions({"foodPortions": [None, 5, "x"]}), [])

    def test_truncates_a_long_source_label(self):
        label = "piece, cooked, excluding refuse " + "padding " * 20

        record = parse_portions(self.portions(modifier=label))[0]

        self.assertEqual(len(record["source_label"]), 100)

    def test_fills_in_a_missing_sequence(self):
        record = parse_portions(self.portions(sequenceNumber=None))[0]

        self.assertEqual(record["sequence"], 1)

    def test_rejects_a_food_that_is_not_an_object(self):
        with self.assertRaises(USDADataError):
            parse_portions(["not", "a", "food"])

    def test_rejects_a_portion_table_that_is_not_an_array(self):
        with self.assertRaises(USDADataError):
            parse_portions({"foodPortions": {"amount": 1}})


class IngredientMeasureTests(TestCase):
    def setUp(self):
        self.ingredient = Ingredient.objects.create(name="Rolled oats")

    def measure(self, **overrides):
        values = {
            "ingredient": self.ingredient,
            "measure": "cup",
            "source_label": "cup",
            "amount": 1.0,
            "gram_weight": 152.0,
            "sequence": 1,
        }
        values.update(overrides)
        return IngredientMeasure.objects.create(**values)

    def test_str_states_the_conversion(self):
        measure = self.measure()

        self.assertEqual(str(measure), "1 cup = 152 g")

    def test_measures_are_reachable_from_the_ingredient(self):
        measure = self.measure()

        self.assertEqual(self.ingredient.measures.get(), measure)

    def test_rejects_a_non_positive_amount(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.measure(amount=0)

    def test_rejects_a_non_positive_gram_weight(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.measure(gram_weight=0)

    def test_sync_replaces_the_existing_measures(self):
        self.measure(sequence=1, gram_weight=90)
        self.measure(sequence=2, gram_weight=180)

        sync_measures(
            self.ingredient,
            [
                {
                    "measure": "tbsp",
                    "source_label": "tbsp",
                    "amount": 1.0,
                    "gram_weight": 33.9,
                    "sequence": 1,
                }
            ],
        )

        self.assertEqual(self.ingredient.measures.count(), 1)
        measure = self.ingredient.measures.get()
        self.assertEqual(measure.measure, "tbsp")
        self.assertEqual(measure.gram_weight, 33.9)

    def test_sync_can_clear_every_measure(self):
        self.measure()

        sync_measures(self.ingredient, [])

        self.assertEqual(self.ingredient.measures.count(), 0)


class ParseAmountTests(TestCase):
    def test_reads_a_mixed_number(self):
        self.assertEqual(parse_amount("1 1/2 cups rolled oats"), (1.5, "cup", "rolled oats"))

    def test_reads_a_plain_fraction(self):
        self.assertEqual(parse_amount("1/2 cup milk"), (0.5, "cup", "milk"))

    def test_reads_an_integer(self):
        self.assertEqual(parse_amount("2 tbsp butter"), (2, "tbsp", "butter"))

    def test_reads_a_decimal(self):
        self.assertEqual(parse_amount("0.75 cup flour"), (0.75, "cup", "flour"))

    def test_reads_unicode_fractions(self):
        self.assertEqual(parse_amount("½ cup blueberries"), (0.5, "cup", "blueberries"))
        self.assertEqual(parse_amount("1½ cups milk"), (1.5, "cup", "milk"))
        self.assertEqual(parse_amount("1 ⅓ cups oats"), (1 + 1 / 3, "cup", "oats"))

    def test_reads_a_count_word(self):
        self.assertEqual(parse_amount("3 cloves garlic"), (3, "clove", "garlic"))

    def test_reads_a_mass_word(self):
        self.assertEqual(parse_amount("1 lb chicken"), (1, "lb", "chicken"))

    def test_drops_a_connecting_of(self):
        self.assertEqual(parse_amount("1 cup of flour"), (1, "cup", "flour"))

    def test_returns_none_for_a_line_without_a_number(self):
        self.assertEqual(parse_amount("salt to taste"), (None, None, "salt to taste"))

    def test_returns_none_for_an_empty_line(self):
        self.assertEqual(parse_amount(""), (None, None, ""))

    def test_leaves_no_remainder_for_a_bare_amount(self):
        self.assertEqual(parse_amount("2"), (2, None, ""))


class GramsForTests(TestCase):
    def test_exact_measure_match(self):
        measures = [Measure("cup", 1.0, 152.0)]

        self.assertEqual(grams_for(measures, "cup", 2), 304.0)

    def test_exact_measure_with_a_multi_unit_amount(self):
        measures = [Measure("tomato", 5.0, 49.7)]

        self.assertAlmostEqual(grams_for(measures, "tomato", 3), 29.82)

    def test_count_word_but_not_the_exact_measure(self):
        measures = [Measure("cup", 1.0, 152.0)]

        self.assertIsNone(grams_for(measures, "clove", 2))

    def test_mass_does_not_need_a_measure(self):
        self.assertEqual(grams_for([], "g", 225), 225.0)
        self.assertAlmostEqual(grams_for([], "oz", 1), 28.3495)

    def test_volume_converts_through_any_volume_measure(self):
        measures = [Measure("tbsp", 1.0, 15.0)]

        self.assertAlmostEqual(grams_for(measures, "cup", 1), 240.0, places=1)

    def test_volume_does_not_convert_without_a_measure(self):
        self.assertIsNone(grams_for([], "cup", 1))

    def test_volume_never_converts_through_a_mass_measure(self):
        measures = [Measure("g", 100.0, 100.0)]

        self.assertIsNone(grams_for(measures, "cup", 1))

    def test_an_unknown_unit_does_not_convert(self):
        self.assertIsNone(grams_for([], "pinch", 1))

    def test_a_missing_unit_does_not_convert(self):
        self.assertIsNone(grams_for([], None, 2))

    def test_a_non_positive_amount_does_not_convert(self):
        measures = [Measure("cup", 1.0, 152.0)]

        self.assertIsNone(grams_for(measures, "cup", 0))
        self.assertIsNone(grams_for(measures, "cup", -1))
        self.assertIsNone(grams_for(measures, "cup", None))


class ScaleNutrientsTests(TestCase):
    def test_scales_each_nutrient_by_grams(self):
        nutrition = IngredientNutrition(
            kcal=400, protein_g=10, carbs_g=50, fat_g=5, fiber_g=20,
            serving_size_g=100,
        )

        totals = scale_nutrients(nutrition, 50)

        self.assertEqual(totals["kcal"], 200)
        self.assertEqual(totals["protein_g"], 5)
        self.assertEqual(totals["carbs_g"], 25)
        self.assertEqual(totals["fat_g"], 2.5)
        self.assertEqual(totals["fiber_g"], 10)

    def test_null_nutrients_scale_to_the_value_that_is_known(self):
        nutrition = IngredientNutrition(
            kcal=400, protein_g=None, carbs_g=50, fat_g=None, fiber_g=20,
            serving_size_g=100,
        )

        totals = scale_nutrients(nutrition, 50)

        self.assertEqual(totals["kcal"], 200)
        self.assertEqual(totals["protein_g"], 0)
        self.assertEqual(totals["fiber_g"], 10)


class ComputeNutritionTests(TestCase):
    def setUp(self):
        self.oats = Ingredient.objects.create(name="Rolled oats")
        IngredientMeasure.objects.create(
            ingredient=self.oats, measure="cup", source_label="cup",
            amount=1.0, gram_weight=90.0, sequence=1,
        )
        IngredientNutrition.objects.create(
            ingredient=self.oats, kcal=389, protein_g=16.9, carbs_g=66.3,
            fat_g=6.9, fiber_g=10.6, serving_size_g=100,
            source="USDA", source_id="1",
        )
        self.salt = Ingredient.objects.create(name="Salt")
        IngredientNutrition.objects.create(
            ingredient=self.salt, kcal=0, protein_g=0, carbs_g=0,
            fat_g=0, fiber_g=0, serving_size_g=100,
            source="USDA", source_id="2",
        )

    def lines(self, *pairs):
        ingredients = {"Rolled oats": self.oats, "Salt": self.salt}
        return [(ingredients[name], quantity) for name, quantity in pairs]

    def test_sums_each_line_and_divides_by_servings(self):
        result = compute(self.lines(("Rolled oats", "2 cups")), servings=4)

        self.assertEqual(result.lines_used, 1)
        self.assertEqual(result.lines_total, 1)
        self.assertEqual(result.unresolved, [])
        # 180 g of oats at 389 kcal / 100 g, over 4 servings
        self.assertAlmostEqual(result.totals["kcal"], 700.2)
        self.assertAlmostEqual(result.per_serving["kcal"], 700.2 / 4)
        self.assertAlmostEqual(result.per_serving["fiber_g"], 19.08 / 4)

    def test_a_line_with_no_measure_is_reported(self):
        # Salt has nutrition but no household measures, so "1 pinch" cannot
        # become a mass even though its unit table is complete.
        result = compute(self.lines(("Salt", "1 pinch")), servings=2)

        self.assertEqual(result.lines_used, 0)
        self.assertEqual(result.per_serving["kcal"], 0)
        self.assertIn(
            {"ingredient": "Salt", "quantity": "1 pinch", "reason": "no unit measure"},
            result.unresolved,
        )

    def test_a_line_without_a_quantity_is_reported(self):
        result = compute(self.lines(("Salt", "to taste")), servings=2)

        self.assertIn(
            {"ingredient": "Salt", "quantity": "to taste", "reason": "no amount"},
            result.unresolved,
        )

    def test_an_ingredient_without_nutrition_is_reported(self):
        pepper = Ingredient.objects.create(name="Black pepper")
        IngredientMeasure.objects.create(
            ingredient=pepper, measure="tsp", source_label="tsp",
            amount=1.0, gram_weight=2.3, sequence=1,
        )

        result = compute([(pepper, "1 tsp")], servings=2)

        self.assertEqual(result.lines_used, 0)
        self.assertEqual(result.unresolved[0]["reason"], "no nutrition")

    def test_a_mix_of_resolved_and_unresolved_lines(self):
        result = compute(
            self.lines(("Rolled oats", "1 cup"), ("Salt", "to taste")),
            servings=2,
        )

        self.assertEqual(result.lines_used, 1)
        self.assertEqual(result.lines_total, 2)
        self.assertAlmostEqual(result.totals["protein_g"], 15.21)
        self.assertEqual(len(result.unresolved), 1)

    def test_servings_of_one_makes_totals_equal_to_per_serving(self):
        result = compute(self.lines(("Rolled oats", "1 cup")), servings=1)

        self.assertAlmostEqual(result.per_serving["kcal"], result.totals["kcal"])


class RecipeModelTests(TestCase):
    def test_slug_is_the_idempotency_key_and_may_be_blank(self):
        first = Recipe.objects.create(slug="bean-burrito-bowl")
        another = Recipe.objects.create(slug=None, name="Homemade")
        duplicate_raise = lambda: Recipe.objects.create(slug="bean-burrito-bowl")

        self.assertIsNotNone(first.slug)
        self.assertIsNone(another.slug)
        with self.assertRaises(IntegrityError), transaction.atomic():
            duplicate_raise()

    def test_preparation_times_are_optional(self):
        recipe = Recipe.objects.create(name="Hasty broth")

        self.assertIsNone(recipe.prep_mins)
        self.assertIsNone(recipe.cook_mins)

    def test_ingredients_are_ordered_by_position(self):
        recipe = Recipe.objects.create(name="Pasta")
        oats = Ingredient.objects.create(name="Oats")
        salt = Ingredient.objects.create(name="Salt")
        RecipeIngredient.objects.create(recipe=recipe, ingredient=salt, quantity_text="1 pinch", position=2)
        RecipeIngredient.objects.create(recipe=recipe, ingredient=oats, quantity_text="2 cups", position=1)

        self.assertEqual(
            [row.ingredient.name for row in recipe.ingredients.all()],
            ["Oats", "Salt"],
        )

    def test_nutrition_method_defaults_to_source(self):
        recipe = Recipe.objects.create(name="Soup")

        nutrition = Nutrition.objects.create(
            recipe=recipe, kcal=1, protein_g=1, carbs_g=1, fat_g=1, fiber_g=0,
        )

        self.assertEqual(nutrition.method, "source")


@override_settings(USDA_API_KEY="test-api-key")
class USDAImportTests(TestCase):
    def food_payload(self, fdc_id=123, kcal=389):
        return {
            "fdcId": fdc_id,
            "description": "Rolled oats",
            "dataType": "Foundation",
            "foodNutrients": [
                {
                    "nutrient": {"id": 2048, "unitName": "kcal"},
                    "amount": kcal,
                },
                {
                    "nutrient": {"id": 1003, "unitName": "g"},
                    "amount": 16.9,
                },
                {
                    "nutrient": {"id": 1005, "unitName": "g"},
                    "amount": 66.3,
                },
                {
                    "nutrient": {"id": 1004, "unitName": "g"},
                    "amount": 6.9,
                },
                {
                    "nutrient": {"id": 1079, "unitName": "g"},
                    "amount": 10.6,
                },
            ],
        }

    @patch("recipes.management.commands.import_usda.USDAClient.get_food")
    def test_imports_foundation_food(self, get_food):
        get_food.return_value = self.food_payload()
        output = StringIO()

        call_command("import_usda", "--fdc-id", "123", stdout=output)

        ingredient = Ingredient.objects.get()
        nutrition = ingredient.nutrition.get()
        self.assertEqual(ingredient.name, "Rolled oats")
        self.assertEqual(nutrition.source, "USDA FoodData Central")
        self.assertEqual(nutrition.source_id, "123")
        self.assertEqual(nutrition.serving_size_g, 100)
        self.assertEqual(nutrition.kcal, 389)
        self.assertIn("created=1", output.getvalue())
        get_food.assert_called_once_with(123)

    @patch("recipes.management.commands.import_usda.USDAClient.get_food")
    def test_dry_run_does_not_write(self, get_food):
        get_food.return_value = self.food_payload()
        output = StringIO()

        call_command("import_usda", "--fdc-id", "123", "--dry-run", stdout=output)

        self.assertFalse(IngredientNutrition.objects.exists())
        self.assertIn("would create", output.getvalue())

    @patch("recipes.management.commands.import_usda.USDAClient.get_food")
    def test_reimport_updates_existing_nutrition(self, get_food):
        get_food.return_value = self.food_payload()
        call_command("import_usda", "--fdc-id", "123", stdout=StringIO())
        get_food.return_value = self.food_payload(kcal=400)
        output = StringIO()

        call_command("import_usda", "--fdc-id", "123", stdout=output)

        self.assertEqual(IngredientNutrition.objects.count(), 1)
        self.assertEqual(IngredientNutrition.objects.get().kcal, 400)
        self.assertIn("updated=1", output.getvalue())

    @patch("recipes.management.commands.import_usda.USDAClient.get_food")
    def test_missing_nutrient_is_reported_without_writing(self, get_food):
        payload = self.food_payload()
        payload["foodNutrients"] = [
            entry
            for entry in payload["foodNutrients"]
            if entry["nutrient"]["id"] != 1079
        ]
        get_food.return_value = payload
        errors = StringIO()

        with self.assertRaises(CommandError):
            call_command(
                "import_usda",
                "--fdc-id",
                "123",
                stdout=StringIO(),
                stderr=errors,
            )

        self.assertIn("missing nutrients: fiber_g", errors.getvalue())
        self.assertFalse(IngredientNutrition.objects.exists())

@override_settings(USDA_API_KEY="test-api-key")
class USDAJSONTests(TestCase):
    def food_payload(self, fdc_id=123, description="Rolled oats", kcal=389):
        return {
            "fdcId": fdc_id,
            "description": description,
            "dataType": "Foundation",
            "foodNutrients": [
                {"nutrient": {"id": 2048, "unitName": "kcal"}, "amount": kcal},
                {"nutrient": {"id": 1003, "unitName": "g"}, "amount": 16.9},
                {"nutrient": {"id": 1005, "unitName": "g"}, "amount": 66.3},
                {"nutrient": {"id": 1004, "unitName": "g"}, "amount": 6.9},
                {"nutrient": {"id": 1079, "unitName": "g"}, "amount": 10.6},
            ],
        }

    def snapshot(self, fdc_id=123, description="Rolled oats", kcal=389):
        return {
            "schema_version": 1,
            "source": "USDA FoodData Central",
            "data_type": "Foundation",
            "basis": {"amount": 100, "unit": "g"},
            "retrieved_at": "2026-01-01T00:00:00Z",
            "foods": [
                {
                    "fdc_id": fdc_id,
                    "description": description,
                    "data_type": "Foundation",
                    "nutrients": {
                        "kcal": kcal,
                        "protein_g": 16.9,
                        "carbs_g": 66.3,
                        "fat_g": 6.9,
                        "fiber_g": 10.6,
                    },
                }
            ],
        }

    def write_snapshot(self, path, snapshot=None):
        path.write_text(
            json.dumps(snapshot or self.snapshot()), encoding="utf-8"
        )

    @patch("recipes.management.commands.fetch_usda_json.USDAClient.get_food")
    def test_fetches_json_snapshot(self, get_food):
        get_food.return_value = self.food_payload()
        output = StringIO()

        with TemporaryDirectory() as directory:
            path = Path(directory) / "nutrition.json"
            call_command(
                "fetch_usda_json",
                "--fdc-id",
                "123",
                "--output",
                str(path),
                stdout=output,
            )
            snapshot = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(snapshot["schema_version"], 1)
        self.assertEqual(snapshot["basis"], {"amount": 100, "unit": "g"})
        self.assertEqual(snapshot["foods"][0]["fdc_id"], 123)
        self.assertEqual(snapshot["foods"][0]["nutrients"]["kcal"], 389)
        self.assertIn("created=1", output.getvalue())
        get_food.assert_called_once_with(123)

    @patch("recipes.management.commands.fetch_usda_json.USDAClient.wait_for_rate_limit")
    @patch("recipes.management.commands.fetch_usda_json.USDAClient.get_food")
    def test_fetch_resumes_and_checks_rate_limit(self, get_food, wait_for_rate_limit):
        get_food.side_effect = [
            self.food_payload(123),
            self.food_payload(124, "Rolled oats, salted"),
        ]

        with TemporaryDirectory() as directory:
            path = Path(directory) / "nutrition.json"
            call_command(
                "fetch_usda_json",
                "--fdc-id",
                "123",
                "--fdc-id",
                "124",
                "--output",
                str(path),
                stdout=StringIO(),
            )
            wait_for_rate_limit.assert_called_once_with(1)
            get_food.reset_mock()
            wait_for_rate_limit.reset_mock()

            call_command(
                "fetch_usda_json",
                "--fdc-id",
                "123",
                "--fdc-id",
                "124",
                "--output",
                str(path),
                stdout=StringIO(),
            )

        get_food.assert_not_called()
        wait_for_rate_limit.assert_not_called()

    def test_rate_limit_wait_uses_reset_header(self):
        from recipes.management.commands.import_usda import USDAClient

        sleeps = []
        client = USDAClient(
            "test-api-key", sleeper=sleeps.append, clock=lambda: 100
        )
        client.last_headers = {
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": "105",
        }

        client.wait_for_rate_limit(1)

        self.assertEqual(sleeps, [5])

    def test_imports_json_snapshot(self):
        output = StringIO()

        with TemporaryDirectory() as directory:
            path = Path(directory) / "nutrition.json"
            self.write_snapshot(path)
            call_command("import_usda_json", "--file", str(path), stdout=output)

        nutrition = IngredientNutrition.objects.get()
        self.assertEqual(nutrition.source_id, "123")
        self.assertEqual(nutrition.kcal, 389)
        self.assertIn("created=1", output.getvalue())

    def test_json_snapshot_dry_run_does_not_write(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "nutrition.json"
            self.write_snapshot(path)
            output = StringIO()

            call_command(
                "import_usda_json", "--file", str(path), "--dry-run", stdout=output
            )

        self.assertFalse(IngredientNutrition.objects.exists())
        self.assertIn("would create", output.getvalue())

    def test_invalid_json_snapshot_is_rejected_before_writing(self):
        snapshot = self.snapshot()
        snapshot["foods"][0]["nutrients"]["fiber_g"] = -1

        with TemporaryDirectory() as directory:
            path = Path(directory) / "nutrition.json"
            self.write_snapshot(path, snapshot)
            with self.assertRaises(CommandError):
                call_command("import_usda_json", "--file", str(path))

        self.assertFalse(IngredientNutrition.objects.exists())

    def test_json_reimport_updates_existing_nutrition(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "nutrition.json"
            self.write_snapshot(path)
            call_command("import_usda_json", "--file", str(path), stdout=StringIO())
            self.write_snapshot(path, self.snapshot(kcal=400))
            output = StringIO()

            call_command("import_usda_json", "--file", str(path), stdout=output)

        self.assertEqual(IngredientNutrition.objects.count(), 1)
        self.assertEqual(IngredientNutrition.objects.get().kcal, 400)
        self.assertIn("updated=1", output.getvalue())

NUTRIENTS = {
    2048: ("Energy", "kcal", 389),
    1003: ("Protein", "g", 16.9),
    1005: ("Carbohydrate, by difference", "g", 66.3),
    1004: ("Total lipid (fat)", "g", 6.9),
    1079: ("Fiber, total dietary", "g", 10.6),
}
DATASET_NAME = "FoundationFoods"


class BulkDatasetMixin:
    def setUp(self):
        super().setUp()
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.directory_path = Path(self.directory.name)
        self.dataset_path = self.directory_path / "dataset.json"

    def food(
        self,
        fdc_id=123,
        description="Rolled oats",
        data_type="Foundation",
        category="Nut and Seed Products",
        publication_date="4/1/2019",
        omit_nutrients=(),
        energy_unit="kcal",
        amounts=None,
        extra_nutrients=None,
        **overrides,
    ):
        values = dict(NUTRIENTS)
        values.update(extra_nutrients or {})
        for nutrient_id in omit_nutrients:
            values.pop(nutrient_id)
        if energy_unit != "kcal":
            values[2048] = ("Energy", energy_unit, values[2048][2])
        for nutrient_id, amount in (amounts or {}).items():
            name, unit, _ = values[nutrient_id]
            values[nutrient_id] = (name, unit, amount)

        food = {
            "foodClass": "FinalFood",
            "fdcId": fdc_id,
            "description": description,
            "dataType": data_type,
            "publicationDate": publication_date,
            "foodCategory": {"description": category},
            "foodNutrients": [
                {
                    "type": "FoodNutrient",
                    "id": 100000 + nutrient_id,
                    "nutrient": {
                        "type": "Nutrient",
                        "id": nutrient_id,
                        "number": str(nutrient_id),
                        "name": name,
                        "rank": 600,
                        "unitName": unit,
                    },
                    "dataPoints": 5,
                    "amount": amount,
                }
                for nutrient_id, (name, unit, amount) in values.items()
            ],
        }
        food.update(overrides)
        return food

    def write_dataset(self, foods, path=None, name=DATASET_NAME):
        target = path or self.dataset_path
        document = json.dumps(foods, indent=2)
        if name is None:
            target.write_text(document, encoding="utf-8")
        else:
            target.write_text(
                json.dumps({name: foods}, indent=2), encoding="utf-8"
            )
        return target

    def write_archive(self, members, path=None):
        target = path or (self.directory_path / "dataset.zip")
        with zipfile.ZipFile(target, "w") as archive:
            for name, foods in members.items():
                document = json.dumps(foods, indent=2)
                archive.writestr(name, f'{{"{name}": {document}}}')
        return target


class USDABulkParserTests(BulkDatasetMixin, TestCase):
    def parse_dataset(self, foods, chunk_size=None, **kwargs):
        text = json.dumps({DATASET_NAME: foods}, indent=2)
        handle = StringIO(text)
        if chunk_size is not None:
            foods = iter_foods(handle, chunk_size=chunk_size)
        return [parse_bulk_food(food, **kwargs) for food in foods]

    def test_streams_foods_across_chunk_boundaries(self):
        foods = [self.food(fdc_id=index) for index in (123, 124, 125)]

        records = self.parse_dataset(foods, chunk_size=7)

        self.assertEqual([record["fdc_id"] for record in records], [123, 124, 125])

    def test_parses_foundation_food(self):
        record = self.parse_dataset([self.food()])[0]

        self.assertEqual(record["fdc_id"], 123)
        self.assertEqual(record["name"], "Rolled oats")
        self.assertEqual(record["category"], "Nut and Seed Products")
        self.assertEqual(record["publication_date"], date(2019, 4, 1))
        self.assertEqual(record["kcal"], 389)
        self.assertEqual(record["protein_g"], 16.9)
        self.assertEqual(record["carbs_g"], 66.3)
        self.assertEqual(record["fat_g"], 6.9)
        self.assertEqual(record["fiber_g"], 10.6)

    def test_parses_sr_legacy_food(self):
        record = self.parse_dataset([self.food(data_type="SR Legacy")])[0]

        self.assertEqual(record["fdc_id"], 123)

    def test_parses_the_measure_table(self):
        portion = {
            "amount": 1.0,
            "gramWeight": 152.0,
            "sequenceNumber": 1,
            "modifier": "cup",
            "measureUnit": {"id": 1, "name": "undetermined", "abbreviation": None},
        }

        record = self.parse_dataset([self.food(foodPortions=[portion])])[0]

        self.assertEqual(len(record["portions"]), 1)
        self.assertEqual(record["portions"][0]["measure"], "cup")
        self.assertEqual(record["portions"][0]["gram_weight"], 152.0)

    def test_reports_no_measures_for_a_food_without_a_portion_table(self):
        record = self.parse_dataset([self.food(foodPortions=None)])[0]

        self.assertEqual(record["portions"], [])

    def test_drops_portions_that_state_no_conversion(self):
        portions = [
            {"amount": 1.0, "gramWeight": 30.0, "modifier": "RACC"},
            {"amount": 1.0, "gramWeight": 30.0, "modifier": ""},
            {"amount": 0.0, "gramWeight": 30.0, "modifier": "cup"},
            {"amount": 1.0, "modifier": "cup"},
        ]

        record = self.parse_dataset([self.food(foodPortions=portions)])[0]

        self.assertEqual(record["portions"], [])

    def test_rejects_a_portion_table_that_is_not_an_array(self):
        with self.assertRaises(USDADataError):
            self.parse_dataset([self.food(foodPortions="cup")])

    def test_parses_iso_publication_date(self):
        record = self.parse_dataset(
            [self.food(publication_date="2026-04-30")]
        )[0]

        self.assertEqual(record["publication_date"], date(2026, 4, 30))

    def test_parses_food_without_optional_metadata(self):
        food = self.food()
        del food["foodCategory"]
        del food["publicationDate"]

        record = self.parse_dataset([food])[0]

        self.assertIsNone(record["category"])
        self.assertIsNone(record["publication_date"])

    def test_category_is_truncated_to_the_model_limit(self):
        record = self.parse_dataset([self.food(category="C" * 60)])[0]

        self.assertEqual(len(record["category"]), 50)

    def test_missing_nutrients_are_null_by_default(self):
        record = self.parse_dataset([self.food(omit_nutrients=(1079, 1004))])[0]

        self.assertIsNone(record["fiber_g"])
        self.assertIsNone(record["fat_g"])
        self.assertEqual(record["kcal"], 389)

    def test_require_all_nutrients_rejects_partial_foods(self):
        with self.assertRaisesMessage(
            USDADataError, "missing nutrients: fiber_g"
        ):
            self.parse_dataset(
                [self.food(omit_nutrients=(1079,))],
                require_all_nutrients=True,
            )

    def test_falls_back_to_alternative_fiber_nutrient(self):
        record = self.parse_dataset(
            [
                self.food(
                    omit_nutrients=(1079,),
                    extra_nutrients={2033: ("Total dietary fiber", "g", 6.1)},
                )
            ]
        )[0]

        self.assertEqual(record["fiber_g"], 6.1)

    def test_falls_back_to_general_factors_energy(self):
        record = self.parse_dataset(
            [
                self.food(
                    omit_nutrients=(2048,),
                    extra_nutrients={
                        2047: ("Energy (Atwater General Factors)", "kcal", 380)
                    },
                )
            ]
        )[0]

        self.assertEqual(record["kcal"], 380)

    def test_food_without_any_tracked_nutrient_is_ignored(self):
        food = self.food(omit_nutrients=tuple(NUTRIENTS))

        self.assertIsNone(parse_bulk_food(food))

    def test_require_all_nutrients_rejects_food_without_any(self):
        with self.assertRaisesMessage(
            USDADataError, "missing nutrients: kcal, protein_g, carbs_g, fat_g, fiber_g"
        ):
            parse_bulk_food(
                self.food(omit_nutrients=tuple(NUTRIENTS)),
                require_all_nutrients=True,
            )

    def test_unusable_unit_becomes_a_null_value(self):
        record = self.parse_dataset([self.food(energy_unit="kJ")])[0]

        self.assertIsNone(record["kcal"])

    def test_reads_empty_dataset(self):
        self.assertEqual(self.parse_dataset([]), [])

    def test_yields_null_entries(self):
        handle = StringIO(json.dumps({DATASET_NAME: [None, self.food(), None]}))

        foods = list(iter_foods(handle))

        self.assertEqual([food is None for food in foods], [True, False, True])

    def test_reads_bare_array(self):
        handle = StringIO(json.dumps([self.food()]))

        self.assertEqual(len(list(iter_foods(handle))), 1)

    def test_reads_any_dataset_name(self):
        handle = StringIO(json.dumps({"SRLegacyFoods": [self.food()]}))

        self.assertEqual(len(list(iter_foods(handle))), 1)

    def test_rejects_truncated_dataset(self):
        text = json.dumps({DATASET_NAME: [self.food()]})

        with self.assertRaisesMessage(
            USDADataError, "truncated"
        ):
            list(iter_foods(StringIO(text[: len(text) // 2]), chunk_size=11))

    def test_rejects_snapshot_document(self):
        snapshot = json.dumps({"schema_version": 1, "foods": []})

        with self.assertRaisesMessage(
            USDADataError, "import_usda_json"
        ):
            list(iter_foods(StringIO(snapshot)))

    def test_rejects_dataset_without_an_array(self):
        with self.assertRaisesMessage(
            USDADataError, "must hold a JSON array of foods"
        ):
            list(iter_foods(StringIO('{"FoundationFoods": 12}')))

    def test_rejects_empty_dataset_file(self):
        with self.assertRaisesMessage(
            USDADataError, "expected a JSON array of foods"
        ):
            list(iter_foods(StringIO("   ")))

    def test_rejects_invalid_chunk_size(self):
        with self.assertRaisesMessage(
            USDADataError, "chunk size must be positive"
        ):
            list(iter_foods(StringIO("[]"), chunk_size=0))

    def test_rejects_non_object_entry(self):
        with self.assertRaisesMessage(
            USDADataError, "must be a JSON object"
        ):
            parse_bulk_food("Rolled oats")

    def test_rejects_branded_food(self):
        with self.assertRaisesMessage(
            USDADataError, "unsupported dataType Branded"
        ):
            parse_bulk_food(self.food(data_type="Branded"))

    def test_rejects_missing_data_type(self):
        food = self.food()
        del food["dataType"]

        with self.assertRaisesMessage(
            USDADataError, "unsupported dataType missing"
        ):
            parse_bulk_food(food)

    def test_rejects_description_over_the_name_limit(self):
        with self.assertRaisesMessage(
            USDADataError, "exceeds the ingredient name limit"
        ):
            parse_bulk_food(self.food(description="O" * 256))

    def test_rejects_blank_description(self):
        with self.assertRaisesMessage(
            USDADataError, "description is required"
        ):
            parse_bulk_food(self.food(description="   "))

    def test_rejects_invalid_fdc_id(self):
        with self.assertRaisesMessage(
            USDADataError, "missing or invalid fdcId"
        ):
            parse_bulk_food(self.food(fdc_id=None))

    def test_opens_plain_json_dataset(self):
        self.write_dataset([self.food()])

        with open_dataset(self.dataset_path) as dataset:
            foods = list(iter_foods(dataset))

        self.assertEqual(foods[0]["fdcId"], 123)

    def test_opens_zip_member(self):
        path = self.write_archive({"FoodData.json": [self.food()]})

        with open_dataset(path) as dataset:
            foods = list(iter_foods(dataset))

        self.assertEqual(foods[0]["fdcId"], 123)

    def test_zip_member_can_be_selected(self):
        path = self.write_archive({"foundation.json": [self.food()]})

        with open_dataset(path, "foundation.json") as dataset:
            foods = list(iter_foods(dataset))

        self.assertEqual(len(foods), 1)

    def test_zip_with_several_datasets_requires_member(self):
        path = self.write_archive(
            {"foundation.json": [self.food()], "sr.json": [self.food(124)]}
        )

        with self.assertRaisesMessage(
            USDADataError, "pick one with --member"
        ):
            open_dataset(path)

    def test_zip_without_json_member_is_rejected(self):
        path = self.write_archive({"readme.txt": []})

        with self.assertRaisesMessage(
            USDADataError, "has no JSON dataset member"
        ):
            open_dataset(path)

    def test_zip_reports_unknown_member(self):
        path = self.write_archive({"foundation.json": [self.food()]})

        with self.assertRaisesMessage(
            USDADataError, "has no member named missing.json"
        ):
            open_dataset(path, "missing.json")

    def test_reports_corrupt_archive(self):
        path = self.directory_path / "dataset.zip"
        path.write_bytes(b"not a zip file")

        with self.assertRaisesMessage(
            USDADataError, "could not open"
        ):
            open_dataset(path)

    def test_reports_missing_file(self):
        with self.assertRaisesMessage(
            USDADataError, "does not exist"
        ):
            open_dataset(self.directory_path / "missing.json")


class USDABulkImportTests(BulkDatasetMixin, TestCase):
    def import_dataset(self, foods, *args, stdout=None, stderr=None, **kwargs):
        self.write_dataset(foods)
        call_command(
            "import_usda_bulk",
            "--file",
            str(self.dataset_path),
            *args,
            stdout=stdout or StringIO(),
            stderr=stderr or StringIO(),
            **kwargs,
        )

    def portion(self, **overrides):
        values = {
            "amount": 1.0,
            "gramWeight": 152.0,
            "sequenceNumber": 1,
            "modifier": "cup",
            "measureUnit": {"id": 1, "name": "undetermined", "abbreviation": None},
        }
        values.update(overrides)
        return values

    def test_imports_foundation_dataset(self):
        output = StringIO()

        self.import_dataset(
            [self.food(), self.food(fdc_id=124, description="Oats, quick")],
            stdout=output,
        )

        self.assertEqual(IngredientNutrition.objects.count(), 2)
        nutrition = IngredientNutrition.objects.get(source_id="123")
        self.assertEqual(nutrition.ingredient.name, "Rolled oats")
        self.assertEqual(nutrition.ingredient.category, "Nut and Seed Products")
        self.assertEqual(nutrition.source, "USDA FoodData Central")
        self.assertEqual(nutrition.serving_size_g, 100)
        self.assertEqual(nutrition.kcal, 389)
        self.assertEqual(nutrition.publication_date, date(2019, 4, 1))
        self.assertIn("created=2", output.getvalue())

    def test_imports_sr_legacy_dataset(self):
        self.import_dataset([self.food(data_type="SR Legacy")])

        self.assertEqual(IngredientNutrition.objects.get().source_id, "123")

    def test_imports_household_measures(self):
        portion = {
            "amount": 2.0,
            "gramWeight": 33.9,
            "sequenceNumber": 1,
            "modifier": "tbsp",
            "measureUnit": {"id": 1, "name": "undetermined", "abbreviation": None},
        }
        output = StringIO()

        self.import_dataset([self.food(foodPortions=[portion])], stdout=output)

        measure = IngredientMeasure.objects.get()
        self.assertEqual(measure.ingredient.name, "Rolled oats")
        self.assertEqual(measure.measure, "tbsp")
        self.assertEqual(measure.amount, 2.0)
        self.assertEqual(measure.gram_weight, 33.9)
        self.assertIn("measures=1", output.getvalue())
        self.assertIn("foods_without_measures=0", output.getvalue())

    def test_reports_foods_without_a_usable_measure(self):
        output = StringIO()

        self.import_dataset(
            [self.food(foodPortions=[self.portion()]), self.food(fdc_id=124)],
            stdout=output,
        )

        self.assertEqual(IngredientMeasure.objects.count(), 1)
        self.assertIn("measures=1", output.getvalue())
        self.assertIn("foods_without_measures=1", output.getvalue())

    def test_reimport_replaces_the_imported_measures(self):
        self.import_dataset([self.food(foodPortions=[self.portion(modifier="cup")])])
        self.import_dataset([self.food(foodPortions=[self.portion(modifier="tbsp")])])

        measure = IngredientMeasure.objects.get()
        self.assertEqual(measure.measure, "tbsp")
        self.assertEqual(IngredientMeasure.objects.count(), 1)

    def test_dry_run_does_not_write_measures(self):
        output = StringIO()

        self.import_dataset(
            [self.food(foodPortions=[self.portion()])],
            "--dry-run",
            stdout=output,
        )

        self.assertEqual(IngredientMeasure.objects.count(), 0)
        self.assertIn("measures=1", output.getvalue())

    def test_stores_missing_nutrients_as_null(self):
        self.import_dataset([self.food(omit_nutrients=(1079,))])

        nutrition = IngredientNutrition.objects.get()
        self.assertIsNone(nutrition.fiber_g)
        self.assertEqual(nutrition.protein_g, 16.9)

    def test_reports_partial_foods(self):
        output = StringIO()

        self.import_dataset(
            [self.food(), self.food(fdc_id=124, omit_nutrients=(1079,))],
            stdout=output,
        )

        self.assertIn("partial=1", output.getvalue())

    def test_require_all_nutrients_skips_partial_foods(self):
        errors = StringIO()

        with self.assertRaises(CommandError):
            self.import_dataset(
                [self.food(), self.food(fdc_id=124, omit_nutrients=(1079,))],
                "--require-all-nutrients",
                stderr=errors,
            )

        self.assertIn("124: skipped", errors.getvalue())
        self.assertIn("missing nutrients: fiber_g", errors.getvalue())
        self.assertEqual(IngredientNutrition.objects.count(), 1)

    def test_ignores_null_dataset_entries(self):
        self.write_dataset([self.food(), None, None])
        output = StringIO()

        call_command(
            "import_usda_bulk",
            "--file",
            str(self.dataset_path),
            stdout=output,
        )

        self.assertEqual(IngredientNutrition.objects.count(), 1)
        self.assertIn("empty=2", output.getvalue())

    def test_ignores_foods_without_tracked_nutrients(self):
        output = StringIO()

        self.import_dataset(
            [self.food(), self.food(fdc_id=124, omit_nutrients=tuple(NUTRIENTS))],
            stdout=output,
        )

        self.assertEqual(IngredientNutrition.objects.count(), 1)
        self.assertIn("ignored=1", output.getvalue())
        self.assertIn("created=1", output.getvalue())

    def test_require_all_nutrients_reports_foods_without_any(self):
        errors = StringIO()

        with self.assertRaises(CommandError):
            self.import_dataset(
                [self.food(fdc_id=124, omit_nutrients=tuple(NUTRIENTS))],
                "--require-all-nutrients",
                stderr=errors,
            )

        self.assertIn("missing nutrients: kcal", errors.getvalue())

    def test_dry_run_does_not_write(self):
        output = StringIO()

        self.import_dataset([self.food()], "--dry-run", stdout=output)

        self.assertFalse(IngredientNutrition.objects.exists())
        self.assertIn("would create", output.getvalue())

    def test_reimport_updates_existing_nutrition(self):
        self.import_dataset([self.food()])
        output = StringIO()

        self.import_dataset([self.food(amounts={2048: 400})], stdout=output)

        self.assertEqual(IngredientNutrition.objects.count(), 1)
        self.assertEqual(IngredientNutrition.objects.get().kcal, 400)
        self.assertIn("updated=1", output.getvalue())

    def test_reimport_keeps_manually_set_category(self):
        self.import_dataset([self.food()])
        ingredient = Ingredient.objects.get()
        ingredient.category = "Breakfast"
        ingredient.save()
        output = StringIO()

        self.import_dataset([self.food()], stdout=output)

        self.assertEqual(Ingredient.objects.get().category, "Breakfast")
        self.assertIn("updated=1", output.getvalue())

    def test_reimport_keeps_known_publication_date(self):
        self.import_dataset([self.food()])
        food = self.food()
        del food["publicationDate"]

        self.import_dataset([food])

        self.assertEqual(
            IngredientNutrition.objects.get().publication_date, date(2019, 4, 1)
        )

    def test_skips_branded_foods(self):
        errors = StringIO()

        with self.assertRaises(CommandError):
            self.import_dataset([self.food(data_type="Branded")], stderr=errors)

        self.assertIn("unsupported dataType Branded", errors.getvalue())
        self.assertFalse(IngredientNutrition.objects.exists())

    def test_limit_stops_after_the_first_food(self):
        self.import_dataset([self.food(), self.food(fdc_id=124)], "--limit", "1")

        self.assertEqual(IngredientNutrition.objects.count(), 1)
        self.assertEqual(IngredientNutrition.objects.get().source_id, "123")

    def test_imports_from_zip_archive(self):
        path = self.write_archive(
            {"FoodData_Central_foundation_food_json_2026-04-30.json": [self.food()]}
        )
        output = StringIO()

        call_command(
            "import_usda_bulk",
            "--file",
            str(path),
            "--chunk-size",
            "16",
            stdout=output,
        )

        self.assertEqual(IngredientNutrition.objects.count(), 1)
        self.assertIn("created=1", output.getvalue())

    def test_reports_unreadable_dataset(self):
        with self.assertRaisesMessage(CommandError, "could not import"):
            call_command(
                "import_usda_bulk",
                "--file",
                str(self.directory_path / "missing.json"),
            )

    def test_duplicate_descriptions_get_an_fdc_suffix(self):
        output = StringIO()

        self.import_dataset(
            [self.food(), self.food(fdc_id=124, amounts={2048: 400})],
            stdout=output,
        )

        names = set(Ingredient.objects.values_list("name", flat=True))
        self.assertEqual(names, {"Rolled oats", "Rolled oats (FDC 124)"})
        for nutrition in IngredientNutrition.objects.all():
            self.assertEqual(nutrition.ingredient.nutrition.count(), 1)
        self.assertEqual(
            IngredientNutrition.objects.get(source_id="123").ingredient.name,
            "Rolled oats",
        )
        self.assertEqual(
            IngredientNutrition.objects.get(source_id="124").kcal, 400
        )
        self.assertIn("renamed=1", output.getvalue())

    def test_duplicate_descriptions_in_one_dataset_are_split(self):
        self.import_dataset(
            [
                self.food(fdc_id=123),
                self.food(fdc_id=124),
                self.food(fdc_id=125),
            ]
        )

        self.assertEqual(Ingredient.objects.count(), 3)
        self.assertEqual(IngredientNutrition.objects.count(), 3)
        self.assertEqual(
            IngredientNutrition.objects.filter(
                ingredient__name__startswith="Rolled oats (FDC"
            ).count(),
            2,
        )

    def test_reimport_does_not_rename_again(self):
        self.import_dataset([self.food(), self.food(fdc_id=124, amounts={2048: 400})])
        output = StringIO()

        self.import_dataset(
            [self.food(), self.food(fdc_id=124, amounts={2048: 410})],
            stdout=output,
        )

        self.assertEqual(Ingredient.objects.count(), 2)
        self.assertEqual(IngredientNutrition.objects.count(), 2)
        self.assertEqual(IngredientNutrition.objects.get(source_id="124").kcal, 410)
        self.assertIn("updated=2", output.getvalue())
        self.assertNotIn("renamed=", output.getvalue())

    def test_dry_run_reports_the_suffixed_name(self):
        output = StringIO()

        self.import_dataset(
            [self.food(), self.food(fdc_id=124, amounts={2048: 400})],
            "--dry-run",
            stdout=output,
        )

        self.assertIn("would create Rolled oats", output.getvalue())
        self.assertIn("would create Rolled oats (FDC 124)", output.getvalue())
        self.assertIn("renamed=1", output.getvalue())

    def test_existing_nutrition_free_ingredient_is_reused(self):
        ingredient = Ingredient.objects.create(name="Rolled oats")

        self.import_dataset([self.food()])

        self.assertEqual(Ingredient.objects.count(), 1)
        self.assertEqual(ingredient.nutrition.count(), 1)

    def test_duplicate_description_suffix_respects_the_name_limit(self):
        base = ("Kale, raw " + "very long padding " * 12).strip()

        self.import_dataset(
            [self.food(description=base), self.food(fdc_id=124, description=base)]
        )

        renamed = Ingredient.objects.exclude(name=base).get()
        self.assertLessEqual(len(renamed.name), NAME_MAX_LENGTH)
        self.assertTrue(renamed.name.endswith("(FDC 124)"))


def card_page(left, right=None, whole=None):
    """Build a synthetic Team Nutrition page for :func:`extract_recipe`."""
    return (
        left,
        right if right is not None else [],
        whole if whole is not None else left,
    )


class SplitQuantityTests(TestCase):
    def test_classic_card_puts_the_name_after_the_measures(self):
        line = "3 ½ cups or 1 lb 5 oz Canned, low sodium pinto beans, drained, rinsed"

        quantity, name = split_quantity(line)

        self.assertEqual(quantity, "3 ½ cups or 1 lb 5 oz")
        self.assertEqual(name, "Canned, low sodium pinto beans, drained, rinsed")

    def test_healthy_kids_table_puts_the_name_before_the_measures(self):
        line = "Brown rice, long grain, regular, dry 4 ¾ oz ¾ cup 9 ½ oz 1 ½ cups"

        quantity, name = split_quantity(line)

        self.assertEqual(quantity, "4 ¾ oz ¾ cup 9 ½ oz 1 ½ cups")
        self.assertEqual(name, "Brown rice, long grain, regular, dry")

    def test_measureless_line_keeps_the_whole_line_as_a_name(self):
        self.assertEqual(split_quantity("Weight Measure Weight Measure"), ("", "Weight Measure Weight Measure"))

    def test_name_only_line_carries_no_quantity(self):
        self.assertEqual(split_quantity("*Fresh butternut squash"), ("", "*Fresh butternut squash"))


class RecipePDFTests(TestCase):
    def test_classic_card(self):
        pages = [
            card_page(
                [
                    "United States Department of Agriculture",
                    "Bean Burrito Bowl – CACFP Home Childcare",
                    "Bean Burrito Bowl",
                    "Ingredients",
                    "3 ½ cups or 1 lb 5 oz Canned, low sodium pinto beans",
                    "OR",
                    "¼ cup or 1 oz Fresh onions, chopped",
                    "¾ tsp Garlic powder",
                    "The grain ingredients used in this recipe must meet",
                ],
                [
                    "Preparation Time: 40 minutes",
                    "Cooking Time: 50 minutes",
                    "Makes: 6 servings",
                    "Directions",
                    "1 Combine the beans and the onions in a saucepan.",
                    "Heat to 140 °F for at least 15 seconds.",
                ],
            )
        ]

        recipe = extract_recipe(pages)

        self.assertEqual(recipe["title"], "Bean Burrito Bowl")
        self.assertEqual(recipe["servings"], 6)
        self.assertEqual(recipe["prep_mins"], 40)
        self.assertEqual(recipe["cook_mins"], 50)
        self.assertEqual(len(recipe["ingredients"]), 3)
        self.assertEqual(recipe["ingredients"][0], "3 ½ cups or 1 lb 5 oz Canned, low sodium pinto beans")
        self.assertGreaterEqual(len(recipe["directions"]), 2)

    def test_letter_spaced_ingredients_header(self):
        pages = [
            card_page(
                [
                    "I ngredients",
                    "¾ cup or 2 oz Bulgur wheat, dry",
                    "1 ½ cups or 11 oz *Dry kidney beans, cooked",
                ],
                ["Directions", "Rinse the beans thoroughly."],
            )
        ]

        recipe = extract_recipe(pages)

        self.assertEqual(len(recipe["ingredients"]), 2)
        self.assertEqual(recipe["ingredients"][0], "¾ cup or 2 oz Bulgur wheat, dry")

    def test_merged_header_sets_both_sections(self):
        pages = [
            card_page(
                [
                    "Ingredients Directions",
                    "1 ½ cups or 11 oz *Dry kidney beans, cooked",
                    "Ingredients",
                ],
                ["Directions", "1 Rinse the beans until the water runs clear."],
            )
        ]

        recipe = extract_recipe(pages)

        self.assertGreaterEqual(len(recipe["ingredients"]), 1)
        self.assertEqual(recipe["ingredients"][0], "1 ½ cups or 11 oz *Dry kidney beans, cooked")
        self.assertIn("Rinse the beans until the water runs clear.", recipe["directions"][0])

    def test_cover_page_without_ingredients_is_none(self):
        pages = [
            card_page(
                [
                    "Recipes for Healthy Kids",
                    "GRAND PRIZE WINNER",
                    "These mouth-watering burgers are made with",
                ],
                ["Our Story", "School nutrition professionals"],
            )
        ]

        self.assertIsNone(extract_recipe(pages))

    def test_name_only_rows_join_the_following_measure_row(self):
        pages = [
            card_page(
                [
                    "Ingredients",
                    "*Fresh butternut squash",
                    "peeled, cubed 2 lb 14 oz 2 qt",
                    "Olive Oil ⅓ cup",
                ],
                ["Directions", "Bake at 375 °F."],
            )
        ]

        recipe = extract_recipe(pages)

        self.assertIn("Olive Oil ⅓ cup", recipe["ingredients"])

    def test_duplicate_sequence_measures_and_credit_lines_are_skipped(self):
        pages = [
            card_page(
                [
                    "Ingredients",
                    "¾ cup (6 oz spoodle) provides ⅝ cup vegetable",
                    "¼ cup or 1 oz Fresh onions, chopped",
                ],
                [],
            )
        ]

        recipe = extract_recipe(pages)

        self.assertEqual(len(recipe["ingredients"]), 1)

    def test_story_pages_before_the_first_ingredients_header_are_skipped(self):
        pages = [
            card_page(["Recipes for Healthy Kids", "Our Story"], ["The students win."]),
            card_page(
                [
                    "Aztec Grain Salad",
                    "Ingredients",
                    "1 ½ cups Quinoa, dry",
                ],
                ["Directions", "1 Preheat the oven to 400 °F."],
            ),
        ]

        recipe = extract_recipe(pages)

        self.assertEqual(recipe["title"], "Aztec Grain Salad")
        self.assertEqual(len(recipe["ingredients"]), 1)
