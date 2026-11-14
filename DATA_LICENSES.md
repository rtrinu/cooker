# Data sources and commercial use

Every nutrition record stores its `source`, `source_id`, `retrieved_at`,
`license`, and `attribution`. The licence is part of the data, not a
README-only claim, so an export cannot quietly drop it.

## Summary

| Source | Licence | Commercial use | Obligations | Status in Cooker |
| --- | --- | --- | --- | --- |
| USDA FoodData Central | CC0 1.0 | Yes | None; attribution requested | In use |
| UK CoFID (McCance & Widdowson) | Open Government Licence v3.0 | Yes | Attribute the source and Crown copyright | Planned |
| Open Food Facts | ODbL 1.0 (database), DbCL 1.0 (contents), CC BY-SA (photos) | Yes | Attribution and share-alike on a publicly used derivative database | Not enabled |

## USDA FoodData Central

USDA publishes FoodData Central under CC0 1.0. It is public domain, is not
copyrighted, and can be copied, adapted, and redistributed commercially
without permission. The USDA asks users to name FoodData Central as the source
and, when possible, to tell USDA about products that use the data.

The importer writes this attribution onto every USDA row:

> U.S. Department of Agriculture, Agricultural Research Service. FoodData
> Central, 2019. fdc.nal.usda.gov.

## UK CoFID

CoFID is published under the Open Government Licence v3.0. Commercial use,
adaptation, and combination with other data are permitted. Any public use
must acknowledge the source and Crown copyright. The required statement is
stored with each CoFID row.

Do not use the separate Quadram Institute API as a shortcut unless its terms
have been reviewed: it is a different source with different terms from the
GOV.UK download.

## Open Food Facts

Open Food Facts is not a public-domain source. The database is under the Open
Database License 1.0 (ODbL), individual contents are under the Database
Contents License 1.0 (DbCL), and photos are under CC BY-SA. Commercial use is
permitted, but:

1. Open Food Facts must be attributed wherever its data is shown.
2. If a publicly used database is derived from the OFDb, the share-alike term
   requires that derivative database to be offered under the ODbL.
3. Combining OFDb data with other databases is only allowed when the other
   sources permit that redistribution.
4. API callers must send a descriptive `User-Agent` and respect rate limits.

Because of the share-alike term, Open Food Facts is deliberately **not**
merged into the main proprietary ingredient database. `nutrition_sources.py`
marks it `share_alike=True`, and `COMMERCIALLY_CLEAR_SOURCES` excludes it. If
branded products are added later, the OFDb-derived rows must stay separable
and the ODbL obligations must be accepted for that subset, or separate
permission must be obtained.

## Recipe corpora

Recipe provenance is stored separately on `Recipe.license` and
`Recipe.attribution`. The importers only accept public-domain or Unlicense
content. See `backend/recipes/openrecipearchive.py`,
`backend/recipes/public_domain_recipes.py`, and
`backend/recipes/management/commands/import_openrecipearchive.py`.

This document is an engineering summary, not legal advice. Review the current
licence text before a commercial launch, especially if Open Food Facts is
enabled.
