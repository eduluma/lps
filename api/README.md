# LPS API

FastAPI + asyncpg HTTP API.

```bash
cd api
uv sync
uv run alembic upgrade head
uv run python -m app.seed
uv run uvicorn app.main:app --reload
```

Open http://localhost:8000/docs for the OpenAPI UI.

Endpoints (see [PRD §9](../PRD.md#L194)):

- `GET /healthz`
- `GET /api/v1/search?q=...&distro=...`
- `GET /api/v1/projects/{name}`
- `GET /api/v1/packages?distro=&release=&q=`
- `GET /api/v1/packages/{distro}/{release}/{name}`
- `GET /api/v1/distros`
- `GET /api/v1/install/{name}?distro=auto&fmt=text|json`
