# Cooker

A read-only archive of historical American recipes, with a Django Ninja API and a React frontend.
Writes stay in the Django admin; the public surface is a typed, paginated REST API.

## Backend

```bash
cp backend/.env.example backend/.env
# set DJANGO_SECRET_KEY in backend/.env
uv sync
uv run python backend/manage.py migrate
uv run python backend/manage.py runserver 127.0.0.1:8000
```

`backend/.env` is loaded automatically. Real environment variables take precedence over its values.

API docs: <http://127.0.0.1:8000/api/docs>
OpenAPI schema: <http://127.0.0.1:8000/api/openapi.json>

Endpoints:

- `GET /api/health`
- `GET /api/stats`
- `GET /api/recipes/` — `q`, `category`, `contributor`, `tag`, `page`, `page_size`
- `GET /api/recipes/{id}`
- `GET /api/recipes/slug/{slug}`
- `GET /api/ingredients/` — `q`, `category`, `page`, `page_size`
- `GET /api/ingredients/{id}`

## Frontend

```bash
cd frontend
npm install
npm run dev
```

The app runs at <http://127.0.0.1:5173>. Vite proxies `/api`, `/admin` and `/static` to the Django
server at `127.0.0.1:8000`, so local development is same-origin.

Production build:

```bash
cd frontend
npm run build
npm run preview
```

For a split deployment, build with `VITE_API_ORIGIN=https://api.example.com` and add the frontend
origin to `CORS_ALLOWED_ORIGINS` in the backend environment.

## Regenerating API types

The frontend client is generated from the Ninja OpenAPI schema:

```bash
uv run python backend/manage.py dump_openapi
cd frontend
npm run api:types
```

This writes `frontend/openapi.json` and `frontend/src/api/schema.d.ts`.

## Tests

```bash
cd backend
uv run python manage.py test

cd ../frontend
npm run build
```
