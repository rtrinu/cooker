import argparse
import json
import math
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from recipes.management.commands.import_usda import (
    NUTRIENT_FIELDS,
    SOURCE,
    USDADataError,
    find_nutrition,
    positive_int,
    upsert_food,
)

SNAPSHOT_VERSION = 1
BASIS_AMOUNT = 100
BASIS_UNIT = "g"


def snapshot_fdc_id(value, index):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise USDADataError(f"food {index} has an invalid fdc_id")
    try:
        fdc_id = positive_int(value)
    except argparse.ArgumentTypeError as exc:
        raise USDADataError(f"food {index} has an invalid fdc_id") from exc
    return fdc_id


def snapshot_amount(value, label):
    if isinstance(value, bool):
        raise USDADataError(f"{label} must be numeric")
    try:
        amount = float(value)
    except (TypeError, ValueError) as exc:
        raise USDADataError(f"{label} must be numeric") from exc
    if not math.isfinite(amount):
        raise USDADataError(f"{label} must be finite")
    if amount < 0:
        raise USDADataError(f"{label} cannot be negative")
    return amount


def validate_snapshot(snapshot):
    if not isinstance(snapshot, dict):
        raise USDADataError("snapshot must be an object")
    schema_version = snapshot.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != SNAPSHOT_VERSION:
        raise USDADataError("unsupported snapshot schema version")
    if snapshot.get("source") != SOURCE:
        raise USDADataError("snapshot source does not match USDA FoodData Central")
    if snapshot.get("data_type") != "Foundation":
        raise USDADataError("snapshot data_type must be Foundation")

    basis = snapshot.get("basis")
    if not isinstance(basis, dict):
        raise USDADataError("snapshot basis must be an object")
    if snapshot_amount(basis.get("amount"), "basis amount") != BASIS_AMOUNT:
        raise USDADataError("snapshot basis amount must be 100")
    if basis.get("unit") != BASIS_UNIT:
        raise USDADataError("snapshot basis unit must be g")

    foods = snapshot.get("foods")
    if not isinstance(foods, list):
        raise USDADataError("snapshot foods must be a list")

    records = []
    seen_ids = set()
    for index, food in enumerate(foods, start=1):
        if not isinstance(food, dict):
            raise USDADataError(f"food {index} must be an object")
        fdc_id = snapshot_fdc_id(food.get("fdc_id"), index)
        if fdc_id in seen_ids:
            raise USDADataError(f"duplicate fdc_id in snapshot: {fdc_id}")
        seen_ids.add(fdc_id)

        description = food.get("description")
        if not isinstance(description, str) or not description.strip():
            raise USDADataError(f"food {fdc_id} description is required")
        description = description.strip()
        if len(description) > 255:
            raise USDADataError(
                f"food {fdc_id} description exceeds the ingredient name limit"
            )

        if food.get("data_type", "Foundation") != "Foundation":
            raise USDADataError(f"food {fdc_id} has an unsupported data type")

        nutrients = food.get("nutrients")
        if not isinstance(nutrients, dict):
            raise USDADataError(f"food {fdc_id} nutrients must be an object")
        values = {}
        for field in NUTRIENT_FIELDS:
            if field not in nutrients:
                raise USDADataError(f"food {fdc_id} is missing nutrient {field}")
            values[field] = snapshot_amount(
                nutrients[field], f"food {fdc_id} nutrient {field}"
            )

        records.append(
            {
                "fdc_id": fdc_id,
                "name": description,
                **values,
            }
        )
    return records


def load_snapshot(path):
    try:
        with path.open(encoding="utf-8") as handle:
            snapshot = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CommandError(f"could not read {path}: {exc}") from exc
    try:
        return validate_snapshot(snapshot)
    except USDADataError as exc:
        raise CommandError(f"invalid snapshot {path}: {exc}") from exc


class Command(BaseCommand):
    help = "Import a USDA Foundation Foods JSON snapshot into the database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=Path,
            required=True,
            help="path to the USDA JSON snapshot",
        )
        parser.add_argument(
            "--batch-size",
            type=positive_int,
            default=100,
            help="number of foods per database transaction",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="validate the snapshot and report actions without writing",
        )

    def handle(self, *args, **options):
        records = load_snapshot(options["file"])
        if not records:
            raise CommandError("snapshot contains no foods")

        created = 0
        updated = 0
        failed = 0
        batch_size = options["batch_size"]

        for start in range(0, len(records), batch_size):
            batch = records[start : start + batch_size]
            if options["dry_run"]:
                for record in batch:
                    if find_nutrition(record["fdc_id"]):
                        action = "update"
                        updated += 1
                    else:
                        action = "create"
                        created += 1
                    self.stdout.write(
                        f"{record['fdc_id']}: would {action} {record['name']}"
                    )
                continue

            batch_created = 0
            batch_updated = 0
            try:
                with transaction.atomic():
                    for record in batch:
                        if upsert_food(record, record["fdc_id"]).created:
                            batch_created += 1
                        else:
                            batch_updated += 1
                created += batch_created
                updated += batch_updated
            except IntegrityError as exc:
                failed += len(batch)
                ids = ", ".join(str(record["fdc_id"]) for record in batch)
                self.stderr.write(f"{ids}: batch skipped ({exc})")

        summary = f"created={created} updated={updated} failed={failed}"
        if options["dry_run"]:
            self.stdout.write(f"dry run: {summary}")
        else:
            self.stdout.write(self.style.SUCCESS(summary))

        if failed:
            raise CommandError(f"USDA snapshot import completed with errors: {summary}")
