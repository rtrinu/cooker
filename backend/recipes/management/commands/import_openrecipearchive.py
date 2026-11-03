import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from recipes.management.commands.import_usda import positive_int
from recipes.matching import IngredientIndex
from recipes.models import Ingredient, Recipe, RecipeIngredient
from recipes.openrecipearchive import (
    ENGLISH_COLLECTIONS,
    SOURCE,
    normalize_name,
    parse_record,
)

PROGRESS_INTERVAL = 250


class Command(BaseCommand):
    help = (
        "Import recipes from the Open Recipe Archive JSONL corpus "
        "(English collections by default)"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "paths",
            nargs="+",
            type=Path,
            help="JSONL files, collection directories, or a checkout of the archive",
        )
        parser.add_argument(
            "--collections",
            help=(
                "comma-separated collection slugs to import; default is the "
                "English collections, use 'all' for every collection"
            ),
        )
        parser.add_argument(
            "--limit",
            type=positive_int,
            help="import at most this many recipes",
        )
        parser.add_argument(
            "--offset",
            type=int,
            default=0,
            help="skip this many eligible recipes before importing",
        )
        parser.add_argument(
            "--batch-size",
            type=positive_int,
            default=100,
            help="number of recipes per progress report (not a transaction size)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="report actions without writing to the database",
        )
        parser.add_argument(
            "--report",
            type=Path,
            help="write every unmatched ingredient name and its suggestions",
        )
        parser.add_argument(
            "--servings-report",
            type=Path,
            help="write the recipes whose servings could not be determined",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="delete previously imported Open Recipe Archive recipes first",
        )

    def handle(self, *args, **options):
        if options["offset"] < 0:
            raise CommandError("--offset must be zero or greater")
        paths = self._expand(options["paths"])
        selected = self._selected_collections(options["collections"])

        if options["reset"]:
            if options["dry_run"]:
                self.stdout.write("dry run: would reset Open Recipe Archive recipes")
            else:
                recipes, ingredients = self._reset()
                self.stdout.write(
                    f"reset: removed {recipes} recipes and {ingredients} orphan ingredients"
                )

        self.index = IngredientIndex()
        self.cache = {}
        self.alias_updates = {}
        self.unmatched = Counter()
        self.unmatched_examples = defaultdict(list)
        self.unknown_servings = []
        self.no_amount = Counter()

        counts = Counter()
        eligible = 0
        stop = False

        for path in paths:
            if stop:
                break
            try:
                handle = path.open(encoding="utf-8")
            except OSError as exc:
                raise CommandError(f"could not read {path}: {exc}") from exc
            with handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    counts["scanned"] += 1
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as exc:
                        counts["failures"] += 1
                        self.stderr.write(f"{path}:{line_number}: invalid JSON ({exc})")
                        continue

                    collection = str(record.get("collection") or path.parent.name).strip()
                    record["collection"] = collection
                    if selected is not None and collection not in selected:
                        counts["collection_skipped"] += 1
                        continue
                    if str(record.get("license") or "") != "public-domain":
                        counts["license_skipped"] += 1
                        continue

                    parsed = parse_record(record)
                    if parsed is None:
                        counts["skipped"] += 1
                        continue
                    if eligible < options["offset"]:
                        eligible += 1
                        continue
                    eligible += 1

                    try:
                        created, ingredients = self._import(
                            parsed, options["dry_run"]
                        )
                    except Exception as exc:
                        counts["failures"] += 1
                        self.stderr.write(
                            f"{path}:{line_number}: {parsed.source_id}: {exc}"
                        )
                        continue

                    counts["created" if created else "updated"] += 1
                    counts["ingredients"] += ingredients
                    counts["processed"] += 1
                    for ingredient in parsed.ingredients:
                        if not ingredient.quantity:
                            self.no_amount[ingredient.name] += 1
                    if parsed.servings is None:
                        self.unknown_servings.append(parsed)

                    if counts["processed"] % options["batch_size"] == 0:
                        self.stderr.write(
                            f"progress processed={counts['processed']} "
                            f"created={counts['created']} updated={counts['updated']} "
                            f"scanned={counts['scanned']}"
                        )
                    if options["limit"] and counts["processed"] >= options["limit"]:
                        stop = True
                        break

        self._save_aliases()
        if options["report"]:
            self._write_unmatched_report(options["report"])
        if options["servings_report"]:
            self._write_servings_report(options["servings_report"])
        self._print_unknown_servings()

        summary = (
            f"created={counts['created']} updated={counts['updated']} "
            f"processed={counts['processed']} skipped={counts['skipped']} "
            f"ingredients={counts['ingredients']}"
        )
        if options["dry_run"]:
            self.stdout.write(f"dry run: {summary}")
        else:
            self.stdout.write(self.style.SUCCESS(summary))
        self.stdout.write(
            f"scanned={counts['scanned']} "
            f"collection_skipped={counts['collection_skipped']} "
            f"license_skipped={counts['license_skipped']} "
            f"no_servings={len(self.unknown_servings)} "
            f"no_amount_lines={sum(self.no_amount.values())} "
            f"unmatched_names={len(self.unmatched)} "
            f"unmatched_lines={sum(self.unmatched.values())}"
        )
        if self.unmatched:
            self._print_unmatched_summary()

        if counts["failures"]:
            raise CommandError(
                f"Open Recipe Archive import completed with "
                f"{counts['failures']} error(s)"
            )

    def _import(self, parsed, dry_run):
        existing = Recipe.objects.filter(
            source=SOURCE, source_id=parsed.source_id
        ).first()
        if dry_run:
            if existing is None:
                created = True
            else:
                created = False
            for item in parsed.ingredients:
                self._note_match(item.name, item.quantity, parsed.source_id)
            return created, len(parsed.ingredients)

        values = {
            "name": parsed.title,
            "description": "",
            "servings": parsed.servings,
            "serving_size": "",
            "prep_mins": None,
            "cook_mins": None,
            "tags": parsed.tags,
            "category": parsed.category,
            "contributor": parsed.contributor,
            "source_url": parsed.source_url[:200],
            "directions": parsed.directions,
            "source_title": parsed.source_title,
            "source_year": parsed.source_year,
            "license": parsed.license,
            "attribution": parsed.attribution,
            "collection": parsed.collection,
        }
        with transaction.atomic():
            if existing is None:
                recipe = Recipe.objects.create(
                    slug=self._unique_slug(parsed),
                    source=SOURCE,
                    source_id=parsed.source_id,
                    **values,
                )
                created = True
            else:
                recipe = existing
                for field, value in values.items():
                    setattr(recipe, field, value)
                recipe.save()
                created = False

            RecipeIngredient.objects.filter(recipe=recipe).delete()
            rows = []
            for position, item in enumerate(parsed.ingredients, start=1):
                ingredient, matched = self._resolve(item.name)
                if ingredient is None:
                    continue
                if not matched:
                    self._note_unmatched(item.name, item.quantity, parsed.source_id)
                rows.append(
                    RecipeIngredient(
                        recipe=recipe,
                        ingredient=ingredient,
                        quantity_text=item.quantity,
                        raw_text=item.raw,
                        position=position,
                    )
                )
            RecipeIngredient.objects.bulk_create(rows)
        return created, len(rows)

    def _resolve(self, name):
        normalized = normalize_name(name)
        if not normalized:
            return None, True
        key = normalized.casefold()
        if key in self.cache:
            return self.cache[key], True
        match = self.index.match(normalized)
        if match is not None:
            ingredient = match.ingredient
            self.cache[key] = ingredient
            if match.strategy not in {"exact", "casefold", "alias"}:
                self._add_alias(ingredient, normalized)
            return ingredient, True
        ingredient, _ = Ingredient.objects.get_or_create(name=normalized)
        self.cache[key] = ingredient
        return ingredient, False

    def _note_match(self, name, quantity, source_id):
        normalized = normalize_name(name)
        if not normalized:
            return
        if self.index.match(normalized) is None:
            self._note_unmatched(normalized, quantity, source_id)

    def _note_unmatched(self, name, quantity, source_id):
        name = normalize_name(name)
        if not name:
            return
        self.unmatched[name] += 1
        if len(self.unmatched_examples[name]) < 3:
            self.unmatched_examples[name].append(
                f"{source_id} ({quantity or 'no amount'})"
            )

    def _add_alias(self, ingredient, alias):
        if alias.casefold() == ingredient.name.casefold():
            return
        bucket = self.alias_updates.get(ingredient.pk)
        if bucket is None:
            bucket = [ingredient, list(ingredient.aliases or [])]
            self.alias_updates[ingredient.pk] = bucket
        if any(str(existing).casefold() == alias.casefold() for existing in bucket[1]):
            return
        bucket[1].append(alias)

    def _save_aliases(self):
        for ingredient, aliases in self.alias_updates.values():
            ingredient.aliases = aliases
            ingredient.save(update_fields=["aliases"])

    def _unique_slug(self, parsed):
        slug = parsed.slug
        if (
            Recipe.objects.filter(slug=slug)
            .exclude(source=SOURCE, source_id=parsed.source_id)
            .exists()
        ):
            digest = hashlib.sha1(parsed.source_id.encode("utf-8")).hexdigest()[:12]
            slug = f"{slug[:187]}-{digest}"
        return slug

    def _print_unmatched_summary(self):
        self.stdout.write(
            f"unmatched names={len(self.unmatched)} "
            f"lines={sum(self.unmatched.values())}"
        )
        ordered = sorted(
            self.unmatched.items(), key=lambda item: (-item[1], item[0].casefold())
        )
        for name, count in ordered[:20]:
            self.stdout.write(f"  {count:4}  {name}")
        if len(ordered) > 20:
            self.stdout.write("  ... use --report for the complete list")

    def _write_unmatched_report(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        ordered = sorted(
            self.unmatched.items(), key=lambda item: (-item[1], item[0].casefold())
        )
        lines = [
            f"Unmatched ingredient names: {len(ordered)} unique, "
            f"{sum(self.unmatched.values())} lines",
            "",
        ]
        for name, count in ordered:
            lines.append(f"{count:5}  {name}")
            lines.append(f"       e.g. {', '.join(self.unmatched_examples[name])}")
            suggestions = self.index.suggest(name, limit=3)
            if not suggestions:
                lines.append("       (no close candidate)")
            for match in suggestions:
                lines.append(f"       {match.score:.2f}  {match.ingredient.name}")
            lines.append("")
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        self.stdout.write(f"report: wrote {len(ordered)} names to {path}")

    def _write_servings_report(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [self._servings_line(parsed) for parsed in self.unknown_servings]
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        self.stdout.write(
            f"servings report: wrote {len(lines)} recipes to {path}"
        )

    def _print_unknown_servings(self):
        for parsed in self.unknown_servings:
            self.stdout.write(self.style.WARNING(self._servings_line(parsed)))

    @staticmethod
    def _servings_line(parsed):
        return (
            f'NO SERVINGS: {parsed.source_id} "{parsed.title}" — '
            f"{parsed.servings_note}; first instruction: "
            f"{parsed.first_instruction or '(none)'}"
        )

    def _reset(self):
        recipes = Recipe.objects.filter(source=SOURCE).count()
        Recipe.objects.filter(source=SOURCE).delete()
        orphans = (
            Ingredient.objects.filter(
                nutrition__isnull=True, measures__isnull=True
            )
            .filter(recipeingredient__isnull=True)
            .distinct()
        )
        ingredients = orphans.count()
        orphans.delete()
        return recipes, ingredients

    @staticmethod
    def _selected_collections(value):
        if not value:
            return ENGLISH_COLLECTIONS
        selected = {part.strip() for part in value.split(",") if part.strip()}
        if not selected or "all" in selected:
            return None
        return selected

    @staticmethod
    def _expand(paths):
        expanded = []
        missing = []
        for path in paths:
            if path.is_dir():
                found = sorted(path.rglob("recipes.jsonl"))
                if not found:
                    found = sorted(path.rglob("*.jsonl"))
                if not found:
                    raise CommandError(f"no JSONL files found in {path}")
                expanded.extend(found)
            elif path.is_file():
                if path.suffix.lower() != ".jsonl":
                    raise CommandError(f"not a JSONL file: {path}")
                expanded.append(path)
            else:
                missing.append(path)
        if missing:
            names = ", ".join(str(path) for path in missing)
            raise CommandError(f"no such file or directory: {names}")
        return list(dict.fromkeys(expanded))
