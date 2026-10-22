from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_completed_auth_context
from app.core.config import Settings
from app.db.session import get_db_session
from app.schemas.common import ErrorResponse
from app.schemas.imports import (
    ImportAcceptedResponse,
    ImportConfirmRequest,
    ImportPreviewResponse,
    ImportStatusResponse,
)
from app.schemas.users import (
    AdminUserCreate,
    AdminUserPatch,
    PasswordResetResponse,
    UserCreateResponse,
    UserDetail,
    UserListResponse,
    UserSummary,
)
from app.services.auth import AuthContext
from app.services.imports import confirm_import, create_import_preview, get_import_status
from app.services.users import (
    create_user,
    delete_user,
    get_user_detail,
    list_users,
    reset_password,
    update_user,
)

router = APIRouter(prefix="/admin", tags=["admin"])

_ADMIN_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Authentication is required."},
    403: {"model": ErrorResponse, "description": "Administrator permission is required."},
}


@router.get(
    "/users",
    response_model=UserListResponse,
    responses={**_ADMIN_RESPONSES, 422: {"model": ErrorResponse}},
    summary="List members with cursor pagination and filters",
)
async def list_users_endpoint(
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    role: Annotated[Literal["admin", "member"] | None, Query()] = None,
    status_filter: Annotated[Literal["active", "disabled"] | None, Query(alias="status")] = None,
) -> UserListResponse:
    return await list_users(
        session,
        context.user,
        limit=limit,
        cursor=cursor,
        search=search,
        role=role,
        status=status_filter,
    )


@router.post(
    "/users",
    response_model=UserCreateResponse,
    status_code=status.HTTP_201_CREATED,
    responses={**_ADMIN_RESPONSES, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    summary="Create a member or administrator account",
)
async def create_user_endpoint(
    payload: AdminUserCreate,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserCreateResponse:
    return await create_user(session, context.user, payload=payload)


@router.post(
    "/users/import/preview",
    response_model=ImportPreviewResponse,
    responses={
        **_ADMIN_RESPONSES,
        413: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
    summary="Validate a UTF-8 member CSV and persist a tamper-evident preview",
)
async def preview_import_endpoint(
    request: Request,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    file: Annotated[UploadFile, File(description="UTF-8 CSV with member rows")],
) -> ImportPreviewResponse:
    settings: Settings = request.app.state.settings
    return await create_import_preview(
        session,
        context.user,
        settings=settings,
        upload=file,
    )


@router.post(
    "/users/import",
    response_model=ImportAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        **_ADMIN_RESPONSES,
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        410: {"model": ErrorResponse},
    },
    summary="Atomically create all members from a confirmed preview",
)
async def confirm_import_endpoint(
    payload: ImportConfirmRequest,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ImportAcceptedResponse:
    return await confirm_import(session, context.user, payload=payload)


@router.get(
    "/users/import/{import_id}",
    response_model=ImportStatusResponse,
    responses={**_ADMIN_RESPONSES, 404: {"model": ErrorResponse}},
    summary="Poll the real persisted status of a member import",
)
async def import_status_endpoint(
    import_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ImportStatusResponse:
    return await get_import_status(session, context.user, import_id)


@router.get(
    "/users/{user_id}",
    response_model=UserDetail,
    responses={**_ADMIN_RESPONSES, 404: {"model": ErrorResponse}},
    summary="Read a member account, profile, and privacy-safe aggregates",
)
async def user_detail_endpoint(
    user_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserDetail:
    return await get_user_detail(session, context.user, user_id)


@router.patch(
    "/users/{user_id}",
    response_model=UserSummary,
    responses={**_ADMIN_RESPONSES, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    summary="Update status, role, display name, or profile fields",
)
async def update_user_endpoint(
    user_id: UUID,
    payload: AdminUserPatch,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserSummary:
    return await update_user(session, context.user, user_id, payload)


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        **_ADMIN_RESPONSES,
        404: {"model": ErrorResponse},
        409: {
            "model": ErrorResponse,
            "description": (
                "SELF_DELETE_FORBIDDEN when deleting the current account; "
                "LAST_ADMIN_PROTECTED when removing the last active administrator."
            ),
        },
    },
    summary="Hard-delete an account after frontend confirmation",
)
async def delete_user_endpoint(
    user_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    await delete_user(session, context.user, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/users/{user_id}/reset-password",
    response_model=PasswordResetResponse,
    responses={**_ADMIN_RESPONSES, 404: {"model": ErrorResponse}},
    summary="Reset a password once and revoke all refresh sessions",
)
async def reset_password_endpoint(
    user_id: UUID,
    context: Annotated[AuthContext, Depends(get_completed_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PasswordResetResponse:
    return await reset_password(session, context.user, user_id)
