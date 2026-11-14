"""Rebuild computed nutrition after ingredient data or matching changes.

Printed panels are never touched: they are the source's own numbers. Every
other recipe is recomputed from its current ingredient lines. A partial sum
can only undercount the dish, so it is stored as a lower bound and reported
with the lines that could not be measured.
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from recipes.models import Nutrition, Recipe
from recipes.nutrition import compute, coverage


class Command(BaseCommand):
    help = "Recompute nutrition for recipes that do not have a printed panel"

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
            .prefetch_related("ingredients__ingredient__nutrition")
            .order_by("name")
        )
        created = updated = removed = kept = 0
        partial = []

        for recipe in recipes:
            existing = getattr(recipe, "nutrition", None)
            if existing is not None and existing.method == "source":
                kept += 1
                continue

            pairs = [
                (row.ingredient, row.quantity_text) for row in recipe.ingredients.all()
            ]
            computed = compute(pairs, recipe.servings or 1)
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

            if share < 1:
                partial.append((recipe, share, computed))

            defaults = {
                **computed.per_serving,
                "method": "computed",
                "lines_used": computed.lines_used,
                "lines_total": computed.lines_total,
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
            f"source_kept={kept} partial={len(partial)}"
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
