"""Compare computed nutrition with the printed panels kept as ground truth.

Only recipes whose source prints a "Nutrients Per Serving" panel can be
checked: they are the one place where the true per-serving values are known.
The printed panel lives on ``NutritionReference`` because the published
``Nutrition`` row is always computed from the ingredients. This command
recomputes each referenced recipe, scores it against the printed calories and
macros, and reports the lines that could not be measured. It is a regression
check for matching and unit-conversion changes, not a source of published
nutrition: the printed panel is ground truth, not the served figure.
"""

import statistics
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand

from recipes.models import NUTRIENT_FIELDS, NutritionReference
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
        references = (
            NutritionReference.objects.select_related("recipe")
            .prefetch_related(
                "recipe__ingredients__ingredient__nutrition",
                "recipe__ingredients__ingredient__measures",
            )
            .order_by("recipe__name")
        )
        for reference in references:
            recipe = reference.recipe
            pairs = [
                (line.ingredient, line.quantity_text, line.raw_text or line.ingredient.name)
                for line in recipe.ingredients.all()
            ]
            computed = compute(pairs, recipe.servings)
            rows.append((recipe, reference, computed))

        compared = []
        unmeasurable = []
        for recipe, reference, computed in rows:
            if not recipe.servings or not computed.lines_used or not reference.kcal:
                unmeasurable.append((recipe, reference, computed))
                continue
            compared.append(
                (
                    recipe,
                    reference,
                    computed,
                    computed.per_serving["kcal"] / reference.kcal,
                    coverage(computed),
                )
            )

        gaps = Counter()
        for _recipe, _reference, computed in rows:
            for entry in computed.unresolved:
                reason = entry["reason"]
                if reason.endswith(" measure"):
                    reason = "no measure"
                gaps[reason] += 1

        ratios = [row[3] for row in compared]
        summary = (
            f"printed={len(rows)} compared={len(compared)} "
            f"unmeasurable={len(unmeasurable)}"
        )
        if gaps:
            summary += f" gaps={self._gap_summary(gaps)}"
        if ratios:
            summary += (
                f" median_ratio={statistics.median(ratios):.2f}"
                f" mean_ratio={statistics.mean(ratios):.2f}"
                f" within_10={self._within(ratios, 0.10)}"
                f" within_20={self._within(ratios, 0.20)}"
                f" at_least_half={sum(1 for ratio in ratios if ratio >= 0.5)}"
            )
        self.stdout.write(self.style.SUCCESS(summary))

        macro_line = self._macro_summary(compared)
        if macro_line:
            self.stdout.write(f"  {macro_line}")

        for recipe, reference, computed, ratio, share in sorted(
            compared, key=lambda row: abs(row[3] - 1), reverse=True
        )[: max(0, options["limit"])]:
            self.stdout.write(
                f"  {recipe.name[:48]:50} printed={reference.kcal:7.1f} "
                f"computed={computed.per_serving['kcal']:7.1f} "
                f"ratio={ratio:5.2f} coverage={share:4.0%} "
                f"confidence={computed.confidence:4.2f} "
                f"({computed.lines_used}/{computed.lines_total})"
                + self._warning_suffix(computed)
            )

        for recipe, reference, computed in unmeasurable:
            self.stdout.write(
                f"  unmeasurable {recipe.name[:48]:50} "
                f"printed={reference.kcal:7.1f} "
                f"({computed.lines_used}/{computed.lines_total})"
                + self._warning_suffix(computed)
            )

        if options["report"]:
            self._write_report(options["report"], compared, unmeasurable, gaps)

    @staticmethod
    def _gap_summary(gaps):
        """Compact worklist of why lines did not contribute."""
        return " ".join(
            f"{reason.replace(' ', '-')}={count}"
            for reason, count in sorted(gaps.items(), key=lambda item: -item[1])
        )

    def _macro_summary(self, compared):
        """Median computed/printed ratio for each macro, when both are present."""
        parts = []
        for field in NUTRIENT_FIELDS:
            if field == "kcal":
                continue
            ratios = [
                computed.per_serving[field] / getattr(reference, field)
                for _recipe, reference, computed, _ratio, _share in compared
                if getattr(reference, field)
            ]
            if ratios:
                parts.append(f"{field}_median={statistics.median(ratios):.2f}")
        return " ".join(parts)

    def _warning_suffix(self, computed):
        if not computed.warnings:
            return ""
        return " warnings=" + ",".join(computed.warnings)

    def _within(self, ratios, tolerance):
        return sum(1 for ratio in ratios if abs(ratio - 1) <= tolerance)

    def _write_report(self, path, compared, unmeasurable, gaps):
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "Computed nutrition versus printed source panels",
            "",
            f"compared: {len(compared)}",
            f"unmeasurable: {len(unmeasurable)}",
            f"unresolved reasons: {self._gap_summary(gaps) if gaps else 'none'}",
            "",
        ]
        for recipe, reference, computed, ratio, share in sorted(
            compared, key=lambda row: row[3]
        ):
            lines.append(
                f"{recipe.slug or recipe.pk}  {recipe.name}  "
                f"printed={reference.kcal:.1f} computed={computed.per_serving['kcal']:.1f} "
                f"ratio={ratio:.2f} coverage={share:.0%} "
                f"confidence={computed.confidence:.2f} "
                f"({computed.lines_used}/{computed.lines_total})"
                f"{self._warning_suffix(computed)}"
            )
            for field in NUTRIENT_FIELDS:
                if field == "kcal":
                    continue
                printed = getattr(reference, field)
                if not printed:
                    continue
                lines.append(
                    f"    {field}: printed={printed:.1f} "
                    f"computed={computed.per_serving[field]:.1f} "
                    f"ratio={computed.per_serving[field] / printed:.2f}"
                )
            for entry in computed.unresolved:
                lines.append(
                    f"    {entry['reason']}: {entry['quantity'] or '(no amount)'} "
                    f"{entry['ingredient']}"
                )
            lines.append("")
        for recipe, reference, computed in unmeasurable:
            lines.append(
                f"{recipe.slug or recipe.pk}  {recipe.name}  "
                f"unmeasurable printed={reference.kcal:.1f} "
                f"({computed.lines_used}/{computed.lines_total})"
                f"{self._warning_suffix(computed)}"
            )
            for entry in computed.unresolved:
                lines.append(
                    f"    {entry['reason']}: {entry['quantity'] or '(no amount)'} "
                    f"{entry['ingredient']}"
                )
            lines.append("")
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        self.stdout.write(
            f"report: wrote {len(compared) + len(unmeasurable)} recipes to {path}"
        )
