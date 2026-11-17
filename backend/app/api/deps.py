from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import decode_access_token
from app.db.session import get_db_session
from app.services.auth import AuthContext, get_authenticated_context

bearer_scheme = HTTPBearer(auto_error=False, bearerFormat="JWT")


async def get_auth_context(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AuthContext:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError(
            status_code=401,
            code="UNAUTHORIZED",
            message="Authentication is required.",
        )
    claims = decode_access_token(credentials.credentials, request.app.state.settings)
    context = await get_authenticated_context(session, claims=claims)
    request.state.auth = context
    return context


async def get_completed_auth_context(
    context: Annotated[AuthContext, Depends(get_auth_context)],
) -> AuthContext:
    if context.user.must_change_password:
        raise AppError(
            status_code=403,
            code="AUTH_PASSWORD_CHANGE_REQUIRED",
            message="Change the password before accessing this resource.",
        )
    return context


def user_self(context: AuthContext):
    from app.schemas.auth import UserSelf

    profile = context.user.profile
    return UserSelf(
        id=context.user.id,
        username=context.user.username,
        display_name=context.user.display_name,
        role=context.user.role,
        status=context.user.status,
        must_change_password=context.user.must_change_password,
        avatar=profile.avatar if profile else "pumpkin",
        department=profile.department if profile else None,
        learning_group=profile.learning_group if profile else None,
        last_login_at=context.user.last_login_at,
        created_at=context.user.created_at,
        updated_at=context.user.updated_at,
    )
