# Backend

FastAPI backend for the private English learning platform. The current identity slice implements
real PostgreSQL-backed accounts, rotating Redis-aware authentication sessions, administrator member
management, CSV member import, audit records, and Alembic migrations.

## Requirements

- Python 3.12
- `uv`
- PostgreSQL 16
- Redis 7

The application and tests use real PostgreSQL and Redis connections. There is no in-memory
database or test-only authentication fallback.

## Local setup

From `backend`:

```powershell
uv sync --locked --all-groups
Copy-Item .env.example .env
# Edit .env and replace every example secret before starting the service.
createdb english_learn
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Create the first administrator only after migrations succeed:

```powershell
uv run python -m app.cli bootstrap-admin
```

The command prompts for the username, display name, and password without echoing the password. For
non-interactive secret injection, set `BOOTSTRAP_ADMIN_USERNAME`,
`BOOTSTRAP_ADMIN_DISPLAY_NAME`, and `BOOTSTRAP_ADMIN_PASSWORD` in the process environment, run the
command, then remove the password variable. The command refuses to create another administrator
while an active administrator already exists. It never accepts a password as a command-line
argument and never writes the password to logs or audit context.

## Identity API

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/change-password`
- `GET /api/v1/auth/me`
- Administrator member management under `/api/v1/admin/users`

Access tokens are short-lived JWTs and are sent as `Authorization: Bearer <token>`. The refresh
token is an opaque random value stored in an `HttpOnly` cookie limited to
`Path=/api/v1/auth/refresh`. The non-HttpOnly CSRF token uses `Path=/` so the SPA can read it from
`document.cookie` on any application route. Both cookies use `SameSite=Lax`; production also sets
`Secure`.

Refresh and logout require:

1. the refresh cookie where applicable;
2. the CSRF cookie;
3. the same value in `X-CSRF-Token`;
4. an allowed `Origin` header.

The CSRF token is also returned in login/refresh responses for immediate use. Do not persist access
tokens in browser storage and do not disable Origin or CSRF validation to work around routing.

OpenAPI and Swagger UI:

- `http://127.0.0.1:8000/api/v1/openapi.json`
- `http://127.0.0.1:8000/api/v1/docs`
- `GET /health/live`
- `GET /health/ready`
- `GET /api/v1`

## CSV member import

Upload a UTF-8 CSV to `POST /api/v1/admin/users/import/preview`. Required headers:

```text
username,display_name,initial_password,department,learning_group
```

`initial_password` may be blank, in which case a one-time strong temporary password is generated.
Preview rows report invalid fields, duplicate usernames in the file, and existing database
conflicts. Confirm the preview through `POST /api/v1/admin/users/import` with both `preview_id` and
`preview_hash`. All rows are created atomically or none are created. Imports always create members,
never administrators. Temporary passwords are returned only in the creation/import response and are
never persisted in plaintext or exposed by later status/detail requests.

## Workers

Run these in separate terminals while the API is running:

```powershell
uv run arq app.workers.worker.WorkerSettings
uv run arq app.workers.scheduler.SchedulerSettings
```

The worker and scheduler are infrastructure entrypoints only. Business jobs belong to later
domain tasks.

## Verification

Create a dedicated integration database and Redis database, then run the checks:

```powershell
$env:TEST_DATABASE_URL="postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/english_learn_test"
$env:TEST_REDIS_URL="redis://127.0.0.1:6379/15"
$env:DATABASE_URL=$env:TEST_DATABASE_URL
uv run alembic upgrade head
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run pytest
uv run pytest tests/test_state_isolation.py -q
uv run pytest tests/test_state_isolation.py -q
```

`pytest` always replaces application database and Redis settings with `TEST_*` values so a developer
shell cannot accidentally target production dependencies. The suite applies the current Alembic
migration before running. Each test runs inside a PostgreSQL transaction that is rolled back during
teardown, and the configured test Redis database is flushed before and after every test.
`TEST_REDIS_URL` must therefore point to a dedicated non-production database. If PostgreSQL or Redis
is unavailable, integration tests fail rather than silently skipping.

The state-isolation regression writes to PostgreSQL and Redis in one test and verifies the next test
starts clean. Running the suite and the regression twice without manually clearing either service is
the required repeatability check.

## Database changes and rollback

Create a migration for every schema change and review both upgrade and downgrade paths:

```powershell
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head
uv run alembic downgrade 20261022_0001
uv run alembic upgrade head
```

The identity migration also supports an empty database:

```powershell
uv run alembic upgrade head
uv run alembic check
```

## Configuration and privacy

All runtime values come from environment variables. `.env.example` contains placeholders only.
Never commit `.env`, API keys, production connection strings, real passwords, access tokens, refresh
tokens, complete member CSV uploads, or organization member data. Audit context records request IDs,
actions, outcomes, and minimal non-secret metadata only.
