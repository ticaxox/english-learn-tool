# Backend

FastAPI backend baseline for the private English learning platform.

## Requirements

- Python 3.12
- `uv`
- PostgreSQL 16
- Redis 7

The application and tests use real PostgreSQL and Redis connections. There is no in-memory
database fallback.

## Local setup

From `backend`:

```powershell
uv sync --all-groups
Copy-Item .env.example .env
# Edit .env and replace every example secret before starting the service.
createdb english_learn
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Endpoints:

- `GET /health/live`
- `GET /health/ready`
- `GET /api/v1`
- OpenAPI: `http://127.0.0.1:8000/api/v1/openapi.json`
- Swagger UI: `http://127.0.0.1:8000/api/v1/docs`

## Workers

Run these in separate terminals while the API is running:

```powershell
uv run arq app.workers.worker.WorkerSettings
uv run arq app.workers.scheduler.SchedulerSettings
```

The worker and scheduler are infrastructure entrypoints only. Business jobs belong to later
domain tasks.

## Verification

Create an integration database and run the checks:

```powershell
$env:TEST_DATABASE_URL="postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/english_learn_test"
$env:TEST_REDIS_URL="redis://127.0.0.1:6379/15"
$env:DATABASE_URL=$env:TEST_DATABASE_URL
uv run alembic upgrade head
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

`pytest` always replaces application database and Redis settings with `TEST_*` values so a
developer shell cannot accidentally target production dependencies. The suite applies the
current Alembic migration before running. Each test runs inside a PostgreSQL transaction that
is rolled back during teardown, and the configured test Redis database is flushed before and
after every test. `TEST_REDIS_URL` must therefore point to a dedicated non-production database.
If PostgreSQL or Redis is unavailable, integration tests fail rather than silently skipping.

## Database changes

Create a migration for every schema change:

```powershell
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head
```

Review generated SQL and provide a downgrade path in the change report.

## Configuration and privacy

All runtime values come from environment variables. `.env.example` contains placeholders only.
Never commit `.env`, API keys, production connection strings, or organization member data.
