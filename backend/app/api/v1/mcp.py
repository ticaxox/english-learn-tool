"""Model Context Protocol server over Streamable HTTP.

Transport: a single POST endpoint that accepts JSON-RPC messages and answers with
``application/json``. Stateful sessions and server-initiated SSE streams are not
used, which the protocol permits for stateless servers.

Authentication: ``Authorization: Bearer <personal access token>``. The same tool
registry is used in-process by the coach, so both paths share one definition.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.session import get_db_session
from app.services.coach_tools import call_coach_tool, tool_list
from app.services.personal_tokens import authenticate_personal_token

router = APIRouter(prefix="/mcp", tags=["mcp"])

SUPPORTED_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
LATEST_VERSION = SUPPORTED_VERSIONS[0]

_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603
_UNAUTHORIZED = -32001


def _error(identifier: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": identifier, "error": {"code": code, "message": message}}


def _result(identifier: Any, value: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": identifier, "result": value}


async def _authenticate(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    authorization: Annotated[str | None, Header()] = None,
):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AppError(
            status_code=401,
            code="MCP_UNAUTHORIZED",
            message="A personal access token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await authenticate_personal_token(session, authorization.split(" ", 1)[1].strip())
    if user is None:
        raise AppError(
            status_code=401,
            code="MCP_UNAUTHORIZED",
            message="The personal access token is invalid or revoked.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def _handle(
    message: Any,
    request: Request,
    session: AsyncSession,
    user,
) -> dict[str, Any] | None:
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _error(None, _INVALID_REQUEST, "Invalid JSON-RPC message.")
    method = message.get("method")
    identifier = message.get("id")
    params = message.get("params") if isinstance(message.get("params"), dict) else {}

    if not isinstance(method, str):
        return _error(identifier, _INVALID_REQUEST, "Missing method.")

    if method == "initialize":
        requested = params.get("protocolVersion")
        version = requested if requested in SUPPORTED_VERSIONS else LATEST_VERSION
        return _result(
            identifier,
            {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": "english-learn-tool",
                    "version": request.app.state.settings.app_version,
                },
            },
        )
    if method in {"notifications/initialized", "notifications/cancelled"}:
        return None
    if method == "ping":
        return _result(identifier, {})
    if method == "tools/list":
        return _result(identifier, {"tools": tool_list()})
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments")
        if not isinstance(name, str):
            return _error(identifier, _INVALID_PARAMS, "Tool name is required.")
        pool = getattr(request.app.state, "arq", None)
        if pool is None:
            return _error(identifier, _INTERNAL_ERROR, "The task queue is unavailable.")
        try:
            outcome = await call_coach_tool(
                session,
                pool,
                user,
                request.app.state.settings,
                name,
                arguments if isinstance(arguments, dict) else None,
            )
        except AppError as exc:
            detail = json.dumps({"code": exc.code, "message": exc.message}, ensure_ascii=False)
            return _result(
                identifier,
                {"content": [{"type": "text", "text": detail}], "isError": True},
            )
        except Exception:  # noqa: BLE001 - a tool crash must not kill the session
            return _result(
                identifier,
                {
                    "content": [{"type": "text", "text": "工具执行失败，请稍后重试。"}],
                    "isError": True,
                },
            )
        return _result(
            identifier,
            {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(outcome, ensure_ascii=False, default=str),
                    }
                ],
                "isError": False,
            },
        )
    return _error(identifier, _METHOD_NOT_FOUND, f"Unknown method: {method}")


@router.post("", include_in_schema=False)
async def mcp_endpoint(
    request: Request,
    user: Annotated[object, Depends(_authenticate)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    try:
        payload = await request.json()
    except ValueError:
        return JSONResponse(_error(None, -32700, "Parse error."), status_code=400)

    if isinstance(payload, list):
        replies = [
            reply
            for reply in [await _handle(item, request, session, user) for item in payload]
            if reply is not None
        ]
        if not replies:
            return Response(status_code=status.HTTP_202_ACCEPTED)
        return JSONResponse(replies)

    reply = await _handle(payload, request, session, user)
    if reply is None:
        return Response(status_code=status.HTTP_202_ACCEPTED)
    return JSONResponse(reply)


@router.get("", include_in_schema=False)
async def mcp_stream_not_supported() -> Response:
    # Stateless server: no server-initiated stream is offered.
    return Response(status_code=status.HTTP_405_METHOD_NOT_ALLOWED, headers={"Allow": "POST"})
