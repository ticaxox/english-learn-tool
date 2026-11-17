import httpx
from sqlalchemy import select

from app.models.identity import AuditLog, RefreshToken
from tests.conftest import TEST_NEW_PASSWORD, TEST_USER_PASSWORD

ORIGIN = "http://testserver"
LOGIN_PATH = "/api/v1/auth/login"
REFRESH_PATH = "/api/v1/auth/refresh"
LOGOUT_PATH = "/api/v1/auth/logout"
CHANGE_PASSWORD_PATH = "/api/v1/auth/change-password"
ME_PATH = "/api/v1/auth/me"


async def login(client: httpx.AsyncClient, username: str, password: str = TEST_USER_PASSWORD):
    return await client.post(
        LOGIN_PATH,
        json={"username": username, "password": password},
    )


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_pixel_avatar_choice_round_trips_and_validates(client, user_factory) -> None:
    member = await user_factory(role="member", must_change_password=False)
    logged_in = await login(client, member.username)
    assert logged_in.status_code == 200
    token = logged_in.json()["access_token"]
    assert logged_in.json()["user"]["avatar"] == "pumpkin"

    changed = await client.patch(
        "/api/v1/auth/me/avatar",
        headers=bearer(token),
        json={"avatar": "witch"},
    )
    assert changed.status_code == 200
    assert changed.json()["avatar"] == "witch"

    me = await client.get(ME_PATH, headers=bearer(token))
    assert me.status_code == 200
    assert me.json()["avatar"] == "witch"

    invalid = await client.patch(
        "/api/v1/auth/me/avatar",
        headers=bearer(token),
        json={"avatar": "not-a-sprite"},
    )
    assert invalid.status_code == 422
    assert me.json()["avatar"] == "witch"


async def test_initial_password_change_flow_and_cookie_contract(client, user_factory) -> None:
    admin_user = await user_factory(role="admin", must_change_password=True)
    response = await login(client, admin_user.username)

    assert response.status_code == 200
    session = response.json()
    assert session["user"]["must_change_password"] is True
    set_cookie_headers = response.headers.get_list("set-cookie")
    refresh_cookie = next(
        header for header in set_cookie_headers if header.startswith("refresh_token=")
    )
    csrf_cookie = next(header for header in set_cookie_headers if header.startswith("csrf_token="))
    assert "HttpOnly" in refresh_cookie
    assert "SameSite=lax" in refresh_cookie
    assert "Path=/api/v1/auth/refresh" in refresh_cookie
    assert "HttpOnly" not in csrf_cookie
    assert "Path=/" in csrf_cookie
    overview_request = client.build_request("GET", "/overview")
    admin_request = client.build_request("GET", "/admin/users")
    overview_cookies = overview_request.headers.get("cookie", "")
    admin_cookies = admin_request.headers.get("cookie", "")
    assert f"csrf_token={session['csrf_token']}" in overview_cookies
    assert f"csrf_token={session['csrf_token']}" in admin_cookies
    assert "refresh_token=" not in overview_cookies

    first_token_response = await client.get(ME_PATH, headers=bearer(session["access_token"]))
    assert first_token_response.status_code == 200
    assert first_token_response.json()["must_change_password"] is True

    blocked = await client.get(
        "/api/v1/admin/users",
        headers=bearer(session["access_token"]),
    )
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "AUTH_PASSWORD_CHANGE_REQUIRED"

    changed = await client.post(
        CHANGE_PASSWORD_PATH,
        headers=bearer(session["access_token"]),
        json={
            "old_password": TEST_USER_PASSWORD,
            "new_password": TEST_NEW_PASSWORD,
        },
    )
    assert changed.status_code == 204
    assert any(
        header.startswith("refresh_token=") for header in changed.headers.get_list("set-cookie")
    )

    assert (await client.get(ME_PATH, headers=bearer(session["access_token"]))).status_code == 401

    relogin = await login(client, admin_user.username, TEST_NEW_PASSWORD)
    assert relogin.status_code == 200
    assert relogin.json()["user"]["must_change_password"] is False
    admin_access = await client.get(
        "/api/v1/admin/users",
        headers=bearer(relogin.json()["access_token"]),
    )
    assert admin_access.status_code == 200


async def test_change_password_rejects_wrong_old_and_unchanged_password(
    client, app, admin_user
) -> None:
    login_response = await login(client, admin_user.username)
    headers = bearer(login_response.json()["access_token"])

    wrong_old = await client.post(
        CHANGE_PASSWORD_PATH,
        headers=headers,
        json={"old_password": "Wrong-Pass-123!", "new_password": TEST_NEW_PASSWORD},
    )
    assert wrong_old.status_code == 401
    assert wrong_old.json()["code"] == "AUTH_INVALID_CREDENTIALS"

    unchanged = await client.post(
        CHANGE_PASSWORD_PATH,
        headers=headers,
        json={"old_password": TEST_USER_PASSWORD, "new_password": TEST_USER_PASSWORD},
    )
    assert unchanged.status_code == 422
    assert unchanged.json()["code"] == "PASSWORD_UNCHANGED"

    async with app.state.session_factory() as db:
        events = list(
            (
                await db.scalars(
                    select(AuditLog)
                    .where(
                        AuditLog.action == "auth.password.change",
                        AuditLog.target_id == admin_user.id,
                    )
                    .order_by(AuditLog.created_at)
                )
            ).all()
        )
    assert [event.reason_code for event in events] == [
        "AUTH_INVALID_CREDENTIALS",
        "PASSWORD_UNCHANGED",
    ]
    assert all(event.outcome == "failure" for event in events)
    assert all("password" not in str(event.context).lower() for event in events)


async def test_change_username_checks_password_uniqueness_and_login(
    client, admin_user, user_factory
) -> None:
    login_response = await login(client, admin_user.username)
    headers = bearer(login_response.json()["access_token"])

    other = await user_factory(role="member")
    taken = await client.patch(
        ME_PATH,
        headers=headers,
        json={"username": other.username},
    )
    assert taken.status_code == 409
    assert taken.json()["code"] == "USERNAME_TAKEN"

    unchanged = await client.patch(
        ME_PATH,
        headers=headers,
        json={"username": admin_user.username},
    )
    assert unchanged.status_code == 422
    assert unchanged.json()["code"] == "USERNAME_UNCHANGED"

    changed = await client.patch(
        ME_PATH,
        headers=headers,
        json={"username": "renamed_admin"},
    )
    assert changed.status_code == 200
    assert changed.json()["username"] == "renamed_admin"

    assert (await login(client, "renamed_admin")).status_code == 200
    assert (await login(client, admin_user.username)).status_code == 401


async def test_login_errors_are_uniform_and_disabled_accounts_cannot_authenticate(
    client, app, member_user
) -> None:
    wrong_password = await login(client, member_user.username, "Wrong-Pass-123!")
    assert wrong_password.status_code == 401
    assert wrong_password.json()["code"] == "AUTH_INVALID_CREDENTIALS"
    assert wrong_password.json()["message"] == "Username or password is incorrect."

    async with app.state.session_factory() as db:
        member = await db.get(type(member_user), member_user.id)
        member.status = "disabled"
        await db.commit()

    disabled = await login(client, member_user.username)
    assert disabled.status_code == 401
    assert disabled.json()["code"] == "AUTH_INVALID_CREDENTIALS"
    assert disabled.json()["message"] == wrong_password.json()["message"]


async def test_login_rate_limit_uses_real_redis_and_returns_retry_after(
    client, member_user
) -> None:
    for _ in range(5):
        failed = await login(client, member_user.username, "Wrong-Pass-123!")
        assert failed.status_code == 401

    throttled = await login(client, member_user.username, "Wrong-Pass-123!")
    assert throttled.status_code == 429
    assert throttled.json()["code"] == "AUTH_RATE_LIMITED"
    assert int(throttled.headers["retry-after"]) >= 1

    correct_while_throttled = await login(client, member_user.username)
    assert correct_while_throttled.status_code == 429


async def test_refresh_rotation_denies_a_stale_tab_without_revoking_the_family(
    app, admin_user
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        login_response = await login(client, admin_user.username)
        assert login_response.status_code == 200
        initial = login_response.json()
        old_refresh = client.cookies.get("refresh_token", path="/api/v1/auth/refresh")
        old_csrf = initial["csrf_token"]
        assert old_refresh

        rotated = await client.post(
            REFRESH_PATH,
            headers={"Origin": ORIGIN, "X-CSRF-Token": old_csrf},
        )
        assert rotated.status_code == 200
        new_session = rotated.json()
        assert new_session["access_token"] != initial["access_token"]
        assert new_session["csrf_token"] != old_csrf
        current_refresh = client.cookies.get("refresh_token", path="/api/v1/auth/refresh")
        assert current_refresh and current_refresh != old_refresh

        async with app.state.session_factory() as db:
            records = list(
                (
                    await db.scalars(
                        select(RefreshToken)
                        .where(RefreshToken.user_id == admin_user.id)
                        .order_by(RefreshToken.created_at)
                    )
                ).all()
            )
        assert len(records) == 2
        assert {record.token_hash for record in records}.isdisjoint({old_refresh, current_refresh})
        old_record = next(record for record in records if record.revoked_at is not None)
        assert old_record.revoked_reason == "rotated"
        assert old_record.replaced_by_id is not None

        grace_replay = await client.post(
            REFRESH_PATH,
            headers={
                "Origin": ORIGIN,
                "X-CSRF-Token": old_csrf,
                "Cookie": f"refresh_token={old_refresh}; csrf_token={old_csrf}",
            },
        )
        assert grace_replay.status_code == 200
        grace_session = grace_replay.json()
        assert grace_session["access_token"] != new_session["access_token"]

        app.state.settings.refresh_reuse_grace_seconds = 0
        replay = await client.post(
            REFRESH_PATH,
            headers={
                "Origin": ORIGIN,
                "X-CSRF-Token": old_csrf,
                "Cookie": f"refresh_token={old_refresh}; csrf_token={old_csrf}",
            },
        )
        assert replay.status_code == 401
        assert replay.json()["code"] == "AUTH_REFRESH_STALE"

        surviving_access = await client.get(
            ME_PATH,
            headers=bearer(grace_session["access_token"]),
        )
        assert surviving_access.status_code == 200

        async with app.state.session_factory() as db:
            events = list(
                (
                    await db.scalars(
                        select(AuditLog)
                        .where(AuditLog.action == "auth.refresh.stale")
                        .order_by(AuditLog.created_at.desc())
                        .limit(1)
                    )
                ).all()
            )
        assert len(events) == 1
        assert events[0].outcome == "failure"
        assert events[0].reason_code == "AUTH_REFRESH_STALE"


async def test_refresh_and_logout_enforce_origin_and_double_submit_csrf(client, admin_user) -> None:
    login_response = await login(client, admin_user.username)
    session = login_response.json()
    refresh_token = client.cookies.get("refresh_token", path="/api/v1/auth/refresh")
    csrf_token = session["csrf_token"]
    assert refresh_token

    invalid_origin = await client.post(
        REFRESH_PATH,
        headers={"Origin": "https://evil.example", "X-CSRF-Token": csrf_token},
    )
    assert invalid_origin.status_code == 403
    assert invalid_origin.json()["code"] == "AUTH_ORIGIN_INVALID"

    missing_csrf = await client.post(REFRESH_PATH, headers={"Origin": ORIGIN})
    assert missing_csrf.status_code == 403
    assert missing_csrf.json()["code"] == "AUTH_CSRF_FAILED"

    wrong_csrf = await client.post(
        REFRESH_PATH,
        headers={"Origin": ORIGIN, "X-CSRF-Token": "tampered-token"},
    )
    assert wrong_csrf.status_code == 403
    assert wrong_csrf.json()["code"] == "AUTH_CSRF_FAILED"

    rotated = await client.post(
        REFRESH_PATH,
        headers={"Origin": ORIGIN, "X-CSRF-Token": csrf_token},
    )
    assert rotated.status_code == 200
    refreshed = rotated.json()

    logout_without_csrf = await client.post(
        LOGOUT_PATH,
        headers={**bearer(refreshed["access_token"]), "Origin": ORIGIN},
    )
    assert logout_without_csrf.status_code == 403
    assert logout_without_csrf.json()["code"] == "AUTH_CSRF_FAILED"

    logged_out = await client.post(
        LOGOUT_PATH,
        headers={
            **bearer(refreshed["access_token"]),
            "Origin": ORIGIN,
            "X-CSRF-Token": refreshed["csrf_token"],
        },
    )
    assert logged_out.status_code == 204
    assert (await client.get(ME_PATH, headers=bearer(refreshed["access_token"]))).status_code == 401

    replay = await client.post(
        REFRESH_PATH,
        headers={
            "Origin": ORIGIN,
            "X-CSRF-Token": refreshed["csrf_token"],
            "Cookie": (f"refresh_token={refresh_token}; csrf_token={refreshed['csrf_token']}"),
        },
    )
    assert replay.status_code == 401


async def test_persisted_cookies_restore_session_after_browser_restart(app, admin_user) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as browser:
        login_response = await login(browser, admin_user.username)
        assert login_response.status_code == 200
        session = login_response.json()
        persisted_cookies = httpx.Cookies(browser.cookies)

    assert persisted_cookies.get("refresh_token") is not None
    assert persisted_cookies.get("csrf_token") == session["csrf_token"]

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        cookies=persisted_cookies,
    ) as restored_browser:
        refresh_request = restored_browser.build_request(
            "POST",
            REFRESH_PATH,
            headers={"Origin": ORIGIN, "X-CSRF-Token": session["csrf_token"]},
        )
        spa_request = restored_browser.build_request("GET", "/admin/users")

        assert "refresh_token=" in refresh_request.headers.get("cookie", "")
        assert f"csrf_token={session['csrf_token']}" in refresh_request.headers.get("cookie", "")
        assert f"csrf_token={session['csrf_token']}" in spa_request.headers.get("cookie", "")
        assert "refresh_token=" not in spa_request.headers.get("cookie", "")

        refreshed = await restored_browser.post(REFRESH_PATH, headers=refresh_request.headers)
        assert refreshed.status_code == 200
        recovered = refreshed.json()
        assert recovered["user"]["username"] == admin_user.username
        assert recovered["csrf_token"] != session["csrf_token"]
        admin_list = await restored_browser.get(
            "/api/v1/admin/users",
            headers=bearer(recovered["access_token"]),
        )
        assert admin_list.status_code == 200
