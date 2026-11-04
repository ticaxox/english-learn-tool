from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Header, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_auth_context, user_self
from app.core.config import Settings
from app.core.security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, REFRESH_COOKIE_NAME
from app.db.session import get_db_session
from app.models.identity import User
from app.schemas.auth import (
    AuthSessionResponse,
    ChangePasswordRequest,
    LoginRequest,
    UsernameChangeRequest,
    UserSelf,
)
from app.schemas.common import ErrorResponse
from app.services.auth import (
    AuthContext,
    IssuedSession,
    change_password,
    change_username,
    login,
    logout,
    refresh_session,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_UNAUTHORIZED_RESPONSE = {
    401: {"model": ErrorResponse, "description": "Authentication failed or session expired."}
}
_FORBIDDEN_RESPONSE = {
    403: {"model": ErrorResponse, "description": "Origin, CSRF, or account policy rejected."}
}
_THROTTLED_RESPONSE = {429: {"model": ErrorResponse, "description": "Authentication throttled."}}
_COOKIE_RESPONSE = {
    200: {
        "description": (
            "Sets an HttpOnly refresh_token cookie with Path=/api/v1/auth/refresh and a "
            "readable csrf_token cookie with Path=/. Both use SameSite=Lax and Secure in "
            "production. Echo the csrf_token value in X-CSRF-Token on refresh and logout."
        ),
        "headers": {
            "Set-Cookie": {
                "description": (
                    "One HttpOnly refresh cookie plus one non-HttpOnly CSRF cookie; "
                    "the SPA reads the latter from document.cookie."
                ),
                "schema": {"type": "string"},
            }
        },
    }
}


def _user_response(user: User) -> UserSelf:
    profile = user.profile
    return UserSelf(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        status=user.status,
        must_change_password=user.must_change_password,
        department=profile.department if profile else None,
        learning_group=profile.learning_group if profile else None,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def _set_session_cookies(response: Response, settings: Settings, issued: IssuedSession) -> None:
    max_age = settings.refresh_token_days * 86400
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=issued.refresh_token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=settings.refresh_cookie_path,
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=issued.csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path=settings.csrf_cookie_path,
    )


def _clear_session_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=settings.refresh_cookie_path,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(
        key=CSRF_COOKIE_NAME,
        path=settings.csrf_cookie_path,
        secure=settings.cookie_secure,
        httponly=False,
        samesite="lax",
    )


@router.post(
    "/login",
    response_model=AuthSessionResponse,
    responses={
        **_UNAUTHORIZED_RESPONSE,
        **_THROTTLED_RESPONSE,
        **_COOKIE_RESPONSE,
    },
    summary="Login and create a rotating refresh session",
)
async def login_endpoint(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AuthSessionResponse:
    settings: Settings = request.app.state.settings
    redis: Redis = request.app.state.redis
    issued = await login(
        session,
        redis,
        settings,
        request=request,
        username=payload.username,
        password=payload.password,
    )
    _set_session_cookies(response, settings, issued)
    return AuthSessionResponse(
        access_token=issued.access_token,
        expires_in=issued.expires_in,
        csrf_token=issued.csrf_token,
        user=_user_response(issued.user),
    )


@router.post(
    "/refresh",
    response_model=AuthSessionResponse,
    responses={
        **_UNAUTHORIZED_RESPONSE,
        **_FORBIDDEN_RESPONSE,
        **_THROTTLED_RESPONSE,
        **_COOKIE_RESPONSE,
    },
    summary="Rotate the refresh token and issue a new access token",
)
async def refresh_endpoint(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    refresh_cookie: Annotated[str | None, Cookie(alias=REFRESH_COOKIE_NAME)] = None,
    csrf_cookie: Annotated[str | None, Cookie(alias=CSRF_COOKIE_NAME)] = None,
    csrf_header: Annotated[str | None, Header(alias=CSRF_HEADER_NAME)] = None,
) -> AuthSessionResponse:
    settings: Settings = request.app.state.settings
    issued = await refresh_session(
        session,
        settings,
        request=request,
        refresh_token=refresh_cookie,
        csrf_header=csrf_header,
        csrf_cookie=csrf_cookie,
    )
    _set_session_cookies(response, settings, issued)
    return AuthSessionResponse(
        access_token=issued.access_token,
        expires_in=issued.expires_in,
        csrf_token=issued.csrf_token,
        user=_user_response(issued.user),
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**_UNAUTHORIZED_RESPONSE, **_FORBIDDEN_RESPONSE},
    summary="Revoke the current session and clear cookies",
)
async def logout_endpoint(
    request: Request,
    response: Response,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    csrf_cookie: Annotated[str | None, Cookie(alias=CSRF_COOKIE_NAME)] = None,
    csrf_header: Annotated[str | None, Header(alias=CSRF_HEADER_NAME)] = None,
) -> Response:
    settings: Settings = request.app.state.settings
    await logout(
        session,
        settings,
        request=request,
        context=context,
        csrf_header=csrf_header,
        csrf_cookie=csrf_cookie,
    )
    _clear_session_cookies(response, settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**_UNAUTHORIZED_RESPONSE, 422: {"model": ErrorResponse}},
    summary="Change the current password and revoke all refresh sessions",
)
async def change_password_endpoint(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    await change_password(
        session,
        context=context,
        old_password=payload.old_password,
        new_password=payload.new_password,
    )
    _clear_session_cookies(response, request.app.state.settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.patch(
    "/me",
    response_model=UserSelf,
    responses={
        **_UNAUTHORIZED_RESPONSE,
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
    summary="Change the caller's username after confirming the password",
)
async def change_username_endpoint(
    payload: UsernameChangeRequest,
    context: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserSelf:
    user = await change_username(
        session,
        context=context,
        username=payload.username,
        current_password=payload.current_password,
    )
    return _user_response(user)


@router.get(
    "/me",
    response_model=UserSelf,
    responses={401: {"model": ErrorResponse}},
    summary="Read the current account and password-change status",
)
async def me(
    context: Annotated[AuthContext, Depends(get_auth_context)],
) -> UserSelf:
    return user_self(context)
