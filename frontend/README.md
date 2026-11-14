# Cooker frontend

React 19, TypeScript and Vite for the Cooker recipe finder. Tailwind CSS v4
provides the design tokens in `src/index.css`; the API client is generated from
the Django Ninja OpenAPI schema.

## Development

The Vite dev server proxies `/api`, `/admin` and `/static` to
`http://127.0.0.1:8000`, so run Django alongside it:

```sh
# from the repository root
.venv/bin/python backend/manage.py runserver

# in another terminal
cd frontend
npm install
npm run dev
```

Set `VITE_API_ORIGIN` only when the API lives somewhere other than the proxied
origin.

## Checks

```sh
npm run lint       # oxlint
npm run typecheck  # tsc -b
npm run build      # typecheck plus a production build
```

## API types

`src/api/schema.d.ts` is generated from `openapi.json`:

```sh
cd frontend
npm run api:types
```

Regenerate both files when the backend schemas change; `openapi.json` is served
by the running API at `/api/openapi.json`.

## Routes

- `/` — pantry hero, stats and featured recipes
- `/finder` — recipes ranked by pantry coverage
- `/recipes` — search plus category, cuisine and nutrition filters
- `/recipes/:slug` — recipe detail, source attribution and nutrition
- `/data` — data sources and licence notes
