Backend - Django

## USDA nutrition snapshots

Set `USDA_API_KEY` in `backend/.env`, then fetch a resumable Foundation Foods snapshot:

```sh
uv run python backend/manage.py fetch_usda_json --fdc-id 2261421 --output /path/to/nutrition.json
```

Import the validated snapshot in batches, optionally reviewing it first:

```sh
uv run python backend/manage.py import_usda_json --file /path/to/nutrition.json --dry-run
uv run python backend/manage.py import_usda_json --file /path/to/nutrition.json --batch-size 100
```

The fetch command skips FDC IDs already present in the snapshot; use `--refresh` to re-fetch them. It waits when the USDA rate-limit headers indicate that too few requests remain.
