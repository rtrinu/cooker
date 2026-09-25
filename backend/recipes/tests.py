import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from .models import Ingredient, IngredientNutrition


class IngredientNutritionTests(TestCase):
    def setUp(self):
        self.ingredient = Ingredient.objects.create(name="Oats")

    def create_nutrition(self, **overrides):
        values = {
            "ingredient": self.ingredient,
            "kcal": 389,
            "protein_g": 16.9,
            "carbs_g": 66.3,
            "fat_g": 6.9,
            "serving_size_g": 100,
            "source": "USDA",
            "source_id": "123",
        }
        values.update(overrides)
        return IngredientNutrition.objects.create(**values)

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
