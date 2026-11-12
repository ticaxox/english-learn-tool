"""Admin-maintained reference knowledge (exam papers) with retrieval.

Only administrators import documents; learners only search. Chunks are embedded
through the same provider gateway the rest of the product uses, and retrieval
falls back to keyword scoring when no embedding is available, so a missing
embedding model degrades quality instead of breaking the coach.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.ai import AiProvider
from app.models.identity import User
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.schemas.knowledge import (
    KnowledgeDocumentResponse,
    KnowledgeDocumentUpdate,
    KnowledgeImportRequest,
    KnowledgeSearchHit,
    KnowledgeSearchResponse,
)
from app.services.ai_secrets import ApiKeyCipher
from app.services.ai_security import ProviderHttpClient, ProviderRequestError
from app.services.users import require_admin

CHUNK_CHARS = 900
CHUNK_OVERLAP = 120
MAX_CHUNKS = 400
EMBED_BATCH = 16

_QUESTION_SPLIT = re.compile(r"\n\s*(?=\d{1,3}[.、．])")


def _document_response(row: KnowledgeDocument) -> KnowledgeDocumentResponse:
    return KnowledgeDocumentResponse(
        id=row.id,
        source_type=row.source_type,
        title=row.title,
        metadata=row.metadata_json,
        status=row.status,
        chunk_count=row.chunk_count,
        embedding_model=row.embedding_model,
        error_message=row.error_message,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def split_text(text: str) -> list[str]:
    """Question-aware chunking: keep each numbered question with its answer."""
    cleaned = text.replace("\r\n", "\n").strip()
    if not cleaned:
        return []
    blocks = [block.strip() for block in _QUESTION_SPLIT.split(cleaned) if block.strip()]
    chunks: list[str] = []
    current = ""
    for block in blocks:
        if len(block) > CHUNK_CHARS:
            # A single long passage: fall back to sliding windows.
            for start in range(0, len(block), CHUNK_CHARS - CHUNK_OVERLAP):
                piece = block[start : start + CHUNK_CHARS].strip()
                if piece:
                    chunks.append(piece)
            current = ""
            continue
        if len(current) + len(block) + 1 <= CHUNK_CHARS:
            current = f"{current}\n{block}".strip()
        else:
            chunks.append(current)
            current = block
    if current:
        chunks.append(current)
    return chunks[:MAX_CHUNKS]


async def _embedding_provider(
    session: AsyncSession, settings: Settings, owner_id: UUID | None
) -> tuple[str, str, dict[str, str], str] | None:
    """(base_url, api_key, headers, model) of the provider that makes vectors.

    Embeddings are configured on their own provider: the service that writes
    text is often not the service that turns it into vectors. A chat provider
    that still names an embedding_model is the older shape and is used only
    when no dedicated one exists, so an upgrade does not silently stop
    indexing.
    """
    query = select(AiProvider).where(
        AiProvider.enabled.is_(True), AiProvider.kind == "embedding"
    )
    if owner_id is not None:
        query = query.where(AiProvider.owner_id == owner_id)
    provider = await session.scalar(query.order_by(AiProvider.priority.asc()).limit(1))

    model: str | None = None
    if provider is not None:
        model = provider.model_id
    else:
        legacy = select(AiProvider).where(
            AiProvider.enabled.is_(True), AiProvider.embedding_model.is_not(None)
        )
        if owner_id is not None:
            legacy = legacy.where(AiProvider.owner_id == owner_id)
        provider = await session.scalar(legacy.order_by(AiProvider.priority.asc()).limit(1))
        if provider is not None:
            model = provider.embedding_model

    if provider is None or not model:
        return None
    cipher = ApiKeyCipher(settings.secret_encryption_key.get_secret_value())
    try:
        api_key = cipher.decrypt(provider.api_key_ciphertext)
    except ValueError:
        return None
    return provider.base_url, api_key, provider.custom_headers or {}, model


async def _embed(
    session: AsyncSession, settings: Settings, texts: list[str]
) -> tuple[list[list[float]] | None, str | None]:
    resolved = await _embedding_provider(session, settings, None)
    if resolved is None:
        return None, None
    base_url, api_key, headers, model = resolved
    client = ProviderHttpClient(settings)
    vectors: list[list[float]] = []
    try:
        for start in range(0, len(texts), EMBED_BATCH):
            batch = texts[start : start + EMBED_BATCH]
            vectors.extend(
                await client.embeddings(
                    base_url=base_url,
                    api_key=api_key,
                    custom_headers=headers,
                    model_id=model,
                    timeout_seconds=30,
                    texts=batch,
                )
            )
    except ProviderRequestError:
        # Retrieval still works with keywords; a failed embed must not block import.
        return None, model
    return vectors, model


async def import_document(
    session: AsyncSession,
    settings: Settings,
    admin: User,
    payload: KnowledgeImportRequest,
) -> KnowledgeDocumentResponse:
    require_admin(admin)
    chunks = split_text(payload.content)
    if not chunks:
        raise AppError(status_code=422, code="KNOWLEDGE_EMPTY", message="The document has no text.")
    document = KnowledgeDocument(
        source_type=payload.source_type,
        title=payload.title,
        metadata_json=payload.metadata,
        status="indexing",
    )
    session.add(document)
    await session.flush()

    vectors, model = await _embed(session, settings, chunks)
    for ordinal, chunk in enumerate(chunks):
        session.add(
            KnowledgeChunk(
                document_id=document.id,
                ordinal=ordinal,
                content=chunk,
                embedding=vectors[ordinal] if vectors else None,
            )
        )
    document.chunk_count = len(chunks)
    document.embedding_model = model
    document.status = "ready"
    await session.commit()
    await session.refresh(document)
    return _document_response(document)


async def list_documents(session: AsyncSession, admin: User) -> list[KnowledgeDocumentResponse]:
    require_admin(admin)
    rows = list(
        (
            await session.scalars(
                select(KnowledgeDocument)
                .where(KnowledgeDocument.status != "archived")
                .order_by(KnowledgeDocument.created_at.desc())
            )
        ).all()
    )
    return [_document_response(row) for row in rows]


async def update_document(
    session: AsyncSession,
    settings: Settings,
    admin: User,
    document_id: UUID,
    payload: KnowledgeDocumentUpdate,
) -> KnowledgeDocumentResponse:
    require_admin(admin)
    document = await session.get(KnowledgeDocument, document_id)
    if document is None or document.status == "archived":
        raise AppError(status_code=404, code="KNOWLEDGE_NOT_FOUND", message="No such document.")
    if payload.title is not None:
        document.title = payload.title
    if payload.metadata is not None:
        document.metadata_json = payload.metadata
    if payload.published is not None:
        document.status = "ready" if payload.published else "draft"
    if payload.content is not None:
        chunks = split_text(payload.content)
        if not chunks:
            raise AppError(
                status_code=422, code="KNOWLEDGE_EMPTY", message="The document has no text."
            )
        await session.execute(
            KnowledgeChunk.__table__.delete().where(KnowledgeChunk.document_id == document.id)
        )
        vectors, model = await _embed(session, settings, chunks)
        for ordinal, chunk in enumerate(chunks):
            session.add(
                KnowledgeChunk(
                    document_id=document.id,
                    ordinal=ordinal,
                    content=chunk,
                    embedding=vectors[ordinal] if vectors else None,
                )
            )
        document.chunk_count = len(chunks)
        document.embedding_model = model
        document.status = "ready"
    await session.commit()
    await session.refresh(document)
    return _document_response(document)


async def archive_document(session: AsyncSession, admin: User, document_id: UUID) -> None:
    require_admin(admin)
    document = await session.get(KnowledgeDocument, document_id)
    if document is None:
        raise AppError(status_code=404, code="KNOWLEDGE_NOT_FOUND", message="No such document.")
    # Chunks cascade on delete; archive keeps the row for audit.
    document.status = "archived"
    await session.execute(
        KnowledgeChunk.__table__.delete().where(KnowledgeChunk.document_id == document.id)
    )
    document.chunk_count = 0
    await session.commit()


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _keyword_score(query: str, content: str) -> float:
    tokens = {token.lower() for token in re.findall(r"[A-Za-z0-9一-鿿]{2,}", query)}
    if not tokens:
        return 0.0
    lowered = content.lower()
    hits = sum(1 for token in tokens if token in lowered)
    return hits / len(tokens)


@dataclass
class RetrievedChunk:
    chunk_id: UUID
    document_id: UUID
    title: str
    content: str
    score: float


async def search(
    session: AsyncSession,
    settings: Settings,
    *,
    query: str,
    limit: int = 6,
    min_score: float = 0.12,
) -> list[RetrievedChunk]:
    # The corpus is exam papers only, so every ready document is fair game.
    filters = [KnowledgeDocument.status == "ready"]
    rows = (
        await session.execute(
            select(KnowledgeChunk, KnowledgeDocument.title)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .where(*filters)
        )
    ).all()
    if not rows:
        return []
    vectors, _ = await _embed(session, settings, [query]) if query.strip() else (None, None)
    query_vector = vectors[0] if vectors else None

    scored: list[RetrievedChunk] = []
    for chunk, title in rows:
        keyword = _keyword_score(query, chunk.content)
        vector = _cosine(query_vector, chunk.embedding) if query_vector and chunk.embedding else 0.0
        # Either signal alone is enough; both together rank clearly higher.
        score = max(keyword, vector) * 0.6 + min(keyword, vector) * 0.4
        if score >= min_score:
            scored.append(
                RetrievedChunk(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    title=title,
                    content=chunk.content,
                    score=round(score, 4),
                )
            )
    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[:limit]


async def search_response(
    session: AsyncSession, settings: Settings, user: User, query: str, limit: int = 6
) -> KnowledgeSearchResponse:
    hits = await search(session, settings, query=query, limit=limit)
    return KnowledgeSearchResponse(
        items=[
            KnowledgeSearchHit(
                document_id=hit.document_id,
                title=hit.title,
                content=hit.content,
                score=hit.score,
            )
            for hit in hits
        ]
    )
