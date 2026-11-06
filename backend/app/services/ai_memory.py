"""The single AI memory document of a learner.

The coach reads this one document before every answer. The product keeps it
current: the profile and stated preferences occupy their own lines, while
practice results, chat notes and explicit "remember this" requests are appended
as new lines. The learner can edit the whole document in AI settings, and an
edited line is never categorised or split into records.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_memory import AiMemory
from app.models.identity import User, UserProfile
from app.models.learning import MemoryConfig
from app.schemas.ai_memory import AiMemoryDocumentResponse, AiMemoryDocumentUpdate

DOCUMENT_KEY = "memory_document"
DOCUMENT_LIMIT = 6000
PROFILE_PREFIX = "用户信息："
PREFERENCE_PREFIX = "习惯偏好："
APPEND_PREFIXES = ("做题：", "对话：", "用户要求：")

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
    "mixed": "混合练习",
}
CHALLENGE_TYPE_LABELS = {
    "fill_blank": "填空",
    "reading": "阅读",
    "translation": "翻译",
    "writing": "作文",
}
DRILL_LABELS = {"flashcard": "翻卡", "choice": "选择", "spelling": "拼写"}

MEMORY_CUE = re.compile(r"记住|请记得|別忘记|别忘记|别忘了|帮我记|记一下|你要记住")


def _normalise(content: str) -> str:
    return content.replace("\r\n", "\n").replace("\r", "\n").strip("\n")


def _response(row: AiMemory | None) -> AiMemoryDocumentResponse:
    if row is None:
        return AiMemoryDocumentResponse(content="", updated_at=None)
    return AiMemoryDocumentResponse(content=row.content, updated_at=row.updated_at)


async def _document_row(session: AsyncSession, user_id: UUID) -> AiMemory | None:
    return await session.scalar(
        select(AiMemory).where(AiMemory.user_id == user_id, AiMemory.memory_key == DOCUMENT_KEY)
    )


async def _ensure_document(session: AsyncSession, user_id: UUID) -> AiMemory:
    row = await _document_row(session, user_id)
    if row is None:
        row = AiMemory(
            user_id=user_id,
            kind="custom",
            content="",
            source="user",
            memory_key=DOCUMENT_KEY,
        )
        session.add(row)
        await session.flush()
    return row


def _trim(lines: list[str]) -> str:
    """Keep the document bounded by dropping the oldest appended note first."""
    while len("\n".join(lines)) > DOCUMENT_LIMIT:
        for index, line in enumerate(lines):
            if line.startswith(APPEND_PREFIXES):
                del lines[index]
                break
        else:
            if len(lines) <= 1:
                break
            del lines[0]
    text = "\n".join(lines)
    return text[-DOCUMENT_LIMIT:] if len(text) > DOCUMENT_LIMIT else text


def _set_line(lines: list[str], prefix: str, line: str) -> None:
    for index, existing in enumerate(lines):
        if existing.startswith(prefix):
            lines[index] = line
            return
    index = 0
    if prefix == PREFERENCE_PREFIX and lines and lines[0].startswith(PROFILE_PREFIX):
        index = 1
    lines.insert(index, line)


def _append_line(lines: list[str], line: str) -> None:
    if lines and lines[-1] == line:
        return
    lines.append(line)


async def _mutate(
    session: AsyncSession, user_id: UUID, change: Callable[[list[str]], None]
) -> None:
    row = await _ensure_document(session, user_id)
    lines = _normalise(row.content).split("\n") if row.content else []
    change(lines)
    row.content = _trim(lines)
    await session.flush()


async def get_document(session: AsyncSession, user: User) -> AiMemoryDocumentResponse:
    return _response(await _document_row(session, user.id))


async def save_document(
    session: AsyncSession, user: User, payload: AiMemoryDocumentUpdate
) -> AiMemoryDocumentResponse:
    row = await _ensure_document(session, user.id)
    row.content = _normalise(payload.content)[:DOCUMENT_LIMIT]
    row.source = "user"
    await session.commit()
    await session.refresh(row)
    return _response(row)


async def memory_document_for_context(session: AsyncSession, user_id: UUID) -> str | None:
    row = await _document_row(session, user_id)
    if row is None or not row.content.strip():
        return None
    row.last_used_at = datetime.now(tz=row.updated_at.tzinfo)
    await session.flush()
    return row.content[:DOCUMENT_LIMIT]


async def sync_profile_memories(session: AsyncSession, user: User) -> None:
    """Refresh the profile and preference lines from the stored settings."""
    profile = await session.scalar(select(UserProfile).where(UserProfile.user_id == user.id))
    profile_line: str | None = None
    if profile is not None:
        exam = EXAM_LABELS.get(profile.target_exam or "", profile.target_exam or "未设置")
        parts = [f"目标考试：{exam}"]
        if profile.exam_date is not None:
            parts.append(f"考试日期：{profile.exam_date.isoformat()}")
        parts.append(f"每日新词：{profile.daily_new_words} 个")
        parts.append(f"每日学习：{profile.daily_study_minutes} 分钟")
        profile_line = PROFILE_PREFIX + f"{user.username} · " + "，".join(parts)

    config = await session.scalar(select(MemoryConfig).where(MemoryConfig.user_id == user.id))
    preference_line: str | None = None
    if config is not None:
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
            preference_line = PREFERENCE_PREFIX + "；".join(parts)

    if profile_line is None and preference_line is None:
        return

    def change(lines: list[str]) -> None:
        if profile_line is not None:
            _set_line(lines, PROFILE_PREFIX, profile_line)
        if preference_line is not None:
            _set_line(lines, PREFERENCE_PREFIX, preference_line)

    await _mutate(session, user.id, change)


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
    line = "做题：" + " · ".join(parts)
    await _mutate(session, user_id, lambda lines: _append_line(lines, line))


async def record_chat_memory(session: AsyncSession, user: User, message: str) -> None:
    cleaned = " ".join(message.split())[:300]
    if not cleaned:
        return

    def change(lines: list[str]) -> None:
        _append_line(lines, f"对话：{cleaned}")
        if MEMORY_CUE.search(message):
            _append_line(lines, f"用户要求：{' '.join(message.split())[:400]}")

    await _mutate(session, user.id, change)
