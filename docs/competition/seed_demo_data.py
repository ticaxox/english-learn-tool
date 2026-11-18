#!/usr/bin/env python3
"""Create a deterministic, synthetic competition demo dataset.

This script writes only rows whose IDs are derived from the demo namespace below.
It refuses to run unless DEMO_SEED_CONFIRM=YES and the database is at the current
Alembic head. Use it on a disposable or dedicated demo database, never on real
member data. The script never prints passwords.

Example:
    $env:DEMO_SEED_CONFIRM = 'YES'
    $env:DEMO_ADMIN_PASSWORD = '<unique demo admin password>'
    $env:DEMO_MEMBER_PASSWORD = '<unique demo member password>'
    uv run --project backend python docs/competition/seed_demo_data.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import delete, select, text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.session import create_engine, create_session_factory  # noqa: E402
from app.models.challenge import (  # noqa: E402
    ChallengeNode,
    ChallengeNodeProgress,
    DailyChallengePlan,
)
from app.models.coach import (  # noqa: E402
    CoachActionReceipt,
    CoachContextSnapshot,
    CoachConversation,
    CoachMessage,
    CoachStreamEvent,
)
from app.models.identity import User, UserProfile  # noqa: E402
from app.models.learning import (  # noqa: E402
    DailyActivity,
    DailyPlan,
    DailyPlanWord,
    MemoryConfig,
    MistakeFlag,
    UserWordState,
)
from app.models.notifications import Notification  # noqa: E402
from app.models.practice import (  # noqa: E402
    PracticeEvent,
    PracticeGeneration,
    PracticeQuestion,
    PracticeSession,
    PracticeSubmission,
)
from app.models.wordbooks import (  # noqa: E402
    Wordbook,
    WordbookActivation,
    WordbookDefinition,
    WordbookEntry,
    WordbookExample,
)
from app.services.fsrs_scheduler import FSRS_ALGORITHM_VERSION, new_card_payload  # noqa: E402

EXPECTED_ALEMBIC_HEAD = "20261114_0032"
DEMO_NAMESPACE = uuid5(NAMESPACE_URL, "english-learn-tool/competition-demo/v1")
DEMO_BOOK_NAME = "Aurora English Lab · Synthetic Demo 20"
DEMO_BOOK_KEY = "wordbook:aurora-demo"
DEMO_USERNAMES = ("demo_admin", "demo_member", "demo_member2", "demo_member3")
DEMO_IDS = {
    "admin": uuid5(DEMO_NAMESPACE, "user:demo_admin"),
    "member": uuid5(DEMO_NAMESPACE, "user:demo_member"),
    "member2": uuid5(DEMO_NAMESPACE, "user:demo_member2"),
    "member3": uuid5(DEMO_NAMESPACE, "user:demo_member3"),
    "wordbook": uuid5(DEMO_NAMESPACE, DEMO_BOOK_KEY),
    "practice_session": uuid5(DEMO_NAMESPACE, "practice:fill-blank:001"),
    "practice_generation": uuid5(DEMO_NAMESPACE, "practice:generation:001"),
    "practice_submission": uuid5(DEMO_NAMESPACE, "practice:submission:001"),
    "coach_conversation": uuid5(DEMO_NAMESPACE, "coach:conversation:001"),
    "coach_user_message": uuid5(DEMO_NAMESPACE, "coach:message:user:001"),
    "coach_assistant_message": uuid5(DEMO_NAMESPACE, "coach:message:assistant:001"),
    "challenge_plan": uuid5(DEMO_NAMESPACE, "challenge:plan:today"),
}
WORDS = [
    (
        "harbor",
        "港口",
        "A place where ships shelter or load cargo.",
        "The ship entered the harbor at dawn.",
    ),
    (
        "compass",
        "指南针",
        "A tool that helps a traveler find direction.",
        "The compass pointed north through the fog.",
    ),
    (
        "lantern",
        "灯笼",
        "A portable light with a protective cover.",
        "A lantern lit the path to the cabin.",
    ),
    (
        "orchard",
        "果园",
        "A place where fruit trees are grown.",
        "The orchard was full of ripe apples.",
    ),
    (
        "meadow",
        "草地",
        "A field covered with grass and flowers.",
        "We crossed the meadow before sunset.",
    ),
    (
        "river",
        "河流",
        "A natural stream of water flowing to the sea.",
        "The river curved around the old town.",
    ),
    (
        "bridge",
        "桥",
        "A structure that carries a path across an obstacle.",
        "The bridge connected the two villages.",
    ),
    (
        "scholar",
        "学者",
        "A person who studies a subject deeply.",
        "The scholar compared the two translations.",
    ),
    (
        "curious",
        "好奇的",
        "Wanting to know or learn something.",
        "The curious student asked a careful question.",
    ),
    (
        "patient",
        "耐心的",
        "Able to wait or continue without becoming upset.",
        "A patient learner reviews one step at a time.",
    ),
    (
        "gather",
        "收集",
        "To bring things or people together.",
        "We gather examples before writing a summary.",
    ),
    ("improve", "改善", "To make something better.", "Daily practice can improve your fluency."),
    ("whisper", "低语", "To speak very quietly.", "She would whisper the answer to herself."),
    (
        "journey",
        "旅程",
        "An act of traveling from one place to another.",
        "The journey taught him to plan ahead.",
    ),
    (
        "courage",
        "勇气",
        "The ability to face difficulty or fear.",
        "It takes courage to speak a new language.",
    ),
    (
        "reflect",
        "反思",
        "To think carefully about something.",
        "Take a moment to reflect on the mistake.",
    ),
    (
        "pattern",
        "模式",
        "A repeated or regular arrangement.",
        "The teacher noticed a useful pattern.",
    ),
    (
        "signal",
        "信号",
        "A sign or action that communicates information.",
        "The signal told the team to begin.",
    ),
    (
        "balance",
        "平衡",
        "A stable state with suitable proportions.",
        "A good plan balances review and new words.",
    ),
    (
        "discover",
        "发现",
        "To find or learn something for the first time.",
        "You may discover a better way to remember.",
    ),
]


def demo_id(key: str) -> UUID:
    return uuid5(DEMO_NAMESPACE, key)


def utcnow() -> datetime:
    return datetime.now(UTC)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def require_password(name: str, fallback_name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name} is required. Do not commit demo passwords.")
    if len(value) < 12:
        raise SystemExit(f"{name} must contain at least 12 characters.")
    if value.lower() in {"password", "changeme", "replace-me", "demo-password"}:
        raise SystemExit(f"{name} is too easy to guess.")
    if value == os.environ.get(fallback_name, ""):
        raise SystemExit(f"{name} and {fallback_name} must be different.")
    return value


async def table_count(session: AsyncSession, model: type) -> int:
    from sqlalchemy import func

    return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def ensure_head(session: AsyncSession) -> None:
    revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
    if revision != EXPECTED_ALEMBIC_HEAD:
        raise SystemExit(
            f"Database revision is {revision!r}; expected {EXPECTED_ALEMBIC_HEAD!r}. "
            "Run `uv run alembic upgrade head` first."
        )


async def reset_demo_rows(session: AsyncSession) -> None:
    expected_usernames = set(DEMO_USERNAMES)
    existing_users = list(
        (await session.scalars(select(User).where(User.username.in_(expected_usernames)))).all()
    )
    for user in existing_users:
        expected_id = DEMO_IDS[user.username.replace("demo_", "", 1)]
        if user.id != expected_id:
            raise SystemExit(f"Refusing to replace non-demo user {user.username!r}.")
    existing_book = await session.scalar(
        select(Wordbook).where(Wordbook.id == DEMO_IDS["wordbook"])
    )
    if existing_book is not None and existing_book.name != DEMO_BOOK_NAME:
        raise SystemExit("Refusing to replace a non-demo wordbook with the demo ID.")
    if existing_book is not None:
        await session.execute(delete(Wordbook).where(Wordbook.id == DEMO_IDS["wordbook"]))
    if existing_users:
        await session.execute(delete(User).where(User.id.in_([u.id for u in existing_users])))
    await session.flush()


def add_user(
    session: AsyncSession,
    key: str,
    username: str,
    display_name: str,
    role: str,
    password: str,
    *,
    department: str,
    group: str,
    target: str,
    new_words: int,
    minutes: int,
) -> User:
    user = User(
        id=DEMO_IDS[key],
        username=username,
        username_normalized=username.lower(),
        display_name=display_name,
        role=role,
        status="active",
        password_hash=hash_password(password),
        must_change_password=False,
        password_changed_at=utcnow(),
        profile=UserProfile(
            department=department,
            learning_group=group,
            target_exam=target,
            exam_date=date.today() + timedelta(days=90),
            daily_new_words=new_words,
            daily_study_minutes=minutes,
            timezone="Asia/Shanghai",
            onboarding_completed=True,
            notification_preferences={
                "categories": {
                    "due_review": True,
                    "today_incomplete": True,
                    "streak_risk": True,
                    "ai_completed": True,
                    "ai_failed": True,
                    "plan_adjusted": True,
                    "ai_action": True,
                },
                "dnd_start": "22:00",
                "dnd_end": "07:00",
                "daily_limit": 8,
            },
        ),
    )
    session.add(user)
    return user


async def add_wordbook(session: AsyncSession, admin: User) -> tuple[Wordbook, list[WordbookEntry]]:
    book = Wordbook(
        id=DEMO_IDS["wordbook"],
        visibility="organization",
        status="ready",
        name=DEMO_BOOK_NAME,
        description=(
            "Synthetic English learning sample for the competition demo. "
            "No real member or private data."
        ),
        created_by=admin.id,
        version="2026.10-demo.1",
        book_metadata={"source_filename": "synthetic-demo.csv", "format": "csv", "demo": True},
    )
    session.add(book)
    await session.flush()
    entries: list[WordbookEntry] = []
    for index, (headword, definition_zh, definition_en, example_en) in enumerate(WORDS):
        entry = WordbookEntry(
            id=demo_id(f"word:{headword}"),
            wordbook_id=book.id,
            headword=headword,
            normalized_headword=headword,
            phonetic=f"/{headword[:3]}.../",
            sequence=index,
        )
        session.add(entry)
        await session.flush()
        definition = WordbookDefinition(
            id=demo_id(f"definition:{headword}"),
            entry_id=entry.id,
            part_of_speech="n." if index < 8 else "v.",
            definition_en=definition_en,
            definition_zh=definition_zh,
            sequence=0,
        )
        session.add(definition)
        await session.flush()
        session.add(
            WordbookExample(
                id=demo_id(f"example:{headword}"),
                definition_id=definition.id,
                example_en=example_en,
                example_zh=f"示例：{definition_zh}。",
                sequence=0,
            )
        )
        entries.append(entry)
    return book, entries


def add_memory_state(
    session: AsyncSession,
    user: User,
    book: Wordbook,
    entry: WordbookEntry,
    *,
    status: str,
    due_at: datetime | None = None,
) -> None:
    session.add(
        UserWordState(
            id=demo_id(f"state:{user.username}:{entry.headword}"),
            user_id=user.id,
            wordbook_id=book.id,
            entry_id=entry.id,
            status=status,
            fsrs_card=new_card_payload(),
            algorithm_version=FSRS_ALGORITHM_VERSION,
            due_at=due_at,
            last_reviewed_at=utcnow() - timedelta(days=2) if status != "new" else None,
            mastered_at=utcnow() - timedelta(days=1) if status == "mastered" else None,
            review_count=2
            if status in {"review", "mastered"}
            else 1
            if status == "learning"
            else 0,
            lapse_count=1 if status == "relearning" else 0,
        )
    )


async def add_daily_plan(
    session: AsyncSession,
    user: User,
    book: Wordbook,
    entries: list[WordbookEntry],
    *,
    status: str,
    new_words: int,
    minutes: int,
) -> DailyPlan:
    today = date.today()
    plan = DailyPlan(
        id=demo_id(f"plan:{user.username}:{today.isoformat()}"),
        user_id=user.id,
        local_date=today,
        wordbook_id=book.id,
        new_word_target=new_words,
        study_minutes_target=minutes,
        generated_at=utcnow(),
        snapshot_time=utcnow(),
        calculation_version="learning-v1",
        status=status,
        new_word_reason="daily_target",
        stats={"new_completed": min(new_words, 6), "due_completed": 3, "active_seconds": 1200},
    )
    session.add(plan)
    await session.flush()
    for position, entry in enumerate(entries[:new_words]):
        session.add(
            DailyPlanWord(
                id=demo_id(f"plan-word:{user.username}:{entry.headword}"),
                plan_id=plan.id,
                entry_id=entry.id,
                reason="new" if position < new_words - 2 else "due",
                position=position,
                is_extra=False,
            )
        )
    return plan


async def add_challenge(
    session: AsyncSession, user: User, book: Wordbook, plan: DailyPlan, entries: list[WordbookEntry]
) -> DailyChallengePlan:
    now = utcnow()
    challenge = DailyChallengePlan(
        id=DEMO_IDS["challenge_plan"],
        user_id=user.id,
        local_date=date.today(),
        daily_plan_id=plan.id,
        wordbook_id=book.id,
        status="ready",
        title="今日航线：20 词进阶",
        summary="复习旧词、学习新词，并用一次 AI 练习完成今日航线。",
        target_minutes=25,
        generation_attempts=1,
        generated_at=now,
        locked_at=now,
        expires_at=now + timedelta(days=1),
    )
    session.add(challenge)
    await session.flush()
    specs = [
        ("review", "REVIEW", "复习昨日航线", "先唤醒已经到期的旧词。", 5, entries[:5]),
        ("new-words", "NEW_WORDS", "学习新词", "完成今天的新词输入。", 8, entries[5:13]),
        ("word-drill", "WORD_DRILL", "词义训练", "用选择题巩固今天的词。", 5, entries[13:17]),
        ("ai-practice", "AI_PRACTICE", "AI 练习", "生成一组真实的填空练习。", 5, entries[17:20]),
        ("boss", "BOSS", "终点挑战", "完成最后的综合挑战。", 2, entries[:5]),
    ]
    for index, (key, node_type, title, description, minutes, node_entries) in enumerate(specs):
        node = ChallengeNode(
            id=demo_id(f"challenge-node:{user.username}:{key}"),
            plan_id=challenge.id,
            client_key=key,
            node_type=node_type,
            order_index=index,
            title=title,
            description=description,
            estimated_minutes=minutes,
            word_entry_ids=[str(entry.id) for entry in node_entries],
            practice_spec={"practice_type": "fill_blank", "count": 3}
            if node_type == "AI_PRACTICE"
            else {},
            optional=False,
        )
        session.add(node)
        await session.flush()
        progress_status = "completed" if index < 2 else "unlocked" if index == 2 else "locked"
        session.add(
            ChallengeNodeProgress(
                id=demo_id(f"challenge-progress:{user.username}:{key}"),
                node_id=node.id,
                plan_id=challenge.id,
                user_id=user.id,
                status=progress_status,
                started_at=now - timedelta(minutes=20) if index < 2 else None,
                completed_at=now - timedelta(minutes=10) if index < 2 else None,
            )
        )
    return challenge


async def add_practice(
    session: AsyncSession, user: User, book: Wordbook, entries: list[WordbookEntry]
) -> None:
    now = utcnow()
    practice = PracticeSession(
        id=DEMO_IDS["practice_session"],
        user_id=user.id,
        practice_type="fill_blank",
        source="whole_book",
        wordbook_id=book.id,
        question_count=3,
        status="submitted",
        generation_number=1,
        current_generation_id=DEMO_IDS["practice_generation"],
        source_context={"target_entry_ids": [str(entry.id) for entry in entries[:3]]},
        request_hash=sha256_text("demo-practice-request"),
        draft_answers={},
        draft_version=1,
        idempotency_key="demo-practice-fill-001",
        score=66.67,
        correct_count=2,
        wrong_count=1,
        submitted_at=now,
    )
    session.add(practice)
    await session.flush()
    generation = PracticeGeneration(
        id=DEMO_IDS["practice_generation"],
        session_id=practice.id,
        generation_number=1,
        status="ready",
        question_count=3,
        ready_at=now,
    )
    session.add(generation)
    await session.flush()
    question_specs = [
        (
            "q1",
            "The ship entered the ____ safely.",
            "The ship entered the harbor safely.",
            "harbor",
        ),
        (
            "q2",
            "A ____ helps travelers find direction.",
            "A compass helps travelers find direction.",
            "compass",
        ),
        (
            "q3",
            "The farmer walked through the fruit ____.",
            "The farmer walked through the fruit orchard.",
            "orchard",
        ),
    ]
    for position, (qid, sentence, explanation, answer) in enumerate(question_specs):
        options = [answer, "lantern", "meadow", "signal"]
        session.add(
            PracticeQuestion(
                id=demo_id(f"practice-question:{qid}"),
                generation_id=generation.id,
                position=position,
                question_type="fill_blank",
                public_payload={
                    "sentence": sentence,
                    "sentence_zh": "请选择最合适的词填空。",
                    "options": [
                        {"id": chr(97 + idx), "text": option, "text_zh": None}
                        for idx, option in enumerate(options)
                    ],
                    "target_entry_ids": [str(entries[position].id)],
                },
                private_payload={"correct_option_id": "a", "explanation": explanation},
                target_entry_ids=[str(entries[position].id)],
            )
        )
    submission_result = {
        "session_id": str(practice.id),
        "submission_id": str(DEMO_IDS["practice_submission"]),
        "status": "completed",
        "score": 66.67,
        "correct_count": 2,
        "wrong_count": 1,
        "total_questions": 3,
        "questions": [
            {
                "question_id": "q1",
                "question_type": "fill_blank",
                "user_answer": "a",
                "is_correct": True,
                "is_mistake": False,
                "score": 100,
                "correct_option_id": "a",
                "correct_option_text": "harbor",
                "explanation": question_specs[0][2],
                "dimensions": [],
                "errors": [],
                "suggestions": [],
            },
            {
                "question_id": "q2",
                "question_type": "fill_blank",
                "user_answer": "a",
                "is_correct": True,
                "is_mistake": False,
                "score": 100,
                "correct_option_id": "a",
                "correct_option_text": "compass",
                "explanation": question_specs[1][2],
                "dimensions": [],
                "errors": [],
                "suggestions": [],
            },
            {
                "question_id": "q3",
                "question_type": "fill_blank",
                "user_answer": "b",
                "is_correct": False,
                "is_mistake": True,
                "score": 0,
                "correct_option_id": "a",
                "correct_option_text": "orchard",
                "explanation": question_specs[2][2],
                "dimensions": [],
                "errors": ["选择错误"],
                "suggestions": ["先判断句子的语义，再排除不合语境的词。"],
            },
        ],
        "mistakes": [],
        "submitted_at": now.isoformat(),
    }
    await session.flush()
    session.add(
        PracticeSubmission(
            id=DEMO_IDS["practice_submission"],
            session_id=practice.id,
            user_id=user.id,
            status="completed",
            answers=[
                {"question_id": "q1", "answer": "a"},
                {"question_id": "q2", "answer": "a"},
                {"question_id": "q3", "answer": "b"},
            ],
            result=submission_result,
            score=66.67,
            correct_count=2,
            total_questions=3,
            wrong_count=1,
            idempotency_key="demo-practice-submit-001",
            request_hash=sha256_text("demo-practice-submit-request"),
            completed_at=now,
        )
    )
    session.add(
        PracticeEvent(
            id=demo_id("practice-event:submitted"),
            user_id=user.id,
            session_id=practice.id,
            event_type="submitted",
            metadata_json={"score": 66.67, "demo": True},
        )
    )
    session.add(
        MistakeFlag(
            id=demo_id("mistake:orchard"),
            user_id=user.id,
            wordbook_id=book.id,
            entry_id=entries[2].id,
            again_count=1,
            last_again_at=now,
            is_priority=True,
        )
    )


async def add_coach(
    session: AsyncSession, user: User, book: Wordbook, entries: list[WordbookEntry]
) -> None:
    now = utcnow()
    conversation = CoachConversation(
        id=DEMO_IDS["coach_conversation"],
        user_id=user.id,
        title="调整今天的学习计划",
        status="active",
        message_count=2,
        last_message_at=now,
    )
    session.add(conversation)
    await session.flush()
    user_message = CoachMessage(
        id=DEMO_IDS["coach_user_message"],
        conversation_id=conversation.id,
        user_id=user.id,
        role="user",
        content="我今天只有 25 分钟，想优先复习港口和方向类词汇。",
        status="completed",
        sequence=0,
        idempotency_key="demo-coach-user-001",
        completed_at=now,
    )
    assistant_message = CoachMessage(
        id=DEMO_IDS["coach_assistant_message"],
        conversation_id=conversation.id,
        user_id=user.id,
        role="assistant",
        content=(
            "可以。我会把今天的新词目标调整为 8 个、学习时长调整为 25 分钟，"
            "并把 harbor 和 compass 放进复习重点。你可以在 24 小时内撤销这次调整。"
        ),
        status="completed",
        sequence=1,
        completed_at=now,
    )
    session.add_all([user_message, assistant_message])
    await session.flush()
    for sequence, (event_type, payload) in enumerate(
        [
            ("message.delta", {"text": assistant_message.content}),
            (
                "action.applied",
                {
                    "action_type": "adjust_daily_plan",
                    "summary": "将今日目标调整为 8 个新词 / 25 分钟",
                },
            ),
            ("usage", {"coach_messages": 1}),
            ("done", {}),
        ]
    ):
        session.add(
            CoachStreamEvent(
                id=demo_id(f"coach-stream:{sequence}"),
                message_id=assistant_message.id,
                sequence=sequence,
                event_type=event_type,
                data=payload,
            )
        )
    session.add(
        CoachActionReceipt(
            id=demo_id("coach-receipt:001"),
            user_id=user.id,
            conversation_id=conversation.id,
            message_id=assistant_message.id,
            action_index=0,
            action_type="adjust_daily_plan",
            parameters={"new_words": 8, "study_minutes": 25},
            before_state={"new_words": 12, "study_minutes": 30},
            after_state={"new_words": 8, "study_minutes": 25},
            summary="将今日目标调整为 8 个新词 / 25 分钟",
            status="applied",
            expires_at=now + timedelta(hours=24),
        )
    )
    session.add(
        CoachContextSnapshot(
            id=demo_id("coach-context:001"),
            conversation_id=conversation.id,
            user_id=user.id,
            context={
                "page_route": "/overview",
                "entity_ids": {"wordbook_id": str(book.id)},
                "selected_options": {"review_focus": ["harbor", "compass"]},
                "draft": {},
                "recent_events": ["daily_plan"],
            },
            expires_at=now + timedelta(hours=24),
        )
    )


def add_notifications(session: AsyncSession, user: User, book: Wordbook) -> None:
    now = utcnow()
    specs = [
        ("due_review", "今日有 5 个到期复习词", "先完成旧词复习，再开始新词。", "sent", True),
        (
            "ai_completed",
            "AI 练习已完成",
            "今日填空练习得分 66.67，错题已进入复习。",
            "sent",
            False,
        ),
        (
            "plan_adjusted",
            "学习计划已调整",
            "AI 教练已将今日目标调整为 8 个新词 / 25 分钟。",
            "sent",
            False,
        ),
    ]
    for index, (category, title, body, status, read) in enumerate(specs):
        session.add(
            Notification(
                id=demo_id(f"notification:{index}"),
                user_id=user.id,
                category=category,
                title=title,
                body=body,
                status=status,
                dedupe_key=f"demo-{category}-{index}",
                business_ref_type="demo",
                business_ref_id=book.id,
                notification_metadata={"demo": True},
                scheduled_at=now - timedelta(minutes=10 - index),
                sent_at=now - timedelta(minutes=10 - index),
                read_at=now - timedelta(minutes=5) if read else None,
                expires_at=now + timedelta(days=7),
            )
        )


async def seed(
    session: AsyncSession, admin_password: str, member_password: str
) -> dict[str, object]:
    await ensure_head(session)
    await reset_demo_rows(session)
    admin = add_user(
        session,
        "admin",
        "demo_admin",
        "Demo Administrator",
        "admin",
        admin_password,
        department="Demo Academy",
        group="Pilot A",
        target="CET6",
        new_words=10,
        minutes=30,
    )
    member = add_user(
        session,
        "member",
        "demo_member",
        "Demo Member",
        "member",
        member_password,
        department="Demo Academy",
        group="Pilot A",
        target="CET4",
        new_words=8,
        minutes=25,
    )
    member2 = add_user(
        session,
        "member2",
        "demo_member2",
        "Demo Learner B",
        "member",
        member_password,
        department="Demo Academy",
        group="Pilot A",
        target="IELTS",
        new_words=10,
        minutes=30,
    )
    member3 = add_user(
        session,
        "member3",
        "demo_member3",
        "Demo Learner C",
        "member",
        member_password,
        department="Demo Academy",
        group="Pilot A",
        target="TOEFL",
        new_words=12,
        minutes=35,
    )
    await session.flush()
    book, entries = await add_wordbook(session, admin)
    for user in (member, member2, member3):
        session.add(WordbookActivation(user_id=user.id, wordbook_id=book.id))
        session.add(
            MemoryConfig(
                user_id=user.id,
                flashcard_enabled=True,
                choice_enabled=True,
                spelling_enabled=True,
                preferences={"demo": True},
            )
        )
    for index, entry in enumerate(entries):
        if index < 5:
            add_memory_state(
                session, member, book, entry, status="review", due_at=utcnow() - timedelta(hours=1)
            )
        elif index < 10:
            add_memory_state(
                session,
                member,
                book,
                entry,
                status="learning",
                due_at=utcnow() + timedelta(hours=2),
            )
        elif index < 15:
            add_memory_state(session, member, book, entry, status="new")
        else:
            add_memory_state(
                session, member, book, entry, status="mastered", due_at=utcnow() + timedelta(days=5)
            )
        add_memory_state(
            session,
            member2,
            book,
            entry,
            status="review" if index < 8 else "new",
            due_at=utcnow() - timedelta(hours=2) if index < 8 else None,
        )
        add_memory_state(session, member3, book, entry, status="new")
    plan = await add_daily_plan(
        session, member, book, entries, status="in_progress", new_words=8, minutes=25
    )
    await add_daily_plan(
        session, member2, book, entries, status="completed", new_words=10, minutes=30
    )
    await add_daily_plan(
        session, member3, book, entries, status="not_started", new_words=12, minutes=35
    )
    await add_challenge(session, member, book, plan, entries)
    await add_practice(session, member, book, entries)
    await add_coach(session, member, book, entries)
    add_notifications(session, member, book)
    for user, base in ((member, 1800), (member2, 2100), (member3, 900)):
        for offset in range(4):
            session.add(
                DailyActivity(
                    user_id=user.id,
                    local_date=date.today() - timedelta(days=offset),
                    active_seconds=max(0, base - offset * 180),
                    heartbeat_count=12 - offset,
                    last_heartbeat_at=utcnow() - timedelta(days=offset),
                )
            )
    await session.commit()
    counts = {
        "users": len(DEMO_USERNAMES),
        "wordbook_entries": len(entries),
        "memory_states": 60,
        "daily_plans": 3,
        "practice_records": 1,
        "coach_conversations": 1,
        "challenge_nodes": 5,
        "notifications": 3,
    }
    return {
        "database_revision": EXPECTED_ALEMBIC_HEAD,
        "wordbook_id": str(book.id),
        "admin_username": "demo_admin",
        "member_username": "demo_member",
        "member2_username": "demo_member2",
        "member3_username": "demo_member3",
        "counts": counts,
        "password_source": "environment only; not printed",
        "demo_marker": "synthetic competition dataset",
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed synthetic competition demo data.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the demo rows. Without this flag only print the plan.",
    )
    args = parser.parse_args()
    if not args.apply:
        print(
            json.dumps(
                {
                    "mode": "dry-run",
                    "requires": [
                        "DEMO_SEED_CONFIRM=YES",
                        "DEMO_ADMIN_PASSWORD",
                        "DEMO_MEMBER_PASSWORD",
                    ],
                    "wordbook": DEMO_BOOK_NAME,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if os.environ.get("DEMO_SEED_CONFIRM") != "YES":
        raise SystemExit(
            "Set DEMO_SEED_CONFIRM=YES to acknowledge that this replaces only "
            "the synthetic demo dataset."
        )
    admin_password = require_password("DEMO_ADMIN_PASSWORD", "DEMO_MEMBER_PASSWORD")
    member_password = require_password("DEMO_MEMBER_PASSWORD", "DEMO_ADMIN_PASSWORD")
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("DATABASE_URL is required.")
    engine = create_engine(database_url, pool_size=2, max_overflow=0)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            summary = await seed(session, admin_password, member_password)
            print(json.dumps({"status": "PASS", **summary}, ensure_ascii=False, indent=2))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
