import json
import os
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from recipes.management.commands.import_usda import (
    SOURCE,
    USDAAPIError,
    USDAClient,
    USDADataError,
    collect_fdc_ids,
    parse_food,
    positive_int,
)

SNAPSHOT_VERSION = 1
BASIS_AMOUNT = 100
BASIS_UNIT = "g"


def nonnegative_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("must be an integer") from exc
    if parsed < 0:
        raise ValueError("cannot be negative")
    return parsed


def empty_snapshot():
    return {
        "schema_version": SNAPSHOT_VERSION,
        "source": SOURCE,
        "data_type": "Foundation",
        "basis": {"amount": BASIS_AMOUNT, "unit": BASIS_UNIT},
        "retrieved_at": timezone.now().isoformat(),
        "foods": [],
    }


def snapshot_food(food, parsed):
    return {
        "fdc_id": int(food["fdcId"]),
        "description": parsed["name"],
        "data_type": food.get("dataType") or "Foundation",
        "nutrients": {
            field: parsed[field]
            for field in ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g")
        },
    }


def write_snapshot(path, snapshot):
    temporary_path = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(snapshot, handle, indent=2)
            handle.write("\n")
        os.replace(temporary_path, path)
    except OSError as exc:
        raise CommandError(f"could not write {path}: {exc}") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def load_snapshot(path):
    from recipes.management.commands.import_usda_json import validate_snapshot

    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as handle:
            snapshot = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CommandError(f"could not read {path}: {exc}") from exc
    try:
        validate_snapshot(snapshot)
    except USDADataError as exc:
        raise CommandError(f"invalid snapshot {path}: {exc}") from exc
    return snapshot


class Command(BaseCommand):
    help = "Fetch USDA Foundation Foods into a resumable JSON snapshot"

    def add_arguments(self, parser):
        parser.add_argument(
            "--fdc-id",
            action="append",
            dest="fdc_ids",
            type=positive_int,
            help="USDA FDC ID; may be provided more than once",
        )
        parser.add_argument(
            "--file",
            type=Path,
            help="text file containing one or more FDC IDs per line",
        )
        parser.add_argument(
            "--output",
            type=Path,
            required=True,
            help="path for the JSON snapshot",
        )
        parser.add_argument(
            "--limit",
            type=positive_int,
            help="maximum number of FDC IDs to fetch",
        )
        parser.add_argument(
            "--min-remaining",
            type=nonnegative_int,
            default=1,
            help="wait when this many API requests remain",
        )
        parser.add_argument(
            "--refresh",
            action="store_true",
            help="re-fetch FDC IDs already present in the output snapshot",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="fetch and validate data without writing the snapshot",
        )

    def handle(self, *args, **options):
        fdc_ids = collect_fdc_ids(
            fdc_ids=options.get("fdc_ids"),
            path=options.get("file"),
            limit=options.get("limit"),
        )
        if not fdc_ids:
            raise CommandError("provide at least one --fdc-id or --file")

        output = options["output"]
        snapshot = load_snapshot(output) or empty_snapshot()
        records = {food["fdc_id"]: food for food in snapshot["foods"]}
        pending = [
            fdc_id
            for fdc_id in fdc_ids
            if options["refresh"] or fdc_id not in records
        ]
        skipped = len(fdc_ids) - len(pending)

        api_key = getattr(settings, "USDA_API_KEY", None)
        if pending and not api_key:
            raise CommandError("set USDA_API_KEY before fetching USDA data")

        created = 0
        updated = 0
        failed = 0
        request_count = 0
        if pending:
            client = USDAClient(api_key)

        for fdc_id in pending:
            try:
                if request_count:
                    client.wait_for_rate_limit(options["min_remaining"])
                food = client.get_food(fdc_id)
                request_count += 1
                parsed = parse_food(food, fdc_id)
                record = snapshot_food(food, parsed)
                is_new = fdc_id not in records
                records[fdc_id] = record
                snapshot["foods"] = list(records.values())
                snapshot["retrieved_at"] = timezone.now().isoformat()
                if not options["dry_run"]:
                    write_snapshot(output, snapshot)
                action = "updated" if not is_new else "created"
                if is_new:
                    created += 1
                else:
                    updated += 1
                self.stdout.write(
                    f"{fdc_id}: {action} {record['description']}"
                )
            except (USDAAPIError, USDADataError) as exc:
                failed += 1
                self.stderr.write(f"{fdc_id}: skipped ({exc})")

        summary = (
            f"created={created} updated={updated} skipped={skipped} failed={failed}"
        )
        if options["dry_run"]:
            self.stdout.write(f"dry run: {summary}")
        else:
            self.stdout.write(self.style.SUCCESS(summary))

        if failed:
            raise CommandError(f"USDA snapshot fetch completed with errors: {summary}")
