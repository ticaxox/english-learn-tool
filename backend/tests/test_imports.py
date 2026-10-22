from uuid import uuid4

import httpx
from sqlalchemy import select

from app.models.identity import AuditLog, ImportPreview, User
from tests.conftest import TEST_USER_PASSWORD

ADMIN_PATH = "/api/v1/admin/users"
PREVIEW_PATH = "/api/v1/admin/users/import/preview"
IMPORT_PATH = "/api/v1/admin/users/import"
LOGIN_PATH = "/api/v1/auth/login"
CSV_HEADER = "username,display_name,initial_password,department,learning_group\n"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def login(client: httpx.AsyncClient, username: str, password: str = TEST_USER_PASSWORD):
    return await client.post(LOGIN_PATH, json={"username": username, "password": password})


async def admin_headers(client: httpx.AsyncClient, admin_user: User) -> dict[str, str]:
    response = await login(client, admin_user.username)
    assert response.status_code == 200
    return bearer(response.json()["access_token"])


def upload_csv(client: httpx.AsyncClient, headers: dict[str, str], content: str):
    return client.post(
        PREVIEW_PATH,
        headers=headers,
        files={"file": ("members.csv", content.encode("utf-8"), "text/csv")},
    )


async def test_preview_reports_file_duplicates_database_conflicts_and_field_errors(
    client, app, admin_user, member_user
) -> None:
    headers = await admin_headers(client, admin_user)
    suffix = uuid4().hex[:8]
    valid_username = f"preview_{suffix}"
    csv_content = CSV_HEADER + (
        f"{valid_username},Valid Member,Valid-Csv-Pass-123!,Learning,Cohort A\n"
        f"{valid_username.upper()},Duplicate Member,Valid-Csv-Pass-123!,Learning,Cohort A\n"
        f"{member_user.username},Existing Member,Valid-Csv-Pass-123!,Learning,Cohort A\n"
        "bad username,Bad Username,Valid-Csv-Pass-123!,Learning,Cohort A\n"
        f"blank_name_{suffix},,,,\n"
        f"bad_password_{suffix},Bad Password,short,Learning,Cohort A\n"
    )

    preview_response = await upload_csv(client, headers, csv_content)
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview["total_rows"] == 6
    assert preview["valid_rows"] == 1
    assert preview["invalid_rows"] == 5
    statuses = [row["status"] for row in preview["rows"]]
    assert statuses == ["valid", "conflict", "conflict", "error", "error", "error"]
    assert "username_duplicate_in_file" in preview["rows"][1]["errors"]
    assert "username_conflict" in preview["rows"][2]["errors"]
    assert "username_invalid" in preview["rows"][3]["errors"]
    assert "display_name_required" in preview["rows"][4]["errors"]
    assert "initial_password_invalid" in preview["rows"][5]["errors"]
    assert "password_hash" not in str(preview)
    assert "Valid-Csv-Pass-123!" not in str(preview)

    rejected = await client.post(
        IMPORT_PATH,
        headers=headers,
        json={
            "preview_id": preview["preview_id"],
            "preview_hash": preview["preview_hash"],
        },
    )
    assert rejected.status_code == 409
    assert rejected.json()["code"] == "IMPORT_PREVIEW_INVALID"

    async with app.state.session_factory() as db:
        actions = list(
            (
                await db.scalars(
                    select(AuditLog.action)
                    .where(
                        AuditLog.action.in_(["admin.users.import.preview", "admin.users.import"])
                    )
                    .order_by(AuditLog.created_at)
                )
            ).all()
        )
    assert actions == ["admin.users.import.preview", "admin.users.import"]


async def test_valid_import_is_atomic_persisted_and_only_returns_temp_password_once(
    client, app, admin_user
) -> None:
    headers = await admin_headers(client, admin_user)
    suffix = uuid4().hex[:8]
    generated_username = f"generated_{suffix}"
    supplied_username = f"supplied_{suffix}"
    supplied_password = "Supplied-Csv-Pass-123!"
    csv_content = CSV_HEADER + (
        f"{generated_username},Generated Password,,Learning,Cohort B\n"
        f"{supplied_username},Supplied Password,{supplied_password},Platform,Group C\n"
    )

    preview_response = await upload_csv(client, headers, csv_content)
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview["valid_rows"] == 2

    imported = await client.post(
        IMPORT_PATH,
        headers=headers,
        json={
            "preview_id": preview["preview_id"],
            "preview_hash": preview["preview_hash"],
        },
    )
    assert imported.status_code == 202
    result = imported.json()
    assert result["status"] == "imported"
    assert result["created_count"] == 2
    by_username = {item["username"]: item for item in result["created_users"]}
    temporary_password = by_username[generated_username]["temporary_password"]
    assert temporary_password
    assert by_username[supplied_username]["temporary_password"] is None
    assert temporary_password not in str(result["created_users"][1])

    status_response = await client.get(
        f"{IMPORT_PATH}/{preview['preview_id']}",
        headers=headers,
    )
    assert status_response.status_code == 200
    persisted_status = status_response.json()
    assert persisted_status["status"] == "imported"
    assert persisted_status["created_count"] == 2
    assert "temporary_password" not in persisted_status

    async with app.state.session_factory() as db:
        users = list(
            (
                await db.scalars(
                    select(User).where(
                        User.username_normalized.in_(
                            [generated_username.lower(), supplied_username.lower()]
                        )
                    )
                )
            ).all()
        )
        preview_row = await db.get(ImportPreview, preview["preview_id"])
    assert len(users) == 2
    assert {user.role for user in users} == {"member"}
    assert all(user.must_change_password for user in users)
    assert all(temporary_password not in user.password_hash for user in users)
    assert preview_row is not None
    assert preview_row.status == "imported"
    assert preview_row.used_at is not None
    assert "temporary_password" not in str(preview_row.summary)

    generated_login = await login(client, generated_username, temporary_password)
    supplied_login = await login(client, supplied_username, supplied_password)
    assert generated_login.status_code == 200
    assert supplied_login.status_code == 200
    assert generated_login.json()["user"]["must_change_password"] is True
    assert supplied_login.json()["user"]["must_change_password"] is True

    repeated = await client.post(
        IMPORT_PATH,
        headers=headers,
        json={
            "preview_id": preview["preview_id"],
            "preview_hash": preview["preview_hash"],
        },
    )
    assert repeated.status_code == 409
    assert repeated.json()["code"] == "IMPORT_ALREADY_COMPLETED"


async def test_import_rejects_tampering_other_admin_and_database_conflict_without_partial_rows(
    client, app, admin_user, user_factory
) -> None:
    headers = await admin_headers(client, admin_user)
    suffix = uuid4().hex[:8]

    tampered_row = f"tampered_{suffix},Tampered,,Learning,Group T\n"
    tampered_preview_response = await upload_csv(client, headers, CSV_HEADER + tampered_row)
    assert tampered_preview_response.status_code == 200
    tampered_preview = tampered_preview_response.json()
    tampered = await client.post(
        IMPORT_PATH,
        headers=headers,
        json={"preview_id": tampered_preview["preview_id"], "preview_hash": "0" * 64},
    )
    assert tampered.status_code == 409
    assert tampered.json()["code"] == "IMPORT_PREVIEW_MISMATCH"

    owner_row = f"owner_{suffix},Owner,,Learning,Group O\n"
    owner_preview_response = await upload_csv(client, headers, CSV_HEADER + owner_row)
    owner_preview = owner_preview_response.json()
    second_admin = await user_factory(role="admin", display_name="Second Import Admin")
    second_headers = await admin_headers(client, second_admin)
    hidden = await client.get(
        f"{IMPORT_PATH}/{owner_preview['preview_id']}",
        headers=second_headers,
    )
    assert hidden.status_code == 404
    assert hidden.json()["code"] == "IMPORT_PREVIEW_NOT_FOUND"

    conflict_username = f"conflict_{suffix}"
    rollback_username = f"rollback_{suffix}"
    conflict_csv = CSV_HEADER + (
        f"{conflict_username},Conflict,,Learning,Group X\n"
        f"{rollback_username},Must Not Exist,,Learning,Group X\n"
    )
    conflict_preview_response = await upload_csv(client, headers, conflict_csv)
    assert conflict_preview_response.status_code == 200
    conflict_preview = conflict_preview_response.json()
    assert conflict_preview["valid_rows"] == 2

    await user_factory(username=conflict_username, display_name="Created After Preview")
    conflict_response = await client.post(
        IMPORT_PATH,
        headers=headers,
        json={
            "preview_id": conflict_preview["preview_id"],
            "preview_hash": conflict_preview["preview_hash"],
        },
    )
    assert conflict_response.status_code == 409
    assert conflict_response.json()["code"] == "IMPORT_USERNAME_CONFLICT"

    async with app.state.session_factory() as db:
        rollback_user = await db.scalar(
            select(User).where(User.username_normalized == rollback_username.lower())
        )
    assert rollback_user is None


async def test_expired_preview_returns_gone_and_keeps_real_status(client, app, admin_user) -> None:
    headers = await admin_headers(client, admin_user)
    suffix = uuid4().hex[:8]
    csv_content = CSV_HEADER + f"expires_{suffix},Expired Preview,,Learning,Group Z\n"
    preview_response = await upload_csv(client, headers, csv_content)
    assert preview_response.status_code == 200
    preview = preview_response.json()

    async with app.state.session_factory() as db:
        record = await db.get(ImportPreview, preview["preview_id"])
        record.expires_at = record.created_at
        await db.commit()

    expired = await client.post(
        IMPORT_PATH,
        headers=headers,
        json={
            "preview_id": preview["preview_id"],
            "preview_hash": preview["preview_hash"],
        },
    )
    assert expired.status_code == 410
    assert expired.json()["code"] == "IMPORT_PREVIEW_EXPIRED"

    status_response = await client.get(
        f"{IMPORT_PATH}/{preview['preview_id']}",
        headers=headers,
    )
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "expired"
