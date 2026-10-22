# Backend

FastAPI backend for the private English learning platform. The implemented M2 slices provide real
PostgreSQL-backed accounts, rotating Redis-aware authentication sessions, administrator member
management, member and wordbook imports, durable ARQ wordbook jobs, audited activation/deletion, and
Alembic migrations.

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

Administrators cannot delete their own account, even when another active administrator exists. The
API returns `409 SELF_DELETE_FORBIDDEN` and records a sanitized failure audit event.

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

The worker consumes `english-learn:wordbooks` and executes the durable `process_wordbook_job`
function for import, export, and deletion. The scheduler consumes the separate
`english-learn:scheduler` queue, recovers persisted queued jobs and stale interrupted runs, repairs
terminal or stale same-ID ARQ entries, and removes expired preview/export artifacts. The scheduler
must never share the business worker queue. `WORDBOOK_JOB_STALE_SECONDS` defaults to 600 seconds,
which is longer than the worker's 300-second job timeout; queue-delivery and processing failures are
persisted and bounded by `WORDBOOK_JOB_MAX_ATTEMPTS`. Job state, ownership, progress, results, retry
counts, and failure codes are stored in PostgreSQL; Redis is the queue transport, not the business
source of truth.

## Wordbook API

- `GET /api/v1/wordbooks` - visible organization/private list with pagination.
- `GET /api/v1/wordbooks/{wordbook_id}` - confirmed entries and definitions with pagination.
- `PATCH /api/v1/wordbooks/{wordbook_id}` - metadata-only update.
- `POST /api/v1/wordbooks/{wordbook_id}/activate` - idempotent ready-book activation.
- `DELETE /api/v1/wordbooks/{wordbook_id}` - idempotent deletion task; organization books require
  exact `confirm_name` confirmation.
- `POST /api/v1/wordbooks/import/preview` - CSV/JSON/TXT upload preview, valid for 24 hours.
- `PATCH /api/v1/wordbooks/import/previews/{preview_id}` - column remapping.
- `POST /api/v1/wordbooks/import` - confirmed asynchronous import.
- `POST /api/v1/wordbooks/{wordbook_id}/export` - CSV/TXT/PDF asynchronous export.
- `GET /api/v1/wordbooks/jobs/{job_id}` - import/export/delete polling.
- `GET /api/v1/exports/{job_id}` - export-only polling and short-lived download metadata.
- `GET /api/v1/exports/{job_id}/download` - owner or authorized organization administrator download.

Import confirmation, export creation, and deletion require an `Idempotency-Key` header. Preview
tokens are hashed at rest. Organization wordbooks are visible to active members but only
administrators can mutate or export them; private wordbooks remain restricted to their owner, even
when the requester is an administrator. Deleting a book immediately changes it to `deleting`, which
blocks activation and export. Cleanup removes entries, definitions, examples, activation state,
previews, related jobs, and isolated files while retaining a tombstone and the delete job for safe
polling.

Wordbook imports accept at most 10 MiB and 20,000 logical entries after duplicate merging. The parser
supports UTF-8 BOM, UTF-8, GB18030, and UTF-16 LE/BE; CSV comma/tab/semicolon/pipe delimiters; JSON
top-level arrays or `{"words": [...]}`; and structured TXT lines. Invalid rows are reported rather
than silently dropped, and a confirmed import commits all entry/definition/example rows atomically.

PDFs are rendered with bundled, OFL-licensed Noto Sans and Noto Sans SC fonts. See
`app/assets/fonts/FONT_MANIFEST.md`. The PDF renderer supports configurable page rows and columns and
uses the Latin font for IPA while using the SC font for Chinese text.

Convert approved CSV/JSON/TXT input with the same production normalization and validation rules:

```powershell
uv run python -m app.cli convert-wordbook .\input.csv .\wordbook.json --report .\report.json
```

The output identifies `english-learn-wordbook-converter/1.0.0`; a non-zero exit status means rejected
rows were reported.

`WORDBOOK_STORAGE_DIR` must be an absolute path and defaults to `/app/var/wordbooks`. The Compose
deployment mounts that directory from the same writable persistent volume into the API, ARQ worker,
and scheduler because preview and export artifacts must cross service-process boundaries. A
process-local directory is not a valid deployment. Uploaded data remains private and must not be
served from a public directory.

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
uv run pytest tests/test_wordbooks.py -q
uv run pytest tests/test_wordbook_jobs.py -q
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
