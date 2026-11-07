"""Normalise stored recipe directions and the Team Nutrition source fixture.

Directions imported before :mod:`recipes.directions` existed still contain PDF
line wraps, source step numbers, crediting blocks and printed nutrition panels.
This command rewrites those rows in place and, unless ``--no-json`` is given,
cleans the JSON fixture used to re-import the same collection.
"""

import json
import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from recipes.directions import clean_directions
from recipes.models import Recipe


class Command(BaseCommand):
    help = "Clean stored recipe directions and the Team Nutrition JSON fixture"

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            default="usda-team-nutrition",
            help=(
                "only clean recipes from this source slug "
                "(default: usda-team-nutrition)"
            ),
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="clean every source, including the unnumbered classic corpus",
        )
        parser.add_argument(
            "--json",
            type=Path,
            default=Path(settings.BASE_DIR)
            / "recipes"
            / "data"
            / "team-nutrition-recipes.json",
            help="JSON fixture to rewrite (default: the Team Nutrition fixture)",
        )
        parser.add_argument(
            "--no-json",
            action="store_true",
            help="leave the JSON fixture untouched",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="report changes without writing them",
        )

    def handle(self, *args, **options):
        recipes = Recipe.objects.exclude(directions="")
        if not options["all"] and options["source"]:
            recipes = recipes.filter(source=options["source"])
        recipes = recipes.order_by("id")

        changed = 0
        examples = []
        for recipe in recipes.iterator():
            cleaned = "\n".join(clean_directions(recipe.directions))
            if cleaned == recipe.directions:
                continue
            changed += 1
            if len(examples) < 5:
                examples.append((recipe.name, recipe.directions, cleaned))
            if not options["dry_run"]:
                recipe.directions = cleaned
                recipe.save(update_fields=["directions"])

        action = "would clean" if options["dry_run"] else "cleaned"
        self.stdout.write(f"{action} {changed} recipe direction block(s)")
        for name, before, after in examples:
            self.stdout.write(
                f"  {name}: {len(before.splitlines())} lines -> "
                f"{len(after.splitlines())} steps"
            )

        if not options["no_json"]:
            self._clean_json(options["json"], options["dry_run"])

    def _clean_json(self, path, dry_run):
        path = Path(path)
        if not path.exists():
            self.stderr.write(f"skipping missing fixture: {path}")
            return
        payload = json.loads(path.read_text(encoding="utf-8"))
        recipes = payload.get("recipes")
        if not isinstance(recipes, list):
            self.stderr.write(f"skipping fixture without a recipes array: {path}")
            return

        changed = 0
        for recipe in recipes:
            directions = recipe.get("directions")
            if not directions:
                continue
            cleaned = clean_directions(directions)
            if cleaned == directions:
                continue
            recipe["directions"] = cleaned
            changed += 1

        action = "would rewrite" if dry_run else "rewrote"
        self.stdout.write(f"{action} {changed} recipe(s) in {path}")
        if dry_run or not changed:
            return
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
