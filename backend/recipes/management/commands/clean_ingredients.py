"""Clean ingredient rows into pantry names.

Jobs:

* remove kitchen equipment that recipes list as ingredients (foil, paper,
  skewers) together with the recipe lines that mention it;
* rewrite alcoholic beverages from USDA's ``Alcoholic Beverage, wine, table,
  red, Barbera`` shape into ``Barbera (red wine)`` with an ``Alcoholic
  Beverage`` category, merging rows that collapse to the same name;
* reduce parsed names to the ingredient itself, dropping a second measure,
  grade, size or alternative that survived import (``/500g liver``,
  ``00 or 0 flour``, ``3 large turnips``);
* remove the categories that are prepared restaurant/market products or baby
  food rather than ingredients a pantry finder should offer;
* delete ingredient rows that no recipe uses and that carry no nutrition data,
  which are the names a re-import with a better parser leaves behind.

The command is safe to re-run. An ingredient still referenced by a recipe is
merged into its target rather than deleted, except for equipment, whose recipe
lines are removed because it was never an ingredient.
"""

from django.db import transaction

from django.core.management.base import BaseCommand

from recipes.ingredient_cleanup import (
    UNWANTED_CATEGORIES,
    canonical_ingredient_name,
    is_equipment,
    normalize_ingredient,
)
from recipes.models import Ingredient, RecipeIngredient


class Command(BaseCommand):
    help = "Remove non-ingredient items and reduce ingredient names to pantry names"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="report changes without writing them",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        equipment, equipment_lines = self._remove_equipment(dry_run)
        renamed, merged = self._normalise_alcohol(dry_run)
        canonical, canonical_merged, prose = self._canonicalise_names(dry_run)
        removed, skipped = self._remove_categories(dry_run)
        pruned = self._prune_unused(dry_run)

        action = "would" if dry_run else "did"
        self.stdout.write(
            f"{action} remove {equipment} equipment item(s) and "
            f"{equipment_lines} recipe line(s)"
        )
        self.stdout.write(
            f"{action} rename {renamed} alcoholic ingredient(s), "
            f"merge {merged} duplicate name(s)"
        )
        self.stdout.write(
            f"{action} canonicalise {canonical} ingredient name(s), "
            f"merge {canonical_merged} duplicate(s), "
            f"remove {prose} prose-only name(s)"
        )
        self.stdout.write(
            f"{action} remove {removed} unwanted ingredient(s)"
            + (f", skipped {skipped} still in use" if skipped else "")
        )
        self.stdout.write(
            f"{action} prune {pruned} unused ingredient(s) with no nutrition data"
        )

    def _remove_equipment(self, dry_run):
        """Delete foil, paper, skewers and the recipe lines naming them."""
        removed = 0
        lines = 0
        for ingredient in Ingredient.objects.only("id", "name").iterator():
            if not is_equipment(ingredient.name):
                continue
            removed += 1
            lines += RecipeIngredient.objects.filter(
                ingredient=ingredient
            ).count()
            if not dry_run:
                with transaction.atomic():
                    RecipeIngredient.objects.filter(ingredient=ingredient).delete()
                    ingredient.delete()
        return removed, lines

    def _canonicalise_names(self, dry_run):
        renamed = 0
        merged = 0
        removed = 0
        queryset = Ingredient.objects.only("id", "name", "category").order_by("id")
        for ingredient in queryset.iterator():
            name = canonical_ingredient_name(ingredient.name)
            if not name:
                # The line named no food at all ("really whatever you like"),
                # so it has no place in the pantry index.
                removed += 1
                if not dry_run:
                    with transaction.atomic():
                        RecipeIngredient.objects.filter(
                            ingredient=ingredient
                        ).delete()
                        ingredient.delete()
                continue
            if name == ingredient.name:
                continue
            if dry_run:
                renamed += 1
                continue
            try:
                with transaction.atomic():
                    if self._apply(ingredient, name, ingredient.category):
                        merged += 1
                    else:
                        renamed += 1
            except Exception as exc:  # noqa: BLE001 - name the row and keep going
                self.stderr.write(f"{ingredient.name!r}: {exc}")
        return renamed, merged, removed

    def _prune_unused(self, dry_run):
        """Delete rows left behind by a re-import with a better parser."""
        queryset = Ingredient.objects.filter(
            recipeingredient__isnull=True, nutrition__isnull=True
        )
        count = queryset.count()
        if count and not dry_run:
            queryset.delete()
        return count

    def _remove_categories(self, dry_run):
        queryset = Ingredient.objects.filter(category__in=UNWANTED_CATEGORIES)
        removed = 0
        skipped = 0
        for ingredient in queryset.iterator():
            if RecipeIngredient.objects.filter(ingredient=ingredient).exists():
                skipped += 1
                self.stderr.write(f"kept {ingredient.name!r}: still used by a recipe")
                continue
            removed += 1
            if not dry_run:
                ingredient.delete()
        return removed, skipped

    def _normalise_alcohol(self, dry_run):
        renamed = 0
        merged = 0
        queryset = Ingredient.objects.only("id", "name", "category", "aliases").order_by(
            "id"
        )
        for ingredient in queryset.iterator():
            name, category = normalize_ingredient(ingredient.name, ingredient.category)
            if name == ingredient.name and category == ingredient.category:
                continue
            if dry_run:
                renamed += 1
                continue
            try:
                with transaction.atomic():
                    if self._apply(ingredient, name, category):
                        merged += 1
                    else:
                        renamed += 1
            except Exception as exc:  # noqa: BLE001 - name the row and keep going
                self.stderr.write(f"{ingredient.name!r}: {exc}")
        return renamed, merged

    def _apply(self, ingredient, name, category):
        """Rename or merge ``ingredient``; return True when it was merged."""
        target = Ingredient.objects.filter(name=name).exclude(pk=ingredient.pk).first()
        if target is None:
            ingredient.name = name
            ingredient.category = category or ingredient.category
            ingredient.save(update_fields=["name", "category"])
            return False

        # Keep the target's row, fold in anything the source knew.
        RecipeIngredient.objects.filter(ingredient=ingredient).update(ingredient=target)
        for nutrition in ingredient.nutrition.all():
            exists = target.nutrition.filter(
                source=nutrition.source, source_id=nutrition.source_id
            ).exists()
            if exists:
                nutrition.delete()
            else:
                nutrition.ingredient = target
                nutrition.save(update_fields=["ingredient"])
        if not target.measures.exists():
            ingredient.measures.update(ingredient=target)
        else:
            ingredient.measures.all().delete()

        aliases = list(target.aliases or [])
        for alias in [ingredient.name, *(ingredient.aliases or [])]:
            alias = " ".join(str(alias or "").split())
            if not alias or alias == target.name:
                continue
            if not any(str(existing).casefold() == alias.casefold() for existing in aliases):
                aliases.append(alias)
        target.aliases = aliases
        target.category = category or target.category
        target.save(update_fields=["aliases", "category"])
        ingredient.delete()
        return True
