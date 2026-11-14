"""Repoint recipe lines at the measured ingredient they describe.

Public-domain recipes were imported before USDA nutrition was loaded, so they
created bare rows such as ``butter`` and ``flour`` that carry no nutrition.
Even after the USDA data arrived, an exact name match kept resolving those
lines to the empty row, and the calorie estimate silently skipped them. This
command applies the curated aliases to existing lines and removes the orphaned
bare rows, so later imports resolve to the measured ingredient too.
"""

import json
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from recipes.models import Ingredient, RecipeIngredient

ALIASES = Path(__file__).resolve().parents[2] / "data" / "aliases.json"


def add_alias(ingredient, alias):
    """Append ``alias`` to ``ingredient`` once, returning whether it changed."""
    alias = " ".join(str(alias or "").split())
    if not alias or alias.casefold() == ingredient.name.casefold():
        return False
    aliases = list(ingredient.aliases or [])
    if any(str(existing).casefold() == alias.casefold() for existing in aliases):
        return False
    aliases.append(alias)
    ingredient.aliases = aliases
    ingredient.save(update_fields=["aliases"])
    return True


class Command(BaseCommand):
    help = "Repoint recipe ingredients at their nutrition-bearing USDA row"

    def add_arguments(self, parser):
        parser.add_argument(
            "--aliases",
            type=Path,
            default=ALIASES,
            help=f"card-name to USDA-name mapping (default: {ALIASES})",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="report actions without writing to the database",
        )
        parser.add_argument(
            "--report",
            type=Path,
            help="write ingredient names that still have no nutrition",
        )

    def handle(self, *args, **options):
        mapping = self._read(options["aliases"])
        targets = {}
        missing = []
        for card, usda in mapping.items():
            target = Ingredient.objects.filter(name=usda).first()
            if target is None or not target.nutrition.exists():
                missing.append(usda)
                continue
            targets[card.casefold()] = target

        repointed = aliases_added = 0
        for bare in Ingredient.objects.filter(nutrition__isnull=True).order_by("name"):
            target = targets.get(bare.name.casefold())
            if target is None or target.pk == bare.pk:
                continue
            rows = RecipeIngredient.objects.filter(ingredient=bare)
            count = rows.count()
            if not count:
                continue
            repointed += count
            if not options["dry_run"]:
                rows.update(ingredient=target)
                if add_alias(target, bare.name):
                    aliases_added += 1

        removed = 0
        if not options["dry_run"]:
            removed, _ = (
                Ingredient.objects.filter(
                    nutrition__isnull=True,
                    measures__isnull=True,
                    recipeingredient__isnull=True,
                )
                .distinct()
                .delete()
            )

        unresolved = self._unresolved()
        if options["report"]:
            self._write_report(options["report"], unresolved)

        for usda in missing:
            self.stderr.write(f"alias target has no nutrition: {usda}")

        summary = (
            f"repointed={repointed} aliases={aliases_added} removed={removed} "
            f"unresolved_names={len(unresolved)} "
            f"unresolved_lines={sum(unresolved.values())}"
        )
        if options["dry_run"]:
            self.stdout.write(f"dry run: {summary}")
        else:
            self.stdout.write(self.style.SUCCESS(summary))

    def _read(self, path):
        try:
            mapping = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"could not read aliases from {path}: {exc}") from exc
        if not isinstance(mapping, dict):
            raise CommandError(f"{path} must contain a JSON object")
        return mapping

    def _unresolved(self):
        counts = Counter()
        rows = RecipeIngredient.objects.select_related("ingredient").prefetch_related(
            "ingredient__nutrition"
        )
        for row in rows:
            if not row.ingredient.nutrition.all():
                counts[row.ingredient.name] += 1
        return counts

    def _write_report(self, path, unresolved):
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            f"Ingredients still without nutrition: {len(unresolved)} names, "
            f"{sum(unresolved.values())} lines",
            "",
        ]
        for name, count in unresolved.most_common():
            lines.append(f"{count:5}  {name}")
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        self.stdout.write(f"report: wrote {len(unresolved)} names to {path}")
