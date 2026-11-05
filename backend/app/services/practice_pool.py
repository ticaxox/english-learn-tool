"""Pre-generated practice sets.

Learners can ask the product to keep a small stock of ready practice sets per
practice type and question count. A set is a normal practice session generated
ahead of time; starting a matching practice claims it and a background task
refills the slot. Failed generations are retried a bounded number of times so a
broken provider cannot burn quota forever.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from uuid import UUID, uuid4

from arq.connections import ArqRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.ai import AiJob
from app.models.identity import User, UserProfile
from app.models.practice import PracticePoolItem, PracticeSession
from app.schemas.practice import BackgroundTaskListResponse, BackgroundTaskResponse
from app.services.ai_jobs import cancel_user_job
from app.services.auth import utcnow
from app.services.practice import (
    create_pool_practice_session,
    reconcile_generation_status,
    regenerate_practice_session,
)

logger = logging.getLogger(__name__)

MAX_TARGET_PER_COMBO = 5
MAX_ATTEMPTS = 3
RETRY_COOLDOWN_SECONDS = 90
STALE_FAILED_SECONDS = 6 * 3600

PRACTICE_TYPES = ("fill_blank", "reading", "translation", "writing")
ALLOWED_COUNTS: dict[str, tuple[int, ...]] = {
    "fill_blank": (3, 5, 10, 15, 20),
    "reading": (3, 5, 10, 15, 20),
    "translation": (3, 5, 10, 15, 20),
    "writing": (1,),
}
# Interleave types at each question count so a slow top-up covers every kind
# quickly instead of filling all fill-in-the-blank slots first.
POOL_COMBOS: tuple[tuple[str, int], ...] = tuple(
    (practice_type, count)
    for count in (1, 3, 5, 10, 15, 20)
    for practice_type in PRACTICE_TYPES
    if count in ALLOWED_COUNTS[practice_type]
)


def allowed_counts(practice_type: str) -> tuple[int, ...]:
    return ALLOWED_COUNTS.get(practice_type, ())


async def _rows(
    session: AsyncSession, user_id: UUID, practice_type: str, count: int
) -> list[tuple[PracticePoolItem, PracticeSession]]:
    return list(
        (
            await session.execute(
                select(PracticePoolItem, PracticeSession)
                .join(PracticeSession, PracticeSession.id == PracticePoolItem.session_id)
                .where(
                    PracticePoolItem.user_id == user_id,
                    PracticePoolItem.practice_type == practice_type,
                    PracticePoolItem.question_count == count,
                )
                .order_by(PracticePoolItem.created_at.asc())
            )
        ).all()
    )


async def _top_up_combo(
    session: AsyncSession,
    pool: ArqRedis,
    user: User,
    settings: Settings,
    *,
    practice_type: str,
    count: int,
    target: int,
    now,
    counters: dict[str, int],
) -> None:
    rows = await _rows(session, user.id, practice_type, count)
    ready = [row for row in rows if row[1].status == "ready"]
    generating = [row for row in rows if row[1].status == "generating"]
    retryable: list[tuple[PracticePoolItem, PracticeSession]] = []
    failed: list[tuple[PracticePoolItem, PracticeSession]] = []
    for item, practice in rows:
        if practice.status != "failed":
            continue
        due = item.next_attempt_at is None or item.next_attempt_at <= now
        if item.attempts < MAX_ATTEMPTS and due:
            retryable.append((item, practice))
        else:
            failed.append((item, practice))

    # A slot that has exhausted its retries stays occupied for a while, then is
    # dropped so a later tick may try again.
    still_failed: list[tuple[PracticePoolItem, PracticeSession]] = []
    for item, practice in failed:
        if practice.updated_at < now - timedelta(seconds=STALE_FAILED_SECONDS):
            await session.delete(item)
            await session.delete(practice)
            await session.commit()
            continue
        still_failed.append((item, practice))

    occupied = len(ready) + len(generating) + len(retryable) + len(still_failed)

    for item, practice in retryable:
        if counters["retried"] >= 2:
            break
        try:
            await regenerate_practice_session(
                session,
                pool,
                user,
                settings,
                practice.id,
                idempotency_key=f"pool-retry:{item.id}:{item.attempts + 1}",
                background=True,
            )
        except AppError as exc:
            logger.warning(
                "practice_pool.retry_rejected",
                extra={"session_id": str(practice.id), "code": exc.code},
            )
            counters["skipped"] += 1
            continue
        except Exception:  # noqa: BLE001 - retry on the next tick
            logger.exception("practice_pool.retry_failed", extra={"session_id": str(practice.id)})
            counters["skipped"] += 1
            continue
        refreshed = await session.get(PracticePoolItem, item.id)
        if refreshed is not None:
            refreshed.attempts += 1
            refreshed.next_attempt_at = utcnow() + timedelta(seconds=RETRY_COOLDOWN_SECONDS)
            await session.commit()
        counters["retried"] += 1

    if counters["created"] >= 2:
        return
    deficit = max(0, target - occupied)
    for _ in range(deficit):
        try:
            practice = await create_pool_practice_session(
                session,
                pool,
                user,
                settings,
                practice_type=practice_type,
                count=count,
            )
        except AppError as exc:
            logger.warning("practice_pool.create_rejected %s: %s", exc.code, exc.message)
            counters["skipped"] += 1
            return
        except Exception:  # noqa: BLE001 - the next tick tries again
            logger.exception(
                "practice_pool.create_failed",
                extra={"practice_type": practice_type, "count": count},
            )
            counters["skipped"] += 1
            return
        session.add(
            PracticePoolItem(
                user_id=user.id,
                practice_type=practice_type,
                question_count=count,
                session_id=practice.id,
                attempts=1,
            )
        )
        await session.commit()
        counters["created"] += 1


async def ensure_pool(
    session: AsyncSession,
    pool: ArqRedis,
    user: User,
    settings: Settings,
) -> dict[str, int]:
    """Keep the configured number of sets ready for every type and count."""
    target = await session.scalar(
        select(UserProfile.practice_pool_target).where(UserProfile.user_id == user.id)
    )
    target = max(0, min(MAX_TARGET_PER_COMBO, int(target or 0)))
    counters = {"created": 0, "retried": 0, "skipped": 0}
    if target == 0:
        return counters

    now = utcnow()
    for practice_type, count in POOL_COMBOS:
        await _top_up_combo(
            session,
            pool,
            user,
            settings,
            practice_type=practice_type,
            count=count,
            target=target,
            now=now,
            counters=counters,
        )
    return counters


async def ensure_pool_for_user_id(
    session: AsyncSession, pool: ArqRedis, settings: Settings, user_id: str | UUID
) -> dict[str, int]:
    try:
        user_uuid = UUID(str(user_id))
    except ValueError:
        return {"created": 0, "retried": 0, "skipped": 0}
    user = await session.get(User, user_uuid)
    if user is None:
        return {"created": 0, "retried": 0, "skipped": 0}
    return await ensure_pool(session, pool, user, settings)


async def pool_users(session: AsyncSession, limit: int = 50) -> list[UUID]:
    rows = (
        await session.scalars(
            select(UserProfile.user_id).where(UserProfile.practice_pool_target > 0).limit(limit)
        )
    ).all()
    return list(rows)


def _task_response(
    item: PracticePoolItem, practice: PracticeSession, job: AiJob | None
) -> BackgroundTaskResponse:
    status = practice.status if practice.status in {"generating", "ready", "failed"} else "failed"
    error_code = job.error_code if practice.status == "failed" and job is not None else None
    error_message = job.error_message if practice.status == "failed" and job is not None else None
    return BackgroundTaskResponse(
        id=item.id,
        practice_type=practice.practice_type,  # type: ignore[arg-type]
        question_count=item.question_count,
        status=status,  # type: ignore[arg-type]
        attempts=item.attempts,
        error_code=error_code,
        error_message=error_message,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


async def _task_row(
    session: AsyncSession, user_id: UUID, task_id: UUID, *, lock: bool = False
) -> tuple[PracticePoolItem, PracticeSession, AiJob | None] | None:
    statement = (
        select(PracticePoolItem, PracticeSession, AiJob)
        .join(PracticeSession, PracticeSession.id == PracticePoolItem.session_id)
        .outerjoin(AiJob, AiJob.id == PracticeSession.ai_job_id)
        .where(PracticePoolItem.id == task_id, PracticePoolItem.user_id == user_id)
    )
    if lock:
        statement = statement.with_for_update(of=PracticePoolItem)
    row = (await session.execute(statement)).first()
    return None if row is None else (row[0], row[1], row[2])


async def list_background_tasks(session: AsyncSession, user: User) -> BackgroundTaskListResponse:
    rows = (
        await session.execute(
            select(PracticePoolItem, PracticeSession, AiJob)
            .join(PracticeSession, PracticeSession.id == PracticePoolItem.session_id)
            .outerjoin(AiJob, AiJob.id == PracticeSession.ai_job_id)
            .where(PracticePoolItem.user_id == user.id)
            .order_by(PracticePoolItem.created_at.desc())
            .limit(100)
        )
    ).all()
    now = utcnow()
    changed = False
    for _item, practice, job in rows:
        changed = reconcile_generation_status(practice, job, now=now) or changed
    if changed:
        await session.commit()
    return BackgroundTaskListResponse(
        items=[_task_response(item, practice, job) for item, practice, job in rows]
    )


async def delete_background_task(
    session: AsyncSession, pool: ArqRedis, user: User, task_id: UUID
) -> None:
    row = await _task_row(session, user.id, task_id, lock=True)
    if row is None:
        raise AppError(
            status_code=404, code="BACKGROUND_TASK_NOT_FOUND", message="The task was not found."
        )
    item, practice, job = row
    if practice.status == "generating" and job is not None and job.status in {"queued", "running"}:
        try:
            await cancel_user_job(session, pool, user, job.id)
        except AppError:
            # A job that finished between the read and the cancel is deleted anyway.
            pass
    await session.delete(item)
    await session.delete(practice)
    await session.commit()


async def retry_background_task(
    session: AsyncSession,
    pool: ArqRedis,
    user: User,
    settings: Settings,
    task_id: UUID,
) -> BackgroundTaskResponse:
    row = await _task_row(session, user.id, task_id, lock=True)
    if row is None:
        raise AppError(
            status_code=404, code="BACKGROUND_TASK_NOT_FOUND", message="The task was not found."
        )
    item, practice, _job = row
    if practice.status != "failed":
        raise AppError(
            status_code=409,
            code="BACKGROUND_TASK_NOT_FAILED",
            message="Only a failed background task can be retried.",
        )
    # A manual retry always gets a fresh chance, regardless of the automatic cap.
    item.attempts = max(1, min(item.attempts, MAX_ATTEMPTS - 1))
    item.next_attempt_at = None
    await session.flush()
    await regenerate_practice_session(
        session,
        pool,
        user,
        settings,
        practice.id,
        idempotency_key=f"pool-manual:{item.id}:{uuid4().hex}",
        background=True,
    )
    refreshed = await session.get(PracticePoolItem, item.id)
    if refreshed is not None:
        refreshed.attempts += 1
        refreshed.next_attempt_at = utcnow() + timedelta(seconds=RETRY_COOLDOWN_SECONDS)
        await session.commit()
    result = await _task_row(session, user.id, task_id)
    if result is None:
        raise AppError(
            status_code=404, code="BACKGROUND_TASK_NOT_FOUND", message="The task was not found."
        )
    return _task_response(*result)
