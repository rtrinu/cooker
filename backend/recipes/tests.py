import json
import zipfile
from collections import namedtuple
from datetime import date, datetime, timezone as dt_timezone
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
from .ingredient_cleanup import canonical_ingredient_name, is_equipment
from .matching import IngredientIndex
from .models import (
    Ingredient,
    IngredientMeasure,
    IngredientNutrition,
    Nutrition,
    Recipe,
    RecipeIngredient,
)
from .nutrition import compute, coverage, is_reliable, scale_nutrients
from .nutrition_sources import (
    COFID,
    OPEN_FOOD_FACTS,
    USDA,
    is_commercially_clear,
    license_fields,
    source_metadata,
)
from .openrecipearchive import (
    ENGLISH_COLLECTIONS,
    SOURCE,
    parse_directions,
    parse_ingredient,
    parse_record,
    parse_servings,
)
from .pdf import extract_recipe, split_quantity
from .public_domain_recipes import parse_ingredient_line, parse_recipe
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


class NutritionSourceTests(TestCase):
    def test_usda_is_clear_for_commercial_use(self):
        self.assertTrue(USDA.commercial_use)
        self.assertFalse(USDA.share_alike)
        self.assertTrue(is_commercially_clear(USDA.name))
        self.assertEqual(USDA.license, "CC0 1.0")

    def test_cofid_allows_commercial_use_with_attribution(self):
        self.assertTrue(COFID.commercial_use)
        self.assertFalse(COFID.share_alike)
        self.assertTrue(is_commercially_clear(COFID.name))
        self.assertIn("Open Government Licence", COFID.license)
        self.assertIn("Crown copyright", COFID.attribution)

    def test_open_food_facts_is_not_merged_into_the_proprietary_database(self):
        self.assertTrue(OPEN_FOOD_FACTS.commercial_use)
        self.assertTrue(OPEN_FOOD_FACTS.share_alike)
        self.assertFalse(is_commercially_clear(OPEN_FOOD_FACTS.name))

    def test_unknown_source_is_treated_as_restricted(self):
        source = source_metadata("Some Blog")

        self.assertFalse(source.commercial_use)
        self.assertTrue(source.share_alike)
        self.assertFalse(is_commercially_clear("Some Blog"))

    def test_licence_fields_travel_with_each_row(self):
        fields = license_fields(USDA)

        self.assertEqual(fields["license"], "CC0 1.0")
        self.assertIn("FoodData Central", fields["attribution"])


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
                {
                    "nutrient": {"id": 1258, "unitName": "g"},
                    "amount": 1.2,
                },
                {
                    "nutrient": {"id": 2000, "unitName": "g"},
                    "amount": 1.0,
                },
                {
                    "nutrient": {"id": 1093, "unitName": "mg"},
                    "amount": 5.0,
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
        self.assertEqual(nutrition.saturated_fat_g, 1.2)
        self.assertEqual(nutrition.sugar_g, 1.0)
        self.assertEqual(nutrition.sodium_mg, 5.0)
        self.assertEqual(nutrition.license, "CC0 1.0")
        self.assertIn("FoodData Central", nutrition.attribution)
        self.assertIsNotNone(nutrition.retrieved_at)
        self.assertEqual(nutrition.verification_status, "unverified")
        self.assertEqual(ingredient.processing_status, "matched")
        self.assertIsNotNone(ingredient.processed_at)
        self.assertIn("created=1", output.getvalue())
        get_food.assert_called_once_with(123)

    @patch("recipes.management.commands.import_usda.USDAClient.get_food")
    def test_missing_extended_nutrients_stay_null(self, get_food):
        payload = self.food_payload()
        payload["foodNutrients"] = [
            entry
            for entry in payload["foodNutrients"]
            if entry["nutrient"]["id"] not in (1258, 2000, 1093)
        ]
        get_food.return_value = payload

        call_command("import_usda", "--fdc-id", "123", stdout=StringIO())

        nutrition = IngredientNutrition.objects.get()
        self.assertIsNone(nutrition.saturated_fat_g)
        self.assertIsNone(nutrition.sugar_g)
        self.assertIsNone(nutrition.sodium_mg)
        self.assertEqual(nutrition.kcal, 389)

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

    @patch("recipes.management.commands.import_usda.USDAClient.get_food")
    def test_imports_household_measures(self, get_food):
        payload = self.food_payload()
        payload["foodPortions"] = [
            {
                "amount": 1.0,
                "gramWeight": 90.0,
                "sequenceNumber": 1,
                "modifier": "cup",
                "portionDescription": "",
                "measureUnit": {"id": 1000, "name": "cup", "abbreviation": "cup"},
            }
        ]
        get_food.return_value = payload

        call_command("import_usda", "--fdc-id", "123", stdout=StringIO())

        measure = IngredientMeasure.objects.get()
        self.assertEqual(measure.measure, "cup")
        self.assertEqual(measure.gram_weight, 90.0)
        self.assertEqual(measure.measurement_system, "us")
        self.assertEqual(
            measure.conversion_source, "USDA FoodData Central foodPortions"
        )
        self.assertEqual(measure.confidence, 0.9)


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
                {"nutrient": {"id": 1258, "unitName": "g"}, "amount": 1.2},
                {"nutrient": {"id": 2000, "unitName": "g"}, "amount": 1.0},
                {"nutrient": {"id": 1093, "unitName": "mg"}, "amount": 5.0},
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
                        "saturated_fat_g": 1.2,
                        "sugar_g": 1.0,
                        "sodium_mg": 5.0,
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
        self.assertEqual(snapshot["foods"][0]["nutrients"]["saturated_fat_g"], 1.2)
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
        self.assertEqual(nutrition.saturated_fat_g, 1.2)
        self.assertEqual(nutrition.sugar_g, 1.0)
        self.assertEqual(nutrition.sodium_mg, 5.0)
        self.assertEqual(nutrition.license, "CC0 1.0")
        self.assertEqual(
            nutrition.retrieved_at,
            datetime(2026, 1, 1, tzinfo=dt_timezone.utc),
        )
        self.assertIn("created=1", output.getvalue())

    def test_json_snapshot_without_extended_nutrients_still_imports(self):
        snapshot = self.snapshot()
        for field in ("saturated_fat_g", "sugar_g", "sodium_mg"):
            snapshot["foods"][0]["nutrients"].pop(field)

        with TemporaryDirectory() as directory:
            path = Path(directory) / "nutrition.json"
            self.write_snapshot(path, snapshot)
            call_command("import_usda_json", "--file", str(path), stdout=StringIO())

        nutrition = IngredientNutrition.objects.get()
        self.assertIsNone(nutrition.saturated_fat_g)
        self.assertIsNone(nutrition.sugar_g)
        self.assertIsNone(nutrition.sodium_mg)
        self.assertEqual(nutrition.kcal, 389)

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

    def test_parses_extended_nutrients(self):
        record = self.parse_dataset(
            [
                self.food(
                    extra_nutrients={
                        1258: ("Fatty acids, total saturated", "g", 1.2),
                        2000: ("Sugars, total including NLEA", "g", 1.0),
                        1093: ("Sodium, Na", "mg", 5.0),
                    }
                )
            ]
        )[0]

        self.assertEqual(record["saturated_fat_g"], 1.2)
        self.assertEqual(record["sugar_g"], 1.0)
        self.assertEqual(record["sodium_mg"], 5.0)

    def test_extended_nutrients_are_null_when_absent(self):
        record = self.parse_dataset([self.food()])[0]

        self.assertIsNone(record["saturated_fat_g"])
        self.assertIsNone(record["sugar_g"])
        self.assertIsNone(record["sodium_mg"])

    def test_parses_sr_legacy_food(self):
        record = self.parse_dataset([self.food(data_type="SR Legacy")])[0]

        self.assertEqual(record["fdc_id"], 123)

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
        self.assertEqual(normalize_measure("centilitres"), "cl")

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

    def test_records_conversion_provenance(self):
        record = parse_portions(self.portions())[0]

        self.assertEqual(record["measurement_system"], "us")
        self.assertEqual(
            record["conversion_source"], "USDA FoodData Central foodPortions"
        )
        self.assertEqual(record["confidence"], 0.9)

    def test_records_metric_mass_conversions_as_certain(self):
        record = parse_portions(
            self.portions(
                modifier="g",
                measureUnit={"id": 1002, "name": "g", "abbreviation": "g"},
            )
        )[0]

        self.assertEqual(record["measurement_system"], "metric")
        self.assertEqual(record["confidence"], 1.0)

    def test_records_count_conversions_as_less_certain(self):
        record = parse_portions(
            self.portions(
                modifier="each",
                measureUnit={"id": 1003, "name": "each", "abbreviation": "ea"},
            )
        )[0]

        self.assertEqual(record["measurement_system"], "unspecified")
        self.assertEqual(record["confidence"], 0.8)

    def test_records_the_preparation_state_from_the_food(self):
        food = self.portions()
        food["description"] = "Rice, white, cooked"

        record = parse_portions(food)[0]

        self.assertEqual(record["preparation_state"], "cooked")

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

    def test_reads_a_pdf_fraction_glyph_as_a_lower_bound(self):
        # The PDFs encode fractions as stray capitals; the integer part is a
        # safe lower bound, but the glyph must not become a litre.
        self.assertEqual(parse_amount("2 L cups chickpeas"), (2, "cup", "chickpeas"))
        self.assertEqual(parse_amount("1 V tsp salt"), (1, "tsp", "salt"))

    def test_keeps_a_lone_capital_l_as_litres_without_a_following_measure(self):
        self.assertEqual(parse_amount("1 L milk"), (1, "l", "milk"))


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
            {"ingredient": "Salt", "quantity": "1 pinch", "reason": "no pinch measure"},
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

    def test_coverage_is_the_share_of_lines_that_resolved(self):
        result = compute(
            self.lines(("Rolled oats", "1 cup"), ("Salt", "to taste")),
            servings=2,
        )

        self.assertAlmostEqual(coverage(result), 0.5)

    def test_a_partial_sum_is_not_reliable(self):
        result = compute(
            self.lines(("Rolled oats", "1 cup"), ("Salt", "to taste")),
            servings=2,
        )

        self.assertFalse(is_reliable(result, servings=2))

    def test_unknown_servings_are_never_reliable(self):
        result = compute(self.lines(("Rolled oats", "1 cup")), servings=1)

        self.assertFalse(is_reliable(result, servings=None))


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

    def test_printed_range_is_a_quantity(self):
        quantity, name = split_quantity("2-4 Tbsp Fresh lime juice (optional)")

        self.assertEqual(quantity, "2-4 Tbsp")
        self.assertEqual(name, "Fresh lime juice (optional)")


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

    def test_long_title_beats_the_two_yield_heading(self):
        pages = [
            card_page(
                [
                    "Stir-Fried Green Rice, Eggs, and Ham (Turkey Ham)",
                    "Meal Components: Meat/Meat Alternate-Grains Main Dishes D-57r",
                    "50 Servings 100 Servings",
                    "Ingredients",
                    "5 lb 10 oz Brown rice, long-grain, regular, dry",
                ],
                ["Directions", "1 Boil water."],
            )
        ]

        recipe = extract_recipe(pages)

        self.assertEqual(
            recipe["title"], "Stir-Fried Green Rice, Eggs, and Ham (Turkey Ham)"
        )


class MatchingIndexTests(NutritionFactoryMixin, TestCase):
    def add_food(self, name, **nutrition):
        ingredient = Ingredient.objects.create(name=name)
        self.create_nutrition(ingredient=ingredient, **nutrition)
        return ingredient

    def test_exact_match_wins(self):
        food = self.add_food("Kale, raw")
        self.add_food("Kale, frozen, cooked")

        match = IngredientIndex().match("Kale, raw")

        self.assertEqual((match.ingredient, match.strategy), (food, "exact"))

    def test_casefold_match_ignores_capitalisation(self):
        food = self.add_food("Kale, raw")

        match = IngredientIndex().match("kale, RAW")

        self.assertEqual((match.ingredient, match.strategy), (food, "casefold"))

    def test_alias_match_uses_a_recorded_card_name(self):
        food = Ingredient.objects.create(
            name="Scallions", aliases=["Fresh onions, chopped"]
        )
        self.create_nutrition(ingredient=food)

        match = IngredientIndex().match("Fresh onions, chopped")

        self.assertEqual((match.ingredient, match.strategy), (food, "alias"))

    def test_token_subset_matches_a_prepared_card_name(self):
        food = self.add_food("Apples, granny smith, with skin, raw")

        match = IngredientIndex().match("Fresh granny smith apples")

        self.assertEqual(match.ingredient, food)
        self.assertLess(match.score, 1.0)

    def test_generic_name_does_not_match_a_different_form(self):
        self.add_food("Chicken, ground, raw")

        self.assertIsNone(IngredientIndex().match("Cooked diced chicken"))

    def test_a_nutritionless_row_is_never_fuzzy_matched(self):
        Ingredient.objects.create(name="Broccoli, raw")

        self.assertIsNone(IngredientIndex().match("Fresh broccoli florets"))

    def test_suggest_lists_close_candidates_best_first(self):
        close = self.add_food("Cabbage, bok choy, raw")
        self.add_food("Pineapple, canned, juice pack")

        suggestions = IngredientIndex().suggest("Fresh bok choy, sliced")

        self.assertEqual(suggestions[0].ingredient, close)


class RecipeImportCommandTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.directory_path = Path(self.directory.name)

    def pdf(self, name="recipe.pdf"):
        path = self.directory_path / name
        path.write_bytes(b"%PDF")
        return path

    def recipe_data(self, **overrides):
        data = {
            "title": "Bean Burrito Bowl",
            "description": "",
            "servings": 6,
            "prep_mins": 40,
            "cook_mins": 50,
            "ingredients": [
                "3 ½ cups or 1 lb 5 oz Canned, low sodium pinto beans",
                "¼ cup or 1 oz Fresh onions, chopped",
            ],
            "directions": [
                "1 Combine the beans and the onions in a saucepan.",
                "Heat to 140 °F for at least 15 seconds.",
            ],
        }
        data.update(overrides)
        return data

    @patch("recipes.management.commands.import_recipe.parse_pdf")
    def test_imports_recipe_and_ingredients(self, parse_pdf):
        parse_pdf.return_value = self.recipe_data()

        call_command("import_recipe", str(self.pdf()), stdout=StringIO())

        recipe = Recipe.objects.get()
        self.assertEqual(recipe.slug, "bean-burrito-bowl")
        self.assertEqual(recipe.name, "Bean Burrito Bowl")
        self.assertEqual(recipe.servings, 6)
        self.assertEqual(recipe.prep_mins, 40)
        self.assertEqual(recipe.cook_mins, 50)
        self.assertIn("Combine the beans", recipe.directions)
        self.assertEqual(
            [row.ingredient.name for row in recipe.ingredients.all()],
            ["Canned, low sodium pinto beans", "Fresh onions, chopped"],
        )
        self.assertEqual(
            [row.quantity_text for row in recipe.ingredients.all()],
            ["3 ½ cups or 1 lb 5 oz", "¼ cup or 1 oz"],
        )

    @patch("recipes.management.commands.import_recipe.parse_pdf")
    def test_creates_unknown_ingredients(self, parse_pdf):
        parse_pdf.return_value = self.recipe_data()

        call_command("import_recipe", str(self.pdf()), stdout=StringIO())

        self.assertEqual(Ingredient.objects.count(), 2)

    @patch("recipes.management.commands.import_recipe.parse_pdf")
    def test_reimport_updates_the_same_recipe(self, parse_pdf):
        path = self.pdf()
        parse_pdf.return_value = self.recipe_data()
        call_command("import_recipe", str(path), stdout=StringIO())
        parse_pdf.return_value = self.recipe_data(
            servings=4, ingredients=["1 cup Fresh onions, chopped"]
        )

        call_command("import_recipe", str(path), stdout=StringIO())

        recipe = Recipe.objects.get()
        self.assertEqual(recipe.servings, 4)
        self.assertEqual(recipe.ingredients.count(), 1)
        self.assertEqual(Ingredient.objects.count(), 2)

    @patch("recipes.management.commands.import_recipe.parse_pdf")
    def test_duplicate_titles_share_one_recipe(self, parse_pdf):
        parse_pdf.return_value = self.recipe_data()

        call_command(
            "import_recipe",
            str(self.pdf("a.pdf")),
            str(self.pdf("b.pdf")),
            stdout=StringIO(),
        )

        self.assertEqual(Recipe.objects.count(), 1)

    @patch("recipes.management.commands.import_recipe.parse_pdf")
    def test_distinct_titles_with_the_same_slug_are_split(self, parse_pdf):
        parse_pdf.side_effect = [
            self.recipe_data(title="Bean Burrito Bowl!"),
            self.recipe_data(title="Bean Burrito Bowl?"),
        ]

        call_command(
            "import_recipe",
            str(self.pdf("a.pdf")),
            str(self.pdf("b.pdf")),
            stdout=StringIO(),
        )

        slugs = set(Recipe.objects.values_list("slug", flat=True))
        self.assertEqual(slugs, {"bean-burrito-bowl", "bean-burrito-bowl-2"})

    @patch("recipes.management.commands.import_recipe.parse_pdf")
    def test_normalizes_names_and_truncates_quantities(self, parse_pdf):
        parse_pdf.return_value = self.recipe_data(
            ingredients=["*Fresh butternut squash 2 lb", "1 cup " * 20 + "Flour"]
        )

        call_command("import_recipe", str(self.pdf()), stdout=StringIO())

        names = set(Ingredient.objects.values_list("name", flat=True))
        self.assertIn("Fresh butternut squash", names)
        for row in RecipeIngredient.objects.all():
            self.assertLessEqual(len(row.quantity_text), 50)

    @patch("recipes.management.commands.import_recipe.parse_pdf")
    def test_computes_per_serving_nutrition_for_known_ingredients(self, parse_pdf):
        onions = Ingredient.objects.create(name="Fresh onions, chopped")
        IngredientNutrition.objects.create(
            ingredient=onions, kcal=40, protein_g=1.1, carbs_g=9.3,
            fat_g=0.1, fiber_g=1.7, serving_size_g=100,
            source="USDA", source_id="1",
        )
        IngredientMeasure.objects.create(
            ingredient=onions, measure="cup", source_label="cup",
            amount=1.0, gram_weight=160.0, sequence=1,
        )
        parse_pdf.return_value = self.recipe_data(
            ingredients=["¼ cup Fresh onions, chopped"]
        )

        call_command("import_recipe", str(self.pdf()), stdout=StringIO())

        nutrition = Nutrition.objects.get()
        self.assertEqual(nutrition.method, "computed")
        self.assertAlmostEqual(nutrition.kcal, 16 / 6)

    @patch("recipes.management.commands.import_recipe.parse_pdf")
    def test_matches_an_existing_ingredient_by_alias(self, parse_pdf):
        ingredient = Ingredient.objects.create(
            name="Scallions", aliases=["Fresh onions, chopped"]
        )
        parse_pdf.return_value = self.recipe_data(
            ingredients=["1 cup Fresh onions, chopped"]
        )

        call_command("import_recipe", str(self.pdf()), stdout=StringIO())

        self.assertEqual(Ingredient.objects.count(), 1)
        self.assertEqual(RecipeIngredient.objects.get().ingredient, ingredient)

    @patch("recipes.management.commands.import_recipe.parse_pdf")
    def test_records_the_card_name_as_an_alias(self, parse_pdf):
        onions = Ingredient.objects.create(name="Onions, raw")
        IngredientNutrition.objects.create(
            ingredient=onions, kcal=40, protein_g=1.1, carbs_g=9.3,
            fat_g=0.1, fiber_g=1.7, serving_size_g=100,
            source="USDA", source_id="1",
        )
        parse_pdf.return_value = self.recipe_data(
            ingredients=["1 cup Fresh onions, peeled, diced"]
        )

        call_command("import_recipe", str(self.pdf()), stdout=StringIO())

        onions.refresh_from_db()
        self.assertIn("Fresh onions, peeled, diced", onions.aliases)
        self.assertEqual(Ingredient.objects.count(), 1)

    @patch("recipes.management.commands.import_recipe.parse_pdf")
    def test_stores_the_printed_panel_as_source_nutrition(self, parse_pdf):
        parse_pdf.return_value = self.recipe_data(
            serving_size="1-cup",
            nutrients={
                "kcal": 298, "protein_g": 9, "carbs_g": 52, "fat_g": 6,
                "fiber_g": 7,
            },
        )

        call_command("import_recipe", str(self.pdf()), stdout=StringIO())

        nutrition = Nutrition.objects.get()
        self.assertEqual(nutrition.method, "source")
        self.assertEqual(nutrition.kcal, 298)
        self.assertEqual(Recipe.objects.get().serving_size, "1-cup")

    @patch("recipes.management.commands.import_recipe.parse_pdf")
    def test_computes_when_the_card_has_no_panel(self, parse_pdf):
        onions = Ingredient.objects.create(name="Fresh onions, chopped")
        IngredientNutrition.objects.create(
            ingredient=onions, kcal=40, protein_g=1.1, carbs_g=9.3,
            fat_g=0.1, fiber_g=1.7, serving_size_g=100,
            source="USDA", source_id="1",
        )
        IngredientMeasure.objects.create(
            ingredient=onions, measure="cup", source_label="cup",
            amount=1.0, gram_weight=160.0, sequence=1,
        )
        parse_pdf.return_value = self.recipe_data(
            ingredients=["¼ cup Fresh onions, chopped"]
        )

        call_command("import_recipe", str(self.pdf()), stdout=StringIO())

        self.assertEqual(Nutrition.objects.get().method, "computed")

    @patch("recipes.management.commands.import_recipe.parse_pdf")
    def test_aliases_flag_seeds_a_mapping(self, parse_pdf):
        food = Ingredient.objects.create(name="Cabbage, bok choy, raw")
        IngredientNutrition.objects.create(
            ingredient=food, kcal=13, protein_g=1.5, carbs_g=2.2,
            fat_g=0.2, fiber_g=1.0, serving_size_g=100,
            source="USDA", source_id="1",
        )
        alias_file = self.directory_path / "aliases.json"
        alias_file.write_text(json.dumps({"Fresh bok choy, sliced": "Cabbage, bok choy, raw"}))
        parse_pdf.return_value = self.recipe_data(ingredients=["2 cups Fresh bok choy, sliced"])

        call_command(
            "import_recipe", str(self.pdf()), "--aliases", str(alias_file),
            stdout=StringIO(),
        )

        self.assertEqual(RecipeIngredient.objects.get().ingredient, food)

    def test_shipped_alias_file_is_a_valid_nonempty_object(self):
        alias_file = Path(__file__).with_name("data") / "aliases.json"
        mapping = json.loads(alias_file.read_text())

        self.assertIsInstance(mapping, dict)
        self.assertTrue(mapping)
        self.assertTrue(
            all(isinstance(key, str) and key for key in mapping),
            mapping,
        )
        self.assertTrue(
            all(isinstance(value, str) and value for value in mapping.values()),
            mapping,
        )

    def test_ambiguous_aliases_resolve_to_the_lower_calorie_option(self):
        # A computed panel is a lower bound, so "X or Y" must never pick the
        # more calorie-dense reading. Aliases without a lower option are dropped
        # rather than left pointing at the higher one.
        alias_file = Path(__file__).with_name("data") / "aliases.json"
        mapping = json.loads(alias_file.read_text())

        self.assertEqual(mapping["lard or butter"], "Butter, salted")
        self.assertEqual(mapping["raisins or currants"], "Currants, zante, dried")
        self.assertTrue(mapping["heavy cream or whole milk"].startswith("Milk, whole"))
        self.assertNotIn("potato starch or cornstarch", mapping)
        self.assertNotIn("chicken broth or water", mapping)

    @patch("recipes.management.commands.import_recipe.parse_pdf")
    def test_reset_removes_recipes_and_junk_ingredients(self, parse_pdf):
        Recipe.objects.create(name="Old Recipe", slug="old-recipe")
        kept = Ingredient.objects.create(name="Kale, raw")
        IngredientNutrition.objects.create(
            ingredient=kept, kcal=49, protein_g=4.3, carbs_g=8.8,
            fat_g=0.9, fiber_g=3.6, serving_size_g=100,
            source="USDA", source_id="1",
        )
        Ingredient.objects.create(name="Junk From An Old Import")
        parse_pdf.return_value = self.recipe_data(ingredients=["1 cup Fresh onions, chopped"])

        call_command(
            "import_recipe", str(self.pdf()), "--reset", stdout=StringIO(),
        )

        self.assertFalse(Recipe.objects.filter(slug="old-recipe").exists())
        self.assertTrue(Ingredient.objects.filter(name="Kale, raw").exists())
        self.assertFalse(
            Ingredient.objects.filter(name="Junk From An Old Import").exists()
        )

    @patch("recipes.management.commands.import_recipe.parse_pdf")
    def test_report_lists_suggestions(self, parse_pdf):
        food = Ingredient.objects.create(name="Cabbage, bok choy, raw")
        IngredientNutrition.objects.create(
            ingredient=food, kcal=13, protein_g=1.5, carbs_g=2.2,
            fat_g=0.2, fiber_g=1.0, serving_size_g=100,
            source="USDA", source_id="1",
        )
        parse_pdf.return_value = self.recipe_data(ingredients=["1 cup Cooked chicken strips"])
        report = self.directory_path / "report.txt"

        call_command(
            "import_recipe", str(self.pdf()), "--report", str(report),
            stdout=StringIO(), stderr=StringIO(),
        )

        self.assertTrue(report.exists())
        self.assertIn("Cooked chicken strips", report.read_text())

    @patch("recipes.management.commands.import_recipe.parse_pdf")
    def test_unresolved_lines_keep_the_recipe_but_skip_nutrition(self, parse_pdf):
        parse_pdf.return_value = self.recipe_data()
        stderr = StringIO()
        stdout = StringIO()

        call_command("import_recipe", str(self.pdf()), stdout=stdout, stderr=stderr)

        self.assertTrue(Recipe.objects.exists())
        self.assertFalse(Nutrition.objects.exists())
        self.assertIn("unresolved=2", stdout.getvalue())
        self.assertIn("no nutrition", stderr.getvalue())

    @patch("recipes.management.commands.import_recipe.parse_pdf")
    def test_partial_ingredient_coverage_is_stored_as_a_lower_bound(self, parse_pdf):
        onions = Ingredient.objects.create(name="Fresh onions, chopped")
        IngredientNutrition.objects.create(
            ingredient=onions, kcal=40, protein_g=1.1, carbs_g=9.3,
            fat_g=0.1, fiber_g=1.7, serving_size_g=100,
            source="USDA", source_id="1",
        )
        IngredientMeasure.objects.create(
            ingredient=onions, measure="cup", source_label="cup",
            amount=1.0, gram_weight=160.0, sequence=1,
        )
        parse_pdf.return_value = self.recipe_data(
            ingredients=["¼ cup Fresh onions, chopped", "1 cup Unknown ingredient"]
        )

        call_command("import_recipe", str(self.pdf()), stdout=StringIO())

        nutrition = Nutrition.objects.get()
        self.assertEqual((nutrition.lines_used, nutrition.lines_total), (1, 2))
        self.assertAlmostEqual(nutrition.kcal, 16 / 6)

    @patch("recipes.management.commands.import_recipe.parse_pdf")
    def test_unknown_servings_do_not_publish_per_serving_calories(self, parse_pdf):
        onions = Ingredient.objects.create(name="Fresh onions, chopped")
        IngredientNutrition.objects.create(
            ingredient=onions, kcal=40, protein_g=1.1, carbs_g=9.3,
            fat_g=0.1, fiber_g=1.7, serving_size_g=100,
            source="USDA", source_id="1",
        )
        IngredientMeasure.objects.create(
            ingredient=onions, measure="cup", source_label="cup",
            amount=1.0, gram_weight=160.0, sequence=1,
        )
        parse_pdf.return_value = self.recipe_data(
            servings=None, ingredients=["¼ cup Fresh onions, chopped"]
        )

        call_command("import_recipe", str(self.pdf()), stdout=StringIO())

        self.assertIsNone(Recipe.objects.get().servings)
        self.assertFalse(Nutrition.objects.exists())

    @patch("recipes.management.commands.import_recipe.parse_pdf")
    def test_dry_run_does_not_write(self, parse_pdf):
        parse_pdf.return_value = self.recipe_data()
        output = StringIO()

        call_command("import_recipe", str(self.pdf()), "--dry-run", stdout=output)

        self.assertFalse(Recipe.objects.exists())
        self.assertFalse(Ingredient.objects.exists())
        self.assertIn("would create", output.getvalue())
        self.assertIn("dry run", output.getvalue())

    @patch("recipes.management.commands.import_recipe.parse_pdf")
    def test_skips_files_without_a_recipe(self, parse_pdf):
        parse_pdf.side_effect = [None, self.recipe_data()]
        output = StringIO()

        call_command(
            "import_recipe",
            str(self.pdf("a.pdf")),
            str(self.pdf("b.pdf")),
            stdout=output,
        )

        self.assertEqual(Recipe.objects.count(), 1)
        self.assertIn("skipped=1", output.getvalue())

    @patch("recipes.management.commands.import_recipe.parse_pdf")
    def test_directory_input_and_limit(self, parse_pdf):
        for index in range(3):
            (self.directory_path / f"{index}.pdf").write_bytes(b"%PDF")
        parse_pdf.side_effect = [
            self.recipe_data(title=f"Recipe {index}") for index in range(3)
        ]

        call_command(
            "import_recipe", str(self.directory_path), "--limit", "1",
            stdout=StringIO(),
        )

        self.assertEqual(Recipe.objects.count(), 1)
        parse_pdf.assert_called_once()

    @patch("recipes.management.commands.import_recipe.parse_pdf")
    def test_slug_override(self, parse_pdf):
        parse_pdf.return_value = self.recipe_data()

        call_command(
            "import_recipe", str(self.pdf()), "--slug", "custom-slug",
            stdout=StringIO(),
        )

        self.assertEqual(Recipe.objects.get().slug, "custom-slug")

    @patch("recipes.management.commands.import_recipe.parse_pdf")
    def test_slug_override_requires_one_file(self, parse_pdf):
        with self.assertRaisesMessage(CommandError, "single PDF"):
            call_command(
                "import_recipe",
                str(self.pdf("a.pdf")),
                str(self.pdf("b.pdf")),
                "--slug", "custom-slug",
                stdout=StringIO(),
            )
        parse_pdf.assert_not_called()

    @patch("recipes.management.commands.import_recipe.parse_pdf")
    def test_missing_path_fails_before_parsing(self, parse_pdf):
        with self.assertRaisesMessage(CommandError, "no such file or directory"):
            call_command(
                "import_recipe", str(self.directory_path / "missing.pdf"),
                stdout=StringIO(),
            )
        parse_pdf.assert_not_called()

    @patch("recipes.management.commands.import_recipe.parse_pdf")
    def test_empty_directory_is_rejected(self, parse_pdf):
        with self.assertRaisesMessage(CommandError, "no PDF files found"):
            call_command("import_recipe", str(self.directory_path), stdout=StringIO())
        parse_pdf.assert_not_called()

    @patch("recipes.management.commands.import_recipe.parse_pdf")
    def test_unreadable_file_reports_an_error(self, parse_pdf):
        parse_pdf.side_effect = OSError("broken")
        stderr = StringIO()

        with self.assertRaises(CommandError):
            call_command(
                "import_recipe", str(self.pdf()), stdout=StringIO(), stderr=stderr
            )

        self.assertIn("could not read", stderr.getvalue())


class RecomputeNutritionCommandTests(TestCase):
    def ingredient(self, name="Rolled oats"):
        ingredient = Ingredient.objects.create(name=name)
        IngredientNutrition.objects.create(
            ingredient=ingredient, kcal=389, protein_g=16.9, carbs_g=66.3,
            fat_g=6.9, fiber_g=10.6, serving_size_g=100,
            source="USDA", source_id=name,
        )
        IngredientMeasure.objects.create(
            ingredient=ingredient, measure="cup", source_label="cup",
            amount=1.0, gram_weight=90.0, sequence=1,
        )
        return ingredient

    def test_keeps_a_partial_computed_panel_as_a_lower_bound(self):
        recipe = Recipe.objects.create(name="Oats and mystery", servings=2)
        oats = self.ingredient()
        RecipeIngredient.objects.create(
            recipe=recipe, ingredient=oats, quantity_text="1 cup", position=1
        )
        RecipeIngredient.objects.create(
            recipe=recipe,
            ingredient=Ingredient.objects.create(name="Mystery"),
            quantity_text="1 cup",
            position=2,
        )

        call_command("recompute_nutrition", stdout=StringIO())

        nutrition = Nutrition.objects.get()
        self.assertEqual(nutrition.method, "computed")
        self.assertEqual((nutrition.lines_used, nutrition.lines_total), (1, 2))
        self.assertAlmostEqual(nutrition.kcal, 350.1 / 2)

    def test_removes_a_panel_when_nothing_resolves(self):
        recipe = Recipe.objects.create(name="Mystery", servings=2)
        RecipeIngredient.objects.create(
            recipe=recipe,
            ingredient=Ingredient.objects.create(name="Mystery"),
            quantity_text="1 cup",
            position=1,
        )
        Nutrition.objects.create(
            recipe=recipe, kcal=1, protein_g=0, carbs_g=0, fat_g=0,
            fiber_g=0, method="computed", lines_used=1, lines_total=2,
        )

        call_command("recompute_nutrition", stdout=StringIO())

        self.assertFalse(Nutrition.objects.exists())

    def test_removes_a_panel_that_measures_no_calories(self):
        recipe = Recipe.objects.create(name="Seasoned water", servings=2)
        salt = Ingredient.objects.create(name="Salt, table")
        IngredientNutrition.objects.create(
            ingredient=salt, kcal=0, protein_g=0, carbs_g=0, fat_g=0,
            fiber_g=0, serving_size_g=100, source="USDA", source_id="salt",
        )
        IngredientMeasure.objects.create(
            ingredient=salt, measure="tsp", source_label="tsp",
            amount=1.0, gram_weight=6.0, sequence=1,
        )
        RecipeIngredient.objects.create(
            recipe=recipe, ingredient=salt, quantity_text="1 tsp", position=1
        )
        Nutrition.objects.create(
            recipe=recipe, kcal=0, protein_g=0, carbs_g=0, fat_g=0,
            fiber_g=0, method="computed", lines_used=1, lines_total=2,
        )

        call_command("recompute_nutrition", stdout=StringIO())

        self.assertFalse(Nutrition.objects.exists())

    def test_removes_a_panel_when_servings_are_unknown(self):
        recipe = Recipe.objects.create(name="Oats", servings=None)
        oats = self.ingredient()
        RecipeIngredient.objects.create(
            recipe=recipe, ingredient=oats, quantity_text="1 cup", position=1
        )

        call_command("recompute_nutrition", stdout=StringIO())

        self.assertFalse(Nutrition.objects.exists())

    def test_creates_a_panel_when_every_line_resolves(self):
        recipe = Recipe.objects.create(name="Oats", servings=2)
        oats = self.ingredient()
        RecipeIngredient.objects.create(
            recipe=recipe, ingredient=oats, quantity_text="1 cup", position=1
        )

        call_command("recompute_nutrition", stdout=StringIO())

        nutrition = Nutrition.objects.get()
        self.assertEqual(nutrition.method, "computed")
        self.assertAlmostEqual(nutrition.kcal, 350.1 / 2)
        self.assertEqual((nutrition.lines_used, nutrition.lines_total), (1, 1))

    def test_printed_panels_are_left_alone(self):
        recipe = Recipe.objects.create(name="Printed", servings=2)
        Nutrition.objects.create(
            recipe=recipe, kcal=250, protein_g=1, carbs_g=1, fat_g=1,
            fiber_g=0, method="source",
        )

        call_command("recompute_nutrition", stdout=StringIO())

        self.assertEqual(Nutrition.objects.get().kcal, 250)

    def test_report_lists_unresolved_lines(self):
        recipe = Recipe.objects.create(name="Oats and mystery", servings=2)
        oats = self.ingredient()
        RecipeIngredient.objects.create(
            recipe=recipe, ingredient=oats, quantity_text="1 cup", position=1
        )
        RecipeIngredient.objects.create(
            recipe=recipe,
            ingredient=Ingredient.objects.create(name="Mystery"),
            quantity_text="1 cup",
            position=2,
        )
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        report = Path(directory.name) / "nutrition.txt"

        call_command(
            "recompute_nutrition", "--report", str(report), stdout=StringIO()
        )

        self.assertIn("Mystery", report.read_text())


class RematchIngredientsCommandTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def aliases(self, mapping):
        path = Path(self.directory.name) / "aliases.json"
        path.write_text(json.dumps(mapping), encoding="utf-8")
        return path

    def measured(self, name="Butter, salted"):
        ingredient = Ingredient.objects.create(name=name)
        IngredientNutrition.objects.create(
            ingredient=ingredient, kcal=717, protein_g=0.9, carbs_g=0.1,
            fat_g=81, fiber_g=0, serving_size_g=100,
            source="USDA", source_id=name,
        )
        return ingredient

    def test_repoints_a_bare_ingredient_at_its_measured_match(self):
        target = self.measured()
        bare = Ingredient.objects.create(name="butter")
        recipe = Recipe.objects.create(name="Cake", servings=4)
        RecipeIngredient.objects.create(
            recipe=recipe, ingredient=bare, quantity_text="1 cup", position=1
        )

        call_command(
            "rematch_ingredients",
            "--aliases",
            str(self.aliases({"butter": target.name})),
            stdout=StringIO(),
        )

        self.assertEqual(RecipeIngredient.objects.get().ingredient, target)
        self.assertFalse(Ingredient.objects.filter(name="butter").exists())
        target.refresh_from_db()
        self.assertIn("butter", target.aliases)

    def test_leaves_measured_ingredients_alone(self):
        target = self.measured()
        recipe = Recipe.objects.create(name="Cake", servings=4)
        RecipeIngredient.objects.create(
            recipe=recipe, ingredient=target, quantity_text="1 cup", position=1
        )

        call_command(
            "rematch_ingredients",
            "--aliases",
            str(self.aliases({"butter": target.name})),
            stdout=StringIO(),
        )

        self.assertEqual(RecipeIngredient.objects.get().ingredient, target)
        self.assertNotIn("butter", target.aliases)

    def test_dry_run_does_not_change_rows(self):
        target = self.measured()
        bare = Ingredient.objects.create(name="butter")
        recipe = Recipe.objects.create(name="Cake", servings=4)
        RecipeIngredient.objects.create(
            recipe=recipe, ingredient=bare, quantity_text="1 cup", position=1
        )

        call_command(
            "rematch_ingredients",
            "--aliases",
            str(self.aliases({"butter": target.name})),
            "--dry-run",
            stdout=StringIO(),
        )

        self.assertEqual(RecipeIngredient.objects.get().ingredient, bare)
        self.assertTrue(Ingredient.objects.filter(name="butter").exists())

    def test_report_lists_names_that_still_have_no_nutrition(self):
        recipe = Recipe.objects.create(name="Cake", servings=4)
        RecipeIngredient.objects.create(
            recipe=recipe,
            ingredient=Ingredient.objects.create(name="Mystery"),
            quantity_text="1 cup",
            position=1,
        )
        report = Path(self.directory.name) / "unresolved.txt"

        call_command(
            "rematch_ingredients",
            "--aliases",
            str(self.aliases({})),
            "--report",
            str(report),
            stdout=StringIO(),
        )

        self.assertIn("Mystery", report.read_text())


class ValidateNutritionCommandTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def measured(self, name="Rolled oats", kcal=200):
        ingredient = Ingredient.objects.create(name=name)
        IngredientNutrition.objects.create(
            ingredient=ingredient, kcal=kcal, protein_g=0, carbs_g=0, fat_g=0,
            fiber_g=0, serving_size_g=100, source="USDA", source_id=name,
        )
        IngredientMeasure.objects.create(
            ingredient=ingredient, measure="cup", source_label="cup",
            amount=1.0, gram_weight=100.0, sequence=1,
        )
        return ingredient

    def printed(self, name, kcal, servings, ingredient=None, quantity="1 cup"):
        recipe = Recipe.objects.create(name=name, servings=servings)
        Nutrition.objects.create(
            recipe=recipe, kcal=kcal, protein_g=0, carbs_g=0, fat_g=0,
            fiber_g=0, method="source",
        )
        if ingredient is not None:
            RecipeIngredient.objects.create(
                recipe=recipe, ingredient=ingredient, quantity_text=quantity,
                position=1,
            )
        return recipe

    def test_scores_computed_against_the_printed_panel(self):
        ingredient = self.measured()
        self.printed("Exact", 100, 2, ingredient)
        out = StringIO()

        call_command("validate_nutrition", stdout=out)

        text = out.getvalue()
        self.assertIn("printed=1 compared=1 unmeasurable=0", text)
        self.assertIn("median_ratio=1.00", text)
        self.assertIn("within_10=1", text)

    def test_recipe_without_resolved_lines_is_unmeasurable(self):
        self.printed("No lines", 100, 2)
        out = StringIO()

        call_command("validate_nutrition", stdout=out)

        self.assertIn("unmeasurable=1", out.getvalue())
        self.assertIn("unmeasurable No lines", out.getvalue())

    def test_report_lists_the_comparison_and_unresolved_lines(self):
        ingredient = self.measured()
        recipe = self.printed("Partial", 100, 2, ingredient)
        RecipeIngredient.objects.create(
            recipe=recipe,
            ingredient=Ingredient.objects.create(name="Mystery"),
            quantity_text="1 cup",
            position=2,
        )
        report = Path(self.directory.name) / "validation.txt"

        call_command(
            "validate_nutrition", "--report", str(report), stdout=StringIO()
        )

        text = report.read_text()
        self.assertIn("Partial", text)
        self.assertIn("Mystery", text)


class NutritionGapsCommandTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def measured(self, name="Nuts, almonds", kcal=579, grams=140):
        ingredient = Ingredient.objects.create(name=name)
        IngredientNutrition.objects.create(
            ingredient=ingredient, kcal=kcal, protein_g=0, carbs_g=0, fat_g=0,
            fiber_g=0, serving_size_g=100, source="USDA", source_id=name,
        )
        IngredientMeasure.objects.create(
            ingredient=ingredient, measure="cup", source_label="cup",
            amount=1.0, gram_weight=grams, sequence=1,
        )
        return ingredient

    def bare_line(self, name, quantity):
        recipe = Recipe.objects.create(name="Cake", servings=4)
        RecipeIngredient.objects.create(
            recipe=recipe,
            ingredient=Ingredient.objects.create(name=name),
            quantity_text=quantity,
            position=1,
        )

    def test_ranks_an_unresolved_name_by_estimated_calories(self):
        self.measured()
        self.bare_line("shelled sweet almonds", "1 cup")
        out = StringIO()

        call_command("nutrition_gaps", stdout=out)

        text = out.getvalue()
        self.assertIn("unresolved_names=1 unresolved_lines=1", text)
        self.assertIn("shelled sweet almonds", text)
        self.assertIn("Nuts, almonds", text)
        self.assertIn("811 kcal", text)

    def test_report_counts_lines_that_have_no_amount(self):
        self.measured()
        self.bare_line("salt to taste", "to taste")
        report = Path(self.directory.name) / "gaps.txt"

        call_command(
            "nutrition_gaps", "--report", str(report), stdout=StringIO()
        )

        self.assertIn("no amount=1", report.read_text())

    def test_rejects_an_out_of_range_score(self):
        with self.assertRaisesMessage(CommandError, "--min-score"):
            call_command("nutrition_gaps", "--min-score", "2", stdout=StringIO())


class OpenRecipeArchiveParserTests(TestCase):
    def test_normalises_word_numbers_and_old_units(self):
        cases = {
            "three table-spoonfuls of flour": ("3 tbsp", "flour"),
            "a quarter of a pound of white sugar": ("1/4 lb", "white sugar"),
            "a tea-spoonful of mixed spice": ("1 tsp", "mixed spice"),
            "half a pound of butter": ("1/2 lb", "butter"),
            "two and a half cups milk": ("2 1/2 cup", "milk"),
            "one-half cup sugar": ("1/2 cup", "sugar"),
            "nine large pippin apples": ("9 large", "pippin apples"),
            "a pinch of salt": ("1 pinch", "salt"),
            "seven eggs": ("7", "egg"),
            "1 (14-ounce) can tomatoes": ("1 can", "tomatoes"),
            "3 1/2 cup half and half": ("3 1/2 cup", "half and half"),
            "1 pint and a half of milk": ("1 1/2 pint", "milk"),
        }

        for line, expected in cases.items():
            with self.subTest(line=line):
                quantity, name, raw = parse_ingredient(line)
                self.assertEqual((quantity, name), expected)
                self.assertEqual(raw, line)

    def test_amountless_lines_keep_the_name_and_no_quantity(self):
        self.assertEqual(
            parse_ingredient("salt and pepper to taste")[:2],
            ("", "salt and pepper"),
        )
        self.assertEqual(parse_ingredient("Bit of bay leaf")[:2], ("", "bay leaf"))
        self.assertIsNone(parse_ingredient("1 cup"))

    def test_measurements_are_moved_out_of_names(self):
        cases = {
            "1/4-1/2 cup chopped parsley": ("1/4-1/2 cup", "chopped parsley"),
            "1 cup + 2 1/2 Tbsp Butter, divided": (
                "1 cup + 2 1/2 tbsp",
                "Butter",
            ),
            "½ cup + 2 tablespoons (150ml) cold whole milk": (
                "1/2 cup + 2 tbsp",
                "cold whole milk",
            ),
            "All-purpose flour 3 cups": ("3 cup", "All-purpose flour"),
            "Active dry yeast 1 tbsp": ("1 tbsp", "Active dry yeast"),
            "Salt - 1 1/2 teaspoons": ("1 1/2 tsp", "Salt"),
            ".5 TB ground allspice": ("1/2 tbsp", "ground allspice"),
            "Light soy sauce, 1 tbsp": ("1 tbsp", "Light soy sauce"),
            "Nearly 2 cups of sugar": ("2 cup", "sugar"),
            "50-70% dark chocolate chips": ("", "dark chocolate chips"),
            "½-1 teaspoon red-pepper flakes.": ("1/2-1 tsp", "red-pepper flakes"),
            "1 15 oz can diced tomatoes": ("1 15 oz can", "diced tomatoes"),
            "4 28 oz cans of whole or diced tomatoes": (
                "4 28 oz cans",
                "whole or diced tomatoes",
            ),
            "100 g / ½ cups butter": ("100 g / 1/2 cup", "butter"),
            "2 heaped tbsp Set honey": ("2 heaped tbsp", "Set honey"),
            "1/2 metric cup (~125ml) buckwheat": (
                "1/2 metric cup",
                "buckwheat",
            ),
            "1⁄2 cup flour": ("1/2 cup", "flour"),
            "2 and 1/4 teaspoons Active Dry Yeast": (
                "2 1/4 tsp",
                "Active Dry Yeast",
            ),
            "Tablespoon of olive oil": ("1 tbsp", "olive oil"),
            "33cl bottles of brown beer": ("33 cl bottles", "brown beer"),
            "<1 liter of milk": ("1 l", "milk"),
            "1 tbsp /~14 grams unsalted butter": (
                "1 tbsp / 14 g",
                "unsalted butter",
            ),
            "1 clove/teaspoon Garlic": ("1 clove / 1 tsp", "Garlic"),
            "6 or 7 tbsp of sugar": ("6-7 tbsp", "sugar"),
            "Overfilled Teaspoon Mixed Spice": (
                "1 overfilled tsp",
                "Mixed Spice",
            ),
            "1 cup /240 milliliters crème fraîche or heavy cream": (
                "1 cup / 240 ml",
                "crème fraîche or heavy cream",
            ),
        }

        for line, expected in cases.items():
            with self.subTest(line=line):
                self.assertEqual(parse_ingredient(line)[:2], expected)

    def test_percentages_and_bare_amounts_are_not_quantities(self):
        self.assertEqual(
            parse_ingredient("4% sea salt by cabbage weight")[:2],
            ("", "sea salt"),
        )
        self.assertIsNone(parse_ingredient("12 oz"))

    def test_servings_are_read_from_the_stated_yield(self):
        self.assertEqual(parse_servings("Makes 6 servings")[0], 6)
        self.assertEqual(parse_servings("Serves six")[0], 6)
        self.assertEqual(parse_servings("This serves 4 to 6.")[0], 4)
        self.assertEqual(parse_servings("for 4 people")[0], 4)
        self.assertIsNone(parse_servings("Yields 2 quarts")[0])
        self.assertIsNone(parse_servings("Makes 1 loaf")[0])

    def test_body_sections_become_ingredients_and_steps(self):
        body = (
            "## Ingredients\n\n"
            "- 1 can tomatoes\n"
            "- 1 pint water\n"
            "- 12 peppercorns\n\n"
            "## Directions\n\n"
            "1. Cook tomatoes and water twenty minutes.\n"
            "2. Strain and serve.\n"
        )

        record = self.record(body=body)
        parsed = parse_record(record)

        self.assertEqual(
            [(item.quantity, item.name) for item in parsed.ingredients],
            [("1 can", "tomatoes"), ("1 pint", "water"), ("12", "peppercorns")],
        )
        self.assertEqual(
            parsed.directions,
            "Cook tomatoes and water twenty minutes.\nStrain and serve.",
        )

    def test_record_carries_provenance_and_unknown_servings(self):
        parsed = parse_record(self.record())

        self.assertEqual(parsed.slug, "ora-ye-old-american-tomato-soup")
        self.assertEqual(parsed.source_id, "ye-old-american/tomato-soup")
        self.assertEqual(parsed.license, "public-domain")
        self.assertEqual(parsed.collection, "ye-old-american")
        self.assertIn("Fannie Farmer", parsed.attribution)
        self.assertIsNone(parsed.servings)
        self.assertIn("no yield statement", parsed.servings_note)
        self.assertEqual(parsed.first_instruction, "Cook and serve.")

    def test_record_with_yield_gets_servings(self):
        parsed = parse_record(
            self.record(body=self.body(directions="Makes 6 servings\n1. Cook."))
        )

        self.assertEqual(parsed.servings, 6)

    def test_english_collection_set_is_exactly_the_english_sources(self):
        self.assertEqual(len(ENGLISH_COLLECTIONS), 9)
        self.assertIn("ye-old-american", ENGLISH_COLLECTIONS)

    def body(self, directions="1. Cook and serve."):
        return (
            "## Ingredients\n\n"
            "- 1 can tomatoes\n"
            "- 1 pint water\n\n"
            f"## Directions\n\n{directions}\n"
        )

    def record(self, **overrides):
        data = {
            "title": "Tomato Soup",
            "slug": "tomato-soup",
            "collection": "ye-old-american",
            "culture": "american-historical",
            "body": self.body(),
            "license": "public-domain",
            "author": "Fannie Farmer",
            "source_title": "The Boston Cooking-School Cook Book",
            "source_year": "1896",
            "source_url": "https://www.gutenberg.org/ebooks/65061",
            "tags": ["american-historical"],
        }
        data.update(overrides)
        return data


class PublicDomainRecipeParserTests(TestCase):
    def test_vague_suggestions_are_not_ingredients(self):
        cases = (
            "Any extra herbs or spices to your taste",
            "Any ingredients you want",
            "Any kind of firm, thin, sliced bread (Sourdough, Baguette)",
            "Any lean, tough cut of meat (ex. chuck, round steak, etc.)",
            "Any other vegetables you want",
            "Any toppings if desired (chocolate chips, ...) although it is very enjoyable on its own",
        )

        for line in cases:
            with self.subTest(line=line):
                self.assertIsNone(parse_ingredient_line(line))

    def test_trailing_measurements_and_optional_words_are_cleaned(self):
        cases = {
            "Greek yogurt, 2 cups": ("2 cup", "Greek yogurt"),
            "Salt and pepper to taste": ("", "Salt and pepper"),
            "Cream 4tbsp (or cashew paste)": ("4 tbsp", "Cream"),
        }

        for line, expected in cases.items():
            with self.subTest(line=line):
                parsed = parse_ingredient_line(line)
                self.assertEqual((parsed["quantity"], parsed["name"]), expected)

    def test_period_inside_parentheses_does_not_truncate_the_name(self):
        parsed = parse_ingredient_line("Tortillas (6 in. corn)")

        self.assertEqual(parsed["name"], "Tortillas (6 in. corn)")

    def test_word_number_and_dozen_yields_are_read(self):
        text = (
            '---\ntitle: "Greek Easter Cookies"\n---\n'
            "- 🍽️ Servings: Five-dozen individual cookies\n\n"
            "## Ingredients\n- 1 cup flour\n\n"
            "## Directions\n1. Bake.\n"
        )

        parsed = parse_recipe(text, "greek-easter-cookies.md")

        self.assertEqual(parsed.servings, 60)

    def test_vague_yields_stay_unknown(self):
        text = (
            '---\ntitle: "Mystery"\n---\n'
            "- 🍽️ Servings: A batch like this will last for two days.\n\n"
            "## Ingredients\n- 1 cup flour\n\n"
            "## Directions\n1. Bake.\n"
        )

        parsed = parse_recipe(text, "mystery.md")

        self.assertIsNone(parsed.servings)


class IngredientCleanupTests(TestCase):
    def test_names_reduce_to_the_ingredient(self):
        cases = {
            "/500g liver (chicken, beef, poultry etc.)": "liver",
            "00 or 0 flour": "flour",
            "Around three to four large turnips with their greens attached": (
                "turnips"
            ),
            "700ml red wine (I prefer Primitivo/Zinfandel)": "red wine",
            "Cassia bark (or cinnamon stick), 2 inches": "Cassia bark",
            "Potatoes (yellow or brown), I don't count but 10": "Potatoes",
            "mushrooms, or chopped clams or oysters (optional)": "mushrooms",
            "or three onions (preferably red)": "onions",
            "pinches of (Mozzarella, Oaxaca, or Montery Jack cheese)": (
                "Montery Jack cheese"
            ),
            "spoon ginger powder (or a bit of fresh ginger)": "ginger powder",
            "spoon of butter": "butter",
            "Some slices of bell pepper**": "bell pepper",
            "branches of fresh _epazote_": "fresh epazote",
            "whole ckicken weighing close to 2,5kg": "whole ckicken",
            "3 onions": "onions",
            "or less of Xanthan Gum": "Xanthan Gum",
            "Dashi powder or any desired seasonings": "Dashi powder",
            "18% sour cream": "sour cream",
            "95% ABV grain alcohol": "grain alcohol",
            "2-4% sea salt by cabbage weight": "sea salt",
            "recipe of your favorite tuna salad": "tuna salad",
            "live lobster that weighs ~750 grams": "live lobster",
            "Kefir about 150-300 ml per serving": "Kefir",
            "Condiments of your choice": "Condiments",
            "pasta, preferably penne": "pasta",
            "Optional herbs and spices": "herbs and spices",
            "milk (you can use water instead)": "milk",
            "sardines (~4oz)": "sardines",
            "Apricot jam (about": "Apricot jam",
            "yellow onion diced": "yellow onion",
            "really whatever you like": "",
            "to your palate": "",
            "finely diced": "",
        }

        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(canonical_ingredient_name(name), expected)

    def test_descriptive_names_are_kept(self):
        for name in (
            "rye flour",
            "whole milk",
            "red pepper flakes",
            "string beans",
            "Salt and freshly ground Black Pepper",
        ):
            with self.subTest(name=name):
                self.assertEqual(canonical_ingredient_name(name), name)

    def test_equipment_is_recognised(self):
        for name in ("Aluminum Foil", "tin foil", "baking paper", "skewers", "twine"):
            with self.subTest(name=name):
                self.assertTrue(is_equipment(name))

    def test_foods_that_look_like_equipment_are_kept(self):
        for name in ("red pepper flakes", "string beans", "glass noodles"):
            with self.subTest(name=name):
                self.assertFalse(is_equipment(name))

    def test_word_ranges_and_grade_flour_parse(self):
        cases = {
            "three to four eggs": ("3-4", "eggs"),
            "two or three large onions": ("2-3 large", "onions"),
            "650 g 00 or 0 flour": ("650 g", "flour"),
            "00 flour": ("", "flour"),
            "flour (0 or 00)": ("", "flour"),
        }

        for line, expected in cases.items():
            with self.subTest(line=line):
                parsed = parse_ingredient_line(line)
                self.assertEqual((parsed["quantity"], parsed["name"]), expected)


class OpenRecipeArchiveImportCommandTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.directory_path = Path(self.directory.name)

    def body(self, directions="1. Cook and serve."):
        return (
            "## Ingredients\n\n"
            "- 1 can tomatoes\n"
            "- 1 pint water\n\n"
            f"## Directions\n\n{directions}\n"
        )

    def record(self, **overrides):
        data = {
            "title": "Tomato Soup",
            "slug": "tomato-soup",
            "collection": "ye-old-american",
            "culture": "american-historical",
            "body": self.body(),
            "license": "public-domain",
            "author": "Fannie Farmer",
            "source_title": "The Boston Cooking-School Cook Book",
            "source_year": "1896",
            "source_url": "https://www.gutenberg.org/ebooks/65061",
            "tags": ["american-historical"],
        }
        data.update(overrides)
        return data

    def jsonl(self, records, name="recipes.jsonl"):
        path = self.directory_path / name
        path.write_text(
            "\n".join(json.dumps(record) for record in records) + "\n",
            encoding="utf-8",
        )
        return path

    def test_imports_recipe_with_provenance_and_raw_ingredient_lines(self):
        path = self.jsonl([self.record(body=self.body("Makes 6 servings.\n1. Cook."))])

        call_command("import_openrecipearchive", str(path), stdout=StringIO())

        recipe = Recipe.objects.get()
        self.assertEqual(recipe.source, SOURCE)
        self.assertEqual(recipe.source_id, "ye-old-american/tomato-soup")
        self.assertEqual(recipe.collection, "ye-old-american")
        self.assertEqual(recipe.license, "public-domain")
        self.assertEqual(recipe.servings, 6)
        self.assertIn("Fannie Farmer", recipe.attribution)
        self.assertEqual(recipe.directions, "Cook.")
        rows = list(recipe.ingredients.all())
        self.assertEqual(
            [(row.quantity_text, row.ingredient.name) for row in rows],
            [("1 can", "tomatoes"), ("1 pint", "water")],
        )
        self.assertEqual(rows[0].raw_text, "1 can tomatoes")

    def test_reimport_updates_the_same_recipe(self):
        path = self.jsonl([self.record()])

        call_command("import_openrecipearchive", str(path), stdout=StringIO())
        call_command("import_openrecipearchive", str(path), stdout=StringIO())

        self.assertEqual(Recipe.objects.count(), 1)
        self.assertEqual(RecipeIngredient.objects.count(), 2)

    def test_unknown_servings_are_printed_with_recipe_and_first_instruction(self):
        path = self.jsonl([self.record()])
        output = StringIO()

        call_command("import_openrecipearchive", str(path), stdout=output)

        text = output.getvalue()
        self.assertIn("NO SERVINGS: ye-old-american/tomato-soup", text)
        self.assertIn('"Tomato Soup"', text)
        self.assertIn("no yield statement", text)
        self.assertIn("first instruction: Cook and serve.", text)
        self.assertIsNone(Recipe.objects.get().servings)

    def test_servings_report_is_written(self):
        path = self.jsonl([self.record()])
        report = self.directory_path / "servings.txt"

        call_command(
            "import_openrecipearchive",
            str(path),
            "--servings-report",
            str(report),
            stdout=StringIO(),
        )

        self.assertIn("ye-old-american/tomato-soup", report.read_text())

    def test_english_collections_and_public_domain_license_are_required(self):
        path = self.jsonl([
            self.record(title="English", slug="english"),
            self.record(title="French", slug="french", collection="cuisine-francaise"),
            self.record(title="Restricted", slug="restricted", license="cc-by-nc"),
        ])
        output = StringIO()

        call_command("import_openrecipearchive", str(path), stdout=output)

        self.assertEqual(Recipe.objects.count(), 1)
        self.assertEqual(Recipe.objects.get().name, "English")
        self.assertIn("collection_skipped=1", output.getvalue())
        self.assertIn("license_skipped=1", output.getvalue())

    def test_collection_override_and_limit_and_offset(self):
        path = self.jsonl([
            self.record(title="One", slug="one"),
            self.record(title="Two", slug="two"),
            self.record(title="Three", slug="three"),
        ])

        call_command(
            "import_openrecipearchive",
            str(path),
            "--limit",
            "1",
            stdout=StringIO(),
        )
        self.assertEqual(list(Recipe.objects.values_list("name", flat=True)), ["One"])

        call_command(
            "import_openrecipearchive",
            str(path),
            "--offset",
            "2",
            stdout=StringIO(),
        )
        self.assertEqual(
            set(Recipe.objects.values_list("name", flat=True)), {"One", "Three"}
        )

    def test_dry_run_does_not_write(self):
        path = self.jsonl([self.record()])
        output = StringIO()

        call_command(
            "import_openrecipearchive", str(path), "--dry-run", stdout=output
        )

        self.assertFalse(Recipe.objects.exists())
        self.assertFalse(Ingredient.objects.exists())
        self.assertIn("dry run", output.getvalue())

    def test_unmatched_report_lists_names_and_suggestions(self):
        food = Ingredient.objects.create(name="Tomatoes, red, ripe, raw")
        IngredientNutrition.objects.create(
            ingredient=food,
            kcal=18,
            protein_g=0.9,
            carbs_g=3.9,
            fat_g=0.2,
            fiber_g=1.2,
            serving_size_g=100,
            source="USDA",
            source_id="1",
        )
        path = self.jsonl([self.record()])
        report = self.directory_path / "unmatched.txt"

        call_command(
            "import_openrecipearchive",
            str(path),
            "--report",
            str(report),
            stdout=StringIO(),
        )

        text = report.read_text()
        self.assertIn("water", text)
        self.assertIn("e.g. ye-old-american/tomato-soup", text)
        self.assertIn("(no close candidate)", text)

    def test_reset_removes_only_the_previous_archive_import(self):
        first = self.jsonl([self.record(title="Old", slug="old")], "first.jsonl")
        second = self.jsonl([self.record(title="New", slug="new")], "second.jsonl")
        call_command("import_openrecipearchive", str(first), stdout=StringIO())

        call_command(
            "import_openrecipearchive",
            str(second),
            "--reset",
            stdout=StringIO(),
        )

        self.assertEqual(
            list(Recipe.objects.values_list("name", flat=True)), ["New"]
        )
