"""Provenance and licence metadata for nutrition data sources.

Every ingredient-nutrition row carries the terms that apply to it, so a
commercial deployment can show the required attribution and know which
obligations follow the data.

* USDA FoodData Central is published under CC0 1.0. It can be used, adapted
  and redistributed commercially without permission; attribution is requested
  but not required.
* UK CoFID is published under the Open Government Licence v3.0. Commercial use
  is permitted; attribution to the source and Crown copyright is required.
* Open Food Facts is published under the Open Database License (ODbL) 1.0.
  Commercial use is permitted, but the share-alike term applies to a publicly
  used derivative database. Its rows therefore carry ``share_alike=True`` and
  should be kept separable from the proprietary ingredient database unless the
  business accepts that obligation or has separate permission.
"""

from collections import namedtuple

Source = namedtuple(
    "Source",
    (
        "name",
        "short_name",
        "license",
        "license_url",
        "attribution",
        "commercial_use",
        "share_alike",
    ),
)

USDA = Source(
    name="USDA FoodData Central",
    short_name="USDA FDC",
    license="CC0 1.0",
    license_url="https://creativecommons.org/publicdomain/zero/1.0/",
    attribution=(
        "U.S. Department of Agriculture, Agricultural Research Service. "
        "FoodData Central, 2019. fdc.nal.usda.gov."
    ),
    commercial_use=True,
    share_alike=False,
)

COFID = Source(
    name="UK CoFID",
    short_name="CoFID",
    license="Open Government Licence v3.0",
    license_url=(
        "https://www.nationalarchives.gov.uk/doc/open-government-licence/"
        "version/3/"
    ),
    attribution=(
        "Contains public sector information licensed under the Open Government "
        "Licence v3.0. McCance and Widdowson's The Composition of Foods "
        "Integrated Dataset 2021, © Crown copyright."
    ),
    commercial_use=True,
    share_alike=False,
)

OPEN_FOOD_FACTS = Source(
    name="Open Food Facts",
    short_name="OFF",
    license="ODbL 1.0",
    license_url="https://opendatacommons.org/licenses/odbl/1-0/",
    attribution=(
        "Contains data from Open Food Facts, available under the Open Database "
        "License. https://openfoodfacts.org"
    ),
    commercial_use=True,
    share_alike=True,
)

SOURCES = {source.name: source for source in (USDA, COFID, OPEN_FOOD_FACTS)}

# Sources that can be merged into a proprietary database without a share-alike
# obligation. Open Food Facts is deliberately absent: use it only when the
# ODbL obligations have been accepted for the derived database.
COMMERCIALLY_CLEAR_SOURCES = frozenset({USDA.name, COFID.name})


def source_metadata(name):
    """Return metadata for ``name``.

    An unknown source is treated as restricted rather than assumed reusable:
    no licence, no commercial permission and share-alike on. That keeps a
    future importer from accidentally claiming terms it has not checked.
    """
    return SOURCES.get(name) or Source(
        name=name or "",
        short_name=name or "",
        license="",
        license_url="",
        attribution="",
        commercial_use=False,
        share_alike=True,
    )


def license_fields(source):
    """The values stored on a nutrition row for ``source``."""
    return {"license": source.license, "attribution": source.attribution}


def is_commercially_clear(name):
    return name in COMMERCIALLY_CLEAR_SOURCES
