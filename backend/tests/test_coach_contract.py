async def test_openapi_publishes_coach_contract(app) -> None:
    document = app.openapi()
    paths = document["paths"]
    expected = {
        "/api/v1/coach/conversations",
        "/api/v1/coach/conversations/{conversation_id}",
        "/api/v1/coach/conversations/{conversation_id}/messages",
        "/api/v1/coach/messages/{message_id}",
        "/api/v1/coach/streams/{message_id}",
        "/api/v1/coach/action-receipts/{receipt_id}",
        "/api/v1/coach/action-receipts/{receipt_id}/undo",
    }
    assert expected.issubset(paths)
    assert "CoachAcceptedResponse" in document["components"]["schemas"]
    assert "CoachActionReceiptResponse" in document["components"]["schemas"]
    assert "CoachStreamEventResponse" in document["components"]["schemas"]
    assert not any("admin/coach" in path for path in paths)
    stream_operation = paths["/api/v1/coach/streams/{message_id}"]["get"]
    assert "text/event-stream" in stream_operation["responses"]["200"]["content"]


async def test_cors_preflight_allows_coach_idempotency_key(client) -> None:
    response = await client.options(
        "/api/v1/coach/conversations/00000000-0000-0000-0000-000000000000/messages",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": (
                "Authorization, Content-Type, Idempotency-Key, Last-Event-ID"
            ),
        },
    )
    assert response.status_code == 200
    allowed = response.headers["access-control-allow-headers"].lower()
    assert "idempotency-key" in allowed
    assert "last-event-id" in allowed
