import json
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.errors import AppError
from app.models.identity import AuditLog, User
from app.services.users import bootstrap_admin
from tests.conftest import TEST_NEW_PASSWORD, TEST_USER_PASSWORD

ORIGIN = "http://testserver"
LOGIN_PATH = "/api/v1/auth/login"
REFRESH_PATH = "/api/v1/auth/refresh"
LOGOUT_PATH = "/api/v1/auth/logout"
CHANGE_PASSWORD_PATH = "/api/v1/auth/change-password"
ME_PATH = "/api/v1/auth/me"
ADMIN_PATH = "/api/v1/admin/users"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_real_login_change_password_me_refresh_admin_and_logout_flow(
    client, user_factory
) -> None:
    user = await user_factory(role="admin", must_change_password=True)

    logged_in = await client.post(
        LOGIN_PATH,
        json={"username": user.username, "password": TEST_USER_PASSWORD},
    )
    assert logged_in.status_code == 200
    first = logged_in.json()
    assert first["user"]["must_change_password"] is True
    spa_request = client.build_request("GET", "/admin/users")
    assert f"csrf_token={first['csrf_token']}" in spa_request.headers.get("cookie", "")

    changed = await client.post(
        CHANGE_PASSWORD_PATH,
        headers=bearer(first["access_token"]),
        json={"old_password": TEST_USER_PASSWORD, "new_password": TEST_NEW_PASSWORD},
    )
    assert changed.status_code == 204

    logged_in_again = await client.post(
        LOGIN_PATH,
        json={"username": user.username, "password": TEST_NEW_PASSWORD},
    )
    assert logged_in_again.status_code == 200
    second = logged_in_again.json()
    assert second["user"]["must_change_password"] is False

    me = await client.get(ME_PATH, headers=bearer(second["access_token"]))
    assert me.status_code == 200
    assert me.json()["username"] == user.username

    refreshed = await client.post(
        REFRESH_PATH,
        headers={"Origin": ORIGIN, "X-CSRF-Token": second["csrf_token"]},
    )
    assert refreshed.status_code == 200
    third = refreshed.json()
    assert third["access_token"] != second["access_token"]

    admin_list = await client.get(ADMIN_PATH, headers=bearer(third["access_token"]))
    assert admin_list.status_code == 200

    logged_out = await client.post(
        LOGOUT_PATH,
        headers={
            **bearer(third["access_token"]),
            "Origin": ORIGIN,
            "X-CSRF-Token": third["csrf_token"],
        },
    )
    assert logged_out.status_code == 204
    assert (await client.get(ME_PATH, headers=bearer(third["access_token"]))).status_code == 401


async def test_identity_openapi_documents_bearer_cookie_csrf_and_privacy_contracts(client) -> None:
    response = await client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    document = response.json()
    paths = document["paths"]

    expected_paths = {
        LOGIN_PATH,
        REFRESH_PATH,
        LOGOUT_PATH,
        CHANGE_PASSWORD_PATH,
        ME_PATH,
        ADMIN_PATH,
        "/api/v1/admin/users/import/preview",
        "/api/v1/admin/users/import",
        "/api/v1/admin/users/import/{import_id}",
        "/api/v1/admin/users/{user_id}",
        "/api/v1/admin/users/{user_id}/reset-password",
    }
    assert expected_paths <= set(paths)
    assert document["components"]["securitySchemes"]["HTTPBearer"] == {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }

    refresh_operation = paths[REFRESH_PATH]["post"]
    refresh_parameters = {
        (parameter["name"], parameter["in"])
        for parameter in refresh_operation.get("parameters", [])
    }
    assert {
        ("X-CSRF-Token", "header"),
        ("refresh_token", "cookie"),
        ("csrf_token", "cookie"),
    } <= refresh_parameters
    assert "403" in refresh_operation["responses"]
    assert "429" in refresh_operation["responses"]

    logout_operation = paths[LOGOUT_PATH]["post"]
    assert logout_operation["security"] == [{"HTTPBearer": []}]
    assert "403" in logout_operation["responses"]
    assert "429" not in logout_operation["responses"]

    delete_operation = paths["/api/v1/admin/users/{user_id}"]["delete"]
    delete_conflict = delete_operation["responses"]["409"]["description"]
    assert "SELF_DELETE_FORBIDDEN" in delete_conflict
    assert "LAST_ADMIN_PROTECTED" in delete_conflict

    login_contract = paths[LOGIN_PATH]["post"]
    assert login_contract.get("security") is None
    assert "403" not in login_contract["responses"]
    login_description = login_contract["responses"]["200"]["description"]
    assert "Path=/api/v1/auth/refresh" in login_description
    assert "Path=/" in login_description
    assert "X-CSRF-Token" in login_description

    for path in (
        ADMIN_PATH,
        "/api/v1/admin/users/import/preview",
        "/api/v1/admin/users/import",
    ):
        for operation in paths[path].values():
            assert operation["security"] == [{"HTTPBearer": []}]
            assert "401" in operation["responses"]
            assert "403" in operation["responses"]

    schemas = document["components"]["schemas"]
    assert set(schemas["UserDetail"]["properties"]) == {"account", "aggregates"}
    private_content_tokens = {
        "answer",
        "answer_text",
        "draft",
        "coach_message",
        "coach_title",
        "wordbook_content",
    }
    admin_response_schemas = (
        schemas["UserSummary"],
        schemas["UserDetail"],
        schemas["UserAggregates"],
        schemas["UserListResponse"],
    )
    for schema in admin_response_schemas:
        assert private_content_tokens.isdisjoint(schema.get("properties", {}))
    assert "temporary_password" not in schemas["UserDetail"]["properties"]
    assert "password_hash" not in schemas["UserSummary"]["properties"]
    assert "password" not in json.dumps(schemas["UserDetail"]).lower()


async def test_private_api_security_headers_are_applied_to_auth_errors(client) -> None:
    response = await client.get(ME_PATH)

    assert response.status_code == 401
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["permissions-policy"]


async def test_bootstrap_admin_service_is_audited_and_refuses_a_second_active_admin(app) -> None:
    suffix = uuid4().hex[:8]
    username = f"bootstrap_{suffix}"
    password = "Bootstrap-Admin-Pass-123!"

    async with app.state.session_factory() as session:
        created = await bootstrap_admin(
            session,
            username=username,
            display_name="Bootstrap Administrator",
            password=password,
        )
    assert created.role == "admin"
    assert created.status == "active"
    assert created.must_change_password is True
    assert password not in created.password_hash

    async with app.state.session_factory() as session:
        stored = await session.scalar(
            select(User).where(User.username_normalized == username.lower())
        )
        audit = await session.scalar(
            select(AuditLog).where(
                AuditLog.action == "admin.bootstrap",
                AuditLog.target_id == created.id,
            )
        )
    assert stored is not None
    assert audit is not None
    assert audit.actor_username == "system"
    assert audit.outcome == "success"
    assert password not in str(audit.context)

    async with app.state.session_factory() as session:
        with pytest.raises(AppError) as exc_info:
            await bootstrap_admin(
                session,
                username=f"bootstrap_second_{suffix}",
                display_name="Second Bootstrap",
                password=password,
            )
    assert exc_info.value.code == "ADMIN_ALREADY_EXISTS"
