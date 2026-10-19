import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from recipes.management.commands.import_usda import positive_int
from recipes.matching import IngredientIndex
from recipes.pdf import parse_pdf
from recipes.recipe_import import load_aliases, reset_recipes, save_recipe


class Command(BaseCommand):
    help = "Import recipes from USDA Team Nutrition PDF cards"

    def add_arguments(self, parser):
        parser.add_argument(
            "paths",
            nargs="+",
            type=Path,
            help="PDF files, or directories whose *.pdf files are imported",
        )
        parser.add_argument(
            "--slug",
            help="override the slug derived from the title (single file only)",
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
        parser.add_argument(
            "--aliases",
            type=Path,
            help="JSON {card name: USDA ingredient name} seed loaded before import",
        )
        parser.add_argument(
            "--report",
            type=Path,
            help="write top-3 match suggestions for unmatched ingredient names",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="delete imported recipes and junk ingredients before importing",
        )

    def handle(self, *args, **options):
        paths = self._expand(options["paths"])
        if options["slug"] and len(paths) != 1:
            raise CommandError("--slug can only be used with a single PDF")

        if options["aliases"]:
            self._load_aliases(options["aliases"])
        if options["reset"]:
            removed = reset_recipes()
            self.stdout.write(f"reset: removed imported recipes and {removed} junk ingredients")

        counts = {
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "ingredients": 0,
            "unresolved": 0,
            "unmatched": 0,
        }
        failures = 0
        report = {}

        for path in paths:
            if options["limit"] and counts["created"] + counts["updated"] >= options["limit"]:
                break
            try:
                data = parse_pdf(path)
            except Exception as exc:
                failures += 1
                self.stderr.write(f"{path}: could not read ({exc})")
                continue
            if data is None:
                counts["skipped"] += 1
                self.stdout.write(f"{path}: skipped (no recipe found)")
                continue

            result = save_recipe(data, slug=options["slug"], dry_run=options["dry_run"])
            if options["dry_run"]:
                verb = "would create" if result.created else "would update"
            else:
                verb = "created" if result.created else "updated"
            self.stdout.write(
                f"{path}: {verb} {result.slug} ({result.ingredients} ingredients)"
            )
            if result.created:
                counts["created"] += 1
            else:
                counts["updated"] += 1
            counts["ingredients"] += result.ingredients
            counts["unresolved"] += len(result.unresolved)
            for entry in result.unresolved:
                self.stderr.write(
                    f"{path}: unresolved {entry['ingredient']} "
                    f"({entry['quantity']}): {entry['reason']}"
                )
            for name, quantity in result.unmatched:
                counts["unmatched"] += 1
                if options["report"]:
                    report.setdefault(name, quantity)

        if options["report"]:
            self._write_report(options["report"], report)

        summary = (
            f"created={counts['created']} updated={counts['updated']} "
            f"skipped={counts['skipped']} ingredients={counts['ingredients']} "
            f"unmatched={counts['unmatched']} unresolved={counts['unresolved']}"
        )
        if options["dry_run"]:
            self.stdout.write(f"dry run: {summary}")
        else:
            self.stdout.write(self.style.SUCCESS(summary))

        if failures:
            raise CommandError(f"recipe import completed with {failures} unreadable file(s)")

    def _load_aliases(self, path):
        try:
            mapping = json.loads(path.read_text())
        except FileNotFoundError:
            raise CommandError(f"no such alias file: {path}")
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"could not read alias file {path}: {exc}")
        if not isinstance(mapping, dict):
            raise CommandError("alias file must be a JSON object")
        missing = load_aliases(mapping)
        self.stdout.write(f"aliases: loaded {len(mapping) - len(missing)} of {len(mapping)}")
        for name in missing:
            self.stderr.write(f"alias target not found: {name}")

    def _write_report(self, path, names):
        index = IngredientIndex()
        lines = []
        for name in sorted(names):
            lines.append(f"{name}")
            suggestions = index.suggest(name)
            if not suggestions:
                lines.append("    (no close candidate)")
            for match in suggestions:
                lines.append(f"    {match.score:.2f}  {match.ingredient.name}")
        path.write_text("\n".join(lines) + "\n")
        self.stdout.write(f"report: wrote {len(names)} names to {path}")

    @staticmethod
    def _expand(paths):
        expanded = []
        missing = []
        for path in paths:
            if path.is_dir():
                found = sorted(path.glob("*.pdf"))
                if not found:
                    raise CommandError(f"no PDF files found in {path}")
                expanded.extend(found)
            elif path.is_file():
                if path.suffix.lower() != ".pdf":
                    raise CommandError(f"not a PDF file: {path}")
                expanded.append(path)
            else:
                missing.append(path)
        if missing:
            names = ", ".join(str(path) for path in missing)
            raise CommandError(f"no such file or directory: {names}")
        return expanded
