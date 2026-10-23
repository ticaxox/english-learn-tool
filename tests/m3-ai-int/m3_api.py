#!/usr/bin/env python3
"""T-QA-002 M3 live API and browser acceptance runner."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import secrets
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import asyncpg
import httpx

RUNTIME_ENV = Path(os.environ["RUNTIME_ENV"]).resolve()
for line in RUNTIME_ENV.read_text(encoding="utf-8").splitlines():
    if "=" in line:
        name, value = line.split("=", 1)
        os.environ.setdefault(name, value)
PG_DSN = os.environ["LIVE_PG_DSN"]
REDIS_URL = os.environ.get("LIVE_REDIS_URL", "redis://127.0.0.1:55445/0")
SQLALCHEMY_DSN = PG_DSN.replace("postgresql://", "postgresql+asyncpg://", 1) if PG_DSN.startswith("postgresql://") else PG_DSN
os.environ["DATABASE_URL"] = SQLALCHEMY_DSN
os.environ["REDIS_URL"] = REDIS_URL
os.environ["APP_ENV"] = "test"
os.environ.setdefault("CORS_ORIGINS", "http://127.0.0.1:8092,http://127.0.0.1:8093")
os.environ.setdefault("FRONTEND_BASE_URL", "http://127.0.0.1:8092")
os.environ.setdefault("APP_BASE_URL", "http://127.0.0.1:8092")

API_BASE = os.environ.get("LIVE_API_BASE_URL", "http://127.0.0.1:8092").rstrip("/") + "/api/v1"
CONTROL_URL = os.environ.get("LIVE_PROVIDER_CONTROL_URL", "http://127.0.0.1:18081")
PROVIDER_BASE_URL = os.environ.get("LIVE_PROVIDER_BASE_URL", "http://a30-m3-ai-provider:18080/v1")
EVIDENCE_ROOT = Path(os.environ["EVIDENCE_DIR"]).resolve()
RUN_ID = os.environ.get("LIVE_RUN_ID", f"m3-{datetime.now(UTC):%Y%m%d%H%M%S}")
REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parents[2])).resolve()
RUN_DIR = EVIDENCE_ROOT / "results" / RUN_ID
LOG_DIR = EVIDENCE_ROOT / "logs"
SHOT_DIR = RUN_DIR / "screenshots"
for directory in (RUN_DIR, LOG_DIR, SHOT_DIR, EVIDENCE_ROOT / "runtime"):
    directory.mkdir(parents=True, exist_ok=True)

STARTED_AT = datetime.now(UTC).isoformat()


class CheckFailure(RuntimeError):
    pass


class Evidence:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []
        self.notes: list[dict[str, Any]] = []
        self.network: list[dict[str, Any]] = []
        self.artifacts: dict[str, Any] = {}

    def check(self, name: str, condition: bool, **details: Any) -> bool:
        status = "PASS" if condition else "FAIL"
        self.checks.append({"name": name, "status": status, "details": details})
        print(f"[{status}] {name}")
        return bool(condition)

    def note(self, name: str, **details: Any) -> None:
        self.notes.append({"name": name, "at": datetime.now(UTC).isoformat(), "details": details})
        print(f"[INFO] {name}")

    def finish(self, *, error: str | None = None) -> dict[str, Any]:
        failed = [item for item in self.checks if item["status"] != "PASS"]
        return {
            "task": "T-QA-002", "phase": "M3", "run_id": RUN_ID,
            "started_at": STARTED_AT, "finished_at": datetime.now(UTC).isoformat(),
            "status": "PASS" if not failed and error is None else "FAIL",
            "error": error, "checks": self.checks, "notes": self.notes,
            "network": self.network, "artifacts": self.artifacts,
        }


EVIDENCE = Evidence()


def safe_body(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {"content_type": response.headers.get("content-type")}
    if not isinstance(body, dict):
        return {"body_type": type(body).__name__, "length": len(body) if isinstance(body, list) else None}
    summary: dict[str, Any] = {"keys": sorted(body.keys())}
    for key in ("code", "status", "id", "job_id", "session_id", "submission_id", "practice_type", "score", "error_code", "retryable", "unread_count", "updated_count"):
        if key in body:
            summary[key] = body[key]
    for key in ("access_token", "refresh_token", "csrf_token", "temporary_password", "api_key", "api_key_masked"):
        if key in body:
            summary[f"{key}_present"] = bool(body[key])
    if isinstance(body.get("user"), dict):
        summary["role"] = body["user"].get("role")
        summary["must_change_password"] = body["user"].get("must_change_password")
    if isinstance(body.get("items"), list):
        summary["item_count"] = len(body["items"])
    if isinstance(body.get("quotas"), list):
        summary["quota_count"] = len(body["quotas"])
    return summary


class Client:
    def __init__(self) -> None:
        self.http = httpx.Client(base_url=API_BASE, timeout=120.0)

    def close(self) -> None:
        self.http.close()

    def request(self, method: str, path: str, *, label: str, token: str | None = None, idempotency_key: str | None = None, expect: int | tuple[int, ...] | None = None, **kwargs: Any) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}) or {})
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        started = time.perf_counter()
        response = self.http.request(method, path, headers=headers, **kwargs)
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        entry = {"label": label, "method": method, "path": path, "status_code": response.status_code, "request_id": response.headers.get("X-Request-ID"), "duration_ms": elapsed, "body": safe_body(response)}
        EVIDENCE.network.append(entry)
        if expect is not None:
            allowed = expect if isinstance(expect, tuple) else (expect,)
            if response.status_code not in allowed:
                raise CheckFailure(f"{label}: expected {allowed}, got {response.status_code}: {response.text[:1000]}")
        return response


def new_key(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def login(client: Client, username: str, password: str, *, label: str) -> dict[str, Any]:
    response = client.request("POST", "/auth/login", label=label, json={"username": username, "password": password})
    if response.status_code != 200:
        raise CheckFailure(f"{label}: {response.status_code} {response.text[:600]}")
    return response.json()


def rotate(client: Client, username: str, initial: str, *, prefix: str) -> dict[str, Any]:
    rotated = initial + ".Rotated1"
    response = client.request("POST", "/auth/login", label=f"{prefix}-login-initial", json={"username": username, "password": initial})
    if response.status_code != 200:
        response = client.request("POST", "/auth/login", label=f"{prefix}-login-rotated", json={"username": username, "password": rotated})
        if response.status_code != 200:
            raise CheckFailure(f"{prefix}: login failed with both passwords")
    session = response.json()
    if session["user"]["must_change_password"]:
        changed = client.request("POST", "/auth/change-password", label=f"{prefix}-change", token=session["access_token"], json={"old_password": initial, "new_password": rotated})
        if changed.status_code not in (200, 204):
            raise CheckFailure(f"{prefix}: password change failed")
        session = login(client, username, rotated, label=f"{prefix}-relogin")
    EVIDENCE.check(f"auth.{prefix}.ready", bool(session.get("access_token")) and session["user"]["must_change_password"] is False, role=session["user"]["role"])
    return {"session": session, "password": rotated}


def create_member(client: Client, admin_token: str, *, username: str, password: str, display: str) -> dict[str, Any]:
    response = client.request("POST", "/admin/users", label=f"create-{username}", token=admin_token, json={"username": username, "display_name": display, "role": "member", "password": password, "department": "QA", "learning_group": "M3"})
    if response.status_code not in (200, 201, 409):
        raise CheckFailure(f"create member {username}: {response.status_code} {response.text[:600]}")
    return response.json() if response.status_code != 409 else {}


def set_provider_modes(modes: dict[str, str], default: str = "ok") -> dict[str, Any]:
    response = httpx.post(f"{CONTROL_URL}/control/config", json={"modes": modes, "default_mode": default}, timeout=10)
    response.raise_for_status()
    return response.json()


def provider_stats() -> dict[str, Any]:
    response = httpx.get(f"{CONTROL_URL}/control/stats", timeout=10)
    response.raise_for_status()
    return response.json()

def csv_bytes(entries: list[tuple[str, str, str, str, str, str]]) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["headword", "phonetic", "part_of_speech", "definition_zh", "definition_en", "example"])
    writer.writerows(entries)
    return output.getvalue().encode("utf-8")


def poll_job(client: Client, token: str, job_id: str, *, label: str, timeout: float = 120.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.request("GET", f"/ai/jobs/{job_id}", label=f"{label}-poll", token=token, expect=200).json()
        if body["status"] in {"succeeded", "failed", "cancelled", "stale"}:
            return body
        time.sleep(0.35)
    raise CheckFailure(f"{label}: job did not finish")


def poll_practice(client: Client, token: str, session_id: str, *, label: str, timeout: float = 120.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.request("GET", f"/practice/sessions/{session_id}", label=f"{label}-poll", token=token, expect=200).json()
        if body["status"] in {"ready", "failed", "cancelled"}:
            return body
        time.sleep(0.4)
    raise CheckFailure(f"{label}: practice session did not finish")


def poll_result(client: Client, token: str, session_id: str, *, label: str, timeout: float = 120.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.request("GET", f"/practice/sessions/{session_id}/result", label=f"{label}-poll", token=token, expect=200).json()
        if body["status"] in {"completed", "failed"}:
            return body
        time.sleep(0.4)
    raise CheckFailure(f"{label}: result did not finish")


def import_book(client: Client, admin_token: str, *, name: str, entries: list[tuple[str, str, str, str, str, str]]) -> dict[str, Any]:
    preview = client.request("POST", "/wordbooks/import/preview", label=f"import-preview-{name}", token=admin_token, files={"file": (f"{name}.csv", csv_bytes(entries), "text/csv")}, data={"visibility": "organization", "name": name, "description": "T-QA-002 synthetic"}, expect=201).json()
    confirm = client.request("POST", "/wordbooks/import", label=f"import-confirm-{name}", token=admin_token, idempotency_key=new_key("import"), json={"preview_id": preview["preview_id"], "preview_token": preview["preview_token"], "preview_hash": preview["preview_hash"], "name": name, "visibility": "organization"}, expect=202).json()
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        job = client.request("GET", f"/wordbooks/jobs/{confirm['job_id']}", label=f"import-{name}-poll", token=admin_token, expect=200).json()
        if job["status"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.4)
    else:
        raise CheckFailure("import job timeout")
    if job["status"] != "succeeded":
        raise CheckFailure(f"import failed: {job}")
    wordbook_id = job.get("wordbook_id") or job.get("result", {}).get("wordbook_id")
    if not wordbook_id:
        listing = client.request("GET", "/wordbooks", label="wordbook-list", token=admin_token, params={"limit": 100}, expect=200).json()
        wordbook_id = next(item["id"] for item in listing["items"] if item["name"] == name)
    detail = client.request("GET", f"/wordbooks/{wordbook_id}", label=f"detail-{name}", token=admin_token, params={"limit": 100}, expect=200).json()
    return {"id": str(wordbook_id), "name": name, "entries": detail["entries"]}


def create_provider(client: Client, admin_token: str, *, name: str, api_key: str, base_url: str = PROVIDER_BASE_URL, model_id: str = "fake-m3-model", priority: int = 10, is_default: bool = True) -> dict[str, Any]:
    response = client.request("POST", "/admin/ai/providers", label=f"create-provider-{name}", token=admin_token, json={"name": name, "base_url": base_url, "api_key": api_key, "model_id": model_id, "priority": priority, "is_default": is_default, "timeout_seconds": 10}, expect=201)
    return response.json()


def create_practice(client: Client, token: str, *, practice_type: str, count: int, wordbook_id: str, key_prefix: str) -> dict[str, Any]:
    return client.request("POST", "/practice/sessions", label=f"{key_prefix}-create", token=token, idempotency_key=new_key(key_prefix), json={"practice_type": practice_type, "source": "whole_book", "count": count, "wordbook_id": wordbook_id}, expect=202).json()


async def enqueue_notification(member_id: str, *, category: str, dedupe_key: str, title: str, body: str, event_type: str) -> None:
    os.environ.setdefault("WORDBOOK_STORAGE_DIR", str(EVIDENCE_ROOT / "runtime" / "wordbooks"))
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.core.config import Settings
    from app.services.notifications import enqueue_notification_event, process_notification_outbox

    sqlalchemy_dsn = PG_DSN.replace("postgresql://", "postgresql+asyncpg://", 1) if PG_DSN.startswith("postgresql://") else PG_DSN
    engine = create_async_engine(sqlalchemy_dsn, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    try:
        async with factory() as session:
            await enqueue_notification_event(session, user_id=uuid.UUID(member_id), category=category, dedupe_key=dedupe_key, event_type=event_type, payload={"title": title, "body": body})
            await session.commit()
            await process_notification_outbox(session, Settings(), now=datetime.now(UTC))
    finally:
        await engine.dispose()


async def enqueue_scheduler_tick() -> None:
    from arq import create_pool
    from arq.connections import RedisSettings
    from app.workers.scheduler import SCHEDULER_QUEUE_NAME

    pool = await create_pool(RedisSettings.from_dsn(REDIS_URL))
    try:
        await pool.enqueue_job("scheduler_tick", _queue_name=SCHEDULER_QUEUE_NAME)
    finally:
        await pool.aclose()


async def wait_notification_row(pg: asyncpg.Connection, user_id: str, dedupe_key: str, *, timeout: float = 30.0) -> asyncpg.Record:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = await pg.fetchrow("SELECT status, suppressed_reason, category FROM notifications WHERE user_id=$1 AND dedupe_key=$2", uuid.UUID(user_id), dedupe_key)
        if row is not None:
            return row
        await asyncio.sleep(0.25)
    raise CheckFailure(f"notification row did not appear: {dedupe_key}")


async def wait_notification_count(pg: asyncpg.Connection, user_id: str, minimum: int, *, timeout: float = 30.0) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = int(await pg.fetchval("SELECT count(*) FROM notifications WHERE user_id=$1", uuid.UUID(user_id)) or 0)
        if value >= minimum:
            return value
        await asyncio.sleep(0.25)
    raise CheckFailure(f"notification count did not reach {minimum}")


def wait_for_notification(client: Client, token: str, *, category: str, timeout: float = 60.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.request("GET", "/notifications", label=f"notifications-wait-{category}", token=token, params={"limit": 100}, expect=200).json()
        match = next((item for item in body["items"] if item["category"] == category), None)
        if match:
            return match
        time.sleep(0.5)
    raise CheckFailure(f"notification {category} did not appear")

async def main() -> int:
    client = Client()
    pg: asyncpg.Connection | None = None
    wordbook: dict[str, Any] | None = None
    primary_provider: dict[str, Any] | None = None
    backup_provider: dict[str, Any] | None = None
    try:
        pg = await asyncpg.connect(PG_DSN)
        ready = httpx.get(f"{API_BASE.rsplit('/api/v1', 1)[0]}/health/ready", timeout=30).json()
        EVIDENCE.artifacts["environment"] = {"postgres": (await pg.fetchval("SELECT version()")).split(" on ")[0], "api_base": API_BASE, "provider_control": CONTROL_URL, "run_dir": str(RUN_DIR.relative_to(EVIDENCE_ROOT))}
        EVIDENCE.check("health.real-pg16-redis7", ready["status"] == "ready" and ready["components"]["database"]["status"] == "ok" and ready["components"]["redis"]["status"] == "ok", database=ready["components"]["database"]["status"], redis=ready["components"]["redis"]["status"])
        openapi = client.request("GET", "/openapi.json", label="openapi", expect=200).json()
        expected = {"/api/v1/admin/ai/providers", "/api/v1/admin/ai/prompts", "/api/v1/ai/jobs", "/api/v1/ai/usage/me", "/api/v1/practice/sessions", "/api/v1/practice/records", "/api/v1/notifications", "/api/v1/notifications/preferences"}
        EVIDENCE.check("contract.openapi.m3-frozen", openapi["openapi"] == "3.1.0" and expected.issubset(set(openapi["paths"])), paths=len(openapi["paths"]), schemas=len(openapi["components"]["schemas"]), missing=sorted(expected - set(openapi["paths"])))

        admin = rotate(client, os.environ.get("LIVE_ADMIN_USERNAME", "qa_m3_ai_admin"), os.environ["LIVE_ADMIN_PASSWORD"], prefix="admin")
        admin_token = admin["session"]["access_token"]
        stamp = datetime.now(UTC).strftime("%H%M%S")
        member_specs = {
            "api": (f"qa_m3_api_{stamp}", "Qa-M3-Api-2026!x"),
            "ui": (f"qa_m3_ui_{stamp}", "Qa-M3-Ui-2026!x"),
            "other": (f"qa_m3_other_{stamp}", "Qa-M3-Other-2026!x"),
        }
        members: dict[str, dict[str, Any]] = {}
        for name, (username, password) in member_specs.items():
            create_member(client, admin_token, username=username, password=password, display=f"M3 {name}")
            rotated = rotate(client, username, password, prefix=username)
            members[name] = {"id": rotated["session"]["user"]["id"], "username": username, "password": rotated["password"], "token": rotated["session"]["access_token"]}

        entries = [
            ("alpha", "/ˈælfə/", "n.", "阿尔法", "first", "Alpha is first."),
            ("bravo", "/ˈbrɑːvəʊ/", "n.", "布拉沃", "second", "Bravo is second."),
            ("charlie", "/ˈtʃɑːli/", "n.", "查理", "third", "Charlie is third."),
            ("delta", "/ˈdeltə/", "n.", "德尔塔", "fourth", "Delta is fourth."),
            ("echo", "/ˈekəʊ/", "n.", "回声", "fifth", "Echo is fifth."),
            ("foxtrot", "/ˈfɒkstrɒt/", "n.", "狐步", "sixth", "Foxtrot is sixth."),
            ("golf", "/ɡɒlf/", "n.", "高尔夫", "seventh", "Golf is seventh."),
            ("hotel", "/həʊˈtel/", "n.", "酒店", "eighth", "Hotel is eighth."),
        ]
        wordbook = import_book(client, admin_token, name=f"T-QA-002 Wordbook {stamp}", entries=entries)
        entry_ids = [str(item["id"]) for item in wordbook["entries"]]
        activate = client.request("POST", f"/wordbooks/{wordbook['id']}/activate", label="activate-wordbook", token=members["api"]["token"], expect=200)
        EVIDENCE.check("setup.member-activate-wordbook", activate.status_code == 200, wordbook_id=wordbook["id"])
        profile = client.request("PATCH", "/users/me/profile", label="profile", token=members["api"]["token"], json={"target_exam": "CET6", "exam_date": "2030-06-01", "daily_new_words": 8, "daily_study_minutes": 15}, expect=200).json()
        EVIDENCE.check("setup.profile", profile["daily_new_words"] == 8, target=profile["daily_new_words"])

        primary_key = "sk-m3-primary-" + secrets.token_urlsafe(18)
        backup_key = "sk-m3-backup-" + secrets.token_urlsafe(18)
        set_provider_modes({primary_key: "ok", backup_key: "ok"})
        primary_provider = create_provider(client, admin_token, name=f"M3 Primary {stamp}", api_key=primary_key, priority=1, is_default=True)
        backup_provider = create_provider(client, admin_token, name=f"M3 Backup {stamp}", api_key=backup_key, priority=2, is_default=False)
        tested = client.request("POST", f"/admin/ai/providers/{primary_provider['id']}/test", label="provider-test", token=admin_token, expect=200).json()
        EVIDENCE.check("provider.real-connection", tested["success"] is True and len(tested["models"]) >= 2, models=len(tested["models"]))
        provider_rows = client.request("GET", "/admin/ai/providers", label="provider-list", token=admin_token, expect=200).json()["items"]
        EVIDENCE.check("provider.key-masked", all(primary_key not in json.dumps(item, ensure_ascii=False) and item["api_key_masked"].startswith("sk-****") for item in provider_rows), count=len(provider_rows))
        stored = await pg.fetchrow("SELECT api_key_ciphertext FROM ai_providers WHERE id=$1", uuid.UUID(primary_provider["id"]))
        EVIDENCE.check("provider.key-encrypted-at-rest", stored is not None and primary_key not in stored["api_key_ciphertext"], ciphertext_length=len(stored["api_key_ciphertext"]))
        forbidden = client.request("GET", "/admin/ai/providers", label="member-provider-forbidden", token=members["api"]["token"])
        EVIDENCE.check("privacy.member-cannot-read-providers", forbidden.status_code == 403, status=forbidden.status_code)
        metadata = client.request("POST", "/admin/ai/providers", label="provider-metadata-blocked", token=admin_token, json={"name": "Metadata", "base_url": "http://169.254.169.254/v1", "api_key": primary_key, "model_id": "fake", "is_default": False})
        EVIDENCE.check("provider.metadata-url-blocked", metadata.status_code == 422 and metadata.json().get("code") == "AI_PROVIDER_URL_BLOCKED", status=metadata.status_code, code=metadata.json().get("code"))
        prompts = client.request("GET", "/admin/ai/prompts", label="prompt-list", token=admin_token, expect=200).json()["items"]
        EVIDENCE.check("prompt.seeded-five-keys", len(prompts) == 5 and {item["key"] for item in prompts} == {"practice_generation", "subjective_grading", "coach_reply", "challenge_plan", "json_repair"}, count=len(prompts))
        prompt_text = "T-QA-002 controlled prompt: return strict JSON only."
        updated_prompt = client.request("PUT", "/admin/ai/prompts/practice_generation", label="prompt-update", token=admin_token, json={"name": "M3 QA Practice Prompt", "summary": "Synthetic acceptance prompt", "template": prompt_text}, expect=200).json()
        EVIDENCE.check("prompt.overwrite", updated_prompt["template"] == prompt_text)
        promoted = client.request("PATCH", f"/admin/ai/providers/{backup_provider['id']}", label="promote-backup", token=admin_token, json={"is_default": True}, expect=200).json()
        provider_rows = client.request("GET", "/admin/ai/providers", label="provider-list-after-promote", token=admin_token, expect=200).json()["items"]
        EVIDENCE.check("provider.single-default-switch", promoted["is_default"] is True and sum(1 for item in provider_rows if item["is_default"]) == 1, default_count=sum(1 for item in provider_rows if item["is_default"]))
        client.request("PATCH", f"/admin/ai/providers/{primary_provider['id']}", label="restore-primary-default", token=admin_token, json={"is_default": True}, expect=200)

        # Idempotency, quota reservation, concurrency cap, cancel/release.
        subprocess.run(["wslc", "stop", "a30-m3-ai-worker"], capture_output=True, text=True, check=True)
        context = {"practice_type": "fill_blank", "count": 3, "source": "whole_book", "difficulty": None, "wordbook_id": wordbook["id"], "target_entry_ids": entry_ids[:3]}
        job_key_1 = new_key("job-idem")
        job_key_2 = new_key("job-second")
        job_key_3 = new_key("job-third")
        job1 = client.request("POST", "/ai/jobs", label="job-idempotent", token=members["api"]["token"], idempotency_key=job_key_1, json={"task_type": "practice_generation", "context": context}, expect=202).json()
        replay = client.request("POST", "/ai/jobs", label="job-replay", token=members["api"]["token"], idempotency_key=job_key_1, json={"task_type": "practice_generation", "context": context}, expect=202).json()
        conflict_context = dict(context)
        conflict_context["target_entry_ids"] = entry_ids[1:4]
        conflict = client.request("POST", "/ai/jobs", label="job-conflict", token=members["api"]["token"], idempotency_key=job_key_1, json={"task_type": "practice_generation", "context": conflict_context})
        job2 = client.request("POST", "/ai/jobs", label="job-2", token=members["api"]["token"], idempotency_key=job_key_2, json={"task_type": "practice_generation", "context": context}, expect=202).json()
        job3 = client.request("POST", "/ai/jobs", label="job-3", token=members["api"]["token"], idempotency_key=job_key_3, json={"task_type": "practice_generation", "context": context})
        cancelled = client.request("POST", f"/ai/jobs/{job1['job_id']}/cancel", label="job-cancel", token=members["api"]["token"], expect=200).json()
        job3_retry = client.request("POST", "/ai/jobs", label="job-3-retry", token=members["api"]["token"], idempotency_key=job_key_3, json={"task_type": "practice_generation", "context": context}, expect=202).json()
        usage_reserved = client.request("GET", "/ai/usage/me", label="usage-reserved", token=members["api"]["token"], expect=200).json()
        quota = next(item for item in usage_reserved["quotas"] if item["quota_kind"] == "question_generation")
        EVIDENCE.check("ai.idempotency-replay-and-conflict", replay["job_id"] == job1["job_id"] and replay["replayed"] is True and conflict.status_code == 409 and conflict.json().get("code") == "AI_IDEMPOTENCY_CONFLICT", replay=replay["job_id"], conflict_status=conflict.status_code)
        EVIDENCE.check("ai.concurrency-limit-two", job3.status_code == 429 and job3.json().get("code") == "AI_CONCURRENCY_LIMIT" and quota["reserved"] == 2 and usage_reserved["concurrency"]["in_use"] == 2, job3_status=job3.status_code, reserved=quota["reserved"], in_use=usage_reserved["concurrency"]["in_use"])
        EVIDENCE.check("ai.cancel-releases-slot", cancelled["status"] == "cancelled" and job3_retry["status"] == "queued", cancelled=cancelled["status"], retry=job3_retry["status"])
        subprocess.run(["wslc", "start", "a30-m3-ai-worker"], capture_output=True, text=True, check=True)
        final_job2 = poll_job(client, members["api"]["token"], job2["job_id"], label="job2")
        final_job3 = poll_job(client, members["api"]["token"], job3_retry["job_id"], label="job3")
        usage_final = client.request("GET", "/ai/usage/me", label="usage-final", token=members["api"]["token"], expect=200).json()
        quota_final = next(item for item in usage_final["quotas"] if item["quota_kind"] == "question_generation")
        prompt_snapshot = await pg.fetchval("SELECT prompt_snapshot FROM ai_jobs WHERE id=$1", uuid.UUID(job2["job_id"]))
        EVIDENCE.check("ai.jobs-complete-after-worker-restart", final_job2["status"] == "succeeded" and final_job3["status"] == "succeeded", job2=final_job2["status"], job3=final_job3["status"])
        EVIDENCE.check("ai.quota-consumed-and-released", quota_final["reserved"] == 0 and usage_final["concurrency"]["in_use"] == 0, reserved=quota_final["reserved"], used=quota_final["used"], in_use=usage_final["concurrency"]["in_use"])
        EVIDENCE.check("ai.prompt-snapshot-frozen", prompt_snapshot == prompt_text, prompt_snapshot=prompt_snapshot)

        # Four practice types through the real API, worker, and provider.
        def ready_practice(practice_type: str, count: int) -> dict[str, Any]:
            created = create_practice(client, members["api"]["token"], practice_type=practice_type, count=count, wordbook_id=wordbook["id"], key_prefix=f"{practice_type}-gen")
            ready = poll_practice(client, members["api"]["token"], created["id"], label=f"{practice_type}-gen")
            raw = json.dumps(ready, ensure_ascii=False)
            EVIDENCE.check(f"practice.{practice_type}.ready", ready["status"] == "ready" and len(ready["questions"]) > 0 and not any(secret_name in raw for secret_name in ("correct_option_id", "explanation", "reference_translation", "reference_essay", "score")), status=ready["status"], questions=len(ready["questions"]), generation=ready["generation_number"])
            return ready

        fill = ready_practice("fill_blank", 3)
        fill_questions = fill["questions"]
        fill_answers = [{"question_id": q["id"], "answer": "a" if i == 0 else "b"} for i, q in enumerate(fill_questions)]
        draft = client.request("PUT", f"/practice/sessions/{fill['id']}/draft", label="fill-draft", token=members["api"]["token"], json={"version": 0, "answers": {fill_questions[0]["id"]: "a"}})
        resumed = client.request("GET", f"/practice/sessions/{fill['id']}", label="fill-resume", token=members["api"]["token"], expect=200).json()
        stale = client.request("PUT", f"/practice/sessions/{fill['id']}/draft", label="fill-stale-draft", token=members["api"]["token"], json={"version": 0, "answers": {}})
        EVIDENCE.check("practice.draft-save-and-resume", draft.status_code == 200 and resumed["draft_answers"] == {fill_questions[0]["id"]: "a"}, status=draft.status_code)
        EVIDENCE.check("practice.draft-optimistic-conflict", stale.status_code == 409 and stale.json().get("code") == "PRACTICE_DRAFT_VERSION_CONFLICT", status=stale.status_code)
        fill_submit = client.request("POST", f"/practice/sessions/{fill['id']}/submit", label="fill-submit", token=members["api"]["token"], idempotency_key=new_key("fill-submit"), json={"answers": fill_answers}, expect=202).json()
        EVIDENCE.check("practice.fill_blank-objective-grading", fill_submit["status"] == "completed" and fill_submit["result"]["score"] == 33.33, score=fill_submit["result"]["score"])
        fill_result = client.request("GET", f"/practice/sessions/{fill['id']}/result", label="fill-result", token=members["api"]["token"], expect=200).json()
        EVIDENCE.check("practice.answer-revealed-after-submit", fill_result["questions"][0]["correct_option_id"] == "a" and bool(fill_result["questions"][0]["explanation"]))

        reading = ready_practice("reading", 3)
        reading_answers = [{"question_id": q["id"], "answer": "a"} for q in reading["questions"]]
        reading_submit = client.request("POST", f"/practice/sessions/{reading['id']}/submit", label="reading-submit", token=members["api"]["token"], idempotency_key=new_key("reading-submit"), json={"answers": reading_answers}, expect=202).json()
        EVIDENCE.check("practice.reading-objective-grading", reading_submit["status"] == "completed" and reading_submit["result"]["score"] == 100.0, score=reading_submit["result"]["score"])

        translation = ready_practice("translation", 3)
        translation_answers = [{"question_id": q["id"], "answer": "我的翻译"} for q in translation["questions"]]
        translation_submit = client.request("POST", f"/practice/sessions/{translation['id']}/submit", label="translation-submit", token=members["api"]["token"], idempotency_key=new_key("translation-submit"), json={"answers": translation_answers}, expect=202).json()
        EVIDENCE.check("practice.translation-starts-scoring", translation_submit["status"] == "scoring", status=translation_submit["status"])
        translation_result = poll_result(client, members["api"]["token"], translation["id"], label="translation-result")
        EVIDENCE.check("practice.translation-ai-grading-low-score", translation_result["status"] == "completed" and translation_result["score"] == 55.0 and translation_result["wrong_count"] == 3, score=translation_result["score"], wrong=translation_result["wrong_count"])

        writing = ready_practice("writing", 1)
        writing_submit = client.request("POST", f"/practice/sessions/{writing['id']}/submit", label="writing-submit", token=members["api"]["token"], idempotency_key=new_key("writing-submit"), json={"answers": [{"question_id": writing["questions"][0]["id"], "answer": "My essay about a harbor."}]}, expect=202).json()
        writing_result = poll_result(client, members["api"]["token"], writing["id"], label="writing-result")
        EVIDENCE.check("practice.writing-ai-grading-high-score", writing_submit["status"] == "scoring" and writing_result["status"] == "completed" and writing_result["score"] == 80.0 and writing_result["wrong_count"] == 0, score=writing_result["score"], wrong=writing_result["wrong_count"])

        regenerate_base = ready_practice("fill_blank", 3)
        regen = client.request("POST", f"/practice/sessions/{regenerate_base['id']}/regenerate", label="practice-regenerate", token=members["api"]["token"], idempotency_key=new_key("regenerate"), expect=202).json()
        regenerated = poll_practice(client, members["api"]["token"], regenerate_base["id"], label="practice-regenerate")
        EVIDENCE.check("practice.regenerate-replaces-generation", regen["generation_number"] == 2 and regenerated["status"] == "ready" and regenerated["generation_number"] == 2, generation=regenerated["generation_number"])
        submitted_regen = client.request("POST", f"/practice/sessions/{fill['id']}/regenerate", label="submitted-regenerate-forbidden", token=members["api"]["token"], idempotency_key=new_key("submitted-regenerate"))
        EVIDENCE.check("practice.submitted-regenerate-forbidden", submitted_regen.status_code == 409, status=submitted_regen.status_code)

        # Controlled generation failure and quota release.
        set_provider_modes({primary_key: "fail", backup_key: "fail"})
        failed = create_practice(client, members["api"]["token"], practice_type="fill_blank", count=3, wordbook_id=wordbook["id"], key_prefix="failure-gen")
        failed_ready = poll_practice(client, members["api"]["token"], failed["id"], label="failure-gen")
        usage_failure = client.request("GET", "/ai/usage/me", label="usage-failure", token=members["api"]["token"], expect=200).json()
        failed_quota = next(item for item in usage_failure["quotas"] if item["quota_kind"] == "question_generation")
        EVIDENCE.check("practice.generation-failure-no-fake-questions", failed_ready["status"] == "failed" and failed_ready["questions"] == [] and failed_ready["error_code"] is not None and failed_quota["reserved"] == 0, status=failed_ready["status"], error=failed_ready["error_code"], reserved=failed_quota["reserved"])
        set_provider_modes({primary_key: "ok", backup_key: "ok"})

        # Provider failover: primary fails, backup succeeds.
        set_provider_modes({primary_key: "fail", backup_key: "ok"})
        failover_created = create_practice(client, members["api"]["token"], practice_type="fill_blank", count=3, wordbook_id=wordbook["id"], key_prefix="failover-gen")
        failover_ready = poll_practice(client, members["api"]["token"], failover_created["id"], label="failover-gen")
        failover_job_id = await pg.fetchval("SELECT ai_job_id FROM practice_sessions WHERE id=$1", uuid.UUID(failover_created["id"]))
        failover_job = await pg.fetchrow("SELECT provider_name, attempt_count, status FROM ai_jobs WHERE id=$1", failover_job_id)
        EVIDENCE.check("provider.failover-to-backup", failover_ready["status"] == "ready" and failover_job["provider_name"] == backup_provider["name"] and failover_job["status"] == "succeeded", provider=failover_job["provider_name"], status=failover_job["status"])
        set_provider_modes({primary_key: "ok", backup_key: "ok"})

        # JSON repair once: malformed first response, valid second response.
        set_provider_modes({primary_key: "repair_once", backup_key: "fail"})
        repair_created = create_practice(client, members["api"]["token"], practice_type="fill_blank", count=3, wordbook_id=wordbook["id"], key_prefix="repair-gen")
        repair_ready = poll_practice(client, members["api"]["token"], repair_created["id"], label="repair-gen")
        repair_job_id = await pg.fetchval("SELECT ai_job_id FROM practice_sessions WHERE id=$1", uuid.UUID(repair_created["id"]))
        repair_row = await pg.fetchrow("SELECT repair_count, status FROM ai_jobs WHERE id=$1", repair_job_id)
        EVIDENCE.check("ai.json-repair-once", repair_ready["status"] == "ready" and repair_row["repair_count"] == 1 and repair_row["status"] == "succeeded", repair_count=repair_row["repair_count"], status=repair_row["status"])
        set_provider_modes({primary_key: "ok", backup_key: "ok"})

        # Privacy and records/mistakes.
        records = client.request("GET", "/practice/records", label="records", token=members["api"]["token"], params={"limit": 100}, expect=200).json()
        mistakes = client.request("GET", "/practice/mistakes", label="practice-mistakes", token=members["api"]["token"], params={"limit": 100}, expect=200).json()
        EVIDENCE.check("practice.records-and-mistakes-persisted", records["total"] >= 4 and mistakes["total"] >= 1, records=records["total"], mistakes=mistakes["total"])
        other_session = client.request("GET", f"/practice/sessions/{fill['id']}", label="other-member-session", token=members["other"]["token"])
        other_result = client.request("GET", f"/practice/sessions/{fill['id']}/result", label="other-member-result", token=members["other"]["token"])
        admin_session = client.request("GET", f"/practice/sessions/{fill['id']}", label="admin-session", token=admin_token)
        other_records = client.request("GET", "/practice/records", label="other-records", token=members["other"]["token"], expect=200).json()
        EVIDENCE.check("privacy.practice-is-user-scoped", other_session.status_code == 404 and other_result.status_code == 404 and other_records["total"] == 0, other_session=other_session.status_code, other_result=other_result.status_code, other_records=other_records["total"])
        EVIDENCE.check("privacy.admin-cannot-read-practice-body", admin_session.status_code in (403, 404), status=admin_session.status_code)
        delete = client.request("DELETE", "/practice/records/bulk", label="practice-bulk-delete", token=members["api"]["token"], idempotency_key=new_key("practice-delete"), json={"ids": [fill["id"], reading["id"]]}, expect=200).json()
        after_delete = client.request("GET", "/practice/records", label="records-after-delete", token=members["api"]["token"], params={"limit": 100}, expect=200).json()
        EVIDENCE.check("practice.owner-bulk-delete", delete["deleted_count"] == 2 and after_delete["total"] == records["total"] - 2, deleted=delete["deleted_count"], remaining=after_delete["total"])

        # Notifications: DND suppression, AI exception, dedupe, category switch.
        prefs_all = {"categories": {"due_review": True, "today_incomplete": True, "streak_risk": True, "ai_completed": True, "ai_failed": True, "plan_adjusted": True, "ai_action": True}, "dnd_start": "00:00", "dnd_end": "23:59", "daily_limit": 20, "timezone": "Asia/Shanghai"}
        client.request("PUT", "/notifications/preferences", label="prefs-dnd", token=members["api"]["token"], json=prefs_all, expect=200)
        await enqueue_notification(members["api"]["id"], category="due_review", dedupe_key="m3-dnd-due", title="T-QA-002 DND due review", body="DND should suppress this.", event_type="learning.due_review")
        dnd_row = await wait_notification_row(pg, members["api"]["id"], "m3-dnd-due")
        EVIDENCE.check("notifications.dnd-suppresses-non-ai", dnd_row["status"] == "suppressed" and dnd_row["suppressed_reason"] == "do_not_disturb", status=dnd_row["status"], reason=dnd_row["suppressed_reason"])

        notification_before = await pg.fetchval("SELECT count(*) FROM notifications WHERE user_id=$1", uuid.UUID(members["api"]["id"]))
        ai_notify_job = client.request("POST", "/ai/jobs", label="dnd-ai-exception-job", token=members["api"]["token"], idempotency_key=new_key("dnd-ai"), json={"task_type": "json_repair", "context": {"raw_text": "not json", "validation_errors": ["invalid"]}}, expect=202).json()
        ai_notify_final = poll_job(client, members["api"]["token"], ai_notify_job["job_id"], label="dnd-ai-exception")
        await enqueue_scheduler_tick()
        await wait_notification_count(pg, members["api"]["id"], int(notification_before) + 1)
        ai_notice_row = await pg.fetchrow("SELECT status, category FROM notifications WHERE user_id=$1 AND category='ai_completed' ORDER BY created_at DESC LIMIT 1", uuid.UUID(members["api"]["id"]))
        EVIDENCE.check("notifications.ai-bypasses-dnd", ai_notify_final["status"] == "succeeded" and ai_notice_row is not None and ai_notice_row["status"] == "sent", job=ai_notify_final["status"], status=ai_notice_row["status"] if ai_notice_row else None)

        await enqueue_notification(members["api"]["id"], category="due_review", dedupe_key="m3-dedupe-key", title="T-QA-002 dedupe", body="First", event_type="learning.due_review")
        await enqueue_notification(members["api"]["id"], category="due_review", dedupe_key="m3-dedupe-key", title="T-QA-002 dedupe", body="Second", event_type="learning.due_review")
        outbox_count = await pg.fetchval("SELECT count(*) FROM notification_outbox WHERE user_id=$1 AND dedupe_key=$2", uuid.UUID(members["api"]["id"]), "m3-dedupe-key")
        EVIDENCE.check("notifications.dedupe-key", outbox_count == 1, outbox_count=outbox_count)

        prefs_no_due = dict(prefs_all)
        prefs_no_due["categories"] = dict(prefs_all["categories"])
        prefs_no_due["categories"]["due_review"] = False
        client.request("PUT", "/notifications/preferences", label="prefs-category-off", token=members["api"]["token"], json=prefs_no_due, expect=200)
        await enqueue_notification(members["api"]["id"], category="due_review", dedupe_key="m3-category-off", title="T-QA-002 category off", body="Should suppress.", event_type="learning.due_review")
        category_row = await wait_notification_row(pg, members["api"]["id"], "m3-category-off")
        EVIDENCE.check("notifications.category-switch", category_row["status"] == "suppressed" and category_row["suppressed_reason"] == "category_disabled", status=category_row["status"], reason=category_row["suppressed_reason"])

        # AI failure notification is produced by the failed practice generation job.
        await enqueue_scheduler_tick()
        failed_notice = wait_for_notification(client, members["api"]["token"], category="ai_failed")
        failed_notice_row = await pg.fetchrow("SELECT status, category FROM notifications WHERE user_id=$1 AND category='ai_failed' ORDER BY created_at DESC LIMIT 1", uuid.UUID(members["api"]["id"]))
        EVIDENCE.check("notifications.ai-failure-visible", failed_notice_row is not None and failed_notice_row["status"] == "sent", status=failed_notice_row["status"] if failed_notice_row else None)

        # Restore usable preferences and prepare the UI member.
        prefs_default = {"categories": {key: True for key in ("due_review", "today_incomplete", "streak_risk", "ai_completed", "ai_failed", "plan_adjusted", "ai_action")}, "dnd_start": "22:00", "dnd_end": "08:00", "daily_limit": 3, "timezone": "Asia/Shanghai"}
        client.request("PUT", "/notifications/preferences", label="prefs-restore", token=members["api"]["token"], json=prefs_default, expect=200)
        client.request("POST", f"/wordbooks/{wordbook['id']}/activate", label="activate-ui-wordbook", token=members["ui"]["token"], expect=200)
        client.request("PATCH", "/users/me/profile", label="ui-profile", token=members["ui"]["token"], json={"daily_new_words": 8, "daily_study_minutes": 15}, expect=200)
        client.request("POST", "/learning/daily-plan/ensure", label="ui-plan", token=members["ui"]["token"], expect=200)
        client.request("PUT", "/notifications/preferences", label="ui-prefs", token=members["ui"]["token"], json=prefs_default, expect=200)

        # Create a failed UI session so the browser can verify the explicit failure state.
        set_provider_modes({primary_key: "fail", backup_key: "fail"})
        ui_failure = create_practice(client, members["ui"]["token"], practice_type="fill_blank", count=3, wordbook_id=wordbook["id"], key_prefix="ui-failure")
        ui_failure_ready = poll_practice(client, members["ui"]["token"], ui_failure["id"], label="ui-failure")
        EVIDENCE.check("browser-seed.failure-session", ui_failure_ready["status"] == "failed", session=ui_failure["id"], status=ui_failure_ready["status"])
        await enqueue_notification(members["ui"]["id"], category="ai_completed", dedupe_key="m3-ui-ai-completed", title="T-QA-002 AI 完成通知", body="受控 AI 任务已完成，可用于浏览器通知验收。", event_type="ai.job.completed")
        await enqueue_notification(members["ui"]["id"], category="ai_failed", dedupe_key="m3-ui-ai-failed", title="T-QA-002 AI 失败通知", body="受控 AI 任务失败，可用于浏览器失败态与通知验收。", event_type="ai.job.failed")
        set_provider_modes({primary_key: "ok", backup_key: "ok"})

        browser_state = {
            "web_base_url": os.environ.get("LIVE_WEB_BASE_URL", "http://127.0.0.1:8093"),
            "run_id": RUN_ID,
            "member_ui": {"username": members["ui"]["username"], "password": members["ui"]["password"]},
            "admin": {"username": os.environ.get("LIVE_ADMIN_USERNAME", "qa_m3_ai_admin"), "password": admin["password"]},
            "wordbook": {"id": wordbook["id"], "name": wordbook["name"]},
            "provider_name": primary_provider["name"],
            "failed_session_id": ui_failure["id"],
            "control_url": CONTROL_URL,
            "provider_key": primary_key,
        }
        state_path = RUNTIME_ENV.parent / "m3_browser_state.json"
        state_path.write_text(json.dumps(browser_state, ensure_ascii=False, indent=2), encoding="utf-8")
        browser_script = Path(__file__).with_name("m3_browser.mjs")
        browser_env = os.environ.copy()
        browser_env.update({"M3_STATE": str(state_path), "EVIDENCE_DIR": str(EVIDENCE_ROOT), "LIVE_RUN_ID": RUN_ID, "LIVE_WEB_BASE_URL": browser_state["web_base_url"]})
        browser_log = LOG_DIR / f"{RUN_ID}-browser.log"
        completed = subprocess.run([os.environ.get("NODE_EXE", "node"), str(browser_script)], cwd=str(REPO_ROOT), env=browser_env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300, check=False)
        browser_log.write_text((completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else ""), encoding="utf-8")
        browser_result_path = RUN_DIR / "browser-acceptance.json"
        browser_result = json.loads(browser_result_path.read_text(encoding="utf-8")) if browser_result_path.exists() else {"status": "FAIL"}
        EVIDENCE.artifacts["browser"] = {"status": browser_result.get("status"), "exit_code": completed.returncode, "checks": len(browser_result.get("checks", [])), "log": str(browser_log.relative_to(EVIDENCE_ROOT))}
        EVIDENCE.check("browser.m3.admin-member-loop", browser_result.get("status") == "PASS" and completed.returncode == 0 and all(item.get("status") == "PASS" for item in browser_result.get("checks", [])), status=browser_result.get("status"), exit_code=completed.returncode, checks=len(browser_result.get("checks", [])))

        # Cleanup practice records and provider/wordbook test data.
        for member_name in ("api", "ui"):
            try:
                records_now = client.request("GET", "/practice/records", label=f"cleanup-records-{member_name}", token=members[member_name]["token"], params={"limit": 100}, expect=200).json()
                ids = [item["id"] for item in records_now["items"]]
                if ids:
                    client.request("DELETE", "/practice/records/bulk", label=f"cleanup-delete-{member_name}", token=members[member_name]["token"], idempotency_key=new_key("cleanup"), json={"ids": ids}, expect=200)
            except Exception as exc:
                EVIDENCE.note("cleanup-practice-note", member=member_name, error=str(exc)[:300])
        # Remove any remaining failed/unsubmitted sessions as disposable QA setup.
        await pg.execute("DELETE FROM practice_sessions WHERE user_id = ANY($1::uuid[])", [uuid.UUID(members["api"]["id"]), uuid.UUID(members["ui"]["id"])])
        delete_book = client.request("DELETE", f"/wordbooks/{wordbook['id']}", label="cleanup-wordbook", token=admin_token, idempotency_key=new_key("cleanup"), json={"confirm_name": wordbook["name"]}, expect=202).json()
        for _ in range(120):
            book_job = client.request("GET", f"/wordbooks/jobs/{delete_book['job_id']}", label="cleanup-wordbook-poll", token=admin_token, expect=200).json()
            if book_job["status"] in {"succeeded", "failed", "cancelled"}:
                break
            time.sleep(0.4)
        client.request("DELETE", f"/admin/ai/providers/{primary_provider['id']}", label="cleanup-primary-provider", token=admin_token, expect=204)
        client.request("DELETE", f"/admin/ai/providers/{backup_provider['id']}", label="cleanup-backup-provider", token=admin_token, expect=204)
        remaining_providers = await pg.fetchval("SELECT count(*) FROM ai_providers WHERE id = ANY($1::uuid[])", [uuid.UUID(primary_provider["id"]), uuid.UUID(backup_provider["id"])])
        remaining_sessions = await pg.fetchval("SELECT count(*) FROM practice_sessions WHERE user_id = ANY($1::uuid[])", [uuid.UUID(members["api"]["id"]), uuid.UUID(members["ui"]["id"])])
        EVIDENCE.check("cleanup.test-providers-removed", remaining_providers == 0, remaining=remaining_providers)
        EVIDENCE.check("cleanup.practice-sessions-removed", remaining_sessions == 0, remaining=remaining_sessions)
        EVIDENCE.check("api.acceptance.all-m3-scenarios-completed", all(item["status"] == "PASS" for item in EVIDENCE.checks), checks=len(EVIDENCE.checks), requests=len(EVIDENCE.network))
        result = EVIDENCE.finish()
        status = 0
    except Exception as exc:
        import traceback
        traceback.print_exc()
        result = EVIDENCE.finish(error=f"{type(exc).__name__}: {exc}")
        status = 1
    finally:
        if pg is not None:
            await pg.close()
        client.close()

    result_path = RUN_DIR / "api-acceptance.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"\nRESULT={result['status']} evidence={result_path}")
    return status


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
