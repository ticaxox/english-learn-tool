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
- `api`, `worker` and `scheduler`: share the `wordbook-data` named volume at `/app/var/wordbooks`.
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

Run the merged-config contract before starting a disposable stack:

```bash
python -m unittest discover -s deploy/tests -p "test_*.py" -v
python deploy/tests/check_compose_storage.py --env-file .env --compose-file docker-compose.yml
```

After the stack is healthy, verify the real cross-container file contract:

```bash
EVIDENCE_FILE=deploy/backups/wordbook-storage-evidence.json \
  ./deploy/scripts/verify-wordbook-storage.sh
```

This probe creates random, non-sensitive marker files, exercises API/worker/scheduler
read-write-delete flows, restarts the three services, reads the surviving marker, checks
runtime UID/GID and security options, and removes its files. Run it only against a
disposable project; it restarts application containers. It writes metadata-only JSON and
does not emit file contents or credentials.

## CI

`.github/workflows/ci.yml` runs on every pull request and on pushes to `main`:

- Backend: locked dependency install, Ruff check, Ruff format check, pytest with real
  PostgreSQL and Redis services.
- Frontend: locked npm install, production build and Vitest.
- Quality: quality-manifest validator and its unit tests.
- Security: Gitleaks scan with secrets redacted.
- Compose integration: contract and cross-container wordbook tests, clean image build,
  empty-database migration, service startup, non-root/read-only checks, restart
  persistence, static-path probes and live/readiness checks through the reverse proxy.

The Compose job is the independent runtime evidence required by `T-SHIP-001` and
`T-SHIP-STORAGE-001`; it runs on an ephemeral GitHub-hosted runner with a unique Compose
project name. The runner uploads a metadata-only JSON artifact and removes that isolated
project with `down --volumes` after collection.

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
pre-deployment backup through an approved manual procedure. Application rollback must
keep the same `wordbook-data` volume name; it must not create a blank replacement volume.

Database backups do not include the wordbook named volume. Preview/export files also are
not reconstructed by a database restore. If file-level RPO is required, use an approved
volume snapshot or file-level backup and restore procedure; do not infer recoverability
from a PostgreSQL dump alone.

## Wordbook storage security and lifecycle

### Invariants

The private wordbook store is a named Docker volume, `wordbook-data`, mounted at the fixed
container path `/app/var/wordbooks` on `api`, `worker` and `scheduler` only. All three use
the same source and set `WORDBOOK_STORAGE_DIR=/app/var/wordbooks`.

The backend image creates that directory before dropping privileges. Its expected owner
is UID/GID `10001:10001`, its directory mode is `0750`, and application files are created
privately. Do not use `chmod 777`, run these services as root, or add capabilities to work
around an ownership error. The container root filesystem remains read-only; only the
wordbook named volume and the existing `/tmp` tmpfs are writable.

On first attachment to an empty named volume, Docker initializes the volume from the
image directory metadata. Existing volume data is not overwritten. Do not replace it with
a host bind mount, an anonymous volume or a separate volume per service. Never mount the
directory into the frontend or reverse proxy. There is no static URL for these files:
every download must use the authenticated API and its existing short-lived token and
path-safety checks.

### Stop and delete semantics

`docker compose down` stops and removes containers and networks but preserves named
volumes, including the wordbook files. `docker compose down -v` permanently removes every
named volume in that Compose project, including PostgreSQL, Redis and wordbook data. The
latter is allowed only for a disposable isolated CI project or after explicit approval of
an irreversible clean-up. Never use `docker volume prune`, `docker system prune --volumes`
or a broad volume-name wildcard on a shared host.

### Cleanup responsibility

Expired preview, export and temporary artifacts are application data and must be removed
by the scheduler's TTL-based retention job, not by an ad hoc whole-directory delete. A
manual cleanup requires all of the following:

1. A documented TTL and an explicit allowlist of randomized key prefixes.
2. A dry-run count using metadata only, with no file bodies copied to logs or tickets.
3. Worker/scheduler quiescence or an approved maintenance window.
4. A current backup or snapshot when recovery is required by policy.
5. An audit record of actor, time, selection rule, count and result.

Never delete the volume root, remove files by a guessed user identifier, or expose private
content while investigating. A compliance or incident deletion that needs immediate
removal is a separate approved incident action.

### Release and rollback

Rolling releases, migrations and application rollbacks must not rename, recreate or
automatically delete `wordbook-data`. Reuse the existing volume and verify directory
ownership after any image change. Before a release that changes storage semantics, take
the approved backup and verify a restore path in a disposable project. If old code is
incompatible with new files, stop the rollout instead of deleting the evidence or the
volume.

### Monitoring, recovery and backup

Use `docker system df -v` or the platform's approved volume metrics to monitor capacity;
do not print host mount paths, credentials or file contents in shared evidence. Alert on
sustained disk growth, and inspect container health and volume attachment metadata before
changing permissions. If the volume is missing or mounted read-only, stop the affected
services and investigate the Compose project/volume identity; do not create a replacement
volume silently.

For file-level RPO, use an approved snapshot or controlled backup workflow and record the
snapshot identifier, time, project and restore test result. A restore must target a new
reviewed volume first, then be attached only after owner/mode and application checks pass.
The database backup script intentionally covers PostgreSQL only; it does not back up the
wordbook files.

## Environment notes

- Passwords containing URL-reserved characters must be percent-encoded inside
  `DATABASE_URL`, while `POSTGRES_PASSWORD` remains the raw database password.
- The `.env.example` placeholders are valid only for disposable CI/local checks.
- The root `.env` must remain untracked and outside build images.
- Backups and logs can contain private data and must not be copied into evidence,
  screenshots or Git.
