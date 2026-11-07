"""Convert Team Nutrition PDF cards into the normalised recipe JSON format.

The repository keeps the normalised JSON as the source of truth and no longer
ships the original PDFs. This command exists so a fresh set of cards can be
converted before the PDFs are removed, using the same parser and direction
cleaner as the importer.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from recipes.management.commands.import_usda import positive_int
from recipes.pdf import parse_pdf

DEFAULT_SOURCE = "usda-team-nutrition"
DEFAULT_TITLE = "USDA Team Nutrition"
DEFAULT_COLLECTION = "usda-team-nutrition"
DEFAULT_LICENSE = "Public domain (U.S. Government work)"
DEFAULT_URL = "https://www.fna.usda.gov/tn/recipes-healthy-kids-cookbook-homes"
DEFAULT_ATTRIBUTION = (
    "USDA Team Nutrition, Recipes for Healthy Kids. "
    "U.S. Government work, public domain."
)


class Command(BaseCommand):
    help = "Convert Team Nutrition PDF cards into normalised recipe JSON"

    def add_arguments(self, parser):
        parser.add_argument(
            "paths",
            nargs="+",
            type=Path,
            help="PDF files, or directories whose *.pdf files are converted",
        )
        parser.add_argument(
            "--output",
            type=Path,
            required=True,
            help="JSON file to write",
        )
        parser.add_argument("--source", default=DEFAULT_SOURCE)
        parser.add_argument("--source-title", default=DEFAULT_TITLE)
        parser.add_argument("--collection", default=DEFAULT_COLLECTION)
        parser.add_argument("--category", default="modern")
        parser.add_argument("--license", default=DEFAULT_LICENSE)
        parser.add_argument("--source-url", default=DEFAULT_URL)
        parser.add_argument("--attribution", default=DEFAULT_ATTRIBUTION)
        parser.add_argument(
            "--limit",
            type=positive_int,
            help="convert at most this many recipes",
        )

    def handle(self, *args, **options):
        paths = self._expand(options["paths"])
        entries = []
        skipped = []
        for path in paths:
            if options["limit"] and len(entries) >= options["limit"]:
                break
            try:
                data = parse_pdf(path)
            except Exception as exc:  # noqa: BLE001 - report the file and keep going
                raise CommandError(f"could not read {path}: {exc}") from exc
            if data is None:
                skipped.append(path)
                continue
            entries.append(self._entry(path, data, options))

        if not entries:
            raise CommandError("no recipes found in the supplied PDFs")

        payload = {
            "source": options["source"],
            "source_title": options["source_title"],
            "source_url": options["source_url"],
            "license": options["license"],
            "attribution": options["attribution"],
            "collection": options["collection"],
            "category": options["category"],
            "recipes": entries,
        }
        output = Path(options["output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        tmp = output.with_suffix(output.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        tmp.replace(output)

        for path in skipped:
            self.stderr.write(f"{path}: skipped (no recipe found)")
        self.stdout.write(
            f"wrote {len(entries)} recipes to {output}"
            + (f", skipped {len(skipped)}" if skipped else "")
        )

    @staticmethod
    def _entry(path, data, options):
        nutrients = data.get("nutrients") or {}
        return {
            "source_id": path.stem,
            "name": data["title"],
            "description": data.get("description") or "",
            "servings": data.get("servings"),
            "serving_size": data.get("serving_size") or "",
            "prep_mins": data.get("prep_mins"),
            "cook_mins": data.get("cook_mins"),
            "ingredients": data.get("ingredients") or [],
            "directions": data.get("directions") or [],
            "nutrients": nutrients,
            "source_url": options["source_url"],
        }

    @staticmethod
    def _expand(paths):
        expanded = []
        missing = []
        for path in paths:
            if path.is_dir():
                found = sorted(path.glob("*.pdf"))
                if not found:
                    raise CommandError(f"no PDF files found in {path}")
                expanded.extend(found)
            elif path.is_file():
                if path.suffix.lower() != ".pdf":
                    raise CommandError(f"not a PDF file: {path}")
                expanded.append(path)
            else:
                missing.append(path)
        if missing:
            names = ", ".join(str(path) for path in missing)
            raise CommandError(f"no such file or directory: {names}")
        return expanded
