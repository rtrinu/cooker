"""Reader for the official USDA FoodData Central bulk download JSON datasets.

The download files are a single object wrapping an array of Food objects, for
example ``{"FoundationFoods": [...]}``, and each entry shares the shape of the
``/food/{fdcId}`` API response, so nutrient parsing is reused from
``import_usda``. Datasets are streamed one food at a time because the largest
of them are far too big to hold in memory.
"""

import argparse
import io
import json
import zipfile

from recipes.management.commands.import_usda import (
    NUTRIENT_FIELDS,
    USDADataError,
    extract_nutrients,
    parse_description,
    parse_publication_date,
    positive_int,
)

SUPPORTED_DATA_TYPES = frozenset({"Foundation", "SR Legacy"})
DEFAULT_CHUNK_SIZE = 1 << 20
MAX_OBJECT_BYTES = 64 << 20
MAX_KEY_BYTES = 1 << 20
CATEGORY_MAX_LENGTH = 50
JSON_SUFFIX = ".json"
SNAPSHOT_HINT = "it looks like a fetch_usda_json snapshot, use import_usda_json"
INCOMPLETE = object()


class ChunkReader:
    """Incremental JSON reader that decodes one value at a time."""

    def __init__(self, handle, chunk_size):
        self.handle = handle
        self.chunk_size = chunk_size
        self.buffer = ""
        self.eof = False
        self.decoder = json.JSONDecoder()

    def fill(self):
        if self.eof:
            return False
        chunk = self.handle.read(self.chunk_size)
        if not chunk:
            self.eof = True
            return False
        self.buffer += chunk
        return True

    def peek(self):
        """Next non-whitespace character, or an empty string when unknown."""
        while True:
            self.buffer = self.buffer.lstrip()
            if self.buffer or not self.fill():
                return self.buffer[:1]

    def take(self, expected):
        found = self.peek()
        if found != expected:
            raise USDADataError(
                f"expected {expected!r} in dataset, got {found or 'end of file'!r}"
            )
        self.buffer = self.buffer[1:]

    def decode(self, max_bytes=MAX_OBJECT_BYTES):
        """Next complete JSON value, or INCOMPLETE when more input is needed."""
        self.buffer = self.buffer.lstrip()
        if not self.buffer:
            return INCOMPLETE
        try:
            value, end = self.decoder.raw_decode(self.buffer)
        except ValueError:
            if len(self.buffer) > max_bytes:
                raise USDADataError(
                    "dataset is malformed, a single value is larger than "
                    f"{max_bytes} bytes"
                )
            return INCOMPLETE
        self.buffer = self.buffer[end:]
        return value

    def decode_required(self, label, max_bytes=MAX_KEY_BYTES):
        while True:
            value = self.decode(max_bytes)
            if value is not INCOMPLETE:
                return value
            if not self.fill():
                raise USDADataError(f"dataset is truncated, expected {label}")


def iter_foods(handle, chunk_size=DEFAULT_CHUNK_SIZE):
    """Yield each food from a dataset without buffering the whole file.

    Handles both a bare JSON array and the download files' object wrapper, and
    yields ``None`` for the stray null entries the exports contain.
    """
    if chunk_size < 1:
        raise USDADataError("chunk size must be positive")
    reader = ChunkReader(handle, chunk_size)

    first = reader.peek()
    if not first:
        raise USDADataError("dataset is empty, expected a JSON array of foods")
    wrapped = first == "{"
    if wrapped:
        reader.take("{")
        name = reader.decode_required("the dataset name")
        if not isinstance(name, str):
            raise USDADataError(
                'dataset must be an object of the form {"FoundationFoods": [...]}'
            )
        reader.take(":")
        first = reader.peek()

    if first != "[":
        hint = f" ({SNAPSHOT_HINT})" if wrapped else ""
        raise USDADataError(f"dataset must hold a JSON array of foods{hint}")
    reader.take("[")

    while True:
        char = reader.peek()
        if not char:
            raise USDADataError("dataset is truncated, expected a closing ]")
        if char == "]":
            return
        if char == ",":
            reader.take(",")
            continue
        food = reader.decode()
        if food is INCOMPLETE:
            if not reader.fill():
                raise USDADataError(
                    "dataset is truncated, expected a closing ]"
                )
            continue
        yield food


class DatasetReader:
    """Text reader that keeps an enclosing zip archive alive."""

    def __init__(self, stream, archive=None):
        self.stream = stream
        self.archive = archive
        self.closed = False

    def read(self, size=-1):
        return self.stream.read(size)

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.stream.close()
        finally:
            if self.archive is not None:
                self.archive.close()
                self.archive = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False


def open_dataset(path, member=None):
    """Open a bulk download file, either a plain .json document or a .zip."""
    if not path.exists():
        raise USDADataError(f"{path} does not exist")
    if path.suffix.casefold() == ".zip":
        return open_zip_dataset(path, member)
    try:
        return DatasetReader(path.open(encoding="utf-8"))
    except OSError as exc:
        raise USDADataError(f"could not read {path}: {exc}") from exc


def open_zip_dataset(path, member=None):
    """Open a zipped download, selecting the JSON dataset inside it."""
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise USDADataError(f"could not open {path}: {exc}") from exc

    try:
        if member:
            if member not in archive.namelist():
                raise USDADataError(
                    f"{path} has no member named {member}; members: "
                    f"{', '.join(archive.namelist()) or 'none'}"
                )
            name = member
        else:
            names = [
                entry
                for entry in archive.namelist()
                if entry.casefold().endswith(JSON_SUFFIX)
                and not entry.endswith("/")
            ]
            if len(names) == 1:
                name = names[0]
            elif not names:
                raise USDADataError(f"{path} has no JSON dataset member")
            else:
                raise USDADataError(
                    f"{path} has {len(names)} JSON members, pick one with "
                    f"--member: {', '.join(sorted(names))}"
                )
        try:
            stream = archive.open(name)
        except (OSError, KeyError, zipfile.BadZipFile) as exc:
            raise USDADataError(f"could not read {name} from {path}: {exc}") from exc
        return DatasetReader(io.TextIOWrapper(stream, encoding="utf-8"), archive)
    except Exception:
        archive.close()
        raise


def parse_category(food):
    category = food.get("foodCategory")
    if isinstance(category, dict):
        category = category.get("description")
    if not isinstance(category, str):
        return None
    category = " ".join(category.split())[:CATEGORY_MAX_LENGTH]
    return category or None


def parse_bulk_food(food, require_all_nutrients=False):
    """Validate one bulk dataset entry into a record ready for upsert_food.

    Nutrients USDA does not publish for a food come back as None unless
    ``require_all_nutrients`` is set. Returns None for a food with none of the
    tracked nutrients at all, such as the pure oils and salts in Foundation
    Foods, because such a row would carry no information.
    """
    if not isinstance(food, dict):
        raise USDADataError("food entry must be a JSON object")

    fdc_id = food.get("fdcId")
    if isinstance(fdc_id, bool) or not isinstance(fdc_id, (int, str)):
        raise USDADataError("missing or invalid fdcId")
    try:
        fdc_id = positive_int(fdc_id)
    except argparse.ArgumentTypeError as exc:
        raise USDADataError("missing or invalid fdcId") from exc

    data_type = food.get("dataType")
    if data_type not in SUPPORTED_DATA_TYPES:
        supported = " or ".join(sorted(SUPPORTED_DATA_TYPES))
        raise USDADataError(
            f"unsupported dataType {data_type or 'missing'}, expected {supported}"
        )

    record = {
        "fdc_id": fdc_id,
        "name": parse_description(food),
        "category": parse_category(food),
        "publication_date": parse_publication_date(food.get("publicationDate")),
    }
    required = NUTRIENT_FIELDS if require_all_nutrients else ()
    record.update(extract_nutrients(food, required=required))
    if all(record[field] is None for field in NUTRIENT_FIELDS):
        return None
    return record