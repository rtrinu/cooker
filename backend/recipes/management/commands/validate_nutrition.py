"""Compare computed nutrition with the printed panels that act as ground truth.

Only recipes whose source prints a "Nutrients Per Serving" panel can be
checked: they are the one place where the true per-serving calories are known.
The command recomputes each of those recipes from its ingredient lines and
reports how close the calculation gets, together with the lines that could not
be measured. It is a regression check for matching and unit-conversion changes,
not a source of published nutrition: the printed panel always wins.
"""

import statistics
from pathlib import Path

from django.core.management.base import BaseCommand

from recipes.models import Nutrition
from recipes.nutrition import compute, coverage


class Command(BaseCommand):
    help = "Score computed nutrition against printed source panels"

    def add_arguments(self, parser):
        parser.add_argument(
            "--report",
            type=Path,
            help="write a per-recipe comparison and its unresolved lines",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=10,
            help="how many of the furthest-off recipes to print (default: 10)",
        )

    def handle(self, *args, **options):
        rows = []
        for source in (
            Nutrition.objects.filter(method="source")
            .select_related("recipe")
            .order_by("recipe__name")
        ):
            recipe = source.recipe
            pairs = [
                (line.ingredient, line.quantity_text)
                for line in recipe.ingredients.select_related("ingredient")
            ]
            computed = compute(pairs, recipe.servings)
            rows.append((recipe, source, computed))

        compared = []
        unmeasurable = []
        for recipe, source, computed in rows:
            if not recipe.servings or not computed.lines_used or not source.kcal:
                unmeasurable.append((recipe, source, computed))
                continue
            compared.append(
                (
                    recipe,
                    source,
                    computed,
                    computed.per_serving["kcal"] / source.kcal,
                    coverage(computed),
                )
            )

        ratios = [row[3] for row in compared]
        summary = (
            f"printed={len(rows)} compared={len(compared)} "
            f"unmeasurable={len(unmeasurable)}"
        )
        if ratios:
            summary += (
                f" median_ratio={statistics.median(ratios):.2f}"
                f" mean_ratio={statistics.mean(ratios):.2f}"
                f" within_10={self._within(ratios, 0.10)}"
                f" within_20={self._within(ratios, 0.20)}"
                f" at_least_half={sum(1 for ratio in ratios if ratio >= 0.5)}"
            )
        self.stdout.write(self.style.SUCCESS(summary))

        for recipe, source, computed, ratio, share in sorted(
            compared, key=lambda row: abs(row[3] - 1), reverse=True
        )[: max(0, options["limit"])]:
            self.stdout.write(
                f"  {recipe.name[:48]:50} printed={source.kcal:7.1f} "
                f"computed={computed.per_serving['kcal']:7.1f} "
                f"ratio={ratio:5.2f} coverage={share:4.0%} "
                f"({computed.lines_used}/{computed.lines_total})"
            )

        for recipe, source, computed in unmeasurable:
            self.stdout.write(
                f"  unmeasurable {recipe.name[:48]:50} "
                f"printed={source.kcal:7.1f} "
                f"({computed.lines_used}/{computed.lines_total})"
            )

        if options["report"]:
            self._write_report(options["report"], compared, unmeasurable)

    def _within(self, ratios, tolerance):
        return sum(1 for ratio in ratios if abs(ratio - 1) <= tolerance)

    def _write_report(self, path, compared, unmeasurable):
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "Computed nutrition versus printed source panels",
            "",
            f"compared: {len(compared)}",
            f"unmeasurable: {len(unmeasurable)}",
            "",
        ]
        for recipe, source, computed, ratio, share in sorted(
            compared, key=lambda row: row[3]
        ):
            lines.append(
                f"{recipe.slug or recipe.pk}  {recipe.name}  "
                f"printed={source.kcal:.1f} computed={computed.per_serving['kcal']:.1f} "
                f"ratio={ratio:.2f} coverage={share:.0%} "
                f"({computed.lines_used}/{computed.lines_total})"
            )
            for entry in computed.unresolved:
                lines.append(
                    f"    {entry['reason']}: {entry['quantity'] or '(no amount)'} "
                    f"{entry['ingredient']}"
                )
            lines.append("")
        for recipe, source, computed in unmeasurable:
            lines.append(
                f"{recipe.slug or recipe.pk}  {recipe.name}  "
                f"unmeasurable printed={source.kcal:.1f} "
                f"({computed.lines_used}/{computed.lines_total})"
            )
            for entry in computed.unresolved:
                lines.append(
                    f"    {entry['reason']}: {entry['quantity'] or '(no amount)'} "
                    f"{entry['ingredient']}"
                )
            lines.append("")
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        self.stdout.write(f"report: wrote {len(compared) + len(unmeasurable)} recipes to {path}")
