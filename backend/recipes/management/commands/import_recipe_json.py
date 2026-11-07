import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from recipes.management.commands.import_usda import positive_int
from recipes.recipe_import import save_recipe


class Command(BaseCommand):
    help = "Import a bulk JSON recipe file, including printed nutrition panels"

    def add_arguments(self, parser):
        parser.add_argument(
            "path",
            type=Path,
            help="JSON file containing a recipe collection",
        )
        parser.add_argument(
            "--limit",
            type=positive_int,
            help="import at most this many recipes",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="report actions without writing to the database",
        )

    def handle(self, *args, **options):
        payload = self._read(options["path"])
        recipes = payload.get("recipes")
        if not isinstance(recipes, list):
            raise CommandError("recipe file must contain a recipes array")

        metadata = {
            key: payload[key]
            for key in (
                "source",
                "source_title",
                "source_year",
                "license",
                "attribution",
                "collection",
                "category",
            )
            if payload.get(key)
        }

        created = updated = failed = 0
        for index, entry in enumerate(recipes, start=1):
            if options["limit"] and index > options["limit"]:
                break
            if not isinstance(entry, dict):
                failed += 1
                self.stderr.write(f"recipe {index}: skipped (not an object)")
                continue
            recipe_metadata = {**metadata, **{
                key: entry[key]
                for key in ("source_id", "source_url", "source_title", "source_year", "license")
                if entry.get(key)
            }}
            recipe_data = {**entry, "title": entry.get("name") or entry.get("title")}
            try:
                result = save_recipe(
                    recipe_data,
                    dry_run=options["dry_run"],
                    metadata=recipe_metadata,
                )
            except Exception as exc:  # noqa: BLE001 - report one bad row, keep importing
                failed += 1
                self.stderr.write(f"recipe {index}: skipped ({exc})")
                continue
            if result.created:
                created += 1
                verb = "would create" if options["dry_run"] else "created"
            else:
                updated += 1
                verb = "would update" if options["dry_run"] else "updated"
            self.stdout.write(f"{index}: {verb} {result.slug} ({result.ingredients} ingredients)")

        summary = f"created={created} updated={updated} failed={failed}"
        if options["dry_run"]:
            self.stdout.write(f"dry run: {summary}")
        else:
            self.stdout.write(self.style.SUCCESS(summary))
        if failed:
            raise CommandError(f"recipe import completed with errors: {summary}")

    @staticmethod
    def _read(path):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise CommandError(f"no such recipe file: {path}") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"could not read recipe file {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise CommandError("recipe file must contain a JSON object")
        return payload
