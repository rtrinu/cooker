"""Rebuild computed nutrition after ingredient data or matching changes.

Every recipe is recomputed from its current ingredient lines. Printed panels
live on ``NutritionReference`` and are never touched here: they are the source's
own numbers, kept for validation. A partial sum can only undercount the dish,
so it is stored as a lower bound with its coverage and confidence, and reported
with the lines that could not be measured.
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from recipes.models import Nutrition, Recipe, RecipeIngredient
from recipes.nutrition import (
    MIN_CONFIDENCE,
    apply_line_conversions,
    compute,
    coverage,
)


class Command(BaseCommand):
    help = "Recompute every recipe's nutrition from its ingredient lines"

    def add_arguments(self, parser):
        parser.add_argument(
            "--min-coverage",
            type=float,
            default=0.0,
            help=(
                "optional floor: skip computed panels below this share of "
                "resolved ingredient lines (default: 0, keep every partial "
                "estimate as a lower bound)"
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="report actions without writing to the database",
        )
        parser.add_argument(
            "--report",
            type=Path,
            help="write recipes whose estimate is a lower bound",
        )

    def handle(self, *args, **options):
        minimum = options["min_coverage"]
        if not 0 <= minimum <= 1:
            raise CommandError("--min-coverage must be between 0 and 1")

        recipes = (
            Recipe.objects.select_related("nutrition")
            .prefetch_related(
                "ingredients__ingredient__nutrition",
                "ingredients__ingredient__measures",
            )
            .order_by("name")
        )
        created = updated = removed = low_confidence = 0
        partial = []

        for recipe in recipes:
            existing = getattr(recipe, "nutrition", None)
            rows = list(recipe.ingredients.all())
            pairs = [
                (row.ingredient, row.quantity_text, row.raw_text or row.ingredient.name)
                for row in rows
            ]
            computed = compute(pairs, recipe.servings)
            # Refresh the persisted per-line grams even when the recipe has no
            # published panel; a line that converted is still evidence of the
            # ingredient data behind it.
            if rows:
                fields = apply_line_conversions(computed, rows)
                if not options["dry_run"]:
                    RecipeIngredient.objects.bulk_update(rows, fields)
            share = coverage(computed)
            usable = bool(recipe.servings) and computed.lines_used > 0
            usable = usable and computed.totals["kcal"] > 0
            usable = usable and share >= minimum

            if not usable:
                if existing is not None:
                    removed += 1
                    if not options["dry_run"]:
                        existing.delete()
                continue

            if share < 1 or computed.confidence < MIN_CONFIDENCE:
                partial.append((recipe, share, computed))
            if computed.confidence < MIN_CONFIDENCE:
                low_confidence += 1

            defaults = {
                **computed.per_serving,
                "method": "computed",
                "lines_used": computed.lines_used,
                "lines_total": computed.lines_total,
                "weight_g": computed.weight_g,
                "confidence": computed.confidence,
                "warnings": computed.warnings,
            }
            if existing is None:
                created += 1
                if not options["dry_run"]:
                    Nutrition.objects.create(recipe=recipe, **defaults)
            else:
                updated += 1
                if not options["dry_run"]:
                    for field, value in defaults.items():
                        setattr(existing, field, value)
                    existing.save()

        if options["report"]:
            self._write_report(options["report"], partial)

        summary = (
            f"created={created} updated={updated} removed={removed} "
            f"partial={len(partial)} low_confidence={low_confidence}"
        )
        if options["dry_run"]:
            self.stdout.write(f"dry run: {summary}")
        else:
            self.stdout.write(self.style.SUCCESS(summary))

    def _write_report(self, path, partial):
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "Recipes whose computed nutrition is a lower bound",
            "",
        ]
        for recipe, share, computed in partial:
            lines.append(
                f"{recipe.slug or recipe.pk}  {recipe.name}  "
                f"coverage={share:.0%} ({computed.lines_used}/{computed.lines_total})"
            )
            for entry in computed.unresolved:
                lines.append(
                    f"    {entry['reason']}: {entry['quantity'] or '(no amount)'} "
                    f"{entry['ingredient']}"
                )
            lines.append("")
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        self.stdout.write(f"report: wrote {len(partial)} recipes to {path}")
