def test_openapi_publishes_notification_inbox_and_preferences_contract(app) -> None:
    document = app.openapi()
    paths = document["paths"]
    expected = {
        "/api/v1/notifications",
        "/api/v1/notifications/{notification_id}/read",
        "/api/v1/notifications/read-all",
        "/api/v1/notifications/preferences",
        "/api/v1/notifications/unread-count",
    }
    assert expected.issubset(paths)
    notification = document["components"]["schemas"]["NotificationResponse"]["properties"]
    assert {"category", "title", "body", "status", "read_at"}.issubset(notification)
    prefs = document["components"]["schemas"]["NotificationPreferencesResponse"]["properties"]
    assert {"categories", "dnd_start", "dnd_end", "daily_limit", "timezone"}.issubset(prefs)
    assert not any(path.startswith("/api/v1/admin/notifications") for path in paths)
