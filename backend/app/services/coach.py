from __future__ import annotations

import base64
import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from arq.connections import ArqRedis
from fastapi import UploadFile
from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.ai import AiJob, AiJobEvent, AiUsageLedger
from app.models.coach import (
    CoachActionReceipt,
    CoachAttachment,
    CoachContextSnapshot,
    CoachConversation,
    CoachMessage,
    CoachStreamEvent,
)
from app.models.identity import User, UserProfile
from app.models.learning import DailyPlan, MistakeFlag
from app.models.practice import PracticeGeneration, PracticeSession
from app.models.wordbooks import Wordbook, WordbookActivation, WordbookEntry
from app.schemas.ai_tasks import (
    CoachAction,
    CoachHistoryTurn,
    CoachReplyContext,
    CoachReplyOutput,
    CoachReplyRequest,
)
from app.schemas.coach import (
    CoachAcceptedResponse,
    CoachActionReceiptResponse,
    CoachActivateWordbookParameters,
    CoachAttachmentResponse,
    CoachConversationCreate,
    CoachConversationListResponse,
    CoachConversationPatch,
    CoachConversationResponse,
    CoachDailyPlanActionParameters,
    CoachMessageCreate,
    CoachMessageListResponse,
    CoachMessageResponse,
    CoachNotificationPreferencesActionParameters,
    CoachReviewFocusParameters,
    CoachUndoResponse,
)
from app.schemas.notifications import (
    NotificationCategoryPreferences,
    NotificationPreferencesResponse,
    NotificationPreferencesUpdate,
)
from app.schemas.practice import PracticeCreateRequest
from app.services.ai_concurrency import release_concurrency_slot
from app.services.ai_jobs import cancel_user_job, create_ai_job
from app.services.ai_usage import resolved_quota_limits
from app.services.ai_validation import sanitize_untrusted_json
from app.services.audit import add_audit_event
from app.services.auth import utcnow
from app.services.coach_memory import (
    import_legacy_document,
    learning_snapshot,
    profile_snapshot,
    recall_memories,
)
from app.services.coach_uploads import (
    delete_attachment_files,
    read_attachment,
    save_coach_attachment,
)
from app.services.learning import local_date_for
from app.services.notifications import notify_ai_action
from app.services.practice import _event as practice_event
from app.services.practice import _hash_request as practice_hash
from app.services.practice import _resolve_target_entries as resolve_practice_entries
from app.services.wordbook_queue import WORDBOOK_QUEUE_NAME

logger = logging.getLogger(__name__)


def _conversation_response(conversation: CoachConversation) -> CoachConversationResponse:
    return CoachConversationResponse(
        id=conversation.id,
        title=conversation.title,
        status=conversation.status,
        scope=conversation.scope,
        message_count=conversation.message_count,
        last_message_at=conversation.last_message_at,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _receipt_response(receipt: CoachActionReceipt) -> CoachActionReceiptResponse:
    return CoachActionReceiptResponse(
        id=receipt.id,
        message_id=receipt.message_id,
        action_index=receipt.action_index,
        action_type=receipt.action_type,
        summary=receipt.summary,
        status=receipt.status,
        parameters=receipt.parameters,
        before_state=receipt.before_state,
        after_state=receipt.after_state,
        conflict_code=receipt.conflict_code,
        conflict_message=receipt.conflict_message,
        created_at=receipt.created_at,
        expires_at=receipt.expires_at,
        undone_at=receipt.undone_at,
    )


def _attachment_response(attachment: CoachAttachment) -> CoachAttachmentResponse:
    return CoachAttachmentResponse(
        id=attachment.id,
        filename=attachment.filename,
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
    )


def _message_response(
    message: CoachMessage,
    actions: list[CoachActionReceipt] | None = None,
    attachments: list[CoachAttachment] | None = None,
) -> CoachMessageResponse:
    return CoachMessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        role=message.role,
        content=message.content,
        status=message.status,
        sequence=message.sequence,
        error_code=message.error_code,
        error_message=message.error_message,
        created_at=message.created_at,
        completed_at=message.completed_at,
        actions=[_receipt_response(item) for item in (actions or [])],
        attachments=[_attachment_response(item) for item in (attachments or [])],
    )


async def _actions_for_messages(
    session: AsyncSession, messages: list[CoachMessage]
) -> dict[UUID, list[CoachActionReceipt]]:
    if not messages:
        return {}
    rows = list(
        (
            await session.scalars(
                select(CoachActionReceipt)
                .where(CoachActionReceipt.message_id.in_([message.id for message in messages]))
                .order_by(CoachActionReceipt.action_index.asc())
            )
        ).all()
    )
    result: dict[UUID, list[CoachActionReceipt]] = {}
    for row in rows:
        result.setdefault(row.message_id, []).append(row)
    return result


async def _attachments_for_messages(
    session: AsyncSession, messages: list[CoachMessage]
) -> dict[UUID, list[CoachAttachment]]:
    if not messages:
        return {}
    rows = list(
        (
            await session.scalars(
                select(CoachAttachment)
                .where(CoachAttachment.message_id.in_([message.id for message in messages]))
                .order_by(CoachAttachment.created_at.asc())
            )
        ).all()
    )
    result: dict[UUID, list[CoachAttachment]] = {}
    for row in rows:
        if row.message_id is not None:
            result.setdefault(row.message_id, []).append(row)
    return result


async def _message_responses(
    session: AsyncSession, messages: list[CoachMessage]
) -> list[CoachMessageResponse]:
    actions = await _actions_for_messages(session, messages)
    attachments = await _attachments_for_messages(session, messages)
    return [
        _message_response(message, actions.get(message.id, []), attachments.get(message.id, []))
        for message in messages
    ]


def _encode_cursor(value: str, identifier: UUID) -> str:
    return base64.urlsafe_b64encode(f"{value}|{identifier}".encode()).decode()


def _decode_cursor(cursor: str) -> tuple[str, UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        value, identifier = raw.split("|", 1)
        return value, UUID(identifier)
    except (ValueError, TypeError, UnicodeDecodeError) as exc:
        raise AppError(
            status_code=422,
            code="COACH_CURSOR_INVALID",
            message="The coach cursor is invalid.",
        ) from exc


async def _load_conversation(
    session: AsyncSession, user: User, conversation_id: UUID, *, lock: bool = False
) -> CoachConversation:
    statement = select(CoachConversation).where(
        CoachConversation.id == conversation_id,
        CoachConversation.user_id == user.id,
        CoachConversation.status == "active",
    )
    if lock:
        statement = statement.with_for_update()
    conversation = await session.scalar(statement)
    if conversation is None:
        raise AppError(
            status_code=404,
            code="COACH_CONVERSATION_NOT_FOUND",
            message="The coach conversation was not found.",
        )
    return conversation


async def _load_message(
    session: AsyncSession, user: User, message_id: UUID, *, lock: bool = False
) -> CoachMessage:
    statement = select(CoachMessage).where(
        CoachMessage.id == message_id,
        CoachMessage.user_id == user.id,
    )
    if lock:
        statement = statement.with_for_update()
    message = await session.scalar(statement)
    if message is None:
        raise AppError(
            status_code=404,
            code="COACH_MESSAGE_NOT_FOUND",
            message="The coach message was not found.",
        )
    return message


async def list_conversations(
    session: AsyncSession,
    user: User,
    *,
    limit: int = 20,
    cursor: str | None = None,
    scope: str = "panel",
) -> CoachConversationListResponse:
    filters = [
        CoachConversation.user_id == user.id,
        CoachConversation.status == "active",
        CoachConversation.scope == scope,
    ]
    if cursor:
        updated_at, cursor_id = _decode_cursor(cursor)
        timestamp = datetime.fromisoformat(updated_at)
        filters.append(
            (CoachConversation.updated_at < timestamp)
            | ((CoachConversation.updated_at == timestamp) & (CoachConversation.id < cursor_id))
        )
    rows = list(
        (
            await session.scalars(
                select(CoachConversation)
                .where(*filters)
                .order_by(CoachConversation.updated_at.desc(), CoachConversation.id.desc())
                .limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    visible = rows[:limit]
    return CoachConversationListResponse(
        items=[_conversation_response(item) for item in visible],
        next_cursor=(
            _encode_cursor(visible[-1].updated_at.isoformat(), visible[-1].id)
            if has_more and visible
            else None
        ),
        has_more=has_more,
    )


async def create_conversation(
    session: AsyncSession, user: User, payload: CoachConversationCreate
) -> CoachConversationResponse:
    conversation = CoachConversation(user_id=user.id, title=payload.title, scope=payload.scope)
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return _conversation_response(conversation)


async def rename_conversation(
    session: AsyncSession, user: User, conversation_id: UUID, payload: CoachConversationPatch
) -> CoachConversationResponse:
    conversation = await _load_conversation(session, user, conversation_id, lock=True)
    conversation.title = payload.title
    await session.commit()
    await session.refresh(conversation)
    return _conversation_response(conversation)


async def delete_or_clear_conversation(
    session: AsyncSession,
    settings: Settings,
    user: User,
    conversation_id: UUID,
    *,
    clear_only: bool,
) -> None:
    conversation = await _load_conversation(session, user, conversation_id, lock=True)
    attachments = list(
        (
            await session.scalars(
                select(CoachAttachment).where(CoachAttachment.conversation_id == conversation.id)
            )
        ).all()
    )
    if not clear_only:
        await session.delete(conversation)
        await session.commit()
        delete_attachment_files(settings, attachments)
        return
    await session.execute(
        delete(CoachAttachment).where(CoachAttachment.conversation_id == conversation.id)
    )
    await session.execute(
        delete(CoachActionReceipt).where(CoachActionReceipt.conversation_id == conversation.id)
    )
    await session.execute(
        delete(CoachStreamEvent).where(
            CoachStreamEvent.message_id.in_(
                select(CoachMessage.id).where(CoachMessage.conversation_id == conversation.id)
            )
        )
    )
    await session.execute(
        delete(CoachMessage).where(CoachMessage.conversation_id == conversation.id)
    )
    await session.execute(
        delete(CoachContextSnapshot).where(CoachContextSnapshot.conversation_id == conversation.id)
    )
    conversation.message_count = 0
    conversation.last_message_at = None
    await session.commit()
    delete_attachment_files(settings, attachments)


async def list_messages(
    session: AsyncSession,
    user: User,
    conversation_id: UUID,
    *,
    limit: int = 50,
    cursor: str | None = None,
) -> CoachMessageListResponse:
    await _load_conversation(session, user, conversation_id)
    filters = [
        CoachMessage.conversation_id == conversation_id,
        CoachMessage.user_id == user.id,
    ]
    if cursor:
        created_at, cursor_id = _decode_cursor(cursor)
        timestamp = datetime.fromisoformat(created_at)
        filters.append(
            (CoachMessage.created_at < timestamp)
            | ((CoachMessage.created_at == timestamp) & (CoachMessage.id < cursor_id))
        )
    rows = list(
        (
            await session.scalars(
                select(CoachMessage)
                .where(*filters)
                .order_by(CoachMessage.created_at.desc(), CoachMessage.id.desc())
                .limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    visible = rows[:limit]
    return CoachMessageListResponse(
        items=await _message_responses(session, visible),
        next_cursor=(
            _encode_cursor(visible[-1].created_at.isoformat(), visible[-1].id)
            if has_more and visible
            else None
        ),
        has_more=has_more,
    )


async def get_message(session: AsyncSession, user: User, message_id: UUID) -> CoachMessageResponse:
    message = await _load_message(session, user, message_id)
    actions = await _actions_for_messages(session, [message])
    attachments = await _attachments_for_messages(session, [message])
    return _message_response(message, actions.get(message.id, []), attachments.get(message.id, []))


async def get_action_receipt(
    session: AsyncSession, user: User, receipt_id: UUID
) -> CoachActionReceiptResponse:
    receipt = await session.scalar(
        select(CoachActionReceipt).where(
            CoachActionReceipt.id == receipt_id,
            CoachActionReceipt.user_id == user.id,
        )
    )
    if receipt is None:
        raise AppError(
            status_code=404,
            code="COACH_ACTION_NOT_FOUND",
            message="The coach action was not found.",
        )
    return _receipt_response(receipt)


async def add_coach_attachment(
    session: AsyncSession,
    settings: Settings,
    user: User,
    conversation_id: UUID,
    upload: UploadFile,
) -> CoachAttachmentResponse:
    conversation = await _load_conversation(session, user, conversation_id)
    attachment = await save_coach_attachment(settings, user, conversation, upload)
    session.add(attachment)
    await session.commit()
    return _attachment_response(attachment)


async def get_coach_attachment_file(
    session: AsyncSession,
    settings: Settings,
    user: User,
    attachment_id: UUID,
) -> tuple[CoachAttachment, bytes]:
    attachment = await session.scalar(
        select(CoachAttachment).where(
            CoachAttachment.id == attachment_id,
            CoachAttachment.user_id == user.id,
        )
    )
    if attachment is None:
        raise AppError(
            status_code=404,
            code="COACH_ATTACHMENT_NOT_FOUND",
            message="The image was not found.",
        )
    return attachment, read_attachment(settings, attachment)


async def create_coach_message(
    session: AsyncSession,
    pool: ArqRedis,
    user: User,
    settings: Settings,
    conversation_id: UUID,
    payload: CoachMessageCreate,
    *,
    idempotency_key: str,
) -> CoachAcceptedResponse:
    if not idempotency_key or len(idempotency_key) > 128:
        raise AppError(
            status_code=422,
            code="COACH_IDEMPOTENCY_KEY_INVALID",
            message="The Idempotency-Key must be between 1 and 128 characters.",
        )
    content = payload.content.strip()
    context = sanitize_untrusted_json(payload.page_context)
    conversation = await _load_conversation(session, user, conversation_id, lock=True)
    attachments: list[CoachAttachment] = []
    if payload.attachment_ids:
        attachment_ids = list(dict.fromkeys(payload.attachment_ids))
        if len(attachment_ids) > settings.coach_upload_max_per_message:
            raise AppError(
                status_code=422,
                code="COACH_ATTACHMENT_LIMIT",
                message="A message can carry at most four images.",
            )
        attachments = list(
            (
                await session.scalars(
                    select(CoachAttachment).where(
                        CoachAttachment.id.in_(attachment_ids),
                        CoachAttachment.user_id == user.id,
                        CoachAttachment.conversation_id == conversation.id,
                        CoachAttachment.message_id.is_(None),
                    )
                )
            ).all()
        )
        if len(attachments) != len(attachment_ids):
            raise AppError(
                status_code=422,
                code="COACH_ATTACHMENT_INVALID",
                message="One or more images are missing or already attached.",
            )
    existing_user = await session.scalar(
        select(CoachMessage).where(
            CoachMessage.user_id == user.id,
            CoachMessage.idempotency_key == idempotency_key,
        )
    )
    if existing_user is not None:
        if existing_user.content != content or existing_user.conversation_id != conversation.id:
            raise AppError(
                status_code=409,
                code="COACH_IDEMPOTENCY_CONFLICT",
                message="The Idempotency-Key was used for a different coach message.",
            )
        assistant = await session.scalar(
            select(CoachMessage).where(
                CoachMessage.conversation_id == existing_user.conversation_id,
                CoachMessage.sequence == existing_user.sequence + 1,
                CoachMessage.role == "assistant",
            )
        )
        if assistant is None:
            raise AppError(
                status_code=409,
                code="COACH_MESSAGE_STATE_INVALID",
                message="The coach message state is invalid.",
            )
        return CoachAcceptedResponse(
            message_id=assistant.id,
            status=assistant.status,
            stream_url=f"{settings.api_v1_prefix}/coach/streams/{assistant.id}",
        )

    context_cutoff = utcnow() - timedelta(hours=settings.coach_context_expire_hours)
    history_rows = list(
        (
            await session.scalars(
                select(CoachMessage)
                .where(
                    CoachMessage.conversation_id == conversation.id,
                    CoachMessage.status == "completed",
                    CoachMessage.content.is_not(None),
                    CoachMessage.created_at >= context_cutoff,
                )
                .order_by(CoachMessage.created_at.desc(), CoachMessage.sequence.desc())
                .limit(12)
            )
        ).all()
    )
    history = [
        CoachHistoryTurn(role=row.role, content=row.content[:4000])
        for row in reversed(history_rows)
        if row.content
    ]
    # Memory is assembled per turn: profile and recent results are computed,
    # only typed memories are stored. Nothing appends to a growing document.
    await import_legacy_document(session, user.id)
    profile = await profile_snapshot(session, user)
    recent = await learning_snapshot(session, user)
    recalled = await recall_memories(session, user.id, content)

    last_sequence = int(
        await session.scalar(
            select(func.coalesce(func.max(CoachMessage.sequence), 0)).where(
                CoachMessage.conversation_id == conversation.id
            )
        )
        or 0
    )
    user_message = CoachMessage(
        conversation_id=conversation.id,
        user_id=user.id,
        role="user",
        content=content,
        status="completed",
        sequence=last_sequence + 1,
        idempotency_key=idempotency_key,
        completed_at=utcnow(),
    )
    assistant = CoachMessage(
        conversation_id=conversation.id,
        user_id=user.id,
        role="assistant",
        content=None,
        status="queued",
        sequence=last_sequence + 2,
    )
    session.add_all([user_message, assistant])
    if attachments:
        # The id is generated at flush time, so link only after it exists.
        await session.flush()
        for attachment in attachments:
            attachment.message_id = user_message.id
    session.add(
        CoachContextSnapshot(
            conversation_id=conversation.id,
            user_id=user.id,
            context=context,
            expires_at=utcnow() + timedelta(days=settings.coach_context_ttl_days),
        )
    )
    conversation.message_count += 2
    conversation.last_message_at = utcnow()
    await session.flush()
    request = CoachReplyRequest(
        task_type="coach_reply",
        context=CoachReplyContext(
            user_message=content or "（用户发来一张图片）",
            attachment_ids=[attachment.id for attachment in attachments],
            learning_summary={"page_context": context},
            history=history,
            profile_snapshot=profile or None,
            learning_snapshot=recent or None,
            recalled_memories=recalled,
            conversation_id=conversation.id,
            message_id=assistant.id,
            page_context=context,
        ),
    )
    job, _ = await create_ai_job(
        session,
        pool,
        user,
        settings,
        request,
        idempotency_key=f"coach:{assistant.id}",
        commit=False,
    )
    assistant = await session.get(CoachMessage, assistant.id)
    if assistant is None:
        raise AppError(
            status_code=409,
            code="COACH_MESSAGE_STATE_INVALID",
            message="The coach message state is invalid.",
        )
    assistant.ai_job_id = job.id
    await session.commit()
    try:
        await pool.enqueue_job(
            "process_ai_job",
            str(job.id),
            _job_id=f"ai:{job.id}",
            _queue_name=WORDBOOK_QUEUE_NAME,
        )
    except Exception as exc:
        await cancel_user_job(session, pool, user, job.id)
        raise AppError(
            status_code=503,
            code="COACH_QUEUE_UNAVAILABLE",
            message="The coach task queue is unavailable.",
            headers={"Retry-After": "5"},
        ) from exc
    return CoachAcceptedResponse(
        message_id=assistant.id,
        status="queued",
        stream_url=f"{settings.api_v1_prefix}/coach/streams/{assistant.id}",
    )


async def _next_event_sequence(session: AsyncSession, message_id: UUID) -> int:
    return (
        int(
            await session.scalar(
                select(func.coalesce(func.max(CoachStreamEvent.sequence), 0)).where(
                    CoachStreamEvent.message_id == message_id
                )
            )
            or 0
        )
        + 1
    )


async def add_stream_event(
    session: AsyncSession, message_id: UUID, event_type: str, data: dict[str, Any]
) -> CoachStreamEvent:
    event = CoachStreamEvent(
        message_id=message_id,
        sequence=await _next_event_sequence(session, message_id),
        event_type=event_type,
        data=data,
    )
    session.add(event)
    await session.flush()
    return event


def _safe_action_error(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, AppError):
        return exc.code, exc.message[:500]
    if isinstance(exc, ValidationError):
        return "COACH_ACTION_PARAMETERS_INVALID", "The action parameters were invalid."
    return "COACH_ACTION_FAILED", "The coach action could not be applied."


async def _get_profile(session: AsyncSession, user_id: UUID) -> UserProfile:
    profile = await session.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    if profile is None:
        profile = UserProfile(user_id=user_id)
        session.add(profile)
        await session.flush()
    return profile


async def _visible_wordbook(
    session: AsyncSession, user: User, wordbook_id: UUID, *, require_ready: bool = False
) -> Wordbook:
    book = await session.scalar(select(Wordbook).where(Wordbook.id == wordbook_id))
    if (
        book is None
        or book.status == "deleted"
        or (require_ready and book.status != "ready")
        or book.owner_id != user.id
    ):
        raise AppError(
            status_code=404,
            code="WORDBOOK_NOT_FOUND",
            message="The wordbook was not found.",
        )
    return book


async def _apply_adjust_daily_plan(
    session: AsyncSession,
    user: User,
    settings: Settings,
    parameters: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    values = CoachDailyPlanActionParameters.model_validate(parameters)
    profile = await _get_profile(session, user.id)
    plan = await session.scalar(
        select(DailyPlan).where(
            DailyPlan.user_id == user.id,
            DailyPlan.local_date == local_date_for(settings, user),
        )
    )
    before = {
        "new_words": profile.daily_new_words,
        "study_minutes": profile.daily_study_minutes,
        "daily_plan_id": str(plan.id) if plan else None,
        "plan_new_words": plan.new_word_target if plan else None,
        "plan_study_minutes": plan.study_minutes_target if plan else None,
    }
    if values.new_words is not None:
        profile.daily_new_words = values.new_words
        if plan is not None:
            plan.new_word_target = values.new_words
    if values.study_minutes is not None:
        profile.daily_study_minutes = values.study_minutes
        if plan is not None:
            plan.study_minutes_target = values.study_minutes
    after = {
        "new_words": profile.daily_new_words,
        "study_minutes": profile.daily_study_minutes,
        "daily_plan_id": str(plan.id) if plan else None,
        "plan_new_words": plan.new_word_target if plan else None,
        "plan_study_minutes": plan.study_minutes_target if plan else None,
    }
    return before, after


async def _apply_notification_preferences(
    session: AsyncSession, user: User, parameters: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    values = CoachNotificationPreferencesActionParameters.model_validate(parameters)
    profile = await _get_profile(session, user.id)
    current_raw = (
        profile.notification_preferences
        if isinstance(profile.notification_preferences, dict)
        else {}
    )
    current = NotificationPreferencesResponse(
        categories=NotificationCategoryPreferences(
            **{
                **NotificationCategoryPreferences().model_dump(),
                **current_raw.get("categories", {}),
            }
        ),
        dnd_start=current_raw.get("dnd_start", "22:00"),
        dnd_end=current_raw.get("dnd_end", "08:00"),
        daily_limit=current_raw.get("daily_limit", 3),
        timezone=current_raw.get("timezone", "Asia/Shanghai"),
    ).model_dump(mode="json")
    merged = current.copy()
    changes = values.model_dump(exclude_none=True)
    if "categories" in changes:
        merged["categories"] = {**merged["categories"], **changes.pop("categories")}
    merged.update(changes)
    validated = NotificationPreferencesUpdate.model_validate(merged)
    after = validated.model_dump(mode="json")
    profile.notification_preferences = after
    return current, after


async def _apply_start_practice(
    session: AsyncSession,
    pool: ArqRedis,
    user: User,
    settings: Settings,
    parameters: dict[str, Any],
    *,
    receipt_id: UUID,
) -> tuple[dict[str, Any], dict[str, Any], list[tuple[UUID, UUID]]]:
    from app.schemas.ai_tasks import PracticeGenerationContext, PracticeGenerationRequest

    payload = PracticeCreateRequest.model_validate(parameters)
    wordbook_id, target_entry_ids = await resolve_practice_entries(session, user, settings, payload)
    session_id = uuid4()
    generation_id = uuid4()
    practice = PracticeSession(
        id=session_id,
        user_id=user.id,
        practice_type=payload.practice_type,
        source=payload.source,
        difficulty=payload.difficulty,
        wordbook_id=wordbook_id,
        question_count=payload.count,
        status="generating",
        generation_number=1,
        current_generation_id=generation_id,
        source_context={
            "practice_type": payload.practice_type,
            "source": payload.source,
            "count": payload.count,
            "difficulty": payload.difficulty,
            "wordbook_id": str(wordbook_id) if wordbook_id else None,
            "target_entry_ids": [str(entry_id) for entry_id in target_entry_ids],
            "started_by": "coach",
        },
        idempotency_key=f"coach-action:{receipt_id}",
        request_hash=practice_hash(payload.model_dump(mode="json")),
    )
    generation = PracticeGeneration(
        id=generation_id,
        session_id=session_id,
        generation_number=1,
        status="generating",
    )
    session.add(practice)
    await session.flush()
    session.add(generation)
    await session.flush()
    session.add(practice_event(practice, "practice.created", metadata={"source": "coach"}))
    job, _ = await create_ai_job(
        session,
        pool,
        user,
        settings,
        PracticeGenerationRequest(
            task_type="practice_generation",
            context=PracticeGenerationContext(
                practice_type=payload.practice_type,
                count=payload.count,
                source=payload.source,
                difficulty=payload.difficulty,
                wordbook_id=wordbook_id,
                target_entry_ids=target_entry_ids,
                practice_session_id=session_id,
            ),
        ),
        idempotency_key=f"coach-practice:{receipt_id}",
        commit=False,
    )
    practice.ai_job_id = job.id
    generation.ai_job_id = job.id
    return (
        {"practice_session_id": None},
        {"practice_session_id": str(session_id), "created": True},
        [(job.id, receipt_id)],
    )


async def _apply_activate_wordbook(
    session: AsyncSession, user: User, parameters: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    values = CoachActivateWordbookParameters.model_validate(parameters)
    await _visible_wordbook(session, user, values.wordbook_id, require_ready=True)
    activation = await session.get(WordbookActivation, user.id)
    before = {"wordbook_id": str(activation.wordbook_id) if activation else None}
    if activation is None:
        session.add(WordbookActivation(user_id=user.id, wordbook_id=values.wordbook_id))
    else:
        activation.wordbook_id = values.wordbook_id
    return before, {"wordbook_id": str(values.wordbook_id)}


async def _apply_mark_review_focus(
    session: AsyncSession, user: User, parameters: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    values = CoachReviewFocusParameters.model_validate(parameters)
    entry = await session.scalar(
        select(WordbookEntry)
        .join(Wordbook, Wordbook.id == WordbookEntry.wordbook_id)
        .where(WordbookEntry.id == values.entry_id, Wordbook.status != "deleted")
    )
    if entry is None:
        raise AppError(
            status_code=404,
            code="WORDBOOK_ENTRY_NOT_FOUND",
            message="The wordbook entry was not found.",
        )
    if values.wordbook_id is not None and entry.wordbook_id != values.wordbook_id:
        raise AppError(
            status_code=404,
            code="WORDBOOK_ENTRY_NOT_FOUND",
            message="The wordbook entry was not found.",
        )
    await _visible_wordbook(session, user, entry.wordbook_id)
    flag = await session.scalar(
        select(MistakeFlag).where(
            MistakeFlag.user_id == user.id,
            MistakeFlag.entry_id == values.entry_id,
        )
    )
    before = {"exists": flag is not None, "is_priority": flag.is_priority if flag else None}
    if flag is None:
        flag = MistakeFlag(
            user_id=user.id,
            wordbook_id=entry.wordbook_id,
            entry_id=entry.id,
            again_count=0,
            last_again_at=utcnow(),
            is_priority=values.is_priority,
        )
        session.add(flag)
    else:
        flag.is_priority = values.is_priority
    return before, {"exists": True, "is_priority": values.is_priority}


async def _apply_action(
    session: AsyncSession,
    pool: ArqRedis,
    user: User,
    settings: Settings,
    action: CoachAction,
    *,
    receipt_id: UUID,
) -> tuple[dict[str, Any], dict[str, Any], list[tuple[UUID, UUID]]]:
    if action.action_type == "adjust_daily_plan":
        before, after = await _apply_adjust_daily_plan(session, user, settings, action.parameters)
    elif action.action_type == "adjust_notification_preferences":
        before, after = await _apply_notification_preferences(session, user, action.parameters)
    elif action.action_type == "start_practice":
        return await _apply_start_practice(
            session, pool, user, settings, action.parameters, receipt_id=receipt_id
        )
    elif action.action_type == "activate_wordbook":
        before, after = await _apply_activate_wordbook(session, user, action.parameters)
    elif action.action_type == "mark_review_focus":
        before, after = await _apply_mark_review_focus(session, user, action.parameters)
    else:
        raise AppError(
            status_code=422,
            code="COACH_ACTION_NOT_ALLOWED",
            message="The coach action is not allowed.",
        )
    return before, after, []


MCP_ACTION_TYPES = (
    "adjust_daily_plan",
    "start_practice",
    "activate_wordbook",
    "mark_review_focus",
)


async def apply_coach_tool(
    session: AsyncSession,
    pool: ArqRedis,
    user: User,
    settings: Settings,
    action_type: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """Apply one whitelisted action for an external MCP caller.

    The coach loop keeps its receipt/undo bookkeeping; this path applies the same
    action through the same executor and reports the before/after state.
    """
    if action_type not in MCP_ACTION_TYPES:
        raise AppError(
            status_code=422,
            code="COACH_ACTION_NOT_ALLOWED",
            message="The coach action is not exposed as a tool.",
        )
    action = CoachAction(
        action_type=action_type,
        parameters=parameters,
        summary=f"MCP 工具调用：{action_type}",
    )
    try:
        before, after, _ = await _apply_action(
            session, pool, user, settings, action, receipt_id=uuid4()
        )
    except ValidationError as exc:
        raise AppError(
            status_code=422,
            code="COACH_ACTION_PARAMETERS_INVALID",
            message="The action parameters were invalid.",
        ) from exc
    await session.commit()
    return {"action_type": action_type, "before": before, "after": after}


async def materialize_coach_success(
    session: AsyncSession,
    job: AiJob,
    settings: Settings,
    pool: ArqRedis,
) -> list[tuple[UUID, UUID]]:
    message_id_raw = job.input_context.get("message_id")
    if not message_id_raw:
        return []
    message = await session.get(CoachMessage, UUID(str(message_id_raw)), with_for_update=True)
    if message is None or message.ai_job_id != job.id:
        return []
    if message.status == "completed":
        return []
    output = CoachReplyOutput.model_validate(job.result or {})
    user = await session.get(User, job.user_id)
    if user is None:
        raise AppError(
            status_code=404,
            code="COACH_USER_NOT_FOUND",
            message="The coach user was not found.",
        )
    message.content = output.message
    message.status = "completed"
    message.error_code = None
    message.error_message = None
    message.completed_at = utcnow()
    for start in range(0, len(output.message), 240):
        await add_stream_event(
            session,
            message.id,
            "message.delta",
            {"text": output.message[start : start + 240]},
        )

    deferred: list[tuple[UUID, UUID]] = []
    for index, action in enumerate(output.actions):
        receipt_id = uuid4()
        try:
            async with session.begin_nested():
                before, after, action_deferred = await _apply_action(
                    session,
                    pool,
                    user,
                    settings,
                    action,
                    receipt_id=receipt_id,
                )
            receipt = CoachActionReceipt(
                id=receipt_id,
                user_id=user.id,
                conversation_id=message.conversation_id,
                message_id=message.id,
                action_index=index,
                action_type=action.action_type,
                parameters=action.parameters,
                before_state=before,
                after_state=after,
                summary=action.summary[:500],
                status="applied",
                expires_at=utcnow() + timedelta(hours=settings.coach_action_undo_hours),
            )
            session.add(receipt)
            await session.flush()
            deferred.extend(action_deferred)
            await add_stream_event(
                session,
                message.id,
                "action.applied",
                {
                    "receipt_id": str(receipt.id),
                    "action_type": action.action_type,
                    "summary": action.summary[:500],
                },
            )
            add_audit_event(
                session,
                actor=user,
                action="coach.action.applied",
                target_type="coach_action",
                target_id=receipt.id,
                outcome="success",
                context={"action_type": action.action_type, "message_id": str(message.id)},
            )
            await notify_ai_action(session, user_id=user.id, action_id=receipt.id)
        except (AppError, ValidationError, ValueError) as exc:
            code, safe_message = _safe_action_error(exc)
            receipt = CoachActionReceipt(
                id=receipt_id,
                user_id=user.id,
                conversation_id=message.conversation_id,
                message_id=message.id,
                action_index=index,
                action_type=action.action_type,
                parameters=action.parameters,
                before_state={},
                after_state={},
                summary=action.summary[:500],
                status="conflict",
                conflict_code=code,
                conflict_message=safe_message,
                expires_at=utcnow() + timedelta(hours=settings.coach_action_undo_hours),
            )
            session.add(receipt)
            await session.flush()
            await add_stream_event(
                session,
                message.id,
                "action.rejected",
                {"receipt_id": str(receipt.id), "action_type": action.action_type, "code": code},
            )
            add_audit_event(
                session,
                actor=user,
                action="coach.action.rejected",
                target_type="coach_action",
                target_id=receipt.id,
                outcome="failure",
                reason_code=code,
                context={"action_type": action.action_type, "message_id": str(message.id)},
            )
    return deferred


async def finalize_coach_success(session: AsyncSession, job: AiJob, settings: Settings) -> None:
    message_id_raw = job.input_context.get("message_id")
    if not message_id_raw:
        return
    message_id = UUID(str(message_id_raw))
    existing = await session.scalar(
        select(CoachStreamEvent.id).where(
            CoachStreamEvent.message_id == message_id,
            CoachStreamEvent.event_type == "done",
        )
    )
    if existing is not None:
        return
    ledgers = list(
        (await session.scalars(select(AiUsageLedger).where(AiUsageLedger.job_id == job.id))).all()
    )
    units = sum(ledger.consumed for ledger in ledgers)
    limits = await resolved_quota_limits(session, job.user_id, settings)
    limit = limits[job.quota_kind] if job.quota_kind else 0
    usage = {"quota_kind": job.quota_kind, "units": units, "limit": limit}
    await add_stream_event(session, message_id, "usage", usage)
    await add_stream_event(
        session,
        message_id,
        "done",
        {"message_id": str(message_id), "status": "completed"},
    )


async def mark_coach_failed(session: AsyncSession, job: AiJob) -> None:
    message_id_raw = job.input_context.get("message_id")
    if not message_id_raw:
        return
    message = await session.get(CoachMessage, UUID(str(message_id_raw)), with_for_update=True)
    if message is None or message.status in {"completed", "failed"}:
        return
    code = job.error_code or "COACH_GENERATION_FAILED"
    safe_message = "The coach reply could not be completed. Please retry."
    message.status = "failed"
    message.error_code = code[:64]
    message.error_message = safe_message
    message.completed_at = utcnow()
    await add_stream_event(
        session,
        message.id,
        "error",
        {"code": code[:64], "message": safe_message, "retryable": bool(job.retryable)},
    )


async def _state_matches_after(
    session: AsyncSession, user: User, receipt: CoachActionReceipt
) -> bool:
    after = receipt.after_state
    if receipt.action_type == "adjust_daily_plan":
        profile = await _get_profile(session, user.id)
        if profile.daily_new_words != after.get(
            "new_words"
        ) or profile.daily_study_minutes != after.get("study_minutes"):
            return False
        plan_id = after.get("daily_plan_id")
        if plan_id:
            plan = await session.get(DailyPlan, UUID(str(plan_id)))
            return (
                plan is not None
                and plan.new_word_target == after.get("plan_new_words")
                and plan.study_minutes_target == after.get("plan_study_minutes")
            )
        return True
    if receipt.action_type == "adjust_notification_preferences":
        profile = await _get_profile(session, user.id)
        return (profile.notification_preferences or {}) == after
    if receipt.action_type == "activate_wordbook":
        activation = await session.get(WordbookActivation, user.id)
        return bool(activation) and str(activation.wordbook_id) == after.get("wordbook_id")
    if receipt.action_type == "mark_review_focus":
        flag = await session.scalar(
            select(MistakeFlag).where(
                MistakeFlag.user_id == user.id,
                MistakeFlag.entry_id == receipt.parameters.get("entry_id"),
            )
        )
        return flag is not None and flag.is_priority == after.get("is_priority")
    if receipt.action_type == "start_practice":
        practice_id = after.get("practice_session_id")
        if not practice_id:
            return False
        practice = await session.get(PracticeSession, UUID(str(practice_id)))
        return (
            practice is not None and practice.user_id == user.id and practice.status != "submitted"
        )
    return False


async def _restore_before(
    session: AsyncSession,
    user: User,
    receipt: CoachActionReceipt,
    *,
    pool: ArqRedis | None = None,
) -> None:
    before = receipt.before_state
    if receipt.action_type == "adjust_daily_plan":
        profile = await _get_profile(session, user.id)
        if before.get("new_words") is not None:
            profile.daily_new_words = int(before["new_words"])
        if before.get("study_minutes") is not None:
            profile.daily_study_minutes = int(before["study_minutes"])
        plan_id = before.get("daily_plan_id")
        if plan_id:
            plan = await session.get(DailyPlan, UUID(str(plan_id)))
            if plan is not None:
                if before.get("plan_new_words") is not None:
                    plan.new_word_target = int(before["plan_new_words"])
                if before.get("plan_study_minutes") is not None:
                    plan.study_minutes_target = int(before["plan_study_minutes"])
        return
    if receipt.action_type == "adjust_notification_preferences":
        profile = await _get_profile(session, user.id)
        profile.notification_preferences = before if isinstance(before, dict) else {}
        return
    if receipt.action_type == "activate_wordbook":
        activation = await session.get(WordbookActivation, user.id)
        previous = before.get("wordbook_id")
        if previous:
            if activation is None:
                session.add(WordbookActivation(user_id=user.id, wordbook_id=UUID(str(previous))))
            else:
                activation.wordbook_id = UUID(str(previous))
        elif activation is not None:
            await session.delete(activation)
        return
    if receipt.action_type == "mark_review_focus":
        flag = await session.scalar(
            select(MistakeFlag).where(
                MistakeFlag.user_id == user.id,
                MistakeFlag.entry_id == receipt.parameters.get("entry_id"),
            )
        )
        if not before.get("exists"):
            if flag is not None and flag.again_count == 0:
                await session.delete(flag)
            elif flag is not None:
                flag.is_priority = False
        elif flag is not None:
            flag.is_priority = bool(before.get("is_priority"))
        return
    if receipt.action_type == "start_practice":
        practice_id = receipt.after_state.get("practice_session_id")
        if practice_id:
            practice = await session.get(PracticeSession, UUID(str(practice_id)))
            if (
                practice is not None
                and practice.user_id == user.id
                and practice.status != "submitted"
            ):
                practice.status = "cancelled"
                practice.error_code = "COACH_ACTION_UNDONE"
                practice.error_message = "The coach-started practice was cancelled."
                generation = await session.get(PracticeGeneration, practice.current_generation_id)
                if generation is not None:
                    generation.status = "cancelled"
                if practice.ai_job_id is not None:
                    job = await session.get(AiJob, practice.ai_job_id, with_for_update=True)
                    if job is not None and job.status in {"queued", "running"}:
                        job.status = "cancelled"
                        job.error_code = "COACH_ACTION_UNDONE"
                        job.error_message = "The coach-started practice was cancelled."
                        job.retryable = False
                        job.finished_at = utcnow()
                        session.add(
                            AiJobEvent(
                                job_id=job.id,
                                event_type="ai.job.cancelled",
                                status="cancelled",
                                metadata_json={"reason": "coach_action_undone"},
                            )
                        )
                        ledgers = list(
                            (
                                await session.scalars(
                                    select(AiUsageLedger)
                                    .where(AiUsageLedger.job_id == job.id)
                                    .with_for_update()
                                )
                            ).all()
                        )
                        for ledger in ledgers:
                            if ledger.status == "reserved":
                                ledger.status = "released"
                                ledger.released = ledger.reserved
                                ledger.reserved = 0
                        if pool is not None:
                            await release_concurrency_slot(pool, user_id=user.id, job_id=job.id)


async def undo_action(
    session: AsyncSession,
    user: User,
    receipt_id: UUID,
    *,
    pool: ArqRedis | None = None,
) -> CoachUndoResponse:
    receipt = await session.scalar(
        select(CoachActionReceipt)
        .where(
            CoachActionReceipt.id == receipt_id,
            CoachActionReceipt.user_id == user.id,
        )
        .with_for_update()
    )
    if receipt is None:
        raise AppError(
            status_code=404,
            code="COACH_ACTION_NOT_FOUND",
            message="The coach action was not found.",
        )
    if receipt.status == "undone":
        return CoachUndoResponse(
            receipt=_receipt_response(receipt), message="The action was already undone."
        )
    if receipt.status == "conflict":
        raise AppError(
            status_code=409,
            code=receipt.conflict_code or "COACH_ACTION_CONFLICT",
            message=receipt.conflict_message or "The action can no longer be undone.",
        )
    if utcnow() > receipt.expires_at:
        raise AppError(
            status_code=409,
            code="COACH_ACTION_UNDO_EXPIRED",
            message="The 24-hour undo window has expired.",
        )
    if not await _state_matches_after(session, user, receipt):
        receipt.status = "conflict"
        receipt.conflict_code = "COACH_ACTION_STATE_CHANGED"
        receipt.conflict_message = (
            "The resource changed after this action, so it cannot be safely undone."
        )
        add_audit_event(
            session,
            actor=user,
            action="coach.action.undo_conflict",
            target_type="coach_action",
            target_id=receipt.id,
            outcome="failure",
            reason_code=receipt.conflict_code,
            context={"action_type": receipt.action_type},
        )
        await session.commit()
        raise AppError(
            status_code=409,
            code=receipt.conflict_code,
            message=receipt.conflict_message,
        )
    await _restore_before(session, user, receipt, pool=pool)
    receipt.status = "undone"
    receipt.undone_at = utcnow()
    add_audit_event(
        session,
        actor=user,
        action="coach.action.undone",
        target_type="coach_action",
        target_id=receipt.id,
        outcome="success",
        context={"action_type": receipt.action_type},
    )
    await session.commit()
    return CoachUndoResponse(receipt=_receipt_response(receipt), message="The action was undone.")


async def list_stream_events(
    session: AsyncSession,
    user: User,
    message_id: UUID,
    *,
    after: int = 0,
    limit: int = 200,
) -> list[CoachStreamEvent]:
    message = await _load_message(session, user, message_id)
    if message.role != "assistant":
        raise AppError(
            status_code=404,
            code="COACH_MESSAGE_NOT_FOUND",
            message="The coach message was not found.",
        )
    return list(
        (
            await session.scalars(
                select(CoachStreamEvent)
                .where(
                    CoachStreamEvent.message_id == message_id,
                    CoachStreamEvent.sequence > after,
                )
                .order_by(CoachStreamEvent.sequence.asc())
                .limit(limit)
            )
        ).all()
    )


async def cleanup_coach_data(
    session: AsyncSession, settings: Settings, *, now: datetime | None = None
) -> dict[str, int]:
    current = now or utcnow()
    cutoff = current - timedelta(days=settings.coach_message_retention_days)
    stale_messages = select(CoachMessage.id).where(
        CoachMessage.created_at < cutoff,
        CoachMessage.status.in_(("completed", "failed")),
    )
    stale_attachments = list(
        (
            await session.scalars(
                select(CoachAttachment).where(CoachAttachment.message_id.in_(stale_messages))
            )
        ).all()
    )
    await session.execute(
        delete(CoachAttachment).where(CoachAttachment.message_id.in_(stale_messages))
    )
    message_result = await session.execute(
        delete(CoachMessage).where(
            CoachMessage.created_at < cutoff,
            CoachMessage.status.in_(("completed", "failed")),
        )
    )
    context_result = await session.execute(
        delete(CoachContextSnapshot).where(CoachContextSnapshot.expires_at < current)
    )
    conversation_ids = list(
        (
            await session.scalars(
                select(CoachConversation.id).where(CoachConversation.status == "active")
            )
        ).all()
    )
    for conversation_id in conversation_ids:
        conversation = await session.get(CoachConversation, conversation_id)
        if conversation is None:
            continue
        conversation.message_count = int(
            await session.scalar(
                select(func.count(CoachMessage.id)).where(
                    CoachMessage.conversation_id == conversation_id
                )
            )
            or 0
        )
        conversation.last_message_at = await session.scalar(
            select(func.max(CoachMessage.created_at)).where(
                CoachMessage.conversation_id == conversation_id
            )
        )
    await session.commit()
    delete_attachment_files(settings, stale_attachments)
    return {
        "messages": int(message_result.rowcount or 0),
        "contexts": int(context_result.rowcount or 0),
        "attachments": len(stale_attachments),
    }
