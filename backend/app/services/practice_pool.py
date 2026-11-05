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
from uuid import UUID

from arq.connections import ArqRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.identity import User, UserProfile
from app.models.practice import PracticePoolItem, PracticeSession
from app.services.auth import utcnow
from app.services.practice import create_pool_practice_session, regenerate_practice_session

logger = logging.getLogger(__name__)

MAX_TARGET_PER_COMBO = 2
MAX_TOTAL_TARGETS = 12
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


def allowed_counts(practice_type: str) -> tuple[int, ...]:
    return ALLOWED_COUNTS.get(practice_type, ())


def normalize_targets(raw: object) -> dict[tuple[str, int], int]:
    """Read the stored JSON into ``{(type, count): target}`` with sane bounds."""
    if not isinstance(raw, dict):
        return {}
    targets: dict[tuple[str, int], int] = {}
    total = 0
    for practice_type, counts in raw.items():
        if practice_type not in ALLOWED_COUNTS or not isinstance(counts, dict):
            continue
        for raw_count, raw_target in counts.items():
            try:
                count = int(raw_count)
                target = int(raw_target)
            except (TypeError, ValueError):
                continue
            if count not in ALLOWED_COUNTS[practice_type]:
                continue
            target = max(0, min(MAX_TARGET_PER_COMBO, target))
            if target == 0:
                continue
            if total + target > MAX_TOTAL_TARGETS:
                continue
            targets[(practice_type, count)] = target
            total += target
    return targets


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


async def ensure_pool(
    session: AsyncSession,
    pool: ArqRedis,
    user: User,
    settings: Settings,
) -> dict[str, int]:
    """Top up every configured type/count slot for one learner."""
    stored = await session.scalar(
        select(UserProfile.practice_pool_targets).where(UserProfile.user_id == user.id)
    )
    targets = normalize_targets(stored or {})
    counters = {"created": 0, "retried": 0, "skipped": 0}
    if not targets:
        return counters

    now = utcnow()
    for (practice_type, count), target in targets.items():
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

        # A slot that has exhausted its retries stays occupied for a while, then
        # is dropped so a later tick may try again.
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
            try:
                await regenerate_practice_session(
                    session,
                    pool,
                    user,
                    settings,
                    practice.id,
                    idempotency_key=f"pool-retry:{item.id}:{item.attempts + 1}",
                )
            except AppError as exc:
                logger.warning(
                    "practice_pool.retry_rejected",
                    extra={"session_id": str(practice.id), "code": exc.code},
                )
                counters["skipped"] += 1
                continue
            except Exception:  # noqa: BLE001 - retry on the next tick
                logger.exception(
                    "practice_pool.retry_failed", extra={"session_id": str(practice.id)}
                )
                counters["skipped"] += 1
                continue
            refreshed = await session.get(PracticePoolItem, item.id)
            if refreshed is not None:
                refreshed.attempts += 1
                refreshed.next_attempt_at = utcnow() + timedelta(seconds=RETRY_COOLDOWN_SECONDS)
                await session.commit()
            counters["retried"] += 1

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
                break
            except Exception:  # noqa: BLE001 - the next tick tries again
                logger.exception(
                    "practice_pool.create_failed",
                    extra={"practice_type": practice_type, "count": count},
                )
                counters["skipped"] += 1
                break
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
        await session.execute(
            select(UserProfile.user_id, UserProfile.practice_pool_targets).limit(200)
        )
    ).all()
    selected = [user_id for user_id, targets in rows if normalize_targets(targets or {})]
    return selected[:limit]
