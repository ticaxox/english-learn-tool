"""Shared helpers for the learning and memory API tests."""

from __future__ import annotations

from uuid import UUID, uuid4

import httpx
from sqlalchemy import select

from app.models.wordbooks import (
    Wordbook,
    WordbookActivation,
    WordbookDefinition,
    WordbookEntry,
)

LOGIN_PATH = "/api/v1/auth/login"
PROFILE_PATH = "/api/v1/users/me/profile"
TODAY_PATH = "/api/v1/learning/today"
ENSURE_PATH = "/api/v1/learning/daily-plan/ensure"
HEARTBEAT_PATH = "/api/v1/learning/heartbeat"
STATS_PATH = "/api/v1/learning/stats"
EVENTS_PATH = "/api/v1/learning/events"
MEMORY_CONFIG_PATH = "/api/v1/memory/config"
SESSIONS_PATH = "/api/v1/memory/sessions"
MISTAKES_PATH = "/api/v1/memory/mistakes"
WORDBOOKS_PATH = "/api/v1/wordbooks"

TEST_PASSWORD = "Valid-Test-Pass-123!"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def login(client: httpx.AsyncClient, username: str) -> dict[str, str]:
    response = await client.post(
        LOGIN_PATH,
        json={"username": username, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return bearer(response.json()["access_token"])


async def seed_wordbook(
    app,
    *,
    owner_id,
    visibility: str = "private",
    entries: int = 8,
    prefix: str = "word",
) -> str:
    async with app.state.session_factory() as session:
        book = Wordbook(
            visibility=visibility,
            status="ready",
            name=f"Learning book {uuid4().hex[:6]}",
            owner_id=owner_id if visibility == "private" else None,
            created_by=owner_id,
            book_metadata={"source_filename": "seed.csv", "format": "csv"},
        )
        session.add(book)
        await session.flush()
        for index in range(entries):
            entry = WordbookEntry(
                wordbook_id=book.id,
                headword=f"{prefix}{index:02d}",
                normalized_headword=f"{prefix}{index:02d}",
                phonetic=f"wɜːd{index}",
                sequence=index,
            )
            session.add(entry)
            await session.flush()
            session.add(
                WordbookDefinition(
                    entry_id=entry.id,
                    part_of_speech="n.",
                    definition_en=f"definition {index}",
                    definition_zh=f"释义{index}",
                    sequence=0,
                )
            )
        await session.commit()
        return str(book.id)


async def activate(app, *, user_id, wordbook_id: str | UUID) -> None:
    async with app.state.session_factory() as session:
        session.add(WordbookActivation(user_id=user_id, wordbook_id=UUID(str(wordbook_id))))
        await session.commit()


async def entry_facts(app, entry_id: str | UUID) -> dict[str, str | None]:
    """Return plain values so a closed session cannot expire an ORM object."""

    async with app.state.session_factory() as session:
        entry = await session.scalar(
            select(WordbookEntry).where(WordbookEntry.id == UUID(str(entry_id)))
        )
        assert entry is not None
        definition = await session.scalar(
            select(WordbookDefinition).where(
                WordbookDefinition.entry_id == entry.id,
                WordbookDefinition.sequence == 0,
            )
        )
        return {
            "headword": entry.headword,
            "entry_id": str(entry.id),
            "definition_zh": definition.definition_zh if definition else None,
        }


async def start_module_session(client: httpx.AsyncClient, headers: dict[str, str], module: str):
    response = await client.post(SESSIONS_PATH, headers=headers, json={"module": module})
    assert response.status_code == 201, response.text
    return response.json()


def session_headers(headers: dict[str, str], key: str) -> dict[str, str]:
    return {**headers, "Idempotency-Key": key}
