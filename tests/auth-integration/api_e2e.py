#!/usr/bin/env python3
"""Live AUTH-INT-001 API and persistence checks.

This runner targets only the isolated QA services configured by environment
variables. It never writes to application source code and redacts secrets from
its evidence output.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import string
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import asyncpg
import httpx

API_BASE_URL = os.environ.get("LIVE_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
FRONTEND_BASE_URL = os.environ.get(
    "LIVE_FRONTEND_BASE_URL", "http://127.0.0.1:4173"
).rstrip("/")
ADMIN_USERNAME = os.environ["LIVE_ADMIN_USERNAME"]
ADMIN_PASSWORD = os.environ["LIVE_ADMIN_PASSWORD"]
PG_DSN = os.environ["LIVE_PG_DSN"]
EVIDENCE_DIR = Path(os.environ["EVIDENCE_DIR"]).resolve()
RUN_ID = os.environ.get("LIVE_RUN_ID", f"a30-authint-{uuid4().hex[:12]}")
SENSITIVE_TERMS = (
    "access_token",
    "refresh_token",
    "csrf_token",
    "initial_password",
    "password",
    "answers",
    "draft",
    "coach_message",
    "wordbook_content",
    "coach title",
    "coach body",
)


class CheckFailure(RuntimeError):
    pass


class Evidence:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []
        self.network: list[dict[str, Any]] = []
        self.artifacts: dict[str, Any] = {}
        self.started_at = datetime.now(UTC).isoformat()
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    def check(
        self, name: str, passed: bool, *, request_id: str | None = None, **details: Any
    ) -> None:
        entry = {
            "name": name,
            "status": "PASS" if passed else "FAIL",
            "request_id": request_id,
            "details": details,
        }
        self.checks.append(entry)
        marker = "PASS" if passed else "FAIL"
        print(f"[{marker}] {name} request_id={request_id or '-'}")
        if not passed:
            raise CheckFailure(f"{name}: {details}")

    @staticmethod
    def _body_summary(response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError:
            return {"content_type": response.headers.get("content-type")}
        if not isinstance(body, dict):
            return {"body_type": type(body).__name__}
        summary: dict[str, Any] = {"keys": sorted(body.keys())}
        if "code" in body:
            summary["code"] = body.get("code")
        if body.get("user") is not None and isinstance(body.get("user"), dict):
            summary["user_keys"] = sorted(body["user"].keys())
        if "access_token" in body:
            summary["access_token_present"] = bool(body["access_token"])
        if "csrf_token" in body:
            summary["csrf_token_present"] = bool(body["csrf_token"])
        if "temporary_password" in body:
            summary["temporary_password_present"] = bool(body["temporary_password"])
        if "created_users" in body and isinstance(body["created_users"], list):
            summary["created_users"] = [
                {
                    "username": item.get("username"),
                    "temporary_password_present": bool(item.get("temporary_password")),
                }
                for item in body["created_users"]
            ]
        if "items" in body:
            summary["item_count"] = len(body["items"])
        return summary

    def capture(self, tag: str, response: httpx.Response) -> dict[str, Any]:
        entry = {
            "tag": tag,
            "method": response.request.method,
            "path": response.request.url.path,
            "status": response.status_code,
            "request_id": response.headers.get("X-Request-ID"),
            "set_cookie_names": [
                header.split("=", 1)[0]
                for header in response.headers.get_list("set-cookie")
                if "=" in header
            ],
            "body": self._body_summary(response),
        }
        self.network.append(entry)
        return entry

    def finish(self, error: str | None = None) -> Path:
        result = {
            "run_id": RUN_ID,
            "started_at": self.started_at,
            "finished_at": datetime.now(UTC).isoformat(),
            "api_base_url": API_BASE_URL,
            "frontend_base_url": FRONTEND_BASE_URL,
            "status": "FAIL"
            if error or any(c["status"] == "FAIL" for c in self.checks)
            else "PASS",
            "error": error,
            "checks": self.checks,
            "network": self.network,
            "artifacts": self.artifacts,
        }
        path = EVIDENCE_DIR / "api-e2e-result.json"
        path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return path


EVIDENCE = Evidence()


def generate_password(prefix: str) -> str:
    alphabet = string.ascii_letters + string.digits
    body = "".join(secrets.choice(alphabet) for _ in range(20))
    return f"{prefix}-{body}-9!z"


def request_id(tag: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._:-]", "-", tag)
    value = f"{RUN_ID}-{safe}"
    return value[:128]


def body_code(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    return payload.get("code") if isinstance(payload, dict) else None


def set_cookie_header(response: httpx.Response, name: str) -> str:
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(f"{name}="):
            return header
    raise AssertionError(f"Missing Set-Cookie header for {name}")


def cookie_value(response: httpx.Response, name: str) -> str:
    header = set_cookie_header(response, name)
    return header.split("=", 1)[1].split(";", 1)[0]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def new_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=API_BASE_URL,
        headers={
            "Origin": FRONTEND_BASE_URL,
            "User-Agent": "A30-AUTH-INT-001-Playwright-API/1.0",
        },
        timeout=20,
        follow_redirects=False,
    )


async def call(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    tag: str,
    *,
    expected: int | tuple[int, ...] | None = None,
    **kwargs: Any,
) -> httpx.Response:
    rid = request_id(tag)
    headers = dict(kwargs.pop("headers", {}))
    headers["X-Request-ID"] = rid
    response = await client.request(method, path, headers=headers, **kwargs)
    EVIDENCE.capture(tag, response)
    EVIDENCE.check(
        f"{tag}: response request_id matches",
        response.headers.get("X-Request-ID") == rid,
        request_id=rid,
        response_request_id=response.headers.get("X-Request-ID"),
    )
    if expected is not None:
        allowed = expected if isinstance(expected, tuple) else (expected,)
        EVIDENCE.check(
            f"{tag}: HTTP {expected}",
            response.status_code in allowed,
            request_id=rid,
            status=response.status_code,
            code=body_code(response),
        )
    return response


async def login(
    client: httpx.AsyncClient,
    username: str,
    password: str,
    tag: str,
    *,
    expected: int | tuple[int, ...] = 200,
) -> httpx.Response:
    return await call(
        client,
        "POST",
        "/api/v1/auth/login",
        tag,
        expected=expected,
        json={"username": username, "password": password},
    )


def assert_no_private_fields(value: Any, label: str, rid: str | None = None) -> None:
    text = json.dumps(value, ensure_ascii=False).lower()
    forbidden = (
        "answer",
        "draft",
        "coach_message",
        "coach_title",
        "coach_body",
        "wordbook_content",
    )
    found = [term for term in forbidden if term in text]
    EVIDENCE.check(
        f"{label}: no private learning fields", not found, request_id=rid, found=found
    )


async def discover_admin_and_last_admin_guards(
    admin: httpx.AsyncClient,
) -> tuple[str, dict[str, Any]]:
    global ADMIN_PASSWORD
    ready = await call(admin, "GET", "/health/ready", "health-ready", expected=200)
    ready_body = ready.json()
    EVIDENCE.check(
        "health: database and redis ready",
        ready_body.get("status") == "ready"
        and ready_body.get("components", {}).get("database", {}).get("status") == "ok"
        and ready_body.get("components", {}).get("redis", {}).get("status") == "ok",
        request_id=ready.headers.get("X-Request-ID"),
    )

    openapi = await call(admin, "GET", "/api/v1/openapi.json", "openapi", expected=200)
    paths = openapi.json().get("paths", {})
    required_paths = {
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/change-password",
        "/api/v1/admin/users",
        "/api/v1/admin/users/import/preview",
        "/api/v1/admin/users/import",
        "/api/v1/admin/users/{user_id}/reset-password",
    }
    EVIDENCE.check(
        "openapi: required identity/admin paths exist",
        required_paths.issubset(paths),
        request_id=openapi.headers.get("X-Request-ID"),
        missing=sorted(required_paths - set(paths)),
    )
    schemas = openapi.json().get("components", {}).get("schemas", {})
    privacy_schema_names = {
        "UserSummary",
        "UserDetail",
        "UserAggregates",
        "UserListResponse",
    }
    privacy_schema_text = json.dumps(
        {name: schemas.get(name, {}) for name in privacy_schema_names},
        ensure_ascii=False,
    ).lower()
    EVIDENCE.check(
        "openapi: member/admin schemas exclude private learning content",
        all(
            term not in privacy_schema_text
            for term in ("answer", "draft", "coach_message", "wordbook_content")
        ),
        request_id=openapi.headers.get("X-Request-ID"),
    )

    login_response = await login(admin, ADMIN_USERNAME, ADMIN_PASSWORD, "admin-login")
    session = login_response.json()
    access_token = session["access_token"]
    user = session["user"]
    EVIDENCE.check(
        "admin login: role",
        user.get("role") == "admin",
        request_id=login_response.headers.get("X-Request-ID"),
    )

    if user.get("must_change_password") is True:
        blocked_admin = await call(
            admin,
            "GET",
            "/api/v1/admin/users",
            "bootstrap-admin-blocked-before-change",
            expected=403,
            headers=bearer(access_token),
        )
        EVIDENCE.check(
            "bootstrap admin: admin APIs blocked before forced change",
            body_code(blocked_admin) == "AUTH_PASSWORD_CHANGE_REQUIRED",
            request_id=blocked_admin.headers.get("X-Request-ID"),
            code=body_code(blocked_admin),
        )
        replacement_password = generate_password("BootstrapAdmin")
        changed_admin = await call(
            admin,
            "POST",
            "/api/v1/auth/change-password",
            "bootstrap-admin-change-password",
            expected=204,
            headers=bearer(access_token),
            json={"old_password": ADMIN_PASSWORD, "new_password": replacement_password},
        )
        EVIDENCE.check(
            "bootstrap admin: old access token revoked after change",
            (
                await call(
                    admin,
                    "GET",
                    "/api/v1/auth/me",
                    "bootstrap-admin-old-token-revoked",
                    expected=401,
                    headers=bearer(access_token),
                )
            ).status_code
            == 401,
            request_id=changed_admin.headers.get("X-Request-ID"),
        )
        admin.cookies.clear()
        login_response = await login(
            admin, ADMIN_USERNAME, replacement_password, "bootstrap-admin-relogin"
        )
        session = login_response.json()
        access_token = session["access_token"]
        user = session["user"]
        ADMIN_PASSWORD = replacement_password
        os.environ["LIVE_ADMIN_PASSWORD"] = replacement_password
        password_out = os.environ.get("LIVE_ADMIN_PASSWORD_OUT")
        if password_out:
            Path(password_out).write_text(replacement_password + "\n", encoding="utf-8")
        EVIDENCE.check(
            "bootstrap admin: new password clears forced-change flag",
            user.get("must_change_password") is False,
            request_id=login_response.headers.get("X-Request-ID"),
        )
    else:
        EVIDENCE.check(
            "admin login: password already changed",
            user.get("must_change_password") is False,
            request_id=login_response.headers.get("X-Request-ID"),
        )

    refresh_header = set_cookie_header(login_response, "refresh_token")
    csrf_header = set_cookie_header(login_response, "csrf_token")
    EVIDENCE.check(
        "cookies: refresh is HttpOnly and path-scoped",
        all(
            flag in refresh_header
            for flag in ("HttpOnly", "Path=/api/v1/auth/refresh", "SameSite=lax")
        ),
        request_id=login_response.headers.get("X-Request-ID"),
    )
    EVIDENCE.check(
        "cookies: CSRF is readable and root-scoped",
        "HttpOnly" not in csrf_header and "Path=/" in csrf_header,
        request_id=login_response.headers.get("X-Request-ID"),
    )

    me = await call(
        admin,
        "GET",
        "/api/v1/auth/me",
        "admin-me",
        expected=200,
        headers=bearer(access_token),
    )
    EVIDENCE.check(
        "admin token: authenticated /me",
        me.json().get("username") == ADMIN_USERNAME,
        request_id=me.headers.get("X-Request-ID"),
    )

    self_delete = await call(
        admin,
        "DELETE",
        f"/api/v1/admin/users/{user['id']}",
        "last-admin-self-delete",
        expected=409,
        headers=bearer(access_token),
    )
    EVIDENCE.check(
        "last admin: self-delete rejected",
        body_code(self_delete) == "SELF_DELETE_FORBIDDEN",
        request_id=self_delete.headers.get("X-Request-ID"),
        code=body_code(self_delete),
    )

    self_disable = await call(
        admin,
        "PATCH",
        f"/api/v1/admin/users/{user['id']}",
        "last-admin-disable",
        expected=409,
        headers=bearer(access_token),
        json={"status": "disabled"},
    )
    EVIDENCE.check(
        "last admin: disable rejected",
        body_code(self_disable) == "LAST_ADMIN_PROTECTED",
        request_id=self_disable.headers.get("X-Request-ID"),
        code=body_code(self_disable),
    )

    self_demote = await call(
        admin,
        "PATCH",
        f"/api/v1/admin/users/{user['id']}",
        "last-admin-demote",
        expected=409,
        headers=bearer(access_token),
        json={"role": "member"},
    )
    EVIDENCE.check(
        "last admin: demote rejected",
        body_code(self_demote) == "LAST_ADMIN_PROTECTED",
        request_id=self_demote.headers.get("X-Request-ID"),
        code=body_code(self_demote),
    )

    return access_token, user


async def member_lifecycle(
    admin: httpx.AsyncClient, admin_token: str
) -> dict[str, Any]:
    suffix = uuid4().hex[:8]
    username = f"qa_life_{suffix}"
    created = await call(
        admin,
        "POST",
        "/api/v1/admin/users",
        "member-create-generated",
        expected=201,
        headers=bearer(admin_token),
        json={
            "username": username,
            "display_name": "A30 Lifecycle Member",
            "role": "member",
            "department": "QA",
            "learning_group": "Integration",
        },
    )
    created_body = created.json()
    member = created_body["user"]
    member_id = member["id"]
    first_password = created_body["temporary_password"]
    EVIDENCE.check(
        "member create: generated temporary password returned once",
        bool(first_password) and len(first_password) >= 12,
        request_id=created.headers.get("X-Request-ID"),
        username=username,
    )
    EVIDENCE.check(
        "member create: forced password change",
        member.get("must_change_password") is True,
        request_id=created.headers.get("X-Request-ID"),
    )

    detail = await call(
        admin,
        "GET",
        f"/api/v1/admin/users/{member_id}",
        "member-detail-safe",
        expected=200,
        headers=bearer(admin_token),
    )
    detail_body = detail.json()
    assert_no_private_fields(
        detail_body, "admin detail", detail.headers.get("X-Request-ID")
    )
    EVIDENCE.check(
        "member detail: temporary password not persisted",
        "temporary_password" not in detail_body and first_password not in detail.text,
        request_id=detail.headers.get("X-Request-ID"),
    )

    filtered = await call(
        admin,
        "GET",
        f"/api/v1/admin/users?search={username}&role=member&status=active&limit=10",
        "member-filter",
        expected=200,
        headers=bearer(admin_token),
    )
    filtered_body = filtered.json()
    EVIDENCE.check(
        "member list: search/role/status filter",
        [item["username"] for item in filtered_body.get("items", [])] == [username],
        request_id=filtered.headers.get("X-Request-ID"),
    )

    async with new_client() as member_client:
        member_login = await login(
            member_client, username, first_password, "member-first-login"
        )
        member_session = member_login.json()
        member_token = member_session["access_token"]
        EVIDENCE.check(
            "member first login: forced change",
            member_session["user"]["must_change_password"] is True,
            request_id=member_login.headers.get("X-Request-ID"),
        )

        blocked = await call(
            member_client,
            "GET",
            "/api/v1/admin/users",
            "member-admin-blocked-before-change",
            expected=403,
            headers=bearer(member_token),
        )
        EVIDENCE.check(
            "forced change: admin API blocked",
            body_code(blocked) == "AUTH_PASSWORD_CHANGE_REQUIRED",
            request_id=blocked.headers.get("X-Request-ID"),
            code=body_code(blocked),
        )

        new_password = generate_password("LifeMember")
        changed = await call(
            member_client,
            "POST",
            "/api/v1/auth/change-password",
            "member-change-password",
            expected=204,
            headers=bearer(member_token),
            json={"old_password": first_password, "new_password": new_password},
        )
        EVIDENCE.check(
            "change password: old access token revoked immediately",
            (
                await call(
                    member_client,
                    "GET",
                    "/api/v1/auth/me",
                    "member-old-token-after-change",
                    expected=401,
                    headers=bearer(member_token),
                )
            ).status_code
            == 401,
            request_id=changed.headers.get("X-Request-ID"),
        )

        relogin = await login(
            member_client, username, new_password, "member-login-new-password"
        )
        relogin_body = relogin.json()
        member_token = relogin_body["access_token"]
        EVIDENCE.check(
            "change password: new password clears forced-change flag",
            relogin_body["user"]["must_change_password"] is False,
            request_id=relogin.headers.get("X-Request-ID"),
        )

        forbidden = await call(
            member_client,
            "GET",
            "/api/v1/admin/users",
            "member-admin-forbidden",
            expected=403,
            headers=bearer(member_token),
        )
        EVIDENCE.check(
            "member role: administrator endpoint returns 403",
            body_code(forbidden) == "FORBIDDEN",
            request_id=forbidden.headers.get("X-Request-ID"),
            code=body_code(forbidden),
        )

        reset = await call(
            admin,
            "POST",
            f"/api/v1/admin/users/{member_id}/reset-password",
            "member-reset-password",
            expected=200,
            headers=bearer(admin_token),
        )
        reset_body = reset.json()
        reset_password = reset_body["temporary_password"]
        EVIDENCE.check(
            "admin reset: temporary password returned and forced change set",
            bool(reset_password) and reset_body.get("must_change_password") is True,
            request_id=reset.headers.get("X-Request-ID"),
        )
        EVIDENCE.check(
            "admin reset: prior access token revoked",
            (
                await call(
                    member_client,
                    "GET",
                    "/api/v1/auth/me",
                    "member-token-after-reset",
                    expected=401,
                    headers=bearer(member_token),
                )
            ).status_code
            == 401,
            request_id=reset.headers.get("X-Request-ID"),
        )

        reset_login = await login(
            member_client, username, reset_password, "member-login-reset-password"
        )
        reset_token = reset_login.json()["access_token"]
        disabled = await call(
            admin,
            "PATCH",
            f"/api/v1/admin/users/{member_id}",
            "member-disable",
            expected=200,
            headers=bearer(admin_token),
            json={"status": "disabled"},
        )
        EVIDENCE.check(
            "disable: response records disabled status",
            disabled.json().get("status") == "disabled",
            request_id=disabled.headers.get("X-Request-ID"),
        )
        EVIDENCE.check(
            "disable: existing access token rejected",
            (
                await call(
                    member_client,
                    "GET",
                    "/api/v1/auth/me",
                    "member-token-after-disable",
                    expected=401,
                    headers=bearer(reset_token),
                )
            ).status_code
            == 401,
            request_id=disabled.headers.get("X-Request-ID"),
        )
        disabled_login = await login(
            member_client,
            username,
            reset_password,
            "member-disabled-login",
            expected=401,
        )
        EVIDENCE.check(
            "disable: login uses uniform invalid-credentials error",
            body_code(disabled_login) == "AUTH_INVALID_CREDENTIALS",
            request_id=disabled_login.headers.get("X-Request-ID"),
        )

        enabled = await call(
            admin,
            "PATCH",
            f"/api/v1/admin/users/{member_id}",
            "member-enable",
            expected=200,
            headers=bearer(admin_token),
            json={"status": "active"},
        )
        EVIDENCE.check(
            "enable: response records active status",
            enabled.json().get("status") == "active",
            request_id=enabled.headers.get("X-Request-ID"),
        )

        deleted = await call(
            admin,
            "DELETE",
            f"/api/v1/admin/users/{member_id}",
            "member-delete",
            expected=204,
            headers=bearer(admin_token),
        )
        EVIDENCE.check(
            "delete: subsequent detail is 404",
            (
                await call(
                    admin,
                    "GET",
                    f"/api/v1/admin/users/{member_id}",
                    "member-detail-after-delete",
                    expected=404,
                    headers=bearer(admin_token),
                )
            ).status_code
            == 404,
            request_id=deleted.headers.get("X-Request-ID"),
        )

    return {"username": username, "id": member_id, "deleted": True}


async def last_admin_concurrency(
    admin: httpx.AsyncClient,
    admin_token: str,
    conn: asyncpg.Connection,
    admin_user: dict[str, Any],
) -> None:
    suffix = uuid4().hex[:8]
    username = f"qa_admin_race_{suffix}"
    created = await call(
        admin,
        "POST",
        "/api/v1/admin/users",
        "race-admin-create",
        expected=201,
        headers=bearer(admin_token),
        json={
            "username": username,
            "display_name": "A30 Concurrent Administrator",
            "role": "admin",
        },
    )
    created_body = created.json()
    second_admin_id = created_body["user"]["id"]
    initial_password = created_body["temporary_password"]

    current_admin_token = admin_token
    async with new_client() as second_admin:
        second_login = await login(
            second_admin, username, initial_password, "race-admin-first-login"
        )
        forced_token = second_login.json()["access_token"]
        EVIDENCE.check(
            "concurrency: second administrator starts with forced password change",
            second_login.json()["user"]["must_change_password"] is True,
            request_id=second_login.headers.get("X-Request-ID"),
        )

        new_password = generate_password("RaceAdmin")
        changed = await call(
            second_admin,
            "POST",
            "/api/v1/auth/change-password",
            "race-admin-change-password",
            expected=204,
            headers=bearer(forced_token),
            json={"old_password": initial_password, "new_password": new_password},
        )
        relogin = await login(
            second_admin, username, new_password, "race-admin-relogin"
        )
        second_admin_token = relogin.json()["access_token"]
        EVIDENCE.check(
            "concurrency: two active administrators prepared",
            changed.status_code == 204
            and relogin.json()["user"]["must_change_password"] is False,
            request_id=relogin.headers.get("X-Request-ID"),
        )

        demote_second, demote_first = await asyncio.gather(
            call(
                admin,
                "PATCH",
                f"/api/v1/admin/users/{second_admin_id}",
                "race-demote-second-admin",
                headers=bearer(current_admin_token),
                json={"role": "member"},
            ),
            call(
                second_admin,
                "PATCH",
                f"/api/v1/admin/users/{admin_user['id']}",
                "race-demote-first-admin",
                headers=bearer(second_admin_token),
                json={"role": "member"},
            ),
        )
        race_statuses = sorted((demote_second.status_code, demote_first.status_code))
        active_admin_count = await conn.fetchval(
            "SELECT count(*) FROM users WHERE role = 'admin' AND status = 'active'"
        )

        # Restore the bootstrap administrator before asserting so a product race failure
        # cannot leave the isolated QA database without an administrator.
        if active_admin_count == 0:
            await conn.execute(
                "UPDATE users SET role = 'admin', status = 'active', session_version = session_version + 1 WHERE id = $1",
                admin_user["id"],
            )
            relogin_bootstrap = await login(
                admin,
                ADMIN_USERNAME,
                ADMIN_PASSWORD,
                "race-cleanup-after-zero-admins",
            )
            current_admin_token = relogin_bootstrap.json()["access_token"]
        elif demote_first.status_code == 200:
            restored = await call(
                second_admin,
                "PATCH",
                f"/api/v1/admin/users/{admin_user['id']}",
                "race-restore-first-admin",
                expected=200,
                headers=bearer(second_admin_token),
                json={"role": "admin"},
            )
            EVIDENCE.check(
                "concurrency cleanup: bootstrap administrator restored",
                restored.json().get("role") == "admin",
                request_id=restored.headers.get("X-Request-ID"),
            )
            relogin_bootstrap = await login(
                admin,
                ADMIN_USERNAME,
                ADMIN_PASSWORD,
                "race-cleanup-admin-relogin",
            )
            current_admin_token = relogin_bootstrap.json()["access_token"]

        deleted = await call(
            admin,
            "DELETE",
            f"/api/v1/admin/users/{second_admin_id}",
            "race-admin-cleanup",
            expected=204,
            headers=bearer(current_admin_token),
        )
        EVIDENCE.check(
            "concurrency cleanup: temporary administrator removed",
            deleted.status_code == 204,
            request_id=deleted.headers.get("X-Request-ID"),
        )
        EVIDENCE.check(
            "concurrency: exactly one last-admin demotion succeeds",
            race_statuses == [200, 409],
            request_id=demote_second.headers.get("X-Request-ID"),
            second_request_id=demote_first.headers.get("X-Request-ID"),
            statuses=race_statuses,
        )
        EVIDENCE.check(
            "concurrency: at least one enabled administrator remains",
            active_admin_count >= 1,
            request_id=demote_second.headers.get("X-Request-ID"),
            active_admin_count=active_admin_count,
        )


async def pagination_checks(admin: httpx.AsyncClient, admin_token: str) -> None:
    suffix = uuid4().hex[:8]
    created_ids: list[str] = []
    for index in range(2):
        response = await call(
            admin,
            "POST",
            "/api/v1/admin/users",
            f"pagination-create-{index}",
            expected=201,
            headers=bearer(admin_token),
            json={
                "username": f"qa_page_{suffix}_{index}",
                "display_name": f"A30 Page {index}",
                "role": "member",
                "password": generate_password("PageMember"),
            },
        )
        created_ids.append(response.json()["user"]["id"])

    first = await call(
        admin,
        "GET",
        "/api/v1/admin/users?limit=1",
        "pagination-page-1",
        expected=200,
        headers=bearer(admin_token),
    )
    first_body = first.json()
    EVIDENCE.check(
        "pagination: first page has next cursor",
        first_body.get("has_more") is True and bool(first_body.get("next_cursor")),
        request_id=first.headers.get("X-Request-ID"),
    )
    second = await call(
        admin,
        "GET",
        f"/api/v1/admin/users?limit=1&cursor={first_body['next_cursor']}",
        "pagination-page-2",
        expected=200,
        headers=bearer(admin_token),
    )
    second_body = second.json()
    EVIDENCE.check(
        "pagination: cursor advances to a different account",
        second_body["items"][0]["id"] != first_body["items"][0]["id"],
        request_id=second.headers.get("X-Request-ID"),
    )

    for index, user_id in enumerate(created_ids):
        await call(
            admin,
            "DELETE",
            f"/api/v1/admin/users/{user_id}",
            f"pagination-cleanup-{index}",
            expected=204,
            headers=bearer(admin_token),
        )


async def refresh_rotation_replay() -> None:
    async with new_client() as client:
        login_response = await login(
            client, ADMIN_USERNAME, ADMIN_PASSWORD, "refresh-login"
        )
        first = login_response.json()
        old_refresh = cookie_value(login_response, "refresh_token")
        old_csrf = first["csrf_token"]

        rotated = await call(
            client,
            "POST",
            "/api/v1/auth/refresh",
            "refresh-rotate",
            expected=200,
            headers={"Origin": FRONTEND_BASE_URL, "X-CSRF-Token": old_csrf},
        )
        second = rotated.json()
        new_refresh = cookie_value(rotated, "refresh_token")
        new_csrf = second["csrf_token"]
        EVIDENCE.check(
            "refresh: token and CSRF rotate",
            new_refresh != old_refresh and new_csrf != old_csrf,
            request_id=rotated.headers.get("X-Request-ID"),
        )

        replay = await call(
            client,
            "POST",
            "/api/v1/auth/refresh",
            "refresh-replay-old-token",
            expected=401,
            headers={
                "Origin": FRONTEND_BASE_URL,
                "X-CSRF-Token": old_csrf,
                "Cookie": f"refresh_token={old_refresh}; csrf_token={old_csrf}",
            },
        )
        EVIDENCE.check(
            "refresh replay: token reuse detected",
            body_code(replay) == "AUTH_TOKEN_REUSED",
            request_id=replay.headers.get("X-Request-ID"),
            code=body_code(replay),
        )
        EVIDENCE.check(
            "refresh replay: entire family access token revoked",
            (
                await call(
                    client,
                    "GET",
                    "/api/v1/auth/me",
                    "refresh-family-access-revoked",
                    expected=401,
                    headers=bearer(second["access_token"]),
                )
            ).status_code
            == 401,
            request_id=replay.headers.get("X-Request-ID"),
        )

        family_refresh = await call(
            client,
            "POST",
            "/api/v1/auth/refresh",
            "refresh-family-cookie-revoked",
            expected=401,
            headers={
                "Origin": FRONTEND_BASE_URL,
                "X-CSRF-Token": new_csrf,
                "Cookie": f"refresh_token={new_refresh}; csrf_token={new_csrf}",
            },
        )
        EVIDENCE.check(
            "refresh replay: replacement refresh token revoked",
            family_refresh.status_code == 401,
            request_id=replay.headers.get("X-Request-ID"),
        )


async def csrf_origin_and_logout() -> None:
    async with new_client() as client:
        login_response = await login(
            client, ADMIN_USERNAME, ADMIN_PASSWORD, "csrf-login"
        )
        session = login_response.json()
        csrf = session["csrf_token"]

        evil = await call(
            client,
            "POST",
            "/api/v1/auth/refresh",
            "refresh-evil-origin",
            expected=403,
            headers={"Origin": "https://evil.example", "X-CSRF-Token": csrf},
        )
        EVIDENCE.check(
            "CSRF/Origin: evil origin rejected",
            body_code(evil) == "AUTH_ORIGIN_INVALID",
            request_id=evil.headers.get("X-Request-ID"),
            code=body_code(evil),
        )
        missing = await call(
            client,
            "POST",
            "/api/v1/auth/refresh",
            "refresh-missing-csrf",
            expected=403,
            headers={"Origin": FRONTEND_BASE_URL},
        )
        EVIDENCE.check(
            "CSRF/Origin: missing CSRF rejected",
            body_code(missing) == "AUTH_CSRF_FAILED",
            request_id=missing.headers.get("X-Request-ID"),
            code=body_code(missing),
        )
        wrong = await call(
            client,
            "POST",
            "/api/v1/auth/refresh",
            "refresh-wrong-csrf",
            expected=403,
            headers={"Origin": FRONTEND_BASE_URL, "X-CSRF-Token": "tampered"},
        )
        EVIDENCE.check(
            "CSRF/Origin: wrong CSRF rejected",
            body_code(wrong) == "AUTH_CSRF_FAILED",
            request_id=wrong.headers.get("X-Request-ID"),
        )

        rotated = await call(
            client,
            "POST",
            "/api/v1/auth/refresh",
            "refresh-valid-after-rejections",
            expected=200,
            headers={"Origin": FRONTEND_BASE_URL, "X-CSRF-Token": csrf},
        )
        current = rotated.json()
        current_refresh = cookie_value(rotated, "refresh_token")
        current_csrf = current["csrf_token"]

        no_csrf_logout = await call(
            client,
            "POST",
            "/api/v1/auth/logout",
            "logout-missing-csrf",
            expected=403,
            headers={**bearer(current["access_token"]), "Origin": FRONTEND_BASE_URL},
        )
        EVIDENCE.check(
            "logout: missing CSRF rejected",
            body_code(no_csrf_logout) == "AUTH_CSRF_FAILED",
            request_id=no_csrf_logout.headers.get("X-Request-ID"),
        )
        logged_out = await call(
            client,
            "POST",
            "/api/v1/auth/logout",
            "logout-valid",
            expected=204,
            headers={
                **bearer(current["access_token"]),
                "Origin": FRONTEND_BASE_URL,
                "X-CSRF-Token": current_csrf,
            },
        )
        cleared = [
            h.split("=", 1)[0] for h in logged_out.headers.get_list("set-cookie")
        ]
        EVIDENCE.check(
            "logout: both cookies are cleared",
            {"refresh_token", "csrf_token"}.issubset(cleared),
            request_id=logged_out.headers.get("X-Request-ID"),
            cleared=cleared,
        )
        EVIDENCE.check(
            "logout: access token revoked",
            (
                await call(
                    client,
                    "GET",
                    "/api/v1/auth/me",
                    "logout-access-revoked",
                    expected=401,
                    headers=bearer(current["access_token"]),
                )
            ).status_code
            == 401,
            request_id=logged_out.headers.get("X-Request-ID"),
        )
        refresh_after_logout = await call(
            client,
            "POST",
            "/api/v1/auth/refresh",
            "logout-refresh-revoked",
            expected=401,
            headers={
                "Origin": FRONTEND_BASE_URL,
                "X-CSRF-Token": current_csrf,
                "Cookie": f"refresh_token={current_refresh}; csrf_token={current_csrf}",
            },
        )
        EVIDENCE.check(
            "logout: refresh token revoked",
            refresh_after_logout.status_code == 401,
            request_id=logged_out.headers.get("X-Request-ID"),
        )


async def csv_import_checks(
    admin: httpx.AsyncClient, admin_token: str, conn: asyncpg.Connection
) -> None:
    suffix = uuid4().hex[:8]
    invalid_username = f"qa_csv_invalid_{suffix}"
    csv_bad = (
        "username,display_name,initial_password,department,learning_group\n"
        f"{ADMIN_USERNAME},Existing Admin,,QA,Integration\n"
        f"{invalid_username},Invalid Row,,QA,Integration\n"
        "x,Too Short,,QA,Integration\n"
    ).encode()
    preview_bad = await call(
        admin,
        "POST",
        "/api/v1/admin/users/import/preview",
        "csv-preview-invalid",
        expected=200,
        headers=bearer(admin_token),
        files={"file": ("a30-invalid.csv", csv_bad, "text/csv")},
    )
    bad_body = preview_bad.json()
    EVIDENCE.check(
        "CSV preview: conflicts and format errors are surfaced",
        bad_body["invalid_rows"] >= 2
        and any(row.get("status") != "valid" for row in bad_body.get("rows", [])),
        request_id=preview_bad.headers.get("X-Request-ID"),
        invalid_rows=bad_body["invalid_rows"],
        valid_rows=bad_body["valid_rows"],
    )
    confirm_bad = await call(
        admin,
        "POST",
        "/api/v1/admin/users/import",
        "csv-confirm-invalid",
        expected=409,
        headers=bearer(admin_token),
        json={
            "preview_id": bad_body["preview_id"],
            "preview_hash": bad_body["preview_hash"],
        },
    )
    EVIDENCE.check(
        "CSV confirm: invalid preview rejected as a batch",
        body_code(confirm_bad) == "IMPORT_PREVIEW_INVALID",
        request_id=confirm_bad.headers.get("X-Request-ID"),
    )
    count = await conn.fetchval(
        "SELECT count(*) FROM users WHERE username_normalized = $1",
        invalid_username.lower(),
    )
    EVIDENCE.check(
        "CSV failure: no partial row persisted",
        count == 0,
        request_id=confirm_bad.headers.get("X-Request-ID"),
        row_count=count,
    )

    valid_supplied = f"qa_csv_supplied_{suffix}"
    valid_generated = f"qa_csv_generated_{suffix}"
    supplied_password = generate_password("CsvSupplied")
    csv_valid = (
        "username,display_name,initial_password,department,learning_group\n"
        f"{valid_supplied},CSV Supplied,{supplied_password},QA,Batch\n"
        f"{valid_generated},CSV Generated,,QA,Batch\n"
    ).encode()
    preview = await call(
        admin,
        "POST",
        "/api/v1/admin/users/import/preview",
        "csv-preview-valid",
        expected=200,
        headers=bearer(admin_token),
        files={"file": ("a30-valid.csv", csv_valid, "text/csv")},
    )
    preview_body = preview.json()
    EVIDENCE.check(
        "CSV preview: valid batch ready",
        preview_body["valid_rows"] == 2 and preview_body["invalid_rows"] == 0,
        request_id=preview.headers.get("X-Request-ID"),
    )
    confirmed = await call(
        admin,
        "POST",
        "/api/v1/admin/users/import",
        "csv-confirm-valid",
        expected=202,
        headers=bearer(admin_token),
        json={
            "preview_id": preview_body["preview_id"],
            "preview_hash": preview_body["preview_hash"],
        },
    )
    confirmed_body = confirmed.json()
    by_username = {item["username"]: item for item in confirmed_body["created_users"]}
    EVIDENCE.check(
        "CSV confirm: atomic batch created",
        confirmed_body["status"] == "imported" and confirmed_body["created_count"] == 2,
        request_id=confirmed.headers.get("X-Request-ID"),
    )
    EVIDENCE.check(
        "CSV confirm: generated password appears only for generated row",
        by_username[valid_generated]["temporary_password"]
        and by_username[valid_supplied]["temporary_password"] is None,
        request_id=confirmed.headers.get("X-Request-ID"),
    )

    status = await call(
        admin,
        "GET",
        f"/api/v1/admin/users/import/{confirmed_body['import_id']}",
        "csv-status-safe",
        expected=200,
        headers=bearer(admin_token),
    )
    status_text = status.text
    EVIDENCE.check(
        "CSV status: no temporary password replay",
        "temporary_password" not in status_text
        and by_username[valid_generated]["temporary_password"] not in status_text,
        request_id=status.headers.get("X-Request-ID"),
    )

    repeated = await call(
        admin,
        "POST",
        "/api/v1/admin/users/import",
        "csv-confirm-repeated",
        expected=409,
        headers=bearer(admin_token),
        json={
            "preview_id": preview_body["preview_id"],
            "preview_hash": preview_body["preview_hash"],
        },
    )
    EVIDENCE.check(
        "CSV confirm: repeat is idempotently refused",
        body_code(repeated) == "IMPORT_ALREADY_COMPLETED",
        request_id=repeated.headers.get("X-Request-ID"),
    )

    rows = await conn.fetch(
        "SELECT id, username_normalized FROM users WHERE username_normalized = ANY($1::text[])",
        [valid_supplied.lower(), valid_generated.lower()],
    )
    EVIDENCE.check(
        "CSV success: exactly two new accounts persisted",
        len(rows) == 2,
        request_id=confirmed.headers.get("X-Request-ID"),
        row_count=len(rows),
    )
    for username in (valid_supplied, valid_generated):
        await call(
            admin,
            "DELETE",
            f"/api/v1/admin/users/{by_username[username]['id']}",
            f"csv-cleanup-{username}",
            expected=204,
            headers=bearer(admin_token),
        )


async def uniform_errors_and_rate_limit(
    admin: httpx.AsyncClient, admin_token: str
) -> None:
    suffix = uuid4().hex[:8]
    missing_username = f"qa_missing_{suffix}"
    async with new_client() as client:
        missing = await login(
            client,
            missing_username,
            "Wrong-Pass-123!",
            "login-missing-user",
            expected=401,
        )
        EVIDENCE.check(
            "login: nonexistent account uses generic error",
            body_code(missing) == "AUTH_INVALID_CREDENTIALS",
            request_id=missing.headers.get("X-Request-ID"),
        )

    disabled_username = f"qa_disabled_{suffix}"
    created = await call(
        admin,
        "POST",
        "/api/v1/admin/users",
        "rate-disabled-create",
        expected=201,
        headers=bearer(admin_token),
        json={
            "username": disabled_username,
            "display_name": "A30 Disabled",
            "role": "member",
        },
    )
    disabled_id = created.json()["user"]["id"]
    disabled_password = created.json()["temporary_password"]
    await call(
        admin,
        "PATCH",
        f"/api/v1/admin/users/{disabled_id}",
        "rate-disabled-patch",
        expected=200,
        headers=bearer(admin_token),
        json={"status": "disabled"},
    )
    async with new_client() as client:
        disabled_login = await login(
            client,
            disabled_username,
            disabled_password,
            "login-disabled-account",
            expected=401,
        )
        EVIDENCE.check(
            "login: disabled account uses same generic error",
            body_code(disabled_login) == "AUTH_INVALID_CREDENTIALS",
            request_id=disabled_login.headers.get("X-Request-ID"),
        )
        EVIDENCE.check(
            "login: no account-existence disclosure",
            body_code(disabled_login) == body_code(missing),
            request_id=disabled_login.headers.get("X-Request-ID"),
        )

    rate_username = f"qa_rate_{suffix}"
    async with new_client() as client:
        for attempt in range(1, 4):
            failed = await login(
                client,
                rate_username,
                "Wrong-Pass-123!",
                f"rate-failure-{attempt}",
                expected=401,
            )
            EVIDENCE.check(
                f"rate limit: failure {attempt} is generic",
                body_code(failed) == "AUTH_INVALID_CREDENTIALS",
                request_id=failed.headers.get("X-Request-ID"),
            )
        throttled = await login(
            client,
            rate_username,
            "Still-Wrong-123!",
            "rate-limit-trigger",
            expected=429,
        )
        EVIDENCE.check(
            "rate limit: returns 429 and Retry-After",
            body_code(throttled) == "AUTH_RATE_LIMITED"
            and int(throttled.headers.get("retry-after", "0")) >= 1,
            request_id=throttled.headers.get("X-Request-ID"),
            retry_after=throttled.headers.get("retry-after"),
        )

    await call(
        admin,
        "DELETE",
        f"/api/v1/admin/users/{disabled_id}",
        "rate-disabled-cleanup",
        expected=204,
        headers=bearer(admin_token),
    )


async def audit_and_privacy_checks(conn: asyncpg.Connection) -> None:
    events = await conn.fetch(
        """
        SELECT actor_id, actor_username, action, target_type, target_id, target_username,
               request_id, outcome, reason_code, context::text AS context_text
        FROM audit_logs
        WHERE request_id LIKE $1
        ORDER BY created_at
        """,
        f"{RUN_ID}%",
    )
    EVIDENCE.check(
        "audit: events exist for this live run",
        bool(events),
        request_id=None,
        event_count=len(events),
    )
    account_events = [row for row in events if row["action"].startswith("admin.user.")]
    EVIDENCE.check(
        "audit: account writes are attributable",
        bool(account_events)
        and all(
            row["actor_username"] and row["target_type"] == "user" and row["request_id"]
            for row in account_events
        ),
        request_id=None,
        event_count=len(account_events),
    )
    context_blob = "\n".join((row["context_text"] or "") for row in events).lower()
    violations = [term for term in SENSITIVE_TERMS if term in context_blob]
    EVIDENCE.check(
        "audit: context excludes secrets and private learning content",
        not violations,
        request_id=None,
        violations=violations,
    )

    columns = await conn.fetch(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name IN ('users', 'user_profiles', 'refresh_tokens', 'audit_logs', 'import_previews')
        """
    )
    EVIDENCE.check(
        "privacy: identity tables contain no learning-content columns",
        not any(
            any(
                term in row["column_name"].lower()
                for term in ("answer", "draft", "coach", "wordbook")
            )
            for row in columns
        ),
        request_id=None,
    )
    EVIDENCE.artifacts["audit_event_count"] = len(events)
    EVIDENCE.artifacts["audit_account_event_count"] = len(account_events)


async def run() -> None:
    conn = await asyncpg.connect(PG_DSN)
    try:
        async with new_client() as admin:
            admin_token, admin_user = await discover_admin_and_last_admin_guards(admin)
            await member_lifecycle(admin, admin_token)
            await last_admin_concurrency(admin, admin_token, conn, admin_user)
            await pagination_checks(admin, admin_token)
            await csv_import_checks(admin, admin_token, conn)
            await uniform_errors_and_rate_limit(admin, admin_token)
        await refresh_rotation_replay()
        await csrf_origin_and_logout()
        await audit_and_privacy_checks(conn)
    finally:
        await conn.close()


def main() -> int:
    error: str | None = None
    try:
        asyncio.run(run())
    except Exception as exc:  # noqa: BLE001 - preserve the first live-test failure
        error = f"{type(exc).__name__}: {exc}"
        print(error, file=sys.stderr)
    result_path = EVIDENCE.finish(error)
    print(f"RESULT={result_path}")
    return 1 if error else 0


if __name__ == "__main__":
    raise SystemExit(main())
