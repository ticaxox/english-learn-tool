"""Memory training: sessions, idempotent events, queue rules, and FSRS state."""

from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.identity import User
from app.models.learning import (
    DailyPlan,
    DailyPlanWord,
    MemoryConfig,
    MemoryEvent,
    MemorySession,
    MemorySessionItem,
    MistakeFlag,
    UserWordState,
)
from app.models.wordbooks import (
    Wordbook,
    WordbookActivation,
    WordbookDefinition,
    WordbookEntry,
)
from app.schemas.learning import (
    MemoryConfigResponse,
    MemoryModuleConfig,
    MemoryProgressResetResponse,
    MistakeListResponse,
    MistakePriorityRequest,
    MistakeResponse,
    SessionCardPrompt,
    SessionCreateRequest,
    SessionEventRequest,
    SessionEventResponse,
    SessionItemResponse,
    SessionResponse,
    WordStateResponse,
)
from app.services import fsrs_scheduler
from app.services.ai_memory import sync_profile_memories
from app.services.auth import utcnow
from app.services.gamification import award
from app.services.learning import LEARNING_CALCULATION_VERSION, local_date_for

REQUIRED_NEW_GOOD_COUNT = 2
MIN_REINSERT_GAP = 4
MAX_OPTIONS = 4
_DUE_STATUSES = ("learning", "review", "relearning")
_ENABLED_ATTR = {
    "flashcard": "flashcard_enabled",
    "choice": "choice_enabled",
    "spelling": "spelling_enabled",
}
EMPTY_UUID = UUID(int=0)


def _fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _normalize_answer(value: str | None) -> str:
    return (value or "").strip().casefold()


async def _config_row(session: AsyncSession, user: User, *, lock: bool = False) -> MemoryConfig:
    statement = select(MemoryConfig).where(MemoryConfig.user_id == user.id)
    if lock:
        statement = statement.with_for_update()
    config = await session.scalar(statement)
    if config is None:
        config = MemoryConfig(user_id=user.id, preferences={})
        session.add(config)
        await session.flush()
        await session.refresh(config)
    return config


def _config_response(config: MemoryConfig) -> MemoryConfigResponse:
    return MemoryConfigResponse(
        flashcard_enabled=config.flashcard_enabled,
        choice_enabled=config.choice_enabled,
        spelling_enabled=config.spelling_enabled,
        preferences=config.preferences or {},
        updated_at=config.updated_at,
    )


async def get_config(session: AsyncSession, user: User) -> MemoryConfigResponse:
    config = await session.scalar(select(MemoryConfig).where(MemoryConfig.user_id == user.id))
    if config is None:
        return MemoryConfigResponse(updated_at=user.updated_at)
    return _config_response(config)


async def set_config(
    session: AsyncSession, user: User, payload: MemoryModuleConfig
) -> MemoryConfigResponse:
    config = await _config_row(session, user, lock=True)
    if not any((payload.flashcard_enabled, payload.choice_enabled, payload.spelling_enabled)):
        raise AppError(
            status_code=422,
            code="MEMORY_MODULE_REQUIRED",
            message="At least one training module must stay enabled.",
        )
    config.flashcard_enabled = payload.flashcard_enabled
    config.choice_enabled = payload.choice_enabled
    config.spelling_enabled = payload.spelling_enabled
    config.preferences = payload.preferences
    await sync_profile_memories(session, user)
    await session.commit()
    await session.refresh(config)
    return _config_response(config)


async def reset_today_progress(
    session: AsyncSession, user: User, settings: Settings
) -> MemoryProgressResetResponse:
    """Put today's reviewed words back in the queue for another run.

    Used by the "reset today's progress" action: today's memory sessions and
    their events are removed, and the words they covered become due now. The
    wordbook, the words themselves and older history stay untouched.
    """
    today = local_date_for(settings, user)
    # Today's sessions, plus any active session left open on an earlier day:
    # that stale session would otherwise be resumed instead of a fresh one.
    sessions = list(
        (
            await session.scalars(
                select(MemorySession).where(
                    MemorySession.user_id == user.id,
                    or_(
                        MemorySession.local_date == today,
                        MemorySession.status == "active",
                    ),
                )
            )
        ).all()
    )
    if not sessions:
        return MemoryProgressResetResponse(sessions_reset=0, words_reset=0)
    session_ids = [item.id for item in sessions]
    state_ids = list(
        (
            await session.scalars(
                select(MemorySessionItem.word_state_id)
                .where(MemorySessionItem.session_id.in_(session_ids))
                .distinct()
            )
        ).all()
    )
    await session.execute(delete(MemoryEvent).where(MemoryEvent.session_id.in_(session_ids)))
    await session.execute(
        delete(MemorySessionItem).where(MemorySessionItem.session_id.in_(session_ids))
    )
    await session.execute(delete(MemorySession).where(MemorySession.id.in_(session_ids)))
    if state_ids:
        await session.execute(
            update(UserWordState).where(UserWordState.id.in_(state_ids)).values(due_at=utcnow())
        )
    await session.commit()
    return MemoryProgressResetResponse(sessions_reset=len(session_ids), words_reset=len(state_ids))


async def _active_wordbook(session: AsyncSession, user: User) -> Wordbook:
    book = await session.scalar(
        select(Wordbook)
        .join(WordbookActivation, WordbookActivation.wordbook_id == Wordbook.id)
        .where(
            WordbookActivation.user_id == user.id,
            Wordbook.owner_id == user.id,
            Wordbook.status == "ready",
        )
    )
    if book is None:
        raise AppError(
            status_code=409,
            code="ACTIVE_WORDBOOK_REQUIRED",
            message="An active wordbook is required before studying.",
        )
    return book


async def _entry_definition(
    session: AsyncSession, entry_id: UUID
) -> tuple[WordbookEntry | None, WordbookDefinition | None]:
    entry = await session.scalar(select(WordbookEntry).where(WordbookEntry.id == entry_id))
    definition = await session.scalar(
        select(WordbookDefinition).where(
            WordbookDefinition.entry_id == entry_id,
            WordbookDefinition.sequence == 0,
        )
    )
    return entry, definition


async def _ensure_state(
    session: AsyncSession,
    user: User,
    book: Wordbook,
    entry_id: UUID,
    *,
    lock: bool = False,
) -> UserWordState:
    statement = select(UserWordState).where(
        UserWordState.user_id == user.id,
        UserWordState.wordbook_id == book.id,
        UserWordState.entry_id == entry_id,
    )
    if lock:
        statement = statement.with_for_update()
    state = await session.scalar(statement)
    if state is not None:
        return state
    state = UserWordState(
        user_id=user.id,
        wordbook_id=book.id,
        entry_id=entry_id,
        status="new",
        fsrs_card=fsrs_scheduler.new_card_payload(),
        algorithm_version=fsrs_scheduler.FSRS_ALGORITHM_VERSION,
    )
    session.add(state)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        state = await session.scalar(statement)
        if state is None:
            raise
    return state


async def _session_items(
    session: AsyncSession, session_id: UUID
) -> list[tuple[MemorySessionItem, WordbookEntry, WordbookDefinition | None]]:
    rows = (
        await session.execute(
            select(MemorySessionItem, WordbookEntry, WordbookDefinition)
            .join(WordbookEntry, WordbookEntry.id == MemorySessionItem.entry_id)
            .outerjoin(
                WordbookDefinition,
                and_(
                    WordbookDefinition.entry_id == WordbookEntry.id,
                    WordbookDefinition.sequence == 0,
                ),
            )
            .where(MemorySessionItem.session_id == session_id)
            .order_by(MemorySessionItem.position, MemorySessionItem.first_position)
        )
    ).all()
    return [(row[0], row[1], row[2]) for row in rows]


async def _load_session(
    session: AsyncSession, user: User, session_id: UUID, *, lock: bool = False
) -> MemorySession:
    statement = select(MemorySession).where(
        MemorySession.id == session_id, MemorySession.user_id == user.id
    )
    if lock:
        statement = statement.with_for_update()
    value = await session.scalar(statement)
    if value is None:
        raise AppError(
            status_code=404,
            code="MEMORY_SESSION_NOT_FOUND",
            message="The memory session was not found.",
        )
    return value


def _item_response(item: MemorySessionItem) -> SessionItemResponse:
    return SessionItemResponse(
        item_id=item.id,
        entry_id=item.entry_id,
        word_state_id=item.word_state_id,
        reason=item.reason,
        is_extra=item.is_extra,
        position=item.position,
        completed=item.completed,
        good_count=item.good_count,
        again_count=item.again_count,
        relearn_count=item.relearn_count,
        last_rating=item.last_rating,
    )


CLOZE_MODES = ("full", "partial", "first_letter", "middle")


def _cloze(headword: str, mode: str) -> str:
    if not headword:
        return ""
    if mode == "first_letter":
        return headword[0] + "_" * (len(headword) - 1)
    if mode == "partial":
        visible = max(1, len(headword) // 3)
        return headword[:visible] + "_" * (len(headword) - visible)
    if mode == "middle":
        # First and last letters stay visible; a random share of the middle is
        # blanked so the same word does not always lose exactly every middle letter.
        if len(headword) <= 2:
            return headword
        positions = list(range(1, len(headword) - 1))
        blank_count = random.randint(max(1, len(positions) // 2), len(positions))
        blanks = set(random.sample(positions, blank_count))
        return "".join(
            "_" if index in blanks else character for index, character in enumerate(headword)
        )
    return "_" * len(headword)


def _stable_options(correct: str, pool: list[str], entry_id: UUID) -> list[str]:
    unique: list[str] = []
    seen = {correct.casefold()}
    for value in pool:
        if value is None:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(value)
        if len(unique) >= MAX_OPTIONS - 1:
            break
    options = [correct, *unique]
    random.Random(f"choice:{entry_id}").shuffle(options)
    return options


PROMPT_SIDES = ("headword", "definition", "phonetic")


def _pick_prompt_type(value: object) -> str:
    """Choose one of the enabled prompt sides; unknown values fall back to a word prompt."""
    if isinstance(value, str):
        candidates = [item for item in value.split(",") if item in PROMPT_SIDES]
    elif isinstance(value, list):
        candidates = [str(item) for item in value if str(item) in PROMPT_SIDES]
    else:
        candidates = []
    if not candidates:
        candidates = ["definition"]
    return random.choice(candidates)


async def _card_prompt(
    session: AsyncSession,
    item: MemorySessionItem,
    entry: WordbookEntry,
    definition: WordbookDefinition | None,
    *,
    module: str,
    book: Wordbook,
    preferences: dict[str, Any],
) -> SessionCardPrompt:
    definition_zh = definition.definition_zh if definition else None
    part_of_speech = definition.part_of_speech if definition else None
    if module == "flashcard":
        # The learner picks which sides may be shown; unset means every side.
        front = _pick_prompt_type(preferences.get("flashcard_prompt_types"))
        if front == "definition" and definition_zh:
            prompt, label = definition_zh, "definition"
        elif front == "phonetic" and entry.phonetic:
            prompt, label = entry.phonetic, "phonetic"
        else:
            prompt, label = entry.headword, "headword"
        return SessionCardPrompt(
            module="flashcard",
            prompt=prompt,
            prompt_label=label,
            phonetic=entry.phonetic,
            part_of_speech=part_of_speech,
        )
    if module == "spelling":
        # Unset or "random" means the cloze type varies from card to card.
        mode = preferences.get("spelling_mode", "random")
        if mode not in {*CLOZE_MODES, "random"}:
            mode = "random"
        if mode == "random":
            mode = random.choice(list(CLOZE_MODES))
        return SessionCardPrompt(
            module="spelling",
            prompt=definition_zh or entry.headword,
            prompt_label="definition" if definition_zh else "headword",
            cloze=_cloze(entry.headword, mode),
            phonetic=entry.phonetic,
            part_of_speech=part_of_speech,
        )
    prompt_type = _pick_prompt_type(
        preferences.get("choice_prompt_types") or preferences.get("choice_prompt")
    )
    if prompt_type not in {"headword", "definition", "phonetic"}:
        prompt_type = "definition"
    if prompt_type == "phonetic" and entry.phonetic:
        pool = list(
            (
                await session.scalars(
                    select(WordbookEntry.headword)
                    .where(
                        WordbookEntry.wordbook_id == book.id,
                        WordbookEntry.id != entry.id,
                    )
                    .order_by(WordbookEntry.sequence)
                    .limit(MAX_OPTIONS * 3)
                )
            ).all()
        )
        correct = entry.headword
        prompt = entry.phonetic
        prompt_label = "phonetic"
    elif prompt_type == "headword" or definition_zh is None:
        pool = list(
            (
                await session.scalars(
                    select(WordbookDefinition.definition_zh)
                    .join(WordbookEntry, WordbookDefinition.entry_id == WordbookEntry.id)
                    .where(
                        WordbookEntry.wordbook_id == book.id,
                        WordbookEntry.id != entry.id,
                        WordbookDefinition.sequence == 0,
                        WordbookDefinition.definition_zh.is_not(None),
                    )
                    .order_by(WordbookEntry.sequence)
                    .limit(MAX_OPTIONS * 3)
                )
            ).all()
        )
        correct = definition_zh or entry.headword
        prompt = entry.headword
        prompt_label = "headword"
    else:
        pool = list(
            (
                await session.scalars(
                    select(WordbookEntry.headword)
                    .where(
                        WordbookEntry.wordbook_id == book.id,
                        WordbookEntry.id != entry.id,
                    )
                    .order_by(WordbookEntry.sequence)
                    .limit(MAX_OPTIONS * 3)
                )
            ).all()
        )
        correct = entry.headword
        prompt = definition_zh
        prompt_label = "definition"
    # The correct option is derived on the server at grading time and is never returned
    # before the learner submits an answer.
    options = _stable_options(correct, pool, entry.id)
    return SessionCardPrompt(
        module="choice",
        prompt=prompt,
        prompt_label=prompt_label,
        phonetic=entry.phonetic,
        part_of_speech=part_of_speech,
        options=options,
        option_count=len(options),
    )


def _next_item(items: list[MemorySessionItem]) -> MemorySessionItem | None:
    pending = [item for item in items if not item.completed]
    if not pending:
        return None
    return min(pending, key=lambda item: (item.position, item.first_position))


async def _mark_plan_word_completed(
    session: AsyncSession,
    user: User,
    book: Wordbook,
    entry_id: UUID,
    *,
    now: datetime,
) -> None:
    """Reflect a finished card on today's plan snapshot without changing the plan set."""

    plan_id = await session.scalar(
        select(DailyPlan.id)
        .where(DailyPlan.user_id == user.id, DailyPlan.wordbook_id == book.id)
        .order_by(DailyPlan.local_date.desc())
        .limit(1)
    )
    if plan_id is None:
        return
    plan_word = await session.scalar(
        select(DailyPlanWord)
        .where(
            DailyPlanWord.plan_id == plan_id,
            DailyPlanWord.entry_id == entry_id,
            DailyPlanWord.completed_at.is_(None),
        )
        .with_for_update()
    )
    if plan_word is not None:
        plan_word.completed_at = now


async def _session_response(
    session: AsyncSession,
    memory_session: MemorySession,
    book: Wordbook,
    *,
    preferences: dict[str, Any],
) -> SessionResponse:
    rows = await _session_items(session, memory_session.id)
    items = [row[0] for row in rows]
    next_item = _next_item(items) if memory_session.status == "active" else None
    card: SessionCardPrompt | None = None
    if next_item is not None:
        row = next(row for row in rows if row[0].id == next_item.id)
        card = await _card_prompt(
            session,
            next_item,
            row[1],
            row[2],
            module=memory_session.module,
            book=book,
            preferences=preferences,
        )
    completed = sum(1 for item in items if item.completed)
    return SessionResponse(
        session_id=memory_session.id,
        module=memory_session.module,
        status=memory_session.status,
        wordbook_id=memory_session.wordbook_id,
        wordbook_name=book.name,
        local_date=memory_session.local_date,
        config_snapshot=memory_session.config_snapshot,
        stats=memory_session.stats,
        calculation_version=memory_session.calculation_version,
        items_total=len(items),
        items_completed=completed,
        next_item=_item_response(next_item) if next_item else None,
        card=card,
        started_at=memory_session.started_at,
        ended_at=memory_session.ended_at,
    )


async def _plan_entries(
    session: AsyncSession, user: User, local_date
) -> tuple[list[UUID], list[UUID]]:
    plan = await session.scalar(
        select(DailyPlan).where(DailyPlan.user_id == user.id, DailyPlan.local_date == local_date)
    )
    if plan is None:
        return [], []
    rows = (
        await session.execute(
            select(DailyPlanWord.reason, DailyPlanWord.entry_id)
            .join(WordbookEntry, WordbookEntry.id == DailyPlanWord.entry_id)
            .where(DailyPlanWord.plan_id == plan.id)
            .where(WordbookEntry.wordbook_id == plan.wordbook_id)
            .order_by(DailyPlanWord.position)
        )
    ).all()
    due = [row[1] for row in rows if row[0] == "due"]
    new = [row[1] for row in rows if row[0] == "new"]
    return due, new


async def start_session(
    session: AsyncSession,
    user: User,
    *,
    settings: Settings,
    payload: SessionCreateRequest,
) -> SessionResponse:
    local_date = local_date_for(settings, user)
    daily_plan = await session.scalar(
        select(DailyPlan).where(
            DailyPlan.user_id == user.id,
            DailyPlan.local_date == local_date,
        )
    )
    if daily_plan is not None:
        # The daily plan is the source of truth for today's study snapshot. An
        # activation switch must not attach the old plan entries to a new book.
        book = await session.scalar(
            select(Wordbook).where(
                Wordbook.id == daily_plan.wordbook_id,
                Wordbook.status == "ready",
            )
        )
        if book is None:
            raise AppError(
                status_code=409,
                code="MEMORY_PLAN_WORDBOOK_UNAVAILABLE",
                message="The wordbook for today's plan is unavailable.",
            )
        if payload.wordbook_id is not None and payload.wordbook_id != book.id:
            raise AppError(
                status_code=409,
                code="MEMORY_WORDBOOK_PLAN_MISMATCH",
                message="The requested wordbook does not match today's plan.",
            )
    else:
        book = await _active_wordbook(session, user)
        if payload.wordbook_id is not None and payload.wordbook_id != book.id:
            raise AppError(
                status_code=409,
                code="WORDBOOK_NOT_ACTIVE",
                message="Only the active wordbook can be studied.",
            )
    config = await _config_row(session, user)
    if not getattr(config, _ENABLED_ATTR[payload.module]):
        raise AppError(
            status_code=409,
            code="MEMORY_MODULE_DISABLED",
            message="This training module is disabled in the memory configuration.",
        )
    preferences = dict(config.preferences or {})
    # A session belongs to one local day. An active session from an earlier day
    # would otherwise be resumed forever (and show "本轮完成" once its items are
    # done), so close those before looking for today's session.
    stale_sessions = list(
        (
            await session.scalars(
                select(MemorySession).where(
                    MemorySession.user_id == user.id,
                    MemorySession.wordbook_id == book.id,
                    MemorySession.module == payload.module,
                    MemorySession.status == "active",
                    MemorySession.local_date != local_date,
                )
            )
        ).all()
    )
    if stale_sessions:
        now = utcnow()
        for stale in stale_sessions:
            stale.status = "abandoned"
            stale.completed_at = now
        await session.flush()
    existing = await session.scalar(
        select(MemorySession).where(
            MemorySession.user_id == user.id,
            MemorySession.wordbook_id == book.id,
            MemorySession.module == payload.module,
            MemorySession.status == "active",
        )
    )
    if existing is not None:
        return await _session_response(session, existing, book, preferences=preferences)

    memory_session = MemorySession(
        user_id=user.id,
        wordbook_id=book.id,
        module=payload.module,
        status="active",
        local_date=local_date,
        config_snapshot={
            "module": payload.module,
            "flashcard_enabled": config.flashcard_enabled,
            "choice_enabled": config.choice_enabled,
            "spelling_enabled": config.spelling_enabled,
            "preferences": preferences,
        },
        stats={},
        calculation_version=LEARNING_CALCULATION_VERSION,
    )
    session.add(memory_session)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        existing = await session.scalar(
            select(MemorySession).where(
                MemorySession.user_id == user.id,
                MemorySession.wordbook_id == book.id,
                MemorySession.module == payload.module,
                MemorySession.status == "active",
            )
        )
        if existing is None:
            raise
        return await _session_response(session, existing, book, preferences=preferences)

    due_entries, new_entries = await _plan_entries(session, user, local_date)
    now = utcnow()
    queue: list[tuple[UUID, UserWordState, str]] = []
    if due_entries:
        due_states = list(
            (
                await session.scalars(
                    select(UserWordState)
                    .where(
                        UserWordState.user_id == user.id,
                        UserWordState.wordbook_id == book.id,
                        UserWordState.entry_id.in_(due_entries),
                        UserWordState.status.in_(_DUE_STATUSES),
                        UserWordState.due_at.is_not(None),
                        UserWordState.due_at <= now,
                    )
                    .order_by(UserWordState.due_at)
                    .with_for_update()
                )
            ).all()
        )
        queue.extend((state.entry_id, state, "due") for state in due_states)
    for entry_id in new_entries:
        state = await _ensure_state(session, user, book, entry_id)
        if state.status in {"mastered", "suspended"}:
            continue
        queue.append((entry_id, state, "new"))
    if not queue:
        # No snapshot words remain: fall back to due reviews, then unseen entries, so an
        # accidental retry never creates an empty session.
        due_states = list(
            (
                await session.scalars(
                    select(UserWordState)
                    .where(
                        UserWordState.user_id == user.id,
                        UserWordState.wordbook_id == book.id,
                        UserWordState.status.in_(_DUE_STATUSES),
                        UserWordState.due_at.is_not(None),
                        UserWordState.due_at <= now,
                    )
                    .order_by(UserWordState.due_at)
                    .limit(payload.limit)
                    .with_for_update()
                )
            ).all()
        )
        queue.extend((state.entry_id, state, "due") for state in due_states)
    if not queue:
        fallback = list(
            (
                await session.scalars(
                    select(WordbookEntry.id)
                    .where(WordbookEntry.wordbook_id == book.id)
                    .order_by(WordbookEntry.sequence, WordbookEntry.id)
                    .limit(payload.limit)
                )
            ).all()
        )
        for entry_id in fallback:
            state = await _ensure_state(session, user, book, entry_id)
            if state.status in {"mastered", "suspended"}:
                continue
            queue.append((entry_id, state, "new"))
    if not queue:
        raise AppError(
            status_code=409,
            code="MEMORY_NO_WORDS_AVAILABLE",
            message="No words are available for this training module.",
        )
    for position, (entry_id, state, reason) in enumerate(queue):
        session.add(
            MemorySessionItem(
                session_id=memory_session.id,
                entry_id=entry_id,
                word_state_id=state.id,
                reason=reason,
                position=position,
                first_position=position,
            )
        )
    memory_session.stats = {"items": len(queue), "completed": 0}
    await session.commit()
    await session.refresh(memory_session)
    return await _session_response(session, memory_session, book, preferences=preferences)


async def get_session(session: AsyncSession, user: User, session_id: UUID) -> SessionResponse:
    memory_session = await _load_session(session, user, session_id)
    book = await session.scalar(select(Wordbook).where(Wordbook.id == memory_session.wordbook_id))
    if book is None:
        raise AppError(
            status_code=404,
            code="MEMORY_SESSION_NOT_FOUND",
            message="The memory session was not found.",
        )
    preferences = (memory_session.config_snapshot or {}).get("preferences", {})
    return await _session_response(session, memory_session, book, preferences=preferences)


async def _judge(
    session: AsyncSession,
    *,
    module: str,
    entry: WordbookEntry,
    answer: str | None,
    preferences: dict[str, Any],
) -> tuple[bool | None, str | None]:
    """Return (is_correct, answer text safe to reveal after grading)."""

    if module == "flashcard":
        return None, None
    if answer is None:
        raise AppError(
            status_code=422,
            code="MEMORY_ANSWER_REQUIRED",
            message="An answer is required for this training module.",
        )
    if module == "spelling":
        return _normalize_answer(answer) == _normalize_answer(entry.headword), entry.headword
    _entry, definition = await _entry_definition(session, entry.id)
    definition_zh = definition.definition_zh if definition else None
    prompt_type = preferences.get("choice_prompt", "definition")
    if prompt_type not in {"headword", "definition"}:
        prompt_type = "definition"
    asks_for_english = prompt_type == "headword" or definition_zh is None
    correct = definition_zh if asks_for_english else entry.headword
    if not correct:
        return None, None
    is_correct = _normalize_answer(answer) == _normalize_answer(correct)
    # After grading the correct word is safe to reveal; the wrong-answer card
    # needs it, otherwise it can only show the meaning the learner just saw.
    return is_correct, None if is_correct else correct


async def _requeue(session: AsyncSession, item: MemorySessionItem, session_id: UUID) -> None:
    items = await _session_items(session, session_id)
    max_position = max((row[0].position for row in items), default=item.position)
    target = item.position + MIN_REINSERT_GAP
    # With four or fewer cards left there is no room for a real gap, so the card goes to the
    # end of the queue instead of being marked complete.
    item.position = target if target > max_position else max_position + 1
    item.next_position = item.position
    item.relearn_count += 1


async def _maybe_complete(
    session: AsyncSession, memory_session: MemorySession, *, now: datetime
) -> None:
    pending = int(
        await session.scalar(
            select(func.count(MemorySessionItem.id)).where(
                MemorySessionItem.session_id == memory_session.id,
                MemorySessionItem.completed.is_(False),
            )
        )
        or 0
    )
    completed = int(
        await session.scalar(
            select(func.count(MemorySessionItem.id)).where(
                MemorySessionItem.session_id == memory_session.id,
                MemorySessionItem.completed.is_(True),
            )
        )
        or 0
    )
    memory_session.stats = {
        **(memory_session.stats or {}),
        "items": pending + completed,
        "completed": completed,
    }
    if pending == 0:
        memory_session.status = "completed"
        memory_session.ended_at = now


async def submit_event(
    session: AsyncSession,
    user: User,
    session_id: UUID,
    *,
    payload: SessionEventRequest,
    idempotency_key: str,
    settings: Settings,
) -> SessionEventResponse:
    if len(idempotency_key) > 128:
        raise AppError(
            status_code=422,
            code="IDEMPOTENCY_KEY_INVALID",
            message="The Idempotency-Key must be at most 128 characters.",
        )
    memory_session = await _load_session(session, user, session_id, lock=True)
    book = await session.scalar(select(Wordbook).where(Wordbook.id == memory_session.wordbook_id))
    if book is None:
        raise AppError(
            status_code=404,
            code="MEMORY_SESSION_NOT_FOUND",
            message="The memory session was not found.",
        )
    preferences = (memory_session.config_snapshot or {}).get("preferences", {})
    fingerprint = _fingerprint(
        {
            "item_id": str(payload.item_id),
            "action": payload.action,
            "answer": payload.answer,
            "duration_ms": payload.duration_ms,
        }
    )
    existing = await session.scalar(
        select(MemoryEvent).where(
            MemoryEvent.session_id == session_id,
            MemoryEvent.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise AppError(
                status_code=409,
                code="IDEMPOTENCY_CONFLICT",
                message="The idempotency key was already used with a different request.",
            )
        item = await session.scalar(
            select(MemorySessionItem).where(MemorySessionItem.id == existing.item_id)
        )
        response = await _session_response(session, memory_session, book, preferences=preferences)
        return SessionEventResponse(
            event_id=existing.id,
            item_id=existing.item_id,
            action=existing.event_type
            if existing.event_type in {"shown", "mastered"}
            else (existing.rating or payload.action),
            rating=existing.rating,
            is_correct=existing.is_correct,
            correct_answer=None,
            item_completed=bool(item.completed) if item else False,
            session_completed=memory_session.status == "completed",
            session=response,
        )
    if memory_session.status != "active":
        raise AppError(
            status_code=409,
            code="MEMORY_SESSION_NOT_ACTIVE",
            message="The memory session is no longer active.",
        )
    item = await session.scalar(
        select(MemorySessionItem)
        .where(
            MemorySessionItem.id == payload.item_id,
            MemorySessionItem.session_id == session_id,
        )
        .with_for_update()
    )
    if item is None:
        raise AppError(
            status_code=404,
            code="MEMORY_ITEM_NOT_FOUND",
            message="The memory session item was not found.",
        )
    entry, _definition = await _entry_definition(session, item.entry_id)
    if entry is None:
        raise AppError(
            status_code=404,
            code="MEMORY_ITEM_NOT_FOUND",
            message="The memory session item was not found.",
        )
    state = await session.scalar(
        select(UserWordState).where(UserWordState.id == item.word_state_id).with_for_update()
    )
    if state is None:
        raise AppError(
            status_code=404,
            code="MEMORY_ITEM_NOT_FOUND",
            message="The memory session item was not found.",
        )
    now = utcnow()
    ordinal = int(
        await session.scalar(
            select(func.count(MemoryEvent.id)).where(MemoryEvent.session_id == session_id)
        )
        or 0
    )

    def _event(event_type: str, **extra: Any) -> MemoryEvent:
        return MemoryEvent(
            user_id=user.id,
            session_id=session_id,
            item_id=item.id,
            entry_id=item.entry_id,
            wordbook_id=memory_session.wordbook_id,
            module=memory_session.module,
            event_type=event_type,
            duration_ms=payload.duration_ms,
            ordinal=ordinal,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            **extra,
        )

    if payload.action == "shown":
        if item.completed:
            raise AppError(
                status_code=409,
                code="MEMORY_ITEM_COMPLETED",
                message="This card is already completed in the current session.",
            )
        event = _event("shown")
        session.add(event)
        await session.commit()
        response = await _session_response(session, memory_session, book, preferences=preferences)
        return SessionEventResponse(
            event_id=event.id,
            item_id=item.id,
            action="shown",
            rating=None,
            is_correct=None,
            correct_answer=None,
            item_completed=item.completed,
            session_completed=memory_session.status == "completed",
            session=response,
        )

    if item.completed:
        raise AppError(
            status_code=409,
            code="MEMORY_ITEM_COMPLETED",
            message="This card is already completed in the current session.",
        )

    if payload.action == "mastered":
        state.status = "mastered"
        state.mastered_at = now
        state.suspended_at = None
        item.completed = True
        item.completed_at = now
        item.last_rating = "good"
        await _mark_plan_word_completed(session, user, book, item.entry_id, now=now)
        item.next_position = None
        event = _event("mastered")
        session.add(event)
        await _maybe_complete(session, memory_session, now=now)
        await session.commit()
        await session.refresh(memory_session)
        response = await _session_response(session, memory_session, book, preferences=preferences)
        return SessionEventResponse(
            event_id=event.id,
            item_id=item.id,
            action="mastered",
            rating=None,
            is_correct=None,
            correct_answer=None,
            item_completed=True,
            session_completed=memory_session.status == "completed",
            session=response,
        )

    is_correct, correct_answer = await _judge(
        session,
        module=memory_session.module,
        entry=entry,
        answer=payload.answer,
        preferences=preferences,
    )
    if memory_session.module == "flashcard":
        rating = "good" if payload.action == "good" else "again"
    else:
        if is_correct is None:
            raise AppError(
                status_code=409,
                code="MEMORY_CARD_UNAVAILABLE",
                message="The card could not be graded; restart the session.",
            )
        rating = "good" if is_correct else "again"

    outcome = fsrs_scheduler.review(
        state.fsrs_card,
        rating=rating,
        reviewed_at=now,
        duration_seconds=max(0, payload.duration_ms // 1000),
    )
    state.fsrs_card = outcome.card_payload
    state.algorithm_version = fsrs_scheduler.FSRS_ALGORITHM_VERSION
    state.due_at = outcome.due_at
    state.last_reviewed_at = now
    state.review_count += 1
    if rating == "again":
        state.lapse_count += 1
        state.status = "relearning"
    else:
        state.status = outcome.status

    if rating == "good":
        item.good_count += 1
    else:
        item.again_count += 1
    item.last_rating = rating
    # One award per answered card, keyed by the event so a retry pays once.
    await award(
        session,
        settings,
        user,
        source_type="review",
        source_id=str(item.id) + ":" + str(state.review_count),
    )

    required_goods = REQUIRED_NEW_GOOD_COUNT if item.reason == "new" else 1
    if rating == "good" and item.good_count >= required_goods:
        item.completed = True
        item.completed_at = now
        item.next_position = None
        await _mark_plan_word_completed(session, user, book, item.entry_id, now=now)
    else:
        await _requeue(session, item, session_id)

    event = _event(
        "answer",
        rating=rating,
        answer=payload.answer,
        is_correct=is_correct,
    )
    session.add(event)
    if rating == "again":
        mistake = await session.scalar(
            select(MistakeFlag)
            .where(MistakeFlag.user_id == user.id, MistakeFlag.entry_id == item.entry_id)
            .with_for_update()
        )
        if mistake is None:
            session.add(
                MistakeFlag(
                    user_id=user.id,
                    wordbook_id=memory_session.wordbook_id,
                    entry_id=item.entry_id,
                    again_count=1,
                    last_again_at=now,
                )
            )
        else:
            mistake.again_count += 1
            mistake.last_again_at = now

    await _maybe_complete(session, memory_session, now=now)
    await session.commit()
    await session.refresh(memory_session)
    response = await _session_response(session, memory_session, book, preferences=preferences)
    return SessionEventResponse(
        event_id=event.id,
        item_id=item.id,
        action=rating,
        rating=rating,
        is_correct=is_correct,
        correct_answer=correct_answer,
        item_completed=item.completed,
        session_completed=memory_session.status == "completed",
        session=response,
    )


async def complete_session(session: AsyncSession, user: User, session_id: UUID) -> SessionResponse:
    memory_session = await _load_session(session, user, session_id, lock=True)
    book = await session.scalar(select(Wordbook).where(Wordbook.id == memory_session.wordbook_id))
    if book is None:
        raise AppError(
            status_code=404,
            code="MEMORY_SESSION_NOT_FOUND",
            message="The memory session was not found.",
        )
    if memory_session.status == "active":
        items = await _session_items(session, session_id)
        completed = sum(1 for row in items if row[0].completed)
        memory_session.status = "completed"
        memory_session.ended_at = utcnow()
        memory_session.stats = {
            **(memory_session.stats or {}),
            "items": len(items),
            "completed": completed,
            "completed_early": completed < len(items),
        }
        await session.commit()
        await session.refresh(memory_session)
    preferences = (memory_session.config_snapshot or {}).get("preferences", {})
    return await _session_response(session, memory_session, book, preferences=preferences)


async def _state_response(session: AsyncSession, state: UserWordState) -> WordStateResponse:
    entry = await session.scalar(select(WordbookEntry).where(WordbookEntry.id == state.entry_id))
    return WordStateResponse(
        word_state_id=state.id,
        entry_id=state.entry_id,
        headword=entry.headword if entry else "",
        status=state.status,
        due_at=state.due_at,
        mastered_at=state.mastered_at,
        review_count=state.review_count,
        lapse_count=state.lapse_count,
        algorithm_version=state.algorithm_version,
    )


async def _own_state(
    session: AsyncSession, user: User, state_id: UUID, *, lock: bool = False
) -> UserWordState:
    statement = select(UserWordState).where(
        UserWordState.id == state_id, UserWordState.user_id == user.id
    )
    if lock:
        statement = statement.with_for_update()
    state = await session.scalar(statement)
    if state is None:
        raise AppError(
            status_code=404,
            code="MEMORY_WORD_NOT_FOUND",
            message="The word state was not found.",
        )
    return state


async def master_word(session: AsyncSession, user: User, state_id: UUID) -> WordStateResponse:
    state = await _own_state(session, user, state_id, lock=True)
    now = utcnow()
    state.status = "mastered"
    state.mastered_at = now
    state.suspended_at = None
    await session.commit()
    return await _state_response(session, state)


async def restore_word(session: AsyncSession, user: User, state_id: UUID) -> WordStateResponse:
    state = await _own_state(session, user, state_id, lock=True)
    now = utcnow()
    payload, status, due_at = fsrs_scheduler.restored_payload(state.fsrs_card, now=now)
    state.fsrs_card = payload
    state.status = status
    state.due_at = due_at
    state.mastered_at = None
    await session.commit()
    return await _state_response(session, state)


def _mistake_response(
    flag: MistakeFlag,
    entry: WordbookEntry | None,
    definition: WordbookDefinition | None,
    state: UserWordState | None,
) -> MistakeResponse:
    return MistakeResponse(
        word_state_id=state.id if state else EMPTY_UUID,
        entry_id=flag.entry_id,
        headword=entry.headword if entry else "",
        phonetic=entry.phonetic if entry else None,
        definition_zh=definition.definition_zh if definition else None,
        again_count=flag.again_count,
        last_again_at=flag.last_again_at,
        is_priority=flag.is_priority,
        status=state.status if state else "new",
    )


async def list_mistakes(
    session: AsyncSession,
    user: User,
    *,
    limit: int = 20,
    cursor: str | None = None,
) -> MistakeListResponse:
    offset = 0
    if cursor:
        try:
            offset = int(cursor)
        except ValueError as exc:
            raise AppError(
                status_code=422,
                code="CURSOR_INVALID",
                message="The pagination cursor is invalid.",
            ) from exc
        if offset < 0:
            raise AppError(
                status_code=422,
                code="CURSOR_INVALID",
                message="The pagination cursor is invalid.",
            )
    flags = list(
        (
            await session.scalars(
                select(MistakeFlag)
                .where(MistakeFlag.user_id == user.id)
                .order_by(MistakeFlag.last_again_at.desc(), MistakeFlag.id)
                .offset(offset)
                .limit(limit + 1)
            )
        ).all()
    )
    has_more = len(flags) > limit
    items: list[MistakeResponse] = []
    for flag in flags[:limit]:
        entry, definition = await _entry_definition(session, flag.entry_id)
        state = await session.scalar(
            select(UserWordState).where(
                UserWordState.user_id == user.id,
                UserWordState.wordbook_id == flag.wordbook_id,
                UserWordState.entry_id == flag.entry_id,
            )
        )
        items.append(_mistake_response(flag, entry, definition, state))
    return MistakeListResponse(
        items=items,
        next_cursor=str(offset + limit) if has_more else None,
        has_more=has_more,
    )


async def set_mistake_priority(
    session: AsyncSession,
    user: User,
    entry_id: UUID,
    payload: MistakePriorityRequest,
) -> MistakeResponse:
    flag = await session.scalar(
        select(MistakeFlag)
        .where(MistakeFlag.user_id == user.id, MistakeFlag.entry_id == entry_id)
        .with_for_update()
    )
    if flag is None:
        raise AppError(
            status_code=404,
            code="MEMORY_MISTAKE_NOT_FOUND",
            message="The mistake record was not found.",
        )
    # Only the review marker changes; the recorded events remain untouched.
    flag.is_priority = payload.is_priority
    await session.commit()
    entry, definition = await _entry_definition(session, entry_id)
    state = await session.scalar(
        select(UserWordState).where(
            UserWordState.user_id == user.id,
            UserWordState.wordbook_id == flag.wordbook_id,
            UserWordState.entry_id == entry_id,
        )
    )
    return _mistake_response(flag, entry, definition, state)
