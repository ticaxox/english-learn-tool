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

## Learning profile, daily plan, and memory training

- `GET`/`PATCH /api/v1/users/me/profile` - learning profile. `daily_new_words` is 5-100 (default 20)
  and `daily_study_minutes` is 15-180 (default 30); changing them only affects the next daily plan.
- `GET /api/v1/learning/today` and `POST /api/v1/learning/daily-plan/ensure` - the local-date plan
  snapshot (`Asia/Shanghai`). The word set, targets, and `calculation_version` freeze at generation
  time; a later due word is reported only through `extra_due_available`.
- `POST /api/v1/learning/heartbeat` - credits at most 30 seconds per server-measured window and needs
  an `Idempotency-Key`. Stale or idle windows credit nothing.
- `GET /api/v1/learning/stats` and `GET /api/v1/learning/events` - personal statistics and paged events
  derived only from persisted rows.
- `GET`/`PUT /api/v1/memory/config`, `POST /api/v1/memory/sessions`,
  `GET /api/v1/memory/sessions/{session_id}`, `POST /api/v1/memory/sessions/{session_id}/events`,
  `POST /api/v1/memory/sessions/{session_id}/complete`,
  `PATCH /api/v1/memory/words/{state_id}/master`, `PATCH /api/v1/memory/words/{state_id}/restore`,
  `GET /api/v1/memory/mistakes`, `PATCH /api/v1/memory/mistakes/{entry_id}/priority`.

Scheduling uses pinned `fsrs==6.3.2` on the server only. Clients submit a card operation or answer and
an `Idempotency-Key`; stability, difficulty, due timestamps, and the rating are never client input.
A new word needs two `Good` ratings in one session and reappears after at least four other cards; an
`Again` never resets the first `Good` but requeues the card. An overdue review completes with one
`Good` and enters `relearning` after `Again`. Choice and spelling prompts never include the correct
answer or option identifiers before submission, and spelling grading ignores case.

Deleting a wordbook also removes the learner states, sessions, session items, events, plans, and
mistake markers that referenced it, so no ghost learning rows survive the tombstone.

## AI provider, prompt, structured generation, and quota foundation

- Administrators configure OpenAI-compatible providers through `/api/v1/admin/ai/providers` and can
  run a real `/models` connection check or fetch the model list. API keys are encrypted with AES-GCM
  using `SECRET_ENCRYPTION_KEY`; every response contains only a mask such as `sk-****abcd`.
- Provider URLs are checked for protocol, credentials, DNS resolution, blocked metadata hosts,
  loopback/private targets, and cross-origin redirects. `AI_ALLOW_PRIVATE_PROVIDER_URLS` exists only
  for local protocol tests and is rejected when `APP_ENV=production`.
- Prompts are seeded by the `c5ab093fd0f9` migration and can be overwritten through
  `/api/v1/admin/ai/prompts`. A job stores a prompt snapshot, so later edits apply only to new jobs.
- `/api/v1/ai/jobs` creates durable structured jobs. The worker requests JSON Schema/JSON Mode,
  validates with Pydantic v2, enforces business rules, performs at most one JSON repair and three
  logical generation attempts, and never returns partial results. The member status endpoint exposes
  only status, provider/model, attempt counts, error, and a privacy-safe result summary.
- `ai_usage_ledger` reserves quota before provider work, consumes only after success, and releases on
  failure, cancellation, or stale reconciliation. Redis enforces at most two active AI jobs per user.
  Daily defaults are 100 coach messages, 20 question-generation jobs, and 50 subjective gradings.
- The existing business ARQ queue is reused for AI jobs, while the scheduler queue remains isolated.
  AI provider failure does not block learning, wordbooks, or persisted records.

Set a deployment-owned master secret of at least 32 characters:

```dotenv
SECRET_ENCRYPTION_KEY=<strong-random-secret>
```

For local OpenAI-compatible tests only:

```dotenv
AI_ALLOW_PRIVATE_PROVIDER_URLS=true
```

Never commit provider keys, real prompts containing member data, or the master encryption secret.

## AI practice sessions, drafts, grading, and records

- `POST /api/v1/practice/sessions` creates fill-in-the-blank, reading, translation, or writing
  practice and enqueues structured generation through the shared AI job queue.
- `GET /api/v1/practice/sessions/{id}` returns only answer-safe public question fields. Correct
  options, explanations, reference translations, reference essays, and grading remain in private
  payloads until the session is submitted.
- `PUT /api/v1/practice/sessions/{id}/draft` saves the caller's draft with optimistic version checks;
  `POST /regenerate` is limited to unanswered sessions and invalidates the old generation.
- Objective practice is graded synchronously by the server. Translation and writing use one bounded
  batch grading AI job; a failed grading task returns an explicit failure and never a default score.
- `GET /records`, `GET /mistakes`, `GET /records/{id}`, `DELETE /records/bulk`, and `GET /events`
  are owner-scoped. Deleting a record cascades its questions, submission, draft, and learning events.
- Migration `fbff60ce778f` adds practice sessions, generations, questions, submissions, events, and
  idempotent deletion records; AI usage ledger amounts support per-question subjective grading.

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
