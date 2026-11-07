"""Import the Public Domain Recipes Markdown collection.

The source is a Hugo site published under the Unlicense. Its recipes are
modern, cover many cuisines, and need no PDF parsing, so the whole collection
is downloaded once as a GitHub tarball and parsed from Markdown.

The tarball is cached outside the repository. Network failures are retried
with exponential backoff rather than hammering GitHub, and an already
downloaded archive is reused on later runs unless ``--refresh`` is given.
"""

import json
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from recipes.management.commands.import_usda import positive_int
from recipes.models import Recipe
from recipes.public_domain_recipes import (
    COLLECTION,
    SOURCE,
    SOURCE_TITLE,
    as_metadata,
    as_recipe_data,
    parse_directory,
)
from recipes.recipe_import import save_recipe

ARCHIVE_URL = (
    "https://codeload.github.com/ronaldl29/public-domain-recipes/"
    "tar.gz/refs/heads/main"
)
DOWNLOAD_ATTEMPTS = 5
DOWNLOAD_TIMEOUT = 60
PROGRESS_INTERVAL = 50


def default_cache_path():
    return Path(tempfile.gettempdir()) / "cooker" / "public-domain-recipes.tar.gz"


def download_archive(destination, url=ARCHIVE_URL, refresh=False):
    """Download ``url`` to ``destination`` with retry and exponential backoff."""
    destination = Path(destination)
    if destination.exists() and not refresh:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    delay = 1.0
    last_error = None
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "cooker-recipe-import/1.0"},
            )
            with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response:
                with partial.open("wb") as handle:
                    while chunk := response.read(1024 * 256):
                        handle.write(chunk)
            partial.replace(destination)
            return destination
        except (OSError, urllib.error.URLError) as exc:
            last_error = exc
            partial.unlink(missing_ok=True)
            if attempt == DOWNLOAD_ATTEMPTS:
                break
            time.sleep(delay)
            delay = min(delay * 2, 30.0)
    raise CommandError(
        f"could not download {url} after {DOWNLOAD_ATTEMPTS} attempts: {last_error}"
    )


def extract_archive(archive, destination):
    """Extract ``archive`` into ``destination`` and return its content directory."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            target = (destination / member.name).resolve()
            if not str(target).startswith(str(destination.resolve())):
                raise CommandError(f"archive member escapes destination: {member.name}")
        tar.extractall(destination)
    matches = sorted(destination.glob("*/content"))
    if not matches:
        raise CommandError(f"no content directory found in {archive}")
    return matches[0]


class Command(BaseCommand):
    help = "Import recipes from the Public Domain Recipes Markdown collection"

    def add_arguments(self, parser):
        parser.add_argument(
            "--content-dir",
            type=Path,
            help="extracted content directory; skips downloading the archive",
        )
        parser.add_argument(
            "--archive",
            type=Path,
            help=f"tarball to import (default: cached download from {ARCHIVE_URL})",
        )
        parser.add_argument(
            "--refresh",
            action="store_true",
            help="download the archive again even if the cache exists",
        )
        parser.add_argument(
            "--output",
            type=Path,
            help="write the normalised recipes to this JSON file",
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
            "--reset",
            action="store_true",
            help="delete previously imported Public Domain Recipes first",
        )

    def handle(self, *args, **options):
        content_dir = self._content_dir(options)
        parsed = list(self._parse(content_dir))
        if options["limit"]:
            parsed = parsed[: options["limit"]]
        if not parsed:
            raise CommandError(f"no recipes found in {content_dir}")

        if options["output"]:
            self._write_output(options["output"], parsed)

        if options["reset"]:
            existing = Recipe.objects.filter(source=SOURCE)
            count = existing.count()
            if options["dry_run"]:
                self.stdout.write(f"dry run: would delete {count} {SOURCE_TITLE} recipes")
            else:
                existing.delete()
                self.stdout.write(f"reset: removed {count} {SOURCE_TITLE} recipes")

        created = updated = failed = 0
        total_ingredients = 0
        for index, recipe in enumerate(parsed, start=1):
            try:
                result = save_recipe(
                    as_recipe_data(recipe),
                    slug=recipe.slug,
                    dry_run=options["dry_run"],
                    metadata=as_metadata(recipe),
                )
            except Exception as exc:  # noqa: BLE001 - report the file and keep going
                failed += 1
                self.stderr.write(f"{recipe.source_id}: {exc}")
                continue
            if result.created:
                created += 1
            else:
                updated += 1
            total_ingredients += result.ingredients
            if index % PROGRESS_INTERVAL == 0:
                self.stderr.write(
                    f"progress processed={index} created={created} updated={updated}"
                )

        summary = (
            f"created={created} updated={updated} failed={failed} "
            f"ingredients={total_ingredients}"
        )
        if options["dry_run"]:
            self.stdout.write(f"dry run: {summary}")
        else:
            self.stdout.write(self.style.SUCCESS(summary))

        if failed:
            raise CommandError(
                f"{SOURCE_TITLE} import completed with {failed} error(s)"
            )

    def _content_dir(self, options):
        if options["content_dir"]:
            path = options["content_dir"]
            if not path.is_dir():
                raise CommandError(f"not a directory: {path}")
            return path
        archive = options["archive"] or default_cache_path()
        archive = download_archive(archive, refresh=options["refresh"])
        destination = Path(tempfile.gettempdir()) / "cooker" / "public-domain-recipes"
        return extract_archive(archive, destination)

    def _parse(self, content_dir):
        for path, recipe in parse_directory(content_dir):
            yield recipe

    def _write_output(self, path, parsed):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "source": SOURCE,
            "source_title": SOURCE_TITLE,
            "license": "Unlicense",
            "collection": COLLECTION,
            "category": "modern",
            "recipes": [
                {
                    "source_id": recipe.source_id,
                    "title": recipe.title,
                    "description": recipe.description,
                    "servings": recipe.servings,
                    "prep_mins": recipe.prep_mins,
                    "cook_mins": recipe.cook_mins,
                    "ingredients": recipe.ingredients,
                    "directions": recipe.directions,
                    "tags": recipe.tags,
                    "cuisine": recipe.cuisine,
                    "source_year": recipe.source_year,
                    "source_url": recipe.source_url,
                }
                for recipe in parsed
            ],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        self.stdout.write(f"wrote {len(parsed)} recipes to {path}")
