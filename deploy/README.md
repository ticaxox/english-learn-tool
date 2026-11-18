# Container and deployment baseline

This directory contains the reproducible release, Compose, health-check, backup and
rollback assets for the private learning platform. It does not modify the existing
OpenResty or 1Panel services and must not occupy host ports `80`, `443` or `30000`.

## Services

`docker-compose.yml` defines:

- `postgres`: PostgreSQL 16 with a persistent named volume.
- `redis`: Redis 7 with AOF persistence and a persistent named volume.
- `migrate`: one-shot API image running `alembic upgrade head`.
- `api`: FastAPI inside the Compose network.
- `worker`: ARQ worker with a Redis health key.
- `scheduler`: ARQ scheduler; container liveness is checked separately.
- `api`, `worker` and `scheduler`: share `wordbook-data` at `/app/var/wordbooks`.
- `frontend`: non-root Nginx serving the built Vue application.
- `reverse-proxy`: non-root Nginx with CSP, HSTS, existing security headers and
  non-buffered SSE routing for `/api/v1/coach/streams/*`.

Only the reverse proxy publishes a host port and it is loopback-bound by default.
PostgreSQL and Redis never publish host ports. Application containers run as UID/GID
`10001`, retain a read-only root filesystem, drop all capabilities and set
`no-new-privileges`.

## Local clean-start verification

Create a disposable environment file outside Git and run:

```bash
cp .env.example .env
chmod 600 .env
docker compose --env-file .env config --quiet
python -m unittest discover -s deploy/tests -p "test_*.py" -v
./deploy/scripts/start-stack.sh
```

For a constrained local profile:

```bash
# In the disposable .env
DEPLOYMENT_PROFILE=local-lightweight
ENABLE_DEMO_TUNNEL=0

./deploy/scripts/start-stack.sh
```

`start-stack.sh` builds images, starts PostgreSQL and Redis, runs migrations, starts the
application services, checks health, confirms non-root containers and validates
`/api/v1`, CSP, HSTS and SSE headers.

Run the real cross-container volume probe after startup:

```bash
COMMIT_SHA="$(git rev-parse HEAD)" \
EVIDENCE_FILE=deploy/backups/wordbook-storage-evidence.json \
  ./deploy/scripts/verify-wordbook-storage.sh
```

The probe creates random metadata-only markers, exercises API/worker/scheduler
create-read-write-append-delete and restart persistence, checks UID/GID `10001:10001`,
volume identity, read-only root filesystem and static-path non-exposure. It never emits
file bodies or credentials.

## CI

`.github/workflows/ci.yml` runs four blocking jobs:

- backend lint and integration tests on real PostgreSQL and Redis;
- frontend build and unit tests;
- Gitleaks secret scanning;
- Compose build, migration, storage, health, security-header and SSE checks.

The Compose job also resolves the merged production/lightweight configuration, validates
release manifests and checks that the active memory caps fit the declared budget.

## Immutable release workflow

`.github/workflows/release.yml` supports both a semver tag push and a manual run from
`main`. A manual run requires a version such as `v0.1.0`, creates the annotated tag from
`main`, builds three application images for `linux/amd64`, records image digests and
publishes a GitHub Release.

The release manifest schema is:

```json
{
  "schema_version": 1,
  "release": "v0.1.0",
  "source_commit": "<40-character-sha>",
  "created_at": "<ISO-8601 UTC>",
  "platform": "linux/amd64",
  "images": {
    "api": "ghcr.io/<owner>/english-learn-api@sha256:<digest>",
    "frontend": "ghcr.io/<owner>/english-learn-frontend@sha256:<digest>",
    "reverse_proxy": "ghcr.io/<owner>/english-learn-reverse-proxy@sha256:<digest>"
  },
  "runtime_images": {
    "postgres": "postgres:16-alpine@sha256:<digest>",
    "redis": "redis:7-alpine@sha256:<digest>",
    "cloudflared": "cloudflare/cloudflared:2026.10.3@sha256:<digest>"
  }
}
```

Every runtime image is digest-pinned. The release workflow uploads a metadata-only
manifest, a private image bundle and SHA-256 checksums. `latest` is not used by deployment.
Validate a downloaded manifest before use:

```bash
python3 deploy/scripts/validate_release_manifest.py deploy/releases/release-manifest.json
```

## Production deployment

Prerequisites:

1. A01/A00-approved target environment or an explicitly accepted equivalent demo route.
2. A validated release manifest and matching image availability.
3. Real PostgreSQL/Redis, approved secrets, domain/TLS or approved tunnel, and a backup
   location outside the repository.
4. Confirmation that 1Panel/OpenResty and ports `80/443/30000` remain untouched.

Copy `.env.example` to a server-only `.env` and replace every secret. Keep the file mode
`0600` outside Git. Set `DEPLOYMENT_PROFILE=production` for the standard profile or
`DEPLOYMENT_PROFILE=lightweight` for the constrained 1 vCPU / 1 GiB profile.

```bash
export RELEASE_MANIFEST=/secure/releases/release-manifest.json
export DEPLOYMENT_RECEIPT_FILE=/secure/evidence/deployment-receipt.json
ENV_FILE=/secure/english-learn/.env ./deploy/scripts/deploy.sh
```

The deployment script:

1. Refuses placeholder secrets, mutable image references or protected host ports.
2. Checks available memory and disk before pulling images.
3. Runs a pre-migration PostgreSQL backup when a database already exists.
4. Pulls the exact manifest images, starts PostgreSQL/Redis and runs migrations.
5. Starts API/worker/scheduler/frontend/reverse-proxy and verifies health, non-root,
   CSP/HSTS, SSE headers and Alembic head.
6. Optionally writes a metadata-only deployment receipt.

The lightweight overlay enforces per-service CPU/memory caps and Redis/PostgreSQL memory
tuning. It is a constrained demo profile, not a claim that a 1 vCPU / 1 GiB server meets
the standard production baseline. Do not deploy the standard profile to that host.

## Public HTTPS and SSE ingress

The preferred production route is a named Cloudflare Tunnel or another A01/A00-approved
ingress that leaves existing OpenResty/1Panel untouched.

`deploy/compose.tunnel.yml` provides an optional account-less Quick Tunnel for short-lived
verification only:

```bash
ENABLE_DEMO_TUNNEL=1
PUBLIC_BASE_URL=https://<assigned>.trycloudflare.com
./deploy/scripts/verify-public.sh
```

Quick Tunnels have no uptime guarantee, rotate without account control and are not suitable
for production or a final competition link. Use a named tunnel/token or the approved
existing proxy for a stable URL. The app itself remains bound to a loopback high port; no
host port `80/443/30000` is changed.

The public verification checks certificate validation, DNS, CSP, HSTS, the existing
security headers, health endpoints, API root and SSE cache behavior. Cloudflare may strip
the diagnostic `X-Accel-Buffering` response header; the origin Nginx check remains
authoritative. It records metadata only, with no cookie or response body.

## Backup and recovery

The approved policy and RPO/RTO placeholders are in
[`BACKUP-AND-RECOVERY.md`](BACKUP-AND-RECOVERY.md). The default is no automatic deletion.

```bash
ENV_FILE=.env ./deploy/scripts/backup-db.sh
ENV_FILE=.env ./deploy/scripts/backup-wordbooks.sh
ENV_FILE=.env ./deploy/scripts/verify-database-restore.sh
ENV_FILE=.env ./deploy/scripts/verify-wordbook-restore.sh
```

Database dumps and wordbook archives are private data. Keep them outside Git and never
copy their contents into evidence. The verification scripts create disposable restore
targets, compare metadata/table counts, write SHA-256 evidence and clean up by default.

## Rollback

`rollback.sh` requires a previously validated release manifest, not a floating tag:

```bash
ENV_FILE=.env ./deploy/scripts/rollback.sh /secure/releases/previous-release.json
```

Before switching images it compares the database's current Alembic revision with the
target image's heads. A mismatch stops the rollback and requires an approved matching
database restore. The script never reverses migrations, deletes `wordbook-data` or
recreates named volumes.

## Wordbook volume lifecycle

### Invariants

The private wordbook store is a named Docker volume, `wordbook-data`, mounted at the fixed
container path `/app/var/wordbooks` on `api`, `worker` and `scheduler` only. All three use
the same source and set `WORDBOOK_STORAGE_DIR=/app/var/wordbooks`.

The backend image creates that directory before dropping privileges. Its expected owner is
UID/GID `10001:10001`, its mode is `0750`, and application files are private. Never use
`chmod 777`, run these services as root or add capabilities to work around ownership.
Never mount the directory into frontend or reverse proxy. Downloads must use the
authenticated API and its short-lived token/path-safety checks.

### Stop, delete and cleanup

`docker compose down` preserves named volumes. `docker compose down -v` permanently
removes PostgreSQL, Redis and wordbook data and is allowed only for a disposable isolated
project or after explicit approval of irreversible deletion. Never use
`docker volume prune`, `docker system prune --volumes` or wildcard volume deletion.

Expired preview/export/temp files are application data and must be removed by the
scheduler's TTL retention job. Manual cleanup requires a documented TTL/allowlist, dry-run
count, quiescence or maintenance window, a current backup and an audit record.

### Monitoring and recovery

Use `docker system df -v` or approved volume metrics to monitor capacity; do not print
credentials or file contents. For file-level RPO, use an approved snapshot or the
wordbook backup workflow, restore into a new reviewed volume first and attach it only
after owner/mode and application checks pass.

## Environment and secret rules

- Passwords containing URL-reserved characters must be percent-encoded in `DATABASE_URL`;
  `POSTGRES_PASSWORD` remains the raw value.
- `.env.example` contains disposable placeholders only. Never commit `.env`, server
  addresses, private keys, JWTs, provider keys, real member data or backup contents.
- Backup/log files may contain private data and must not be included in Git, screenshots,
  public chats or CI artifacts.
- The existing OpenResty, 1Panel, firewall, DNS and production data are out of scope unless
  a separate approved change window exists.