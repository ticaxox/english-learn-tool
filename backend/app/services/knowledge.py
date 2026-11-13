"""Reference knowledge with retrieval.

Two kinds of shelf hold documents. A global shelf belongs to the product: the
administrator files exam papers there, one per difficulty, so a CET-4 learner's
coach reads CET-4 material. A personal shelf belongs to one learner, who puts
their own material there and is the only one who can read it.

Retrieval asks a narrower question than it used to: not "every ready chunk",
but "the shelves this learner may read" — the general shelf, the shelf for
their target exam, and their own.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.ai import AiProvider
from app.models.identity import User, UserProfile
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument, KnowledgeFolder
from app.schemas.knowledge import (
    KnowledgeDocumentDetail,
    KnowledgeDocumentResponse,
    KnowledgeDocumentUpdate,
    KnowledgeFolderCreate,
    KnowledgeFolderResponse,
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

# Seeded by the migration: the global shelf that applies to every exam, and
# where every document imported before shelves existed now lives.
GENERAL_FOLDER_ID = UUID("00000000-0000-4000-8000-000000000001")

_QUESTION_SPLIT = re.compile(r"\n\s*(?=\d{1,3}[.、．])")


def _document_response(row: KnowledgeDocument, snippet: str = "") -> KnowledgeDocumentResponse:
    return KnowledgeDocumentResponse(
        id=row.id,
        folder_id=row.folder_id,
        snippet=snippet,
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


def _folder_response(row: KnowledgeFolder, user: User, count: int = 0) -> KnowledgeFolderResponse:
    return KnowledgeFolderResponse(
        id=row.id,
        parent_id=row.parent_id,
        scope=row.scope,
        difficulty=row.difficulty,
        name=row.name,
        document_count=count,
        writable=can_write(user, row),
        is_general=row.id == GENERAL_FOLDER_ID,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def can_read(user: User, folder: KnowledgeFolder) -> bool:
    """Global shelves are the product's; a personal shelf is its owner's."""
    if folder.scope == "global":
        return True
    return folder.owner_id == user.id


def can_write(user: User, folder: KnowledgeFolder) -> bool:
    if folder.scope == "global":
        return user.role == "admin"
    return folder.owner_id == user.id


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
    query = select(AiProvider).where(AiProvider.enabled.is_(True), AiProvider.kind == "embedding")
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


# ---------------------------------------------------------------- folders


async def _folder_or_404(session: AsyncSession, folder_id: UUID) -> KnowledgeFolder:
    folder = await session.get(KnowledgeFolder, folder_id)
    if folder is None:
        raise AppError(
            status_code=404, code="KNOWLEDGE_FOLDER_NOT_FOUND", message="No such folder."
        )
    return folder


async def list_folders(session: AsyncSession, user: User) -> list[KnowledgeFolderResponse]:
    """Every shelf this user may read, with how many documents sit on each."""
    rows = list(
        (
            await session.scalars(
                select(KnowledgeFolder).order_by(
                    KnowledgeFolder.scope.desc(),
                    KnowledgeFolder.difficulty.asc().nullsfirst(),
                    KnowledgeFolder.name.asc(),
                )
            )
        ).all()
    )
    counts = dict(
        (
            await session.execute(
                select(KnowledgeDocument.folder_id, func.count(KnowledgeDocument.id))
                .where(KnowledgeDocument.status != "archived")
                .group_by(KnowledgeDocument.folder_id)
            )
        ).all()
    )
    return [
        _folder_response(row, user, counts.get(row.id, 0)) for row in rows if can_read(user, row)
    ]


async def create_folder(
    session: AsyncSession, user: User, payload: KnowledgeFolderCreate
) -> KnowledgeFolderResponse:
    parent: KnowledgeFolder | None = None
    if payload.parent_id is not None:
        parent = await _folder_or_404(session, payload.parent_id)
        if not can_write(user, parent):
            raise AppError(status_code=403, code="KNOWLEDGE_FORBIDDEN", message="Read-only shelf.")
        # A child is the same kind of shelf as its parent, on the same side of
        # the global/personal line; asking for a different one is a mistake,
        # not an instruction. Only a global shelf can name an exam.
        scope = parent.scope
        owner_id = parent.owner_id
    else:
        scope = payload.scope
        owner_id = None if scope == "global" else user.id
        if scope == "global":
            require_admin(user)

    if scope != "global":
        level = None
    elif payload.difficulty is not None:
        if user.role != "admin":
            raise AppError(
                status_code=403,
                code="KNOWLEDGE_FORBIDDEN",
                message="Administrator permission is required.",
            )
        exists = await session.scalar(
            select(KnowledgeFolder.id).where(
                KnowledgeFolder.scope == "global",
                KnowledgeFolder.difficulty == payload.difficulty,
            )
        )
        if exists is not None:
            raise AppError(
                status_code=409,
                code="KNOWLEDGE_FOLDER_EXISTS",
                message="That difficulty already has a shelf.",
            )
        level = payload.difficulty
    else:
        level = None

    folder = KnowledgeFolder(
        parent_id=parent.id if parent is not None else None,
        scope=scope,
        owner_id=owner_id,
        difficulty=level,
        name=payload.name,
    )
    session.add(folder)
    await session.commit()
    await session.refresh(folder)
    return _folder_response(folder, user, 0)


async def rename_folder(
    session: AsyncSession, user: User, folder_id: UUID, name: str
) -> KnowledgeFolderResponse:
    folder = await _folder_or_404(session, folder_id)
    if not can_write(user, folder):
        raise AppError(status_code=403, code="KNOWLEDGE_FORBIDDEN", message="Not your shelf.")
    folder.name = name
    await session.commit()
    await session.refresh(folder)
    return _folder_response(folder, user, 0)


async def delete_folder(session: AsyncSession, user: User, folder_id: UUID) -> None:
    folder = await _folder_or_404(session, folder_id)
    if not can_write(user, folder):
        raise AppError(status_code=403, code="KNOWLEDGE_FORBIDDEN", message="Not your shelf.")
    # Only the fallback shelf itself is protected. Its children — and every
    # other global folder without a difficulty — are ordinary shelves.
    if folder.id == GENERAL_FOLDER_ID:
        raise AppError(
            status_code=422,
            code="KNOWLEDGE_GENERAL_SHELF",
            message="The general shelf cannot be deleted.",
        )
    # The papers survive the shelf: everything in the subtree moves to the
    # general one rather than disappearing with a folder someone renamed.
    doomed = [folder.id, *await _descendant_ids(session, folder.id)]
    await session.execute(
        KnowledgeDocument.__table__.update()
        .where(KnowledgeDocument.folder_id.in_(doomed))
        .values(folder_id=GENERAL_FOLDER_ID)
    )
    await session.execute(KnowledgeFolder.__table__.delete().where(KnowledgeFolder.id.in_(doomed)))
    await session.commit()


async def _descendant_ids(session: AsyncSession, folder_id: UUID) -> list[UUID]:
    """Every folder under this one, breadth first. Walks in memory: the tree is
    a handful of rows, not a graph worth a recursive CTE."""
    rows = (await session.execute(select(KnowledgeFolder.id, KnowledgeFolder.parent_id))).all()
    children: dict[UUID, list[UUID]] = {}
    for child_id, parent_id in rows:
        if parent_id is not None:
            children.setdefault(parent_id, []).append(child_id)
    found: list[UUID] = []
    queue = list(children.get(folder_id, []))
    while queue:
        current = queue.pop(0)
        found.append(current)
        queue.extend(children.get(current, []))
    return found


# -------------------------------------------------------------- documents


async def _folder_for_import(
    session: AsyncSession, user: User, folder_id: UUID | None
) -> KnowledgeFolder:
    if folder_id is None:
        folder = await session.get(KnowledgeFolder, GENERAL_FOLDER_ID)
        if folder is None:
            raise AppError(
                status_code=500, code="KNOWLEDGE_GENERAL_SHELF_MISSING", message="No general shelf."
            )
        if not can_write(user, folder):
            raise AppError(status_code=403, code="KNOWLEDGE_FORBIDDEN", message="Read-only shelf.")
        return folder
    folder = await _folder_or_404(session, folder_id)
    if not can_write(user, folder):
        raise AppError(status_code=403, code="KNOWLEDGE_FORBIDDEN", message="Read-only shelf.")
    return folder


async def import_document(
    session: AsyncSession,
    settings: Settings,
    user: User,
    payload: KnowledgeImportRequest,
) -> KnowledgeDocumentResponse:
    folder = await _folder_for_import(session, user, payload.folder_id)
    chunks = split_text(payload.content)
    if not chunks:
        raise AppError(status_code=422, code="KNOWLEDGE_EMPTY", message="The document has no text.")
    document = KnowledgeDocument(
        folder_id=folder.id,
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


async def list_documents(
    session: AsyncSession, user: User, folder_id: UUID | None = None
) -> list[KnowledgeDocumentResponse]:
    folder = await _folder_or_404(session, folder_id) if folder_id else None
    if folder is not None and not can_read(user, folder):
        raise AppError(
            status_code=404, code="KNOWLEDGE_FOLDER_NOT_FOUND", message="No such folder."
        )
    query = select(KnowledgeDocument).where(KnowledgeDocument.status != "archived")
    if folder is not None:
        query = query.where(KnowledgeDocument.folder_id == folder.id)
    rows = list((await session.scalars(query.order_by(KnowledgeDocument.created_at.desc()))).all())
    if not rows:
        return []
    # One query for the opening line of each, not one per card.
    snippets = dict(
        (
            await session.execute(
                select(KnowledgeChunk.document_id, KnowledgeChunk.content).where(
                    KnowledgeChunk.document_id.in_([row.id for row in rows]),
                    KnowledgeChunk.ordinal == 0,
                )
            )
        ).all()
    )
    return [
        _document_response(row, " ".join((snippets.get(row.id) or "").split())[:120])
        for row in rows
    ]


async def document_detail(
    session: AsyncSession, user: User, document_id: UUID
) -> KnowledgeDocumentDetail:
    document = await session.get(KnowledgeDocument, document_id)
    if document is None or document.status == "archived":
        raise AppError(status_code=404, code="KNOWLEDGE_NOT_FOUND", message="No such document.")
    if document.folder_id is not None:
        folder = await session.get(KnowledgeFolder, document.folder_id)
        if folder is not None and not can_read(user, folder):
            raise AppError(status_code=404, code="KNOWLEDGE_NOT_FOUND", message="No such document.")
    chunks = list(
        (
            await session.scalars(
                select(KnowledgeChunk.content)
                .where(KnowledgeChunk.document_id == document.id)
                .order_by(KnowledgeChunk.ordinal.asc())
            )
        ).all()
    )
    folder_name = None
    if document.folder_id is not None:
        folder_row = await session.get(KnowledgeFolder, document.folder_id)
        folder_name = folder_row.name if folder_row is not None else None
    base = _document_response(document)
    return KnowledgeDocumentDetail(
        **base.model_dump(), content="\n\n".join(chunks), folders=folder_name
    )


async def update_document(
    session: AsyncSession,
    settings: Settings,
    user: User,
    document_id: UUID,
    payload: KnowledgeDocumentUpdate,
) -> KnowledgeDocumentResponse:
    document = await session.get(KnowledgeDocument, document_id)
    if document is None or document.status == "archived":
        raise AppError(status_code=404, code="KNOWLEDGE_NOT_FOUND", message="No such document.")
    if document.folder_id is not None:
        folder = await session.get(KnowledgeFolder, document.folder_id)
        if folder is not None and not can_write(user, folder):
            raise AppError(status_code=403, code="KNOWLEDGE_FORBIDDEN", message="Read-only shelf.")
    else:
        require_admin(user)
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


async def archive_document(session: AsyncSession, user: User, document_id: UUID) -> None:
    document = await session.get(KnowledgeDocument, document_id)
    if document is None:
        raise AppError(status_code=404, code="KNOWLEDGE_NOT_FOUND", message="No such document.")
    if document.folder_id is not None:
        folder = await session.get(KnowledgeFolder, document.folder_id)
        if folder is not None and not can_write(user, folder):
            raise AppError(status_code=403, code="KNOWLEDGE_FORBIDDEN", message="Read-only shelf.")
    else:
        require_admin(user)
    # Chunks cascade on delete; archive keeps the row for audit.
    document.status = "archived"
    await session.execute(
        KnowledgeChunk.__table__.delete().where(KnowledgeChunk.document_id == document.id)
    )
    document.chunk_count = 0
    await session.commit()


# --------------------------------------------------------------- retrieval


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


async def searchable_folder_ids(session: AsyncSession, user: User) -> list[UUID]:
    """The shelves one learner reads: general, their exam's, and their own.

    Subtrees count: a document under 四级 / 真题 / 2023 belongs to the CET-4
    shelf just as much as one filed directly on it. A document with no shelf
    (imported before shelves existed, or moved off a deleted one) stays
    readable — it is reference material nobody filed.
    """
    target_exam = await session.scalar(
        select(UserProfile.target_exam).where(UserProfile.user_id == user.id)
    )
    rows = (
        await session.execute(
            select(
                KnowledgeFolder.id,
                KnowledgeFolder.parent_id,
                KnowledgeFolder.scope,
                KnowledgeFolder.owner_id,
                KnowledgeFolder.difficulty,
            )
        )
    ).all()

    def readable(row) -> bool:
        if row.scope == "global":
            return row.difficulty is None or (
                target_exam is not None and row.difficulty == target_exam
            )
        return row.owner_id == user.id

    readable_ids = {row.id for row in rows if readable(row)}
    roots = {row.id for row in rows if row.parent_id is None and row.id in readable_ids}
    children: dict[UUID, list[UUID]] = {}
    for row in rows:
        if row.parent_id is not None:
            children.setdefault(row.parent_id, []).append(row.id)

    # Pruning happens per node, not per root: the exam shelves all hang off
    # 学习目标, so a branch is skipped when its own exam is not this learner's.
    found: list[UUID] = []
    queue = list(roots)
    while queue:
        current = queue.pop(0)
        found.append(current)
        queue.extend(child for child in children.get(current, []) if child in readable_ids)
    return [*found, GENERAL_FOLDER_ID]


async def search(
    session: AsyncSession,
    settings: Settings,
    *,
    query: str,
    limit: int = 6,
    min_score: float = 0.12,
    folder_ids: list[UUID] | None = None,
) -> list[RetrievedChunk]:
    filters = [KnowledgeDocument.status == "ready"]
    if folder_ids is not None:
        filters.append(
            or_(
                KnowledgeDocument.folder_id.in_(folder_ids),
                KnowledgeDocument.folder_id.is_(None),
            )
        )
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


async def search_for_user(
    session: AsyncSession, settings: Settings, user: User, query: str, limit: int = 6
) -> list[RetrievedChunk]:
    folder_ids = await searchable_folder_ids(session, user)
    return await search(session, settings, query=query, limit=limit, folder_ids=folder_ids)


async def search_response(
    session: AsyncSession, settings: Settings, user: User, query: str, limit: int = 6
) -> KnowledgeSearchResponse:
    hits = await search_for_user(session, settings, user, query, limit)
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
