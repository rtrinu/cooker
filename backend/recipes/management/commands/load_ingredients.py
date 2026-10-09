"""Load curated ingredient names, aliases, and categories from ingredients.json.

The USDA importers enrich ingredients with nutrition data but never fill the
``aliases`` field, and only set a category when the ingredient has none. This
command is the curated layer on top: every record in
``recipes/fixtures/ingredients.json`` is upserted by its canonical ``name``,
replacing the stored aliases and category.

Running it before or after USDA imports is safe:
* Ingredients already created by ``import_usda*`` keep their nutrition rows and
  just gain aliases and a category.
* The USDA upsert only writes a category when ``Ingredient.category`` is empty,
  so a curated category set here is never clobbered by a later import.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from recipes.models import Ingredient

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"
DEFAULT_FIXTURE = FIXTURES_DIR / "ingredients.json"


def normalize_aliases(aliases):
    """Lowercase, strip, and de-duplicate an alias list, preserving order."""
    seen = set()
    normalized = []
    for alias in aliases:
        text = " ".join(str(alias).split()).lower()
        if text and text not in seen:
            seen.add(text)
            normalized.append(text)
    return normalized


class Command(BaseCommand):
    help = "Upsert curated ingredients from ingredients.json (names, aliases, categories)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=Path,
            default=DEFAULT_FIXTURE,
            help="path to the ingredients JSON file (default: the app fixture)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="report what would change without writing to the database",
        )

    def handle(self, *args, **options):
        path = options["file"]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise CommandError(f"could not read {path}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise CommandError(f"{path} is not valid JSON: {exc}") from exc
        if not isinstance(data, list):
            raise CommandError(f"{path} must contain a JSON array of ingredient objects")

        records, failed = [], 0
        for offset, item in enumerate(data, start=1):
            try:
                records.append(self._parse_record(item))
            except ValueError as exc:
                failed += 1
                self.stderr.write(f"entry {offset}: skipped ({exc})")
        if failed:
            raise CommandError(
                f"{path} has {failed} invalid entry/entries; nothing was loaded"
            )

        created, updated = self._apply(records, path, options["dry_run"])
        summary = f"created={created} updated={updated}"
        if options["dry_run"]:
            self.stdout.write(f"dry run: {summary}")
        else:
            self.stdout.write(self.style.SUCCESS(summary))

    @staticmethod
    def _parse_record(item):
        if not isinstance(item, dict):
            raise ValueError("must be an object with name, aliases, and category")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("name is required")
        name = " ".join(name.split())
        if len(name) > 255:
            raise ValueError(f"name exceeds 255 characters: {name}")

        aliases = item.get("aliases")
        if aliases is None:
            aliases = []
        if not isinstance(aliases, list) or not all(
            isinstance(alias, str) for alias in aliases
        ):
            raise ValueError(f"aliases for {name} must be a list of strings")
        aliases = normalize_aliases(aliases)

        category = item.get("category")
        if category is not None:
            if not isinstance(category, str) or not category.strip():
                raise ValueError(f"category for {name} must be a non-empty string")
            category = " ".join(category.split())
            if len(category) > 50:
                raise ValueError(f"category for {name} exceeds 50 characters")

        return {"name": name, "aliases": aliases, "category": category}

    def _apply(self, records, path, dry_run):
        created = updated = 0
        names = {record["name"] for record in records}
        if len(names) != len(records):
            raise CommandError(f"{path} has duplicate ingredient names")

        with transaction.atomic():
            for record in records:
                defaults = {"aliases": record["aliases"]}
                if record["category"] is not None:
                    defaults["category"] = record["category"]

                if dry_run:
                    if Ingredient.objects.filter(name=record["name"]).exists():
                        updated += 1
                        self.stdout.write(f"would update {record['name']}")
                    else:
                        created += 1
                        self.stdout.write(f"would create {record['name']}")
                    continue

                _, was_created = Ingredient.objects.update_or_create(
                    name=record["name"], defaults=defaults
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
        return created, updated