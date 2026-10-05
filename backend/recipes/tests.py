import json
import zipfile
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
)
from .management.commands.usda_bulk import (
    iter_foods,
    open_dataset,
    parse_bulk_food,
)
from .models import Ingredient, IngredientNutrition


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
