from collections import namedtuple
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from recipes.management.commands.import_usda import (
    NUTRIENT_FIELDS,
    USDADataError,
    find_nutrition,
    positive_int,
    preview_name,
    upsert_food,
)
from recipes.management.commands.usda_bulk import (
    DEFAULT_CHUNK_SIZE,
    iter_foods,
    open_dataset,
    parse_bulk_food,
)

PROGRESS_INTERVAL = 500

BatchResult = namedtuple("BatchResult", ("created", "updated", "skipped", "renamed"))


class Command(BaseCommand):
    help = (
        "Import a USDA FoodData Central bulk download JSON dataset "
        "(Foundation or SR Legacy foods, no API key required)"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=Path,
            required=True,
            help="path to a bulk download .json or .zip file",
        )
        parser.add_argument(
            "--member",
            help="name of the JSON file to read when --file is a .zip archive",
        )
        parser.add_argument(
            "--batch-size",
            type=positive_int,
            default=200,
            help="number of foods per database transaction",
        )
        parser.add_argument(
            "--chunk-size",
            type=positive_int,
            default=DEFAULT_CHUNK_SIZE,
            help="characters read from the dataset at a time",
        )
        parser.add_argument(
            "--limit",
            type=positive_int,
            help="import at most this many foods",
        )
        parser.add_argument(
            "--require-all-nutrients",
            action="store_true",
            help="skip foods that are missing any of the five tracked nutrients",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="report actions without writing to the database",
        )

    def handle(self, *args, **options):
        path = options["file"]
        batch_size = options["batch_size"]
        progress_every = max(batch_size, PROGRESS_INTERVAL)
        strict = options["require_all_nutrients"]
        counts = {
            "parsed": 0,
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "empty": 0,
            "partial": 0,
            "ignored": 0,
            "renamed": 0,
        }
        reported = 0
        pending = []
        claimed = set()

        def flush(records):
            result = self._write_batch(records, options["dry_run"], claimed)
            counts["created"] += result.created
            counts["updated"] += result.updated
            counts["skipped"] += result.skipped
            if result.skipped:
                return
            counts["renamed"] += len(result.renamed)
            for name in result.renamed:
                self.stderr.write(f"duplicate USDA description, stored as {name}")

        try:
            with open_dataset(path, options["member"]) as dataset:
                for food in iter_foods(dataset, options["chunk_size"]):
                    if options["limit"] and counts["parsed"] >= options["limit"]:
                        break
                    if food is None:
                        counts["empty"] += 1
                        continue
                    try:
                        record = parse_bulk_food(food, require_all_nutrients=strict)
                    except USDADataError as exc:
                        counts["skipped"] += 1
                        label = food.get("fdcId") if isinstance(food, dict) else None
                        self.stderr.write(f"{label or '?'}: skipped ({exc})")
                        continue
                    if record is None:
                        counts["ignored"] += 1
                        continue
                    pending.append(record)
                    counts["parsed"] += 1
                    if any(record[field] is None for field in NUTRIENT_FIELDS):
                        counts["partial"] += 1
                    if len(pending) < batch_size:
                        continue
                    flush(pending)
                    pending = []
                    if counts["parsed"] - reported >= progress_every:
                        reported = counts["parsed"]
                        self.stderr.write(f"progress {self._progress(counts)}")
                if pending:
                    flush(pending)
        except USDADataError as exc:
            raise CommandError(f"could not import {path}: {exc}") from exc

        summary = (
            f"created={counts['created']} updated={counts['updated']} "
            f"skipped={counts['skipped']}"
        )
        if options["dry_run"]:
            self.stdout.write(f"dry run: {summary}")
        else:
            self.stdout.write(self.style.SUCCESS(summary))
        self.stdout.write(
            f"parsed={counts['parsed']} partial={counts['partial']} "
            f"ignored={counts['ignored']} empty={counts['empty']}"
        )
        if counts["renamed"]:
            self.stdout.write(
                f"renamed={counts['renamed']} duplicate descriptions "
                "given an (FDC id) suffix"
            )

        if counts["skipped"]:
            raise CommandError(f"USDA bulk import completed with errors: {summary}")

    def _progress(self, counts):
        return (
            f"parsed={counts['parsed']} partial={counts['partial']} "
            f"created={counts['created']} updated={counts['updated']} "
            f"skipped={counts['skipped']} ignored={counts['ignored']} "
            f"empty={counts['empty']}"
        )

    def _write_batch(self, records, dry_run, claimed):
        if dry_run:
            created = 0
            updated = 0
            renamed = []
            for record in records:
                existing = find_nutrition(record["fdc_id"])
                label = (
                    existing.ingredient.name
                    if existing
                    else preview_name(record["name"], record["fdc_id"], claimed)
                )
                if existing:
                    updated += 1
                else:
                    created += 1
                    if label != record["name"]:
                        renamed.append(label)
                claimed.add(label)
                verb = "update" if existing else "create"
                self.stdout.write(f"{record['fdc_id']}: would {verb} {label}")
            return BatchResult(created, updated, 0, renamed)

        created = 0
        updated = 0
        renamed = []
        try:
            with transaction.atomic():
                for record in records:
                    result = upsert_food(
                        record,
                        record["fdc_id"],
                        category=record["category"],
                        publication_date=record["publication_date"],
                    )
                    if result.created:
                        created += 1
                    else:
                        updated += 1
                    if result.renamed:
                        renamed.append(result.name)
        except IntegrityError as exc:
            self.stderr.write(f"batch of {len(records)} foods skipped ({exc})")
            return BatchResult(0, 0, len(records), [])
        return BatchResult(created, updated, 0, renamed)