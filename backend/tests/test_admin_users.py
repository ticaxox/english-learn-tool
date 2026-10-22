import asyncio
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppError
from app.core.security import hash_password, password_policy_error
from app.models.identity import AuditLog, User, UserProfile
from app.schemas.users import AdminUserPatch
from app.services.users import delete_user, update_user
from tests.conftest import TEST_USER_PASSWORD

ADMIN_PATH = "/api/v1/admin/users"
LOGIN_PATH = "/api/v1/auth/login"
ME_PATH = "/api/v1/auth/me"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def login(client: httpx.AsyncClient, username: str, password: str = TEST_USER_PASSWORD):
    return await client.post(LOGIN_PATH, json={"username": username, "password": password})


async def admin_headers(client: httpx.AsyncClient, admin_user: User) -> tuple[dict[str, str], str]:
    response = await login(client, admin_user.username)
    assert response.status_code == 200
    return bearer(response.json()["access_token"]), response.json()["access_token"]


async def test_admin_routes_reject_unauthenticated_and_member_callers(
    client, admin_user, member_user
) -> None:
    unauthenticated = await client.get(ADMIN_PATH)
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["code"] == "UNAUTHORIZED"

    member_login = await login(client, member_user.username)
    assert member_login.status_code == 200
    forbidden = await client.get(
        ADMIN_PATH,
        headers=bearer(member_login.json()["access_token"]),
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "FORBIDDEN"

    headers, _ = await admin_headers(client, admin_user)
    allowed = await client.get(ADMIN_PATH, headers=headers)
    assert allowed.status_code == 200


async def test_create_list_detail_patch_and_disable_member(client, app, admin_user) -> None:
    headers, _ = await admin_headers(client, admin_user)
    username = f"created_{uuid4().hex[:8]}"
    created_password = "Created-Member-Pass-123!"

    created = await client.post(
        ADMIN_PATH,
        headers=headers,
        json={
            "username": username,
            "display_name": "Created Member",
            "password": created_password,
            "role": "member",
            "department": "Learning",
            "learning_group": "Cohort A",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["temporary_password"] is None
    assert body["user"]["must_change_password"] is True
    assert "password" not in body["user"]
    member_id = body["user"]["id"]

    duplicate = await client.post(
        ADMIN_PATH,
        headers=headers,
        json={
            "username": username.upper(),
            "display_name": "Duplicate",
            "password": created_password,
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "USERNAME_TAKEN"

    first_page = await client.get(f"{ADMIN_PATH}?limit=1", headers=headers)
    assert first_page.status_code == 200
    first_body = first_page.json()
    assert first_body["has_more"] is True
    assert first_body["next_cursor"]
    second_page = await client.get(
        f"{ADMIN_PATH}?limit=1&cursor={first_body['next_cursor']}",
        headers=headers,
    )
    assert second_page.status_code == 200
    assert second_page.json()["items"][0]["id"] != first_body["items"][0]["id"]

    filtered = await client.get(
        f"{ADMIN_PATH}?role=member&search={username}",
        headers=headers,
    )
    assert filtered.status_code == 200
    assert [item["username"] for item in filtered.json()["items"]] == [username]

    detail = await client.get(f"{ADMIN_PATH}/{member_id}", headers=headers)
    assert detail.status_code == 200
    detail_body = detail.json()
    assert set(detail_body) == {"account", "aggregates"}
    assert set(detail_body["aggregates"]) == {
        "active_sessions",
        "audit_events_30d",
        "learning_metrics_available",
        "study_minutes",
        "completed_tasks",
        "practice_submissions",
        "ai_usage_count",
        "error_rate",
    }
    forbidden_fields = {"answer", "answers", "draft", "coach_message", "wordbook_content"}
    assert forbidden_fields.isdisjoint(detail_body["account"])

    member_login = await login(client, username, created_password)
    assert member_login.status_code == 200
    member_token = member_login.json()["access_token"]

    updated = await client.patch(
        f"{ADMIN_PATH}/{member_id}",
        headers=headers,
        json={
            "display_name": "Updated Member",
            "department": "Platform",
            "learning_group": None,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["display_name"] == "Updated Member"
    assert updated.json()["department"] == "Platform"
    assert updated.json()["learning_group"] is None

    disabled = await client.patch(
        f"{ADMIN_PATH}/{member_id}",
        headers=headers,
        json={"status": "disabled"},
    )
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"
    assert (await client.get(ME_PATH, headers=bearer(member_token))).status_code == 401

    async with app.state.session_factory() as db:
        actions = set(
            (
                await db.scalars(
                    select(AuditLog.action).where(
                        AuditLog.action.in_(["admin.user.create", "admin.user.update"])
                    )
                )
            ).all()
        )
    assert actions == {"admin.user.create", "admin.user.update"}

    missing = await client.get(f"{ADMIN_PATH}/{uuid4()}", headers=headers)
    assert missing.status_code == 404
    assert missing.json()["code"] == "USER_NOT_FOUND"


async def test_generated_password_and_reset_are_returned_once_and_revoke_sessions(
    client, app, admin_user
) -> None:
    headers, _ = await admin_headers(client, admin_user)
    username = f"reset_{uuid4().hex[:8]}"

    created = await client.post(
        ADMIN_PATH,
        headers=headers,
        json={"username": username, "display_name": "Reset Target"},
    )
    assert created.status_code == 201
    created_body = created.json()
    first_password = created_body["temporary_password"]
    assert first_password
    assert password_policy_error(first_password) is None
    member_id = created_body["user"]["id"]

    first_login = await login(client, username, first_password)
    assert first_login.status_code == 200
    assert first_login.json()["user"]["must_change_password"] is True
    first_token = first_login.json()["access_token"]

    reset = await client.post(f"{ADMIN_PATH}/{member_id}/reset-password", headers=headers)
    assert reset.status_code == 200
    reset_body = reset.json()
    second_password = reset_body["temporary_password"]
    assert second_password and second_password != first_password
    assert reset_body["must_change_password"] is True
    assert (await client.get(ME_PATH, headers=bearer(first_token))).status_code == 401

    detail = await client.get(f"{ADMIN_PATH}/{member_id}", headers=headers)
    assert detail.status_code == 200
    assert "temporary_password" not in str(detail.json())
    assert "password_hash" not in str(detail.json())

    second_login = await login(client, username, second_password)
    assert second_login.status_code == 200
    assert second_login.json()["user"]["must_change_password"] is True

    async with app.state.session_factory() as db:
        events = list(
            (
                await db.scalars(
                    select(AuditLog).where(
                        AuditLog.action == "admin.user.reset_password",
                        AuditLog.target_id == UUID(member_id),
                    )
                )
            ).all()
        )
    assert len(events) == 1
    assert events[0].outcome == "success"
    assert "password" not in str(events[0].context).lower()


async def test_last_admin_self_delete_disable_and_demote_are_protected(client, admin_user) -> None:
    headers, _ = await admin_headers(client, admin_user)

    delete_response = await client.delete(f"{ADMIN_PATH}/{admin_user.id}", headers=headers)
    assert delete_response.status_code == 409
    assert delete_response.json()["code"] == "SELF_DELETE_FORBIDDEN"

    disable_response = await client.patch(
        f"{ADMIN_PATH}/{admin_user.id}",
        headers=headers,
        json={"status": "disabled"},
    )
    assert disable_response.status_code == 409
    assert disable_response.json()["code"] == "LAST_ADMIN_PROTECTED"

    demote_response = await client.patch(
        f"{ADMIN_PATH}/{admin_user.id}",
        headers=headers,
        json={"role": "member"},
    )
    assert demote_response.status_code == 409
    assert demote_response.json()["code"] == "LAST_ADMIN_PROTECTED"


async def test_last_admin_delete_service_guard_remains(app, admin_user) -> None:
    unrelated_actor = User(
        id=uuid4(),
        username="service_guard_admin",
        username_normalized="service_guard_admin",
        display_name="Service Guard Administrator",
        role="admin",
        status="active",
        password_hash="not-used-by-the-service-guard",
        must_change_password=False,
    )

    async with app.state.session_factory() as db:
        with pytest.raises(AppError) as exc_info:
            await delete_user(db, unrelated_actor, admin_user.id)

    assert exc_info.value.code == "LAST_ADMIN_PROTECTED"


async def test_self_delete_is_forbidden_even_when_another_active_admin_remains(
    client, app, admin_user, user_factory
) -> None:
    headers, access_token = await admin_headers(client, admin_user)
    second_admin = await user_factory(role="admin", display_name="Second Administrator")

    deleted = await client.delete(f"{ADMIN_PATH}/{admin_user.id}", headers=headers)
    assert deleted.status_code == 409
    assert deleted.json()["code"] == "SELF_DELETE_FORBIDDEN"
    assert (await client.get(ME_PATH, headers=bearer(access_token))).status_code == 200

    second_login = await login(client, second_admin.username)
    assert second_login.status_code == 200
    second_headers = bearer(second_login.json()["access_token"])

    remaining = await client.get(f"{ADMIN_PATH}/{second_admin.id}", headers=second_headers)
    assert remaining.status_code == 200
    assert remaining.json()["account"]["role"] == "admin"

    async with app.state.session_factory() as db:
        target = await db.get(User, admin_user.id)
        failure_audit = await db.scalar(
            select(AuditLog).where(
                AuditLog.action == "admin.user.delete",
                AuditLog.target_id == admin_user.id,
                AuditLog.reason_code == "SELF_DELETE_FORBIDDEN",
            )
        )
        active_admins = await db.scalar(
            select(func.count(User.id)).where(User.role == "admin", User.status == "active")
        )
    assert target is not None
    assert failure_audit is not None
    assert failure_audit.outcome == "failure"
    assert "password" not in str(failure_audit.context).lower()
    assert active_admins == 2


async def test_concurrent_demotions_cannot_remove_every_active_admin(app) -> None:
    suffix = uuid4().hex[:8]
    credentials_hash = hash_password("Concurrent-Admin-Pass-123!")
    first_id = uuid4()
    second_id = uuid4()

    async def create_direct_admin(user_id, username: str) -> None:
        async with app.state.engine.begin() as connection:
            await connection.execute(
                User.__table__.insert().values(
                    id=user_id,
                    username=username,
                    username_normalized=username.lower(),
                    display_name=username,
                    role="admin",
                    status="active",
                    password_hash=credentials_hash,
                    must_change_password=False,
                )
            )
            await connection.execute(
                UserProfile.__table__.insert().values(
                    id=uuid4(),
                    user_id=user_id,
                    department="Concurrency",
                    learning_group="Test",
                )
            )

    await create_direct_admin(first_id, f"race_admin_a_{suffix}")
    await create_direct_admin(second_id, f"race_admin_b_{suffix}")

    try:
        # Load both actors before either mutation so each request starts with stale admin state.
        async with app.state.engine.connect() as connection:
            async with AsyncSession(bind=connection, expire_on_commit=False) as session:
                actors = list(
                    (
                        await session.scalars(
                            select(User)
                            .options(selectinload(User.profile))
                            .where(User.id.in_([first_id, second_id]))
                            .order_by(User.id)
                        )
                    ).all()
                )
        actor_a = next(actor for actor in actors if actor.id == first_id)
        actor_b = next(actor for actor in actors if actor.id == second_id)

        async def demote(actor: User, target_id) -> str:
            async with AsyncSession(bind=app.state.engine, expire_on_commit=False) as session:
                try:
                    await update_user(
                        session,
                        actor,
                        target_id,
                        AdminUserPatch(role="member"),
                    )
                    return "success"
                except AppError as exc:
                    return exc.code

        outcomes = await asyncio.gather(
            demote(actor_a, second_id),
            demote(actor_b, first_id),
        )
        assert sorted(outcomes) == ["LAST_ADMIN_PROTECTED", "success"]

        async with AsyncSession(bind=app.state.engine, expire_on_commit=False) as session:
            active_admins = await session.scalar(
                select(func.count(User.id)).where(
                    User.role == "admin",
                    User.status == "active",
                )
            )
        assert active_admins == 1
    finally:
        async with app.state.engine.begin() as connection:
            id_values = [first_id, second_id]
            await connection.execute(
                AuditLog.__table__.delete().where(
                    or_(
                        AuditLog.actor_id.in_(id_values),
                        AuditLog.target_id.in_(id_values),
                    )
                )
            )
            await connection.execute(User.__table__.delete().where(User.id.in_(id_values)))
