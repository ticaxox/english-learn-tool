# Container and deployment baseline

This directory contains the reproducible build, Compose, health-check, backup and
rollback assets for the private learning platform. It does not deploy to the shared
cloud server and does not modify the existing OpenResty or 1Panel services.

## Services

`docker-compose.yml` defines:

- `postgres`: PostgreSQL 16 with a persistent named volume.
- `redis`: Redis 7 with AOF persistence and a persistent named volume.
- `migrate`: one-shot API image running `alembic upgrade head`.
- `api`: FastAPI on port 8000 inside the Compose network.
- `worker`: ARQ worker.
- `scheduler`: ARQ scheduler.
- `frontend`: non-root Nginx serving the built Vue application.
- `reverse-proxy`: non-root Nginx routing `/` to the frontend and `/api`, `/health` to the API.

Only the reverse proxy publishes a host port, bound to loopback by default. PostgreSQL
and Redis never publish host ports. API, worker, scheduler, frontend and reverse proxy
run as non-root UID `10001`; the base PostgreSQL and Redis images use their own managed
service users.

## Local clean-start verification

Create a disposable environment file and never commit it:

```bash
cp .env.example .env
chmod 600 .env
```

Then run:

```bash
docker compose --env-file .env config --quiet
./deploy/scripts/start-stack.sh
```

`start-stack.sh` performs the following sequence:

1. Build all project images.
2. Start PostgreSQL and Redis and wait for their health checks.
3. Run the Alembic migration as a one-shot container.
4. Start API, worker, scheduler, frontend and reverse proxy.
5. Verify all container health states, non-root application UIDs, HTTP routes, readiness
   and the applied Alembic head.

The script deliberately recreates the same sequence used by CI. A successful YAML parse
alone is not treated as container verification.

## CI

`.github/workflows/ci.yml` runs on every pull request and on pushes to `main`:

- Backend: locked dependency install, Ruff check, Ruff format check, pytest with real
  PostgreSQL and Redis services.
- Frontend: locked npm install, production build and Vitest.
- Quality: quality-manifest validator and its unit tests.
- Security: Gitleaks scan with secrets redacted.
- Compose integration: clean image build, empty-database migration, service startup,
  non-root checks and live/readiness checks through the reverse proxy.

The Compose job is the independent runtime evidence required by `T-SHIP-001`; it runs on
an ephemeral GitHub-hosted runner.

## Release images

`.github/workflows/release.yml` publishes three GHCR images on a semantic version tag or
manual dispatch:

- `english-learn-api`
- `english-learn-frontend`
- `english-learn-reverse-proxy`

Each image receives a full Git SHA tag. Version tags also receive semantic-version and
`latest` tags. Production deployment uses either the full 40-character SHA or a semantic
version tag; `local` and `latest` are rejected by `deploy.sh`.

## Production deployment guardrails

The shared server currently has about 1 vCPU and 1 GiB RAM. That is below the product
baseline for the full stack. Do not deploy this complete Compose stack to the current
server without either:

- a confirmed server upgrade, or
- a separately reviewed and runtime-tested lightweight profile.

A later, approved deployment task must also resolve domain, TLS, reverse-proxy routing,
backup storage and monitoring. The current repository does not contain server addresses,
credentials or real member data.

Required pre-deployment checks:

1. Confirm host-key validation and server access through the central access checklist.
2. Confirm the existing OpenResty and 1Panel services and ports remain untouched.
3. Expose the application only on a loopback high port or through an approved existing
   proxy; do not bind this project to `80`, `443` or `30000`.
4. Prepare a production `.env` outside Git with unique secrets.
5. Confirm the release images exist in GHCR and use an immutable SHA tag.
6. Confirm available disk and memory meet the measured stack footprint.
7. Run a database backup before changing a populated deployment.

A deployment invocation has the following shape, but must only be run under the later
server task:

```bash
ENV_FILE=/secure/path/english-learn.env \
  GHCR_OWNER=ticaxox \
  IMAGE_TAG=<full-40-character-sha> \
  ./deploy/scripts/deploy.sh
```

The script validates configuration, backs up a running database, pulls immutable images,
runs migrations and verifies the live stack.

## Backup and rollback

Create a PostgreSQL custom-format backup:

```bash
ENV_FILE=/secure/path/english-learn.env ./deploy/scripts/backup-db.sh
```

Backups are written with restrictive permissions under `BACKUP_DIR` and must never be
committed. Restore is intentionally not automated: it is a destructive database action
that requires a separately approved incident or rollback task.

Application rollback to a previous immutable image tag:

```bash
ENV_FILE=/secure/path/english-learn.env \
  GHCR_OWNER=ticaxox \
  ./deploy/scripts/rollback.sh <previous-full-sha-or-semver-tag>
```

`rollback.sh` does not reverse migrations automatically. If the prior application is
schema-incompatible with the current database, stop the rollout and restore the matching
pre-deployment backup through an approved manual procedure.

## Environment notes

- Passwords containing URL-reserved characters must be percent-encoded inside
  `DATABASE_URL`, while `POSTGRES_PASSWORD` remains the raw database password.
- The `.env.example` placeholders are valid only for disposable CI/local checks.
- The root `.env` must remain untracked and outside build images.
- Backups and logs can contain private data and must not be copied into evidence,
  screenshots or Git.
