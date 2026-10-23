"""Contract-level guarantees: pinned FSRS, published paths, and local dates."""

from __future__ import annotations

import tomllib
from datetime import UTC, datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]

LEARNING_PATHS = (
    "/api/v1/users/me/profile",
    "/api/v1/learning/today",
    "/api/v1/learning/daily-plan/ensure",
    "/api/v1/learning/heartbeat",
    "/api/v1/learning/stats",
    "/api/v1/learning/events",
    "/api/v1/memory/config",
    "/api/v1/memory/sessions",
    "/api/v1/memory/sessions/{session_id}",
    "/api/v1/memory/sessions/{session_id}/events",
    "/api/v1/memory/sessions/{session_id}/complete",
    "/api/v1/memory/words/{state_id}/master",
    "/api/v1/memory/words/{state_id}/restore",
    "/api/v1/memory/mistakes",
    "/api/v1/memory/mistakes/{entry_id}/priority",
)


def test_fsrs_is_pinned_in_pyproject_and_lock() -> None:
    project = tomllib.loads((BACKEND_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = project["project"]["dependencies"]
    assert "fsrs==6.3.2" in dependencies, dependencies

    lock = (BACKEND_DIR / "uv.lock").read_text(encoding="utf-8")
    assert 'name = "fsrs"\nversion = "6.3.2"' in lock
    assert '{ name = "fsrs", specifier = "==6.3.2" }' in lock
    # No floating or caret version may sneak back in.
    assert "fsrs>=" not in lock
    assert "fsrs = " not in lock


def test_openapi_publishes_every_learning_and_memory_path(app) -> None:
    document = app.openapi()
    paths = document["paths"]
    for path in LEARNING_PATHS:
        assert path in paths, path
    event_post = paths["/api/v1/memory/sessions/{session_id}/events"]["post"]
    header_names = {parameter["name"] for parameter in event_post.get("parameters", [])}
    assert "Idempotency-Key" in header_names

    heartbeat = paths["/api/v1/learning/heartbeat"]["post"]
    assert "Idempotency-Key" in {parameter["name"] for parameter in heartbeat["parameters"]}

    schemas = document["components"]["schemas"]
    for forbidden in ("fsrs_card", "stability", "difficulty", "due_at"):
        assert forbidden not in schemas["SessionEventRequest"]["properties"]


def test_import_and_delete_paths_still_describe_conflict_contracts(app) -> None:
    document = app.openapi()
    assert "/api/v1/wordbooks/import/preview" in document["paths"]
    assert "/api/v1/wordbooks/{wordbook_id}" in document["paths"]
    delete_responses = document["paths"]["/api/v1/wordbooks/{wordbook_id}"]["delete"]["responses"]
    assert "409" in delete_responses


def test_local_date_uses_asia_shanghai_across_the_utc_boundary() -> None:
    from app.services.learning import local_date_for

    class _Settings:
        app_timezone = "Asia/Shanghai"

    class _Profile:
        timezone = "Asia/Shanghai"

    class _User:
        profile = _Profile()

    # 2026-10-22T16:30Z is 2026-10-23 00:30 in Shanghai: the plan must roll over.
    before = datetime(2026, 10, 22, 15, 59, tzinfo=UTC)
    after = datetime(2026, 10, 22, 16, 1, tzinfo=UTC)
    assert local_date_for(_Settings(), _User(), now=before).isoformat() == "2026-10-22"
    assert local_date_for(_Settings(), _User(), now=after).isoformat() == "2026-10-23"


def test_tracked_openapi_contract_matches_the_application(app) -> None:
    import hashlib
    import json

    tracked = json.loads((BACKEND_DIR / "openapi.json").read_text(encoding="utf-8"))
    live = app.openapi()

    def canonical(value: dict) -> bytes:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )

    assert (
        hashlib.sha256(canonical(tracked)).hexdigest()
        == hashlib.sha256(canonical(live)).hexdigest()
    )
    assert len(tracked["paths"]) == len(live["paths"])
