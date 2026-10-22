async def test_openapi_is_available_and_contains_health_routes(client) -> None:
    response = await client.get("/api/v1/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/health/live" in paths
    assert "/health/ready" in paths
    assert "/api/v1" in paths


async def test_service_metadata_is_available(client) -> None:
    response = await client.get("/api/v1")

    assert response.status_code == 200
    assert response.json() == {
        "name": "AI English Learning Tool",
        "version": "0.1.0",
        "environment": "test",
        "api_version": "v1",
    }


async def test_unknown_route_uses_standard_error_and_request_id(client) -> None:
    response = await client.get("/does-not-exist", headers={"X-Request-ID": "error-route-1"})

    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"code", "message", "details", "request_id"}
    assert body["code"] == "NOT_FOUND"
    assert body["request_id"] == "error-route-1"
    assert response.headers["x-request-id"] == "error-route-1"


async def test_validation_error_uses_standard_error(app, client) -> None:
    @app.get("/__test/validate")
    async def validate(value: int) -> dict[str, int]:
        return {"value": value}

    response = await client.get("/__test/validate?value=not-an-integer")

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["details"]
    assert body["request_id"] == response.headers["x-request-id"]


async def test_cors_allows_configured_origin(client) -> None:
    response = await client.options(
        "/health/live",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["access-control-allow-credentials"] == "true"


async def test_unexpected_error_is_hidden_from_client(app, client) -> None:
    @app.get("/__test/unexpected-error")
    async def unexpected_error() -> None:
        raise RuntimeError("secret internal detail")

    response = await client.get("/__test/unexpected-error", headers={"X-Request-ID": "error-500"})

    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "INTERNAL_SERVER_ERROR"
    assert body["message"] == "An unexpected internal error occurred."
    assert "secret internal detail" not in str(body)
    assert body["request_id"] == "error-500"
    assert response.headers["x-request-id"] == "error-500"
