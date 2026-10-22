from redis.asyncio import Redis


async def test_liveness_echoes_valid_request_id(client) -> None:
    response = await client.get("/health/live", headers={"X-Request-ID": "test.live-001"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "test.live-001"
    assert response.json() == {
        "status": "ok",
        "service": "AI English Learning Tool",
        "version": "0.1.0",
    }


async def test_readiness_checks_real_postgresql_redis_and_configuration(client) -> None:
    response = await client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["components"]["configuration"]["status"] == "ok"
    assert body["components"]["database"]["status"] == "ok"
    assert body["components"]["redis"]["status"] == "ok"


async def test_readiness_failure_uses_error_envelope(app, client) -> None:
    original_redis = app.state.redis
    unavailable_redis = Redis.from_url(
        "redis://127.0.0.1:6399/0",
        socket_connect_timeout=0.1,
        socket_timeout=0.1,
    )
    app.state.redis = unavailable_redis
    try:
        response = await client.get("/health/ready")
    finally:
        app.state.redis = original_redis
        await unavailable_redis.aclose()

    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_NOT_READY"
    assert response.json()["details"]["components"]["redis"]["status"] == "error"
    assert response.json()["request_id"] == response.headers["x-request-id"]
