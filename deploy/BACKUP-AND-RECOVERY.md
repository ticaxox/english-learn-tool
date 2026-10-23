# Backup and recovery policy

## Status and approval

This document defines the proposed production backup contract for the English learning
tool. The technical drill is complete, but the RPO/RTO values below require explicit
A01/A00 approval before they may be treated as a production commitment.

| Item | Proposed value | Approval |
|---|---|---|
| PostgreSQL RPO | 24 hours | PENDING A01/A00 |
| Full recovery RTO | 2 hours | PENDING A01/A00 |
| Wordbook file RPO | 24 hours | PENDING A01/A00 |
| Demo-environment retention | 7 daily copies | PENDING A01/A00 |
| Backup owner | A40 SHIP｜部署 | PENDING A01/A00 |
| Restore approver | A01 SYNC｜协同 | PENDING A01/A00 |

## Scope

Authoritative data:

- PostgreSQL: application records, audit metadata, teacher/learner settings, job state.
- `wordbook-data` named volume: private preview/export files used by API, worker and scheduler.

Redis is a queue/cache and AOF persistence is not treated as the recovery source of
record. After a restore, queued work must be reconciled from PostgreSQL and Redis jobs may
be safely recreated. Application secrets, JWT keys, refresh-token pepper and AI provider
keys are configuration data and must never be stored inside database or file backups.

## Storage layout

Production backup directory is a dedicated private directory such as:

```text
/var/backups/english-learn/
```

Requirements:

1. Directory owner is the deployment operator and mode is `0700`.
2. Backup files are mode `0600` and kept outside the Git checkout.
3. Full-disk or storage-snapshot encryption is required for production at-rest storage.
4. Backup storage must not be mounted into application containers or served by Nginx.
5. Database dumps must not be mixed with environment files or provider keys.
6. Encryption master keys and AI keys are restored from the approved secret store, not
   from the backup archive.

## Schedule and retention

Proposed production schedule:

- PostgreSQL custom-format dump once per day.
- Wordbook volume tar archive once per day, in the same maintenance window.
- Retain seven daily copies for the demonstration environment.
- A production retention period longer than seven days requires a separate approved
  policy and storage-capacity check.

`ENABLE_BACKUP_RETENTION=0` is the default. Automatic deletion is disabled unless the
approved schedule sets `ENABLE_BACKUP_RETENTION=1` and `BACKUP_RETENTION_DAYS=7`. The
retention command only matches `postgres-*.dump*` and `wordbooks-*.tar.gz*` in the
explicit backup directory; it must never delete the whole directory or a Docker volume.

## Database backup

```bash
ENV_FILE=.env ./deploy/scripts/backup-db.sh
```

The script creates a custom-format `pg_dump`, a SHA-256 sidecar, mode `0600`, and refuses
to report success for an empty dump.

## Wordbook volume backup

```bash
ENV_FILE=.env ./deploy/scripts/backup-wordbooks.sh
```

The archive is produced through the existing API container's read-only view of the
private volume. It contains private learning content and must not be uploaded to Git,
chat, CI artifact storage, screenshots or public logs. Only hashes and status metadata may
be shared as evidence.

## Database restore drill

```bash
ENV_FILE=.env ./deploy/scripts/verify-database-restore.sh
```

The drill:

1. Creates and checksums a fresh PostgreSQL dump.
2. Restores into a new database whose name starts with `english_learn_restore_`.
3. Compares public table lists and row counts between source and restore.
4. Writes metadata-only evidence with table counts and archive SHA-256.
5. Drops only the disposable restore database by default.

`KEEP_RESTORE_DB=1` may be used during incident investigation with explicit approval.
The primary database is never a restore target.

## Wordbook restore drill

```bash
ENV_FILE=.env ./deploy/scripts/verify-wordbook-restore.sh
```

The drill creates a random non-sensitive marker in the private volume, archives the
volume, restores into a new `english-learn-wordbook-restore-*` volume, verifies UID/GID
`10001:10001`, mode `0750`, marker integrity and then removes the disposable volume.
The restricted restore helper has no network and only the minimum ownership-related
capabilities needed to restore file metadata. It is never part of the running application
profile.

## Recovery procedure

1. Declare an incident and freeze application writes where practical.
2. Record the current image release manifest, database revision and volume identity.
3. Select the latest approved database and wordbook backup; verify both SHA-256 sidecars.
4. Restore the database into a validated replacement target, never over the live database.
5. Restore wordbook files into a new reviewed volume; verify owner, mode and application
   readability before attachment.
6. Attach reviewed volumes and start the frozen release manifest.
7. Run `/health/live`, `/health/ready`, login, private-file and public HTTPS checks.
8. Record the recovery point, recovery time, operator, evidence paths and remaining data
   loss window.
9. Remove old or failed restore targets only with explicit approval and an audit record.

Do not use `docker compose down -v`, `docker volume prune`, broad wildcard deletion or an
unreviewed migration rollback as part of recovery.

## Completed drill evidence

The local WSL Ubuntu-26.04 drill on 2026-10-24 verified:

- PostgreSQL isolated restore with table-list and row-count equality.
- Wordbook volume backup, isolated restore, owner/mode and marker integrity.
- Checksums and metadata-only evidence; no private file bodies were archived in the
  evidence directory.
- Network and capabilities of the restore helper remained restricted.

The evidence is stored under
`ai-workspace/10-collaboration/sessions/A40-SHIP/test-artifacts/T-SHIP-002-20261024/`.
This does not replace approval of the production schedule or a production restore drill.