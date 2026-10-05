import argparse
import json
import math
import time
from collections import namedtuple
from datetime import date, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from recipes.models import Ingredient, IngredientNutrition

SOURCE = "USDA FoodData Central"
API_BASE_URL = "https://api.nal.usda.gov/fdc/v1"
DEFAULT_TIMEOUT = 30
DEFAULT_RETRIES = 3
NAME_MAX_LENGTH = 255
NUTRIENT_SPECS = {
    "kcal": ((2048, 2047, 1008), "kcal"),
    "protein_g": ((1003,), "g"),
    "carbs_g": ((1005,), "g"),
    "fat_g": ((1004,), "g"),
    "fiber_g": ((1079, 2033), "g"),
}
NUTRIENT_FIELDS = ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g")

UpsertResult = namedtuple("UpsertResult", ("created", "renamed", "name"))


class USDAAPIError(Exception):
    pass


class USDADataError(Exception):
    pass


def positive_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def collect_fdc_ids(fdc_ids=None, path=None, limit=None):
    values = list(fdc_ids or [])
    if path:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise CommandError(f"could not read {path}: {exc}") from exc
        for line in lines:
            value = line.split("#", 1)[0].strip()
            if not value:
                continue
            for item in value.split(","):
                try:
                    values.append(positive_int(item.strip()))
                except argparse.ArgumentTypeError as exc:
                    raise CommandError(
                        f"invalid FDC ID in {path}: {item.strip()}"
                    ) from exc

    values = list(dict.fromkeys(values))
    return values[:limit] if limit else values


def parse_description(food):
    description = food.get("description")
    if not isinstance(description, str) or not description.strip():
        raise USDADataError("food description is required")
    description = description.strip()
    if len(description) > NAME_MAX_LENGTH:
        raise USDADataError("food description exceeds the ingredient name limit")
    return description


def parse_publication_date(value):
    """Accept both the API's ISO dates and the download files' M/D/YYYY."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
    try:
        return datetime.strptime(text, "%m/%d/%Y").date()
    except ValueError:
        return None


def parse_amount(entry, expected_unit):
    amount = entry.get("amount")
    if isinstance(amount, bool):
        raise USDADataError("nutrient amount must be numeric")
    try:
        amount = float(amount)
    except (TypeError, ValueError) as exc:
        raise USDADataError("nutrient amount must be numeric") from exc
    if not math.isfinite(amount):
        raise USDADataError("nutrient amount must be finite")
    if amount < 0:
        raise USDADataError("nutrient amount cannot be negative")

    nutrient = entry.get("nutrient") or {}
    unit = str(nutrient.get("unitName", "")).strip().casefold()
    expected_unit = expected_unit.casefold()
    if unit != expected_unit:
        raise USDADataError(
            f"expected {expected_unit} for nutrient {nutrient.get('id')}, got {unit or 'no unit'}"
        )
    return amount


def extract_nutrients(food, required=NUTRIENT_FIELDS):
    """Pull the tracked nutrients out of a food's foodNutrients list.

    Every field in NUTRIENT_FIELDS is always returned. Fields listed in
    ``required`` raise when missing or unusable, which is what the single food
    API path wants; the rest come back as None so partial bulk records survive.
    """
    entries = food.get("foodNutrients")
    if not isinstance(entries, list):
        raise USDADataError("foodNutrients must be a list")

    entries_by_id = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        nutrient = entry.get("nutrient") or {}
        try:
            nutrient_id = int(nutrient.get("id"))
        except (TypeError, ValueError):
            continue
        if "amount" in entry:
            entries_by_id.setdefault(nutrient_id, []).append(entry)

    values = {}
    missing = []
    for field, (nutrient_ids, expected_unit) in NUTRIENT_SPECS.items():
        last_error = None
        for nutrient_id in nutrient_ids:
            for entry in entries_by_id.get(nutrient_id, []):
                try:
                    values[field] = parse_amount(entry, expected_unit)
                    last_error = None
                    break
                except USDADataError as exc:
                    last_error = exc
            if field in values:
                break
        if field in values:
            continue
        if field in required:
            if last_error:
                raise last_error
            missing.append(field)
        values[field] = None

    if missing:
        raise USDADataError(f"missing nutrients: {', '.join(missing)}")
    return values


def parse_food(food, requested_fdc_id):
    if not isinstance(food, dict):
        raise USDADataError("API response must be an object")

    fdc_id = food.get("fdcId")
    if fdc_id is None or str(fdc_id) != str(requested_fdc_id):
        raise USDADataError("API response FDC ID does not match the request")

    data_type = food.get("dataType")
    if data_type and data_type != "Foundation":
        raise USDADataError(f"unsupported USDA data type: {data_type}")

    return {
        "name": parse_description(food),
        "publication_date": parse_publication_date(food.get("publicationDate")),
        **extract_nutrients(food),
    }


def find_nutrition(fdc_id):
    return (
        IngredientNutrition.objects.select_related("ingredient")
        .filter(source=SOURCE, source_id=str(fdc_id))
        .first()
    )


def disambiguated_name(name, fdc_id):
    """Suffix a description with its FDC ID so duplicates stay distinguishable."""
    suffix = f" (FDC {fdc_id})"
    return f"{name[: NAME_MAX_LENGTH - len(suffix)].rstrip()}{suffix}"


def name_is_claimed(name):
    """True when an ingredient already exists under this name with nutrition data."""
    return Ingredient.objects.filter(name=name, nutrition__isnull=False).exists()


def resolve_ingredient(name, fdc_id):
    """Find or create the ingredient for a food, keeping its nutrition unambiguous.

    USDA reuses some descriptions across distinct FDC IDs -- "Hummus, commercial"
    exists in both Foundation (321358) and SR Legacy (174289) with slightly
    different nutrients. Because ``Ingredient.name`` is unique, matching on name
    alone would attach both records to one ingredient and leave two conflicting
    nutrition rows, so the later record is stored under an "(FDC <id>)" name.
    """
    ingredient = Ingredient.objects.filter(name=name).first()
    if ingredient is None:
        return Ingredient.objects.create(name=name)
    if not ingredient.nutrition.exists():
        return ingredient
    return Ingredient.objects.get_or_create(name=disambiguated_name(name, fdc_id))[0]


def preview_name(name, fdc_id, claimed=None):
    """The name a food would be stored under, without writing anything.

    Mirrors :func:`resolve_ingredient` for ``--dry-run``. ``claimed`` holds the
    names already planned during this run, which the database cannot know about
    because nothing has been written yet.
    """
    if (claimed is not None and name in claimed) or name_is_claimed(name):
        return disambiguated_name(name, fdc_id)
    return name


def upsert_food(parsed, fdc_id, category=None, publication_date=None):
    """Store one parsed food.

    Returns whether the nutrition row was created, whether a duplicate USDA
    description had to be stored under a suffixed name, and the ingredient name
    actually used.
    """
    existing = find_nutrition(fdc_id)
    if existing:
        ingredient = existing.ingredient
        renamed = False
    else:
        ingredient = resolve_ingredient(parsed["name"], fdc_id)
        renamed = ingredient.name != parsed["name"]

    if category and not ingredient.category:
        ingredient.category = category
        ingredient.save(update_fields=["category"])

    defaults = {field: parsed[field] for field in NUTRIENT_FIELDS}
    defaults["serving_size_g"] = 100
    if publication_date is not None:
        defaults["publication_date"] = publication_date

    _, was_created = IngredientNutrition.objects.update_or_create(
        ingredient=ingredient,
        source=SOURCE,
        source_id=str(fdc_id),
        defaults=defaults,
    )
    return UpsertResult(created=was_created, renamed=renamed, name=ingredient.name)


class USDAClient:
    def __init__(self, api_key, opener=urlopen, sleeper=time.sleep, clock=time.time):
        self.api_key = api_key
        self.opener = opener
        self.sleeper = sleeper
        self.clock = clock
        self.last_headers = {}

    def get_food(self, fdc_id):
        query = urlencode({"api_key": self.api_key})
        url = f"{API_BASE_URL}/food/{fdc_id}?{query}"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "cooker-usda-import/1.0",
            },
        )

        for attempt in range(DEFAULT_RETRIES + 1):
            try:
                with self.opener(request, timeout=DEFAULT_TIMEOUT) as response:
                    headers = getattr(response, "headers", None)
                    self.last_headers = dict(headers.items()) if headers else {}
                    payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, dict):
                    raise USDAAPIError("USDA API returned an invalid response")
                return payload
            except HTTPError as exc:
                if not self._should_retry(exc.code) or attempt == DEFAULT_RETRIES:
                    raise USDAAPIError(
                        f"USDA API returned HTTP {exc.code} for FDC ID {fdc_id}"
                    ) from exc
                self._wait(attempt, getattr(exc, "headers", None))
            except (URLError, TimeoutError, OSError) as exc:
                if attempt == DEFAULT_RETRIES:
                    raise USDAAPIError(
                        f"could not reach USDA API for FDC ID {fdc_id}"
                    ) from exc
                self._wait(attempt, None)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise USDAAPIError("USDA API returned invalid JSON") from exc

        raise USDAAPIError(f"could not fetch FDC ID {fdc_id}")

    def wait_for_rate_limit(self, reserve=1):
        remaining = self._header_number("X-RateLimit-Remaining")
        if remaining is None or remaining > reserve:
            return
        reset = self._header_number("X-RateLimit-Reset")
        delay = max(reset - self.clock(), 1) if reset is not None else 1
        self.sleeper(delay)

    def _header_number(self, name):
        value = self.last_headers.get(name)
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _should_retry(status_code):
        return status_code == 429 or 500 <= status_code < 600

    def _wait(self, attempt, headers):
        delay = min(2**attempt, 30)
        if headers:
            retry_after = headers.get("Retry-After")
            try:
                delay = max(delay, float(retry_after))
            except (TypeError, ValueError):
                pass
        self.sleeper(delay)


class Command(BaseCommand):
    help = "Import USDA FoodData Central Foundation Foods nutrition data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--fdc-id",
            action="append",
            dest="fdc_ids",
            type=positive_int,
            help="USDA FDC ID; may be provided more than once",
        )
        parser.add_argument(
            "--file",
            type=Path,
            help="text file containing one or more FDC IDs per line",
        )
        parser.add_argument(
            "--limit",
            type=positive_int,
            help="maximum number of FDC IDs to import",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="fetch and validate data without writing to the database",
        )

    def handle(self, *args, **options):
        fdc_ids = self._collect_ids(options)
        if not fdc_ids:
            raise CommandError("provide at least one --fdc-id or --file")

        api_key = getattr(settings, "USDA_API_KEY", None)
        if not api_key:
            raise CommandError("set USDA_API_KEY before importing USDA data")

        client = USDAClient(api_key)
        created = 0
        updated = 0
        failed = 0

        for fdc_id in fdc_ids:
            try:
                food = client.get_food(fdc_id)
                parsed = parse_food(food, fdc_id)
                if options["dry_run"]:
                    existing = find_nutrition(fdc_id)
                    if existing:
                        updated += 1
                        label, action = existing.ingredient.name, "update"
                    else:
                        created += 1
                        label = preview_name(parsed["name"], fdc_id)
                        action = "create"
                        if label != parsed["name"]:
                            action = "create as"
                    self.stdout.write(f"{fdc_id}: would {action} {label}")
                    continue

                with transaction.atomic():
                    result = upsert_food(
                        parsed,
                        fdc_id,
                        publication_date=parsed.get("publication_date"),
                    )
                if result.renamed:
                    self.stderr.write(
                        f"{fdc_id}: duplicate description, stored as {result.name}"
                    )
                if result.created:
                    created += 1
                else:
                    updated += 1
            except (USDAAPIError, USDADataError, IntegrityError) as exc:
                failed += 1
                self.stderr.write(f"{fdc_id}: skipped ({exc})")

        summary = f"created={created} updated={updated} failed={failed}"
        if options["dry_run"]:
            self.stdout.write(f"dry run: {summary}")
        else:
            self.stdout.write(self.style.SUCCESS(summary))

        if failed:
            raise CommandError(f"USDA import completed with errors: {summary}")

    def _collect_ids(self, options):
        return collect_fdc_ids(
            fdc_ids=options.get("fdc_ids"),
            path=options.get("file"),
            limit=options.get("limit"),
        )
