"""Rank the ingredient names that still have no nutrition by calorie impact.

An unresolved line contributes nothing to a computed panel, so a name that
appears often or in large amounts costs more accuracy than a rare garnish. This
command estimates that cost: for each nutritionless name it converts the recipe
amounts against the closest nutrition-bearing candidate and sums the calories
those lines would have added.

The candidates are *suggestions only*. Fuzzy matching is often wrong on
historical and card wording ("sifted flour" lands on potato flour), so nothing
is written here. The report is a worklist for a human to turn the clear cases
into curated aliases in ``data/aliases.json``; ambiguous names stay unresolved
until there is evidence for them.
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from recipes.matching import IngredientIndex
from recipes.models import RecipeIngredient
from recipes.nutrition import best_nutrition, scale_nutrients
from recipes.units import parse_quantity, resolve_grams


class Command(BaseCommand):
    help = "Rank unresolved ingredient names by their estimated calorie impact"

    def add_arguments(self, parser):
        parser.add_argument(
            "--report",
            type=Path,
            help="write the ranked gap list, with candidate suggestions",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=40,
            help="how many names to print (default: 40; 0 prints none)",
        )
        parser.add_argument(
            "--min-score",
            type=float,
            default=0.3,
            help="minimum fuzzy score for a candidate to be considered (default: 0.3)",
        )
        parser.add_argument(
            "--suggestions",
            type=int,
            default=3,
            help="candidate suggestions to show per name (default: 3)",
        )

    def handle(self, *args, **options):
        minimum = options["min_score"]
        if not 0 <= minimum <= 1:
            raise CommandError("--min-score must be between 0 and 1")

        index = IngredientIndex()
        gaps = self._collect(index, minimum, max(1, options["suggestions"]))
        ranked = sorted(
            gaps.values(), key=lambda gap: (gap["kcal"], gap["lines"]), reverse=True
        )

        total_lines = sum(gap["lines"] for gap in ranked)
        total_kcal = sum(gap["kcal"] for gap in ranked)
        self.stdout.write(
            self.style.SUCCESS(
                f"unresolved_names={len(ranked)} unresolved_lines={total_lines} "
                f"estimated_kcal={total_kcal:.0f}"
            )
        )

        for gap in ranked[: max(0, options["limit"])]:
            self.stdout.write(
                f"  {gap['kcal']:8.0f} kcal  {gap['lines']:3} lines  "
                f"{gap['measurable']:3} measurable  {gap['name'][:52]:54} "
                f"-> {gap['candidates'][0] if gap['candidates'] else '(no candidate)'}"
            )

        if options["report"]:
            self._write_report(options["report"], ranked)

    def _collect(self, index, minimum, suggestion_count):
        gaps = {}
        rows = RecipeIngredient.objects.select_related("ingredient").prefetch_related(
            "ingredient__nutrition", "ingredient__measures"
        )
        for row in rows:
            ingredient = row.ingredient
            if ingredient.nutrition.all():
                continue
            gap = gaps.setdefault(
                ingredient.name,
                {
                    "name": ingredient.name,
                    "lines": 0,
                    "measurable": 0,
                    "no_amount": 0,
                    "no_candidate": 0,
                    "no_measure": 0,
                    "kcal": 0.0,
                    "candidates": [],
                    "best_score": 0.0,
                },
            )
            gap["lines"] += 1
            quantity = parse_quantity(row.quantity_text)
            if quantity.amount is None:
                gap["no_amount"] += 1
                continue
            suggestions = index.suggest(
                ingredient.name, limit=suggestion_count, threshold=minimum
            )
            if not suggestions:
                gap["no_candidate"] += 1
                continue
            if not gap["candidates"]:
                gap["candidates"] = [
                    f"{match.ingredient.name} ({match.score:.2f})"
                    for match in suggestions
                ]
            best = suggestions[0]
            if best.score > gap["best_score"]:
                gap["best_score"] = best.score
            conversion = resolve_grams(
                best.ingredient,
                quantity,
                f"{best.ingredient.name} {row.raw_text or ingredient.name}",
            )
            if conversion is None:
                gap["no_measure"] += 1
                continue
            nutrition = best_nutrition(best.ingredient)
            if nutrition is None:
                gap["no_candidate"] += 1
                continue
            gap["measurable"] += 1
            gap["kcal"] += scale_nutrients(nutrition, conversion.grams)["kcal"]
        return gaps

    def _write_report(self, path, ranked):
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "Unresolved ingredient names ranked by estimated calorie impact",
            "",
            "kcal is what the lines would add against the first candidate; it is",
            "an estimate, not a decision. Candidates are suggestions, not aliases.",
            "",
        ]
        for gap in ranked:
            lines.append(
                f"{gap['kcal']:9.0f} kcal  {gap['lines']:4} lines  "
                f"{gap['measurable']:4} measurable  {gap['name']}"
            )
            lines.append(
                f"    no amount={gap['no_amount']} no candidate={gap['no_candidate']} "
                f"no measure={gap['no_measure']} best_score={gap['best_score']:.2f}"
            )
            for candidate in gap["candidates"]:
                lines.append(f"    candidate: {candidate}")
            lines.append("")
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        self.stdout.write(f"report: wrote {len(ranked)} names to {path}")
