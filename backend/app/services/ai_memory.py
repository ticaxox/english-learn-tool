"""Durable AI memories for the personal coach.

The coach reads a bounded slice of these notes before every answer. Memories
are written by the product itself (learner profile, finished practice runs,
chat turns, stated preferences) and by the learner directly through the AI
settings page. Only the owning account can read or change them.
"""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.ai_memory import AiMemory
from app.models.identity import User, UserProfile
from app.models.learning import MemoryConfig
from app.schemas.ai_memory import (
    AiMemoryClearResponse,
    AiMemoryCreateRequest,
    AiMemoryListResponse,
    AiMemoryResponse,
    AiMemoryUpdateRequest,
)

CONTENT_LIMIT = 500
# Append-only memories are capped per kind so the list stays readable.
AUTO_CAPS: dict[str, int] = {"practice": 40, "chat": 60, "custom": 60}
PROFILE_KEY = "learner_profile"
PREFERENCE_KEY = "learner_preferences"

EXAM_LABELS = {
    "CET4": "四级",
    "CET6": "六级",
    "POSTGRAD": "考研",
    "IELTS": "雅思",
    "TOEFL": "托福",
}
PRACTICE_LABELS = {
    "fill_blank": "填空练习",
    "reading": "阅读练习",
    "translation": "翻译练习",
    "writing": "作文练习",
}
CHALLENGE_TYPE_LABELS = {
    "fill_blank": "填空",
    "reading": "阅读",
    "translation": "翻译",
    "writing": "作文",
}
DRILL_LABELS = {"flashcard": "翻卡", "choice": "选择", "spelling": "拼写"}

MEMORY_CUE = re.compile(r"记住|请记得|別忘记|别忘记|别忘了|帮我记|记一下|你要记住")

# What the coach receives, per kind. Kept small: memory must not crowd out the
# current message and recent turns.
CONTEXT_CAPS: dict[str, int] = {
    "profile": 2,
    "preference": 4,
    "custom": 12,
    "practice": 6,
    "chat": 8,
}


def _response(memory: AiMemory) -> AiMemoryResponse:
    return AiMemoryResponse(
        id=memory.id,
        kind=memory.kind,  # type: ignore[arg-type]
        content=memory.content,
        source=memory.source,  # type: ignore[arg-type]
        pinned=memory.pinned,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
        last_used_at=memory.last_used_at,
    )


def _clean(value: str, limit: int = CONTENT_LIMIT) -> str:
    return " ".join(value.split())[:limit]


async def upsert_memory(
    session: AsyncSession,
    user_id: UUID,
    *,
    kind: str,
    content: str,
    source: str = "auto",
    key: str | None = None,
) -> AiMemory | None:
    """Write one memory. ``key`` refreshes a single slot instead of appending."""
    cleaned = _clean(content)
    if not cleaned:
        return None
    if key:
        existing = await session.scalar(
            select(AiMemory).where(AiMemory.user_id == user_id, AiMemory.memory_key == key)
        )
        if existing is not None:
            # Only touch the row when something changed, so an unchanged sync
            # does not reorder the list or move the "updated" date every turn.
            if (existing.content, existing.kind, existing.source) != (cleaned, kind, source):
                existing.content = cleaned
                existing.kind = kind
                existing.source = source
                await session.flush()
            return existing
    memory = AiMemory(user_id=user_id, kind=kind, content=cleaned, source=source, memory_key=key)
    session.add(memory)
    await session.flush()
    await _prune(session, user_id, kind, source=source)
    return memory


async def _prune(session: AsyncSession, user_id: UUID, kind: str, *, source: str) -> None:
    cap = AUTO_CAPS.get(kind)
    if cap is None:
        return
    stale_ids = list(
        (
            await session.scalars(
                select(AiMemory.id)
                .where(
                    AiMemory.user_id == user_id,
                    AiMemory.kind == kind,
                    AiMemory.source == source,
                    AiMemory.memory_key.is_(None),
                )
                .order_by(AiMemory.updated_at.desc(), AiMemory.id.desc())
                .offset(cap)
            )
        ).all()
    )
    if stale_ids:
        await session.execute(delete(AiMemory).where(AiMemory.id.in_(stale_ids)))


async def list_memories(
    session: AsyncSession, user: User, *, kind: str | None = None
) -> AiMemoryListResponse:
    statement = select(AiMemory).where(AiMemory.user_id == user.id)
    if kind is not None:
        statement = statement.where(AiMemory.kind == kind)
    rows = list(
        (
            await session.scalars(
                statement.order_by(
                    AiMemory.pinned.desc(), AiMemory.updated_at.desc(), AiMemory.created_at.desc()
                )
            )
        ).all()
    )
    counts = {
        row_kind: count
        for row_kind, count in (
            await session.execute(
                select(AiMemory.kind, func.count(AiMemory.id))
                .where(AiMemory.user_id == user.id)
                .group_by(AiMemory.kind)
            )
        ).all()
    }
    return AiMemoryListResponse(items=[_response(row) for row in rows], counts=counts)


async def create_memory(
    session: AsyncSession, user: User, payload: AiMemoryCreateRequest
) -> AiMemoryResponse:
    memory = AiMemory(
        user_id=user.id,
        kind=payload.kind,
        content=payload.content,
        source="user",
    )
    session.add(memory)
    await session.commit()
    await session.refresh(memory)
    return _response(memory)


async def _owned_memory(session: AsyncSession, user: User, memory_id: UUID) -> AiMemory:
    memory = await session.scalar(
        select(AiMemory).where(AiMemory.id == memory_id, AiMemory.user_id == user.id)
    )
    if memory is None:
        raise AppError(
            status_code=404, code="AI_MEMORY_NOT_FOUND", message="The memory was not found."
        )
    return memory


async def update_memory(
    session: AsyncSession, user: User, memory_id: UUID, payload: AiMemoryUpdateRequest
) -> AiMemoryResponse:
    memory = await _owned_memory(session, user, memory_id)
    if payload.content is not None:
        memory.content = payload.content
    if payload.kind is not None:
        memory.kind = payload.kind
    if payload.pinned is not None:
        memory.pinned = payload.pinned
    await session.commit()
    await session.refresh(memory)
    return _response(memory)


async def delete_memory(session: AsyncSession, user: User, memory_id: UUID) -> None:
    memory = await _owned_memory(session, user, memory_id)
    await session.delete(memory)
    await session.commit()


async def clear_auto_memories(session: AsyncSession, user: User) -> AiMemoryClearResponse:
    result = await session.execute(
        delete(AiMemory).where(AiMemory.user_id == user.id, AiMemory.source == "auto")
    )
    await session.commit()
    return AiMemoryClearResponse(deleted_count=int(result.rowcount or 0))


async def sync_profile_memories(session: AsyncSession, user: User) -> None:
    """Refresh the two single-slot memories from the stored profile."""
    profile = await session.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
    if profile is not None:
        exam = EXAM_LABELS.get(profile.target_exam or "", profile.target_exam or "未设置")
        parts = [f"目标考试：{exam}"]
        if profile.exam_date is not None:
            parts.append(f"考试日期：{profile.exam_date.isoformat()}")
        parts.append(f"每日新词：{profile.daily_new_words} 个")
        parts.append(f"每日学习：{profile.daily_study_minutes} 分钟")
        await upsert_memory(
            session,
            user.id,
            kind="profile",
            content=f"{user.username} · " + "，".join(parts),
            key=PROFILE_KEY,
        )

    config = await session.scalar(select(MemoryConfig).where(MemoryConfig.user_id == user.id))
    if config is None:
        return
    challenge = (config.preferences or {}).get("challenge") or {}
    practice_types = [
        CHALLENGE_TYPE_LABELS.get(item, item) for item in challenge.get("practiceTypes", [])
    ]
    drill_modes = [DRILL_LABELS.get(item, item) for item in challenge.get("drillModes", [])]
    enabled_modes = [
        DRILL_LABELS[item]
        for item in ("flashcard", "choice", "spelling")
        if getattr(config, f"{item}_enabled", False)
    ]
    parts = []
    if practice_types:
        parts.append("偏好题型：" + "、".join(practice_types))
    if drill_modes:
        parts.append("关卡巩固方式：" + "、".join(drill_modes))
    if enabled_modes:
        parts.append("记忆训练方式：" + "、".join(enabled_modes))
    if parts:
        await upsert_memory(
            session,
            user.id,
            kind="preference",
            content="；".join(parts),
            key=PREFERENCE_KEY,
        )


async def record_practice_memory(
    session: AsyncSession,
    user_id: UUID,
    *,
    practice_type: str,
    total_questions: int,
    correct_count: int | None,
    wrong_count: int,
    score: float | None,
) -> None:
    label = PRACTICE_LABELS.get(practice_type, "AI 练习")
    parts = [label, f"{total_questions} 题"]
    if correct_count is not None:
        parts.append(f"正确 {correct_count}" + (f"，错误 {wrong_count}" if wrong_count else ""))
    elif wrong_count:
        parts.append(f"薄弱题 {wrong_count}")
    if score is not None:
        parts.append(f"得分 {round(score)}")
    if correct_count is not None and total_questions and correct_count == total_questions:
        parts.append("全部答对")
    await upsert_memory(session, user_id, kind="practice", content=" · ".join(parts))


async def record_chat_memory(session: AsyncSession, user: User, message: str) -> None:
    cleaned = _clean(message, 300)
    if not cleaned:
        return
    last = await session.scalar(
        select(AiMemory)
        .where(AiMemory.user_id == user.id, AiMemory.kind == "chat", AiMemory.memory_key.is_(None))
        .order_by(AiMemory.updated_at.desc(), AiMemory.id.desc())
        .limit(1)
    )
    if last is None or last.content != f"我：{cleaned}":
        await upsert_memory(session, user.id, kind="chat", content=cleaned)
    if MEMORY_CUE.search(message):
        await upsert_memory(
            session,
            user.id,
            kind="custom",
            content=_clean(message, 400),
            source="user",
        )


async def memory_lines_for_context(session: AsyncSession, user_id: UUID) -> list[tuple[str, str]]:
    """Return the bounded set of ``(kind, content)`` pairs sent to the coach."""
    rows = list(
        (
            await session.scalars(
                select(AiMemory)
                .where(AiMemory.user_id == user_id)
                .order_by(AiMemory.pinned.desc(), AiMemory.updated_at.desc(), AiMemory.id.desc())
                .limit(200)
            )
        ).all()
    )
    selected: list[AiMemory] = []
    used: dict[str, int] = {}
    for row in rows:
        cap = CONTEXT_CAPS.get(row.kind, 4)
        if used.get(row.kind, 0) >= cap:
            continue
        used[row.kind] = used.get(row.kind, 0) + 1
        selected.append(row)
    now = datetime.now(tz=rows[0].updated_at.tzinfo) if rows else None
    if now is not None:
        for row in selected:
            row.last_used_at = now
        await session.flush()
    return [(row.kind, row.content) for row in selected]
