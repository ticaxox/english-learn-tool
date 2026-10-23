#!/usr/bin/env python3
"""M2-CORE-INT-001 Phase B live acceptance runner.

Runs against the isolated Phase A stack rebuilt from the Phase B frozen inputs:
PostgreSQL 16, Redis 7, the real API, ARQ business worker, independent
scheduler, nginx frontend/proxy, and the shared writable wordbook volume.

The script drives one complete API flow, then launches the real-browser flow
against the same stack, then deletes the synthetic wordbooks and verifies
database-level cleanup. It is intentionally one-shot: no warm reruns.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import asyncpg
import httpx

API_BASE = os.environ.get("LIVE_API_BASE_URL", "http://127.0.0.1:8090").rstrip("/") + "/api/v1"
PG_DSN = os.environ["LIVE_PG_DSN"]
EVIDENCE_ROOT = Path(os.environ["EVIDENCE_DIR"]).resolve() / "phase-b"
RUN_ID = os.environ.get("LIVE_RUN_ID", f"phase-b-{datetime.now(UTC):%Y%m%d%H%M%S}")
REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parents[2])).resolve()
RUNTIME_ENV = Path(os.environ["RUNTIME_ENV"]).resolve()
BROWSER_SCRIPT = Path(__file__).with_name("phase_b_browser.mjs")
NODE_EXE = os.environ.get("NODE_EXE", "node")
ADMIN_USERNAME = os.environ.get("LIVE_ADMIN_USERNAME", "qa_m2core_admin")
ADMIN_PASSWORD = os.environ["LIVE_ADMIN_PASSWORD"]

RUN_DIR = EVIDENCE_ROOT / "results" / RUN_ID
LOG_DIR = EVIDENCE_ROOT / "logs"
SHOT_DIR = RUN_DIR / "screenshots"
for directory in (RUN_DIR, LOG_DIR, SHOT_DIR, EVIDENCE_ROOT / "runtime"):
    directory.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


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
        self.notes.append({"name": name, "at": now_iso(), "details": details})
        print(f"[INFO] {name}")

    def finish(self, *, error: str | None = None) -> dict[str, Any]:
        failed = [item for item in self.checks if item["status"] != "PASS"]
        return {
            "task": "M2-CORE-INT-001",
            "phase": "B",
            "run_id": RUN_ID,
            "started_at": STARTED_AT,
            "finished_at": now_iso(),
            "status": "PASS" if not failed and error is None else "FAIL",
            "error": error,
            "checks": self.checks,
            "notes": self.notes,
            "network": self.network,
            "artifacts": self.artifacts,
        }


EVIDENCE = Evidence()
STARTED_AT = now_iso()


def safe_body(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {"content_type": response.headers.get("content-type")}
    if not isinstance(body, dict):
        return {"body_type": type(body).__name__, "length": len(body) if isinstance(body, list) else None}
    summary: dict[str, Any] = {"keys": sorted(body.keys())}
    for key in (
        "code", "status", "wordbook_id", "job_id", "session_id", "item_id", "event_id",
        "option_count", "total_entries", "has_more",
    ):
        if key in body:
            summary[key] = body[key]
    for key in ("access_token", "refresh_token", "csrf_token", "temporary_password"):
        if key in body:
            summary[f"{key}_present"] = bool(body[key])
    if isinstance(body.get("user"), dict):
        summary["user_role"] = body["user"].get("role")
        summary["must_change_password"] = body["user"].get("must_change_password")
    if isinstance(body.get("items"), list):
        summary["item_count"] = len(body["items"])
    if isinstance(body.get("entries"), list):
        summary["entry_count"] = len(body["entries"])
    if isinstance(body.get("next_item"), dict):
        summary["next_item_keys"] = sorted(body["next_item"].keys())
    if isinstance(body.get("card"), dict):
        summary["card"] = {
            "module": body["card"].get("module"),
            "prompt_label": body["card"].get("prompt_label"),
            "option_count": body["card"].get("option_count"),
            "cloze": body["card"].get("cloze"),
            "option_count_rendered": len(body["card"].get("options") or []),
        }
    return summary


class Client:
    def __init__(self) -> None:
        self.http = httpx.Client(base_url=API_BASE, timeout=120.0)

    def close(self) -> None:
        self.http.close()

    def request(self, method: str, path: str, *, label: str, token: str | None = None,
                idempotency_key: str | None = None, expect: int | tuple[int, ...] | None = None,
                **kwargs: Any) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}) or {})
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        started = time.perf_counter()
        response = self.http.request(method, path, headers=headers, **kwargs)
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        entry = {
            "label": label, "method": method, "path": path,
            "status_code": response.status_code,
            "request_id": response.headers.get("X-Request-ID"),
            "duration_ms": elapsed, "body": safe_body(response),
        }
        EVIDENCE.network.append(entry)
        if expect is not None:
            allowed = expect if isinstance(expect, tuple) else (expect,)
            if response.status_code not in allowed:
                raise CheckFailure(f"{label}: expected {allowed}, got {response.status_code}: {response.text[:800]}")
        return response


def json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return value if isinstance(value, dict) else {}


def key(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def login(client: Client, username: str, password: str, *, label: str) -> dict[str, Any]:
    response = client.request("POST", "/auth/login", label=label, json={"username": username, "password": password})
    if response.status_code != 200:
        raise CheckFailure(f"{label}: login returned {response.status_code}: {response.text[:500]}")
    return response.json()


def ensure_password_rotated(client: Client, username: str, initial_password: str, *, label_prefix: str) -> dict[str, Any]:
    rotated_password = initial_password + ".Rotated1"
    response = client.request("POST", "/auth/login", label=f"{label_prefix}-login-initial", json={"username": username, "password": initial_password})
    if response.status_code != 200:
        response = client.request("POST", "/auth/login", label=f"{label_prefix}-login-rotated", json={"username": username, "password": rotated_password})
        if response.status_code != 200:
            raise CheckFailure(f"{label_prefix}: login failed with both initial and rotated passwords: {response.status_code} {response.text[:500]}")
    session = response.json()
    if session["user"]["must_change_password"]:
        changed = client.request("POST", "/auth/change-password", label=f"{label_prefix}-change-password", token=session["access_token"], json={"old_password": initial_password, "new_password": rotated_password})
        if changed.status_code not in (200, 204):
            raise CheckFailure(f"{label_prefix}: password change failed: {changed.text[:500]}")
        session = login(client, username, rotated_password, label=f"{label_prefix}-login-after-rotation")
    EVIDENCE.check(f"auth.{label_prefix}.password-ready", bool(session.get("access_token")) and session["user"]["must_change_password"] is False, role=session["user"]["role"], csrf_present=bool(session.get("csrf_token")))
    return {"session": session, "password": rotated_password}


def create_member(client: Client, admin_token: str, *, username: str, display_name: str, password: str) -> dict[str, Any]:
    response = client.request("POST", "/admin/users", label=f"create-member-{username}", token=admin_token, json={"username": username, "display_name": display_name, "role": "member", "password": password, "department": "QA", "learning_group": "M2-Phase-B"})
    if response.status_code == 409:
        EVIDENCE.note("member-reused", username=username)
        return {}
    if response.status_code not in (200, 201):
        raise CheckFailure(f"create member {username}: {response.status_code} {response.text[:500]}")
    return response.json()

def poll_job(client: Client, token: str, job_id: str, *, label: str) -> dict[str, Any]:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        body = client.request("GET", f"/wordbooks/jobs/{job_id}", label=f"{label}-poll", token=token, expect=200).json()
        if body["status"] in {"succeeded", "failed", "cancelled"}:
            return body
        time.sleep(0.4)
    raise CheckFailure(f"{label}: job {job_id} did not finish")


def csv_bytes(entries: list[tuple[str, str, str, str, str, str]]) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["headword", "phonetic", "part_of_speech", "definition_zh", "definition_en", "example"])
    writer.writerows(entries)
    return output.getvalue().encode("utf-8")


def import_book(client: Client, admin_token: str, *, name: str, entries: list[tuple[str, str, str, str, str, str]]) -> dict[str, Any]:
    preview = client.request("POST", "/wordbooks/import/preview", label=f"import-preview-{name}", token=admin_token, files={"file": (f"{name}.csv", csv_bytes(entries), "text/csv")}, data={"visibility": "organization", "name": name, "description": "M2 Phase B synthetic"}, expect=201).json()
    EVIDENCE.check(f"setup.import-preview.{name}", preview["valid_rows"] == len(entries) and preview["error_count"] == 0, valid_rows=preview["valid_rows"], error_count=preview["error_count"], detected_format=preview.get("detected_format"))
    confirm = client.request("POST", "/wordbooks/import", label=f"import-confirm-{name}", token=admin_token, idempotency_key=key("m2-phase-b-import"), json={"preview_id": preview["preview_id"], "preview_token": preview["preview_token"], "preview_hash": preview["preview_hash"], "name": name, "visibility": "organization"}, expect=202).json()
    job = poll_job(client, admin_token, confirm["job_id"], label=f"import-{name}")
    if job["status"] != "succeeded":
        raise CheckFailure(f"import {name} failed: {job}")
    wordbook_id = job.get("wordbook_id") or job.get("result", {}).get("wordbook_id")
    if not wordbook_id:
        listing = client.request("GET", "/wordbooks", label="list-after-import", token=admin_token, params={"limit": 100}, expect=200).json()
        match = next((item for item in listing["items"] if item["name"] == name), None)
        if not match:
            raise CheckFailure(f"imported book not listed: {name}")
        wordbook_id = match["id"]
    detail = client.request("GET", f"/wordbooks/{wordbook_id}", label=f"detail-{name}", token=admin_token, params={"limit": 100}, expect=200).json()
    return {"id": str(wordbook_id), "name": name, "entries": detail.get("entries", []), "job_id": str(job["job_id"])}


def word_map(book: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for entry in book["entries"]:
        definition = entry.get("definition_zh")
        if not definition:
            definition = next(
                (item.get("definition_zh") for item in entry.get("definitions", []) if item.get("definition_zh")),
                "",
            )
        headword = entry.get("headword") or ""
        if definition and headword:
            result[definition.strip()] = headword
    return result


def activate(client: Client, token: str, wordbook_id: str, *, label: str) -> None:
    client.request("POST", f"/wordbooks/{wordbook_id}/activate", label=label, token=token, expect=200)


def patch_profile(client: Client, token: str, payload: dict[str, Any], *, label: str) -> dict[str, Any]:
    return client.request("PATCH", "/users/me/profile", label=label, token=token, json=payload, expect=200).json()


def today(client: Client, token: str, *, label: str) -> dict[str, Any]:
    return client.request("GET", "/learning/today", label=label, token=token, expect=200).json()


def ensure_today(client: Client, token: str, *, label: str) -> dict[str, Any]:
    return client.request("POST", "/learning/daily-plan/ensure", label=label, token=token, expect=200).json()


def create_session(client: Client, token: str, module: str, *, label: str, wordbook_id: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"module": module}
    if wordbook_id:
        body["wordbook_id"] = wordbook_id
    return client.request("POST", "/memory/sessions", label=label, token=token, json=body, expect=201).json()


def submit_event(client: Client, token: str, session_id: str, item_id: str, action: str, *, label: str, answer: str | None = None, idempotency_key: str | None = None) -> dict[str, Any]:
    return client.request("POST", f"/memory/sessions/{session_id}/events", label=label, token=token, idempotency_key=idempotency_key or key("event"), json={"item_id": item_id, "action": action, "answer": answer, "duration_ms": 1500}, expect=200).json()


def complete_session(client: Client, token: str, session_id: str, *, label: str) -> dict[str, Any]:
    return client.request("POST", f"/memory/sessions/{session_id}/complete", label=label, token=token, json={}, expect=200).json()


async def count(pg: asyncpg.Connection, sql: str, *args: Any) -> int:
    return int(await pg.fetchval(sql, *args) or 0)


async def force_due(pg: asyncpg.Connection, *, user_id: str, wordbook_id: str, plan_id: str, entry_id: str) -> None:
    state_id = uuid.uuid4()
    past = datetime.now(UTC) - timedelta(hours=1)
    await pg.execute("UPDATE daily_plan_words SET reason = 'due', completed_at = NULL WHERE plan_id = $1 AND entry_id = $2", plan_id, entry_id)
    await pg.execute("""
        INSERT INTO user_word_states
          (id, user_id, wordbook_id, entry_id, status, fsrs_card, algorithm_version,
           due_at, review_count, lapse_count, created_at, updated_at)
        VALUES ($1,$2,$3,$4,'review','{}'::jsonb,'fsrs-6.3.2',$5,3,0,now(),now())
        ON CONFLICT (user_id, wordbook_id, entry_id) DO UPDATE SET
          status='review', due_at=$5, review_count=3, algorithm_version='fsrs-6.3.2',
          updated_at=now()
        """, state_id, user_id, wordbook_id, entry_id, past)


async def snapshot_cleanup_ids(pg: asyncpg.Connection, wordbook_id: str) -> dict[str, list[str]]:
    entry_ids = [str(row["id"]) for row in await pg.fetch("SELECT id FROM wordbook_entries WHERE wordbook_id=$1", wordbook_id)]
    plan_ids = [str(row["id"]) for row in await pg.fetch("SELECT id FROM daily_plans WHERE wordbook_id=$1", wordbook_id)]
    session_ids = [str(row["id"]) for row in await pg.fetch("SELECT id FROM memory_sessions WHERE wordbook_id=$1", wordbook_id)]
    return {"entry_ids": entry_ids, "plan_ids": plan_ids, "session_ids": session_ids}


async def residual_counts(pg: asyncpg.Connection, *, wordbook_id: str, entry_ids: list[str], plan_ids: list[str], session_ids: list[str]) -> dict[str, int]:
    return {
        "wordbook_entries": await count(pg, "SELECT count(*) FROM wordbook_entries WHERE wordbook_id=$1", wordbook_id),
        "definitions": await count(pg, "SELECT count(*) FROM wordbook_definitions WHERE entry_id = ANY($1::uuid[])", entry_ids),
        "examples": await count(pg, "SELECT count(*) FROM wordbook_examples WHERE definition_id IN (SELECT id FROM wordbook_definitions WHERE entry_id = ANY($1::uuid[]))", entry_ids),
        "activations": await count(pg, "SELECT count(*) FROM wordbook_activations WHERE wordbook_id=$1", wordbook_id),
        "word_states": await count(pg, "SELECT count(*) FROM user_word_states WHERE wordbook_id=$1", wordbook_id),
        "daily_plans": await count(pg, "SELECT count(*) FROM daily_plans WHERE wordbook_id=$1", wordbook_id),
        "daily_plan_words": await count(pg, "SELECT count(*) FROM daily_plan_words WHERE plan_id = ANY($1::uuid[])", plan_ids),
        "memory_sessions": await count(pg, "SELECT count(*) FROM memory_sessions WHERE wordbook_id=$1", wordbook_id),
        "memory_session_items": await count(pg, "SELECT count(*) FROM memory_session_items WHERE session_id = ANY($1::uuid[])", session_ids),
        "memory_events": await count(pg, "SELECT count(*) FROM memory_events WHERE wordbook_id=$1", wordbook_id),
        "mistake_flags": await count(pg, "SELECT count(*) FROM mistake_flags WHERE wordbook_id=$1", wordbook_id),
        "import_previews": await count(pg, "SELECT count(*) FROM wordbook_import_previews WHERE wordbook_id=$1", wordbook_id),
        "non_delete_jobs": await count(pg, "SELECT count(*) FROM wordbook_jobs WHERE wordbook_id=$1 AND kind <> 'delete'", wordbook_id),
    }


async def run_browser(state_path: Path) -> dict[str, Any]:
    env = os.environ.copy()
    env.update({"PHASE_B_STATE": str(state_path), "EVIDENCE_DIR": str(EVIDENCE_ROOT), "LIVE_RUN_ID": RUN_ID, "LIVE_WEB_BASE_URL": os.environ.get("LIVE_WEB_BASE_URL", "http://127.0.0.1:8091")})
    log_path = LOG_DIR / f"{RUN_ID}-browser.log"
    completed = subprocess.run([NODE_EXE, str(BROWSER_SCRIPT)], cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300, check=False)
    log_path.write_text((completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else ""), encoding="utf-8")
    result_path = RUN_DIR / "browser-acceptance.json"
    result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {"status": "FAIL"}
    result["exit_code"] = completed.returncode
    result["log"] = str(log_path.relative_to(EVIDENCE_ROOT))
    return result

async def main() -> int:
    client = Client()
    pg: asyncpg.Connection | None = None
    browser_result: dict[str, Any] = {}
    try:
        pg = await asyncpg.connect(PG_DSN)
        EVIDENCE.artifacts["environment"] = {
            "postgres": (await pg.fetchval("SELECT version()")).split(" on ")[0],
            "api_base": API_BASE,
            "run_dir": str(RUN_DIR.relative_to(EVIDENCE_ROOT)),
        }
        openapi = client.request("GET", "/openapi.json", label="openapi", expect=200).json()
        EVIDENCE.check("contract.openapi.phase-b-frozen", openapi["openapi"] == "3.1.0" and len(openapi["paths"]) == 39 and len(openapi["components"]["schemas"]) == 67, openapi=openapi["openapi"], paths=len(openapi["paths"]), schemas=len(openapi["components"]["schemas"]))
        readiness = httpx.get(f"{API_BASE.rsplit('/api/v1', 1)[0]}/health/ready", timeout=30).json()
        EVIDENCE.check("health.phase-b-stack-ready", readiness["status"] == "ready" and readiness["components"]["database"]["status"] == "ok" and readiness["components"]["redis"]["status"] == "ok", database=readiness["components"]["database"]["status"], redis=readiness["components"]["redis"]["status"])

        admin = ensure_password_rotated(client, ADMIN_USERNAME, ADMIN_PASSWORD, label_prefix="admin")
        admin_token = admin["session"]["access_token"]
        stamp = datetime.now(UTC).strftime("%H%M%S")
        members = {
            "api": {"username": f"qa_m2b_api_{stamp}", "password": "Qa-M2B-Api-2026!x", "display": "M2 Phase B API"},
            "ui": {"username": f"qa_m2b_ui_{stamp}", "password": "Qa-M2B-Ui-2026!x", "display": "M2 Phase B UI"},
            "small": {"username": f"qa_m2b_small_{stamp}", "password": "Qa-M2B-Small-2026!x", "display": "M2 Phase B Small"},
        }
        for item in members.values():
            create_member(client, admin_token, username=item["username"], display_name=item["display"], password=item["password"])
            rotated = ensure_password_rotated(client, item["username"], item["password"], label_prefix=item["username"])
            item["token"] = rotated["session"]["access_token"]
            item["password"] = rotated["password"]
            item["id"] = rotated["session"]["user"]["id"]

        primary_entries = [
            ("resilient", "/rɪˈzɪliənt/", "adj.", "有弹性的；能恢复的", "able to recover quickly", "She remained resilient after the setback."),
            ("fragile", "/ˈfrædʒaɪl/", "adj.", "易碎的；脆弱的", "easily broken", "The glass is fragile."),
            ("meticulous", "/məˈtɪkjələs/", "adj.", "一丝不苟的", "very careful and precise", "He kept meticulous notes."),
            ("ambiguous", "/æmˈbɪɡjuəs/", "adj.", "模棱两可的", "open to more than one interpretation", "The answer was deliberately ambiguous."),
            ("compelling", "/kəmˈpelɪŋ/", "adj.", "令人信服的；引人入胜的", "convincing or fascinating", "She made a compelling argument."),
            ("diligent", "/ˈdɪlɪdʒənt/", "adj.", "勤勉的", "showing care and effort", "A diligent learner reviews every day."),
            ("elaborate", "/ɪˈlæbərət/", "adj.", "精心制作的；复杂的", "detailed and complicated", "They prepared an elaborate plan."),
            ("inevitable", "/ɪnˈevɪtəbl/", "adj.", "不可避免的", "certain to happen", "Change was inevitable."),
        ]
        small_entries = [
            ("lucid", "/ˈluːsɪd/", "adj.", "清晰易懂的", "clear and easy to understand", "Her explanation was lucid."),
            ("candid", "/ˈkændɪd/", "adj.", "坦率的", "honest and direct", "She gave a candid answer."),
        ]
        primary = import_book(client, admin_token, name=f"M2 Phase B Primary {stamp}", entries=primary_entries)
        small = import_book(client, admin_token, name=f"M2 Phase B Small {stamp}", entries=small_entries)
        EVIDENCE.artifacts["wordbooks"] = {"primary": {"id": primary["id"], "name": primary["name"], "entries": len(primary["entries"])}, "small": {"id": small["id"], "name": small["name"], "entries": len(small["entries"])}}
        EVIDENCE.artifacts["members"] = {name: {"id": item["id"], "username": item["username"]} for name, item in members.items()}

        api_token = members["api"]["token"]
        activate(client, api_token, primary["id"], label="member-api-activate-primary")
        for label, payload in (("daily-words-below-min", {"daily_new_words": 4}), ("daily-words-above-max", {"daily_new_words": 101}), ("minutes-below-min", {"daily_study_minutes": 14}), ("minutes-above-max", {"daily_study_minutes": 181}), ("past-exam-date", {"exam_date": "2000-01-01"})):
            response = client.request("PATCH", "/users/me/profile", label=f"profile-{label}", token=api_token, json=payload)
            EVIDENCE.check(f"profile.boundary.{label}.rejected", response.status_code == 422, status=response.status_code)
        patch_profile(client, api_token, {"daily_new_words": 5, "daily_study_minutes": 180}, label="profile-min-accepted")
        patch_profile(client, api_token, {"daily_new_words": 8, "daily_study_minutes": 15, "target_exam": "CET6", "exam_date": "2030-06-01"}, label="profile-valid")
        first_today = ensure_today(client, api_token, label="today-first")
        second_today = ensure_today(client, api_token, label="today-ensure-idempotent")
        EVIDENCE.check("today.ensure.snapshot-stable", first_today["wordbook_id"] == second_today["wordbook_id"] and [x["entry_id"] for x in first_today["items"]] == [x["entry_id"] for x in second_today["items"]] and first_today["new_words"]["target"] == 8, target=first_today["new_words"]["target"], item_count=len(first_today["items"]))
        plan_id = str(await pg.fetchval("SELECT id FROM daily_plans WHERE user_id=$1", members["api"]["id"]))
        plan_count = await count(pg, "SELECT count(*) FROM daily_plans WHERE user_id=$1 AND local_date=$2", members["api"]["id"], date.fromisoformat(first_today["local_date"]))
        EVIDENCE.check("today.ensure.single-daily-plan", plan_count == 1, plan_id=plan_id, count=plan_count)
        patch_profile(client, api_token, {"daily_new_words": 9}, label="profile-change-after-snapshot")
        stable_today = today(client, api_token, label="today-after-profile-change")
        EVIDENCE.check("today.profile-change-does-not-mutate-snapshot", stable_today["new_words"]["target"] == 8, target=stable_today["new_words"]["target"])

        hb1 = client.request("POST", "/learning/heartbeat", label="heartbeat-1", token=api_token, idempotency_key=key("hb"), json={"session_id": None}, expect=200).json()
        time.sleep(31)
        hb2 = client.request("POST", "/learning/heartbeat", label="heartbeat-2", token=api_token, idempotency_key=key("hb"), json={"session_id": None}, expect=200).json()
        replay_key = key("hb-replay")
        hb3 = client.request("POST", "/learning/heartbeat", label="heartbeat-replay-1", token=api_token, idempotency_key=replay_key, json={"session_id": None}, expect=200).json()
        hb4 = client.request("POST", "/learning/heartbeat", label="heartbeat-replay-2", token=api_token, idempotency_key=replay_key, json={"session_id": None}, expect=200).json()
        await pg.execute("UPDATE daily_activities SET last_heartbeat_at = now() - interval '200 seconds' WHERE user_id=$1", members["api"]["id"])
        stale = client.request("POST", "/learning/heartbeat", label="heartbeat-stale", token=api_token, idempotency_key=key("hb"), json={"session_id": None}, expect=200).json()
        EVIDENCE.check("heartbeat.30s-window", hb1["credited_seconds"] == 0 and 0 < hb2["credited_seconds"] <= 30, first=hb1["credited_seconds"], second=hb2["credited_seconds"])
        EVIDENCE.check("heartbeat.idempotent-replay", 0 <= hb3["credited_seconds"] <= 1 and hb4["credited_seconds"] == 0 and hb3["heartbeat_count"] == hb4["heartbeat_count"], first_credit=hb3["credited_seconds"], replay_credit=hb4["credited_seconds"], counts=[hb3["heartbeat_count"], hb4["heartbeat_count"]])
        EVIDENCE.check("heartbeat.stale-window-zero", stale["credited_seconds"] == 0, credited=stale["credited_seconds"])

        flash = create_session(client, api_token, "flashcard", label="flashcard-new-session")
        flash_session_id = str(flash["session_id"])
        first_item = flash["next_item"]
        first_entry = str(first_item["entry_id"])
        first_state = str(first_item["word_state_id"])
        first_good = submit_event(client, api_token, flash_session_id, str(first_item["item_id"]), "good", label="flashcard-first-good")
        item_position = await pg.fetchval("SELECT position FROM memory_session_items WHERE id=$1", first_item["item_id"])
        state_after_good = await pg.fetchrow("SELECT status, review_count, lapse_count, fsrs_card, algorithm_version FROM user_word_states WHERE id=$1", first_state)
        EVIDENCE.check("flashcard.new-word-first-good-requeued-with-gap", first_good["item_completed"] is False and item_position >= first_item["position"] + 4 and state_after_good["algorithm_version"] == "fsrs-6.3.2", position=item_position, first_position=first_item["position"], status=state_after_good["status"])
        resumed = create_session(client, api_token, "flashcard", label="flashcard-resume-session")
        EVIDENCE.check("session.refresh-resume-same-active-session", str(resumed["session_id"]) == flash_session_id, expected=flash_session_id, actual=str(resumed["session_id"]))
        first_card_after_good = json_object(state_after_good["fsrs_card"])
        again = submit_event(client, api_token, flash_session_id, str(first_item["item_id"]), "again", label="flashcard-first-again")
        state_after_again = await pg.fetchrow("SELECT status, lapse_count, fsrs_card, due_at FROM user_word_states WHERE id=$1", first_state)
        EVIDENCE.check("flashcard.again-enters-relearning-and-updates-fsrs", again["item_completed"] is False and state_after_again["status"] == "relearning" and state_after_again["lapse_count"] >= 1 and json_object(state_after_again["fsrs_card"]) != first_card_after_good, status=state_after_again["status"], lapse_count=state_after_again["lapse_count"])
        second_good = submit_event(client, api_token, flash_session_id, str(first_item["item_id"]), "good", label="flashcard-second-good")
        EVIDENCE.check("flashcard.two-goods-complete-new-word", second_good["item_completed"] is True, item_completed=second_good["item_completed"])
        complete_session(client, api_token, flash_session_id, label="flashcard-session-complete")

        plan_items = first_today["items"]
        due_entry = str(plan_items[1]["entry_id"])
        await force_due(pg, user_id=members["api"]["id"], wordbook_id=primary["id"], plan_id=plan_id, entry_id=due_entry)
        due_session = create_session(client, api_token, "flashcard", label="due-review-session")
        due_item = due_session["next_item"]
        EVIDENCE.check("fsrs.due-review-is-first-card", due_item["reason"] == "due", reason=due_item["reason"])
        due_good = submit_event(client, api_token, str(due_session["session_id"]), str(due_item["item_id"]), "good", label="due-review-good")
        EVIDENCE.check("fsrs.due-review-one-good-completes", due_good["item_completed"] is True, item_completed=due_good["item_completed"])
        complete_session(client, api_token, str(due_session["session_id"]), label="due-review-session-complete")

        await force_due(pg, user_id=members["api"]["id"], wordbook_id=primary["id"], plan_id=plan_id, entry_id=due_entry)
        due_again_session = create_session(client, api_token, "flashcard", label="due-again-session")
        due_again_item = due_again_session["next_item"]
        due_again = submit_event(client, api_token, str(due_again_session["session_id"]), str(due_again_item["item_id"]), "again", label="due-review-again")
        due_state = await pg.fetchrow("SELECT status, lapse_count, due_at FROM user_word_states WHERE id=$1", due_again_item["word_state_id"])
        EVIDENCE.check("fsrs.due-review-again-enters-relearning", due_again["item_completed"] is False and due_state["status"] == "relearning" and due_state["due_at"] is not None, status=due_state["status"], lapse_count=due_state["lapse_count"])
        complete_session(client, api_token, str(due_again_session["session_id"]), label="due-again-session-complete")

        detail = client.request("GET", f"/wordbooks/{primary['id']}", label="primary-detail-for-map", token=api_token, params={"limit": 100}, expect=200).json()
        entry_by_id = {str(entry["id"]): entry for entry in detail["entries"]}
        choice = create_session(client, api_token, "choice", label="choice-session")
        choice_item = choice["next_item"]
        choice_entry = entry_by_id[str(choice_item["entry_id"])]
        choice_labels = [option["label"] if isinstance(option, dict) else str(option) for option in choice["card"]["options"]]
        choice_raw = json.dumps(choice, ensure_ascii=False)
        EVIDENCE.check("choice.options-have-no-correctness-marker", "is_correct" not in choice_raw and "correct_answer" not in choice_raw and "correct_option" not in choice_raw, option_count=choice["card"]["option_count"], rendered=len(choice_labels))
        EVIDENCE.check("choice.full-wordbook-four-options", choice["card"]["option_count"] == 4 and len(choice_labels) == 4, labels=choice_labels)
        choice_correct = submit_event(client, api_token, str(choice["session_id"]), str(choice_item["item_id"]), "good", label="choice-correct-answer", answer=choice_entry["headword"])
        EVIDENCE.check("choice.server-grades-correct", choice_correct["is_correct"] is True, is_correct=choice_correct["is_correct"])
        complete_session(client, api_token, str(choice["session_id"]), label="choice-session-complete")

        for mode in ("full", "partial", "first_letter"):
            client.request("PUT", "/memory/config", label=f"config-spelling-{mode}", token=api_token, json={"flashcard_enabled": True, "choice_enabled": True, "spelling_enabled": True, "preferences": {"spelling_mode": mode}}, expect=200)
            spelling = create_session(client, api_token, "spelling", label=f"spelling-{mode}-session")
            spelling_item = spelling["next_item"]
            spelling_entry = entry_by_id[str(spelling_item["entry_id"])]
            cloze = spelling["card"]["cloze"]
            if mode == "full":
                expected_cloze = "_" * len(spelling_entry["headword"])
            elif mode == "partial":
                visible = max(1, len(spelling_entry["headword"]) // 3)
                expected_cloze = spelling_entry["headword"][:visible] + "_" * (len(spelling_entry["headword"]) - visible)
            else:
                expected_cloze = spelling_entry["headword"][0] + "_" * (len(spelling_entry["headword"]) - 1)
            EVIDENCE.check(f"spelling.{mode}-cloze-is-server-masked", cloze == expected_cloze and "correct_answer" not in json.dumps(spelling, ensure_ascii=False), cloze=cloze)
            if mode == "full":
                graded = submit_event(client, api_token, str(spelling["session_id"]), str(spelling_item["item_id"]), "good", label="spelling-correct-answer", answer=spelling_entry["headword"])
                EVIDENCE.check("spelling.server-grades-correct", graded["is_correct"] is True, is_correct=graded["is_correct"])
            complete_session(client, api_token, str(spelling["session_id"]), label=f"spelling-{mode}-complete")

        mistakes = client.request("GET", "/memory/mistakes", label="mistakes-after-again", token=api_token, params={"limit": 50}, expect=200).json()
        mistake = next((item for item in mistakes["items"] if item["entry_id"] == first_entry), None)
        EVIDENCE.check("mistakes.again-word-appears", mistake is not None, item_count=len(mistakes["items"]))
        event_count_before = await count(pg, "SELECT count(*) FROM memory_events WHERE user_id=$1", members["api"]["id"])
        if mistake:
            priority = client.request("PATCH", f"/memory/mistakes/{mistake['entry_id']}/priority", label="mistake-priority", token=api_token, json={"is_priority": True}, expect=200).json()
            event_count_after = await count(pg, "SELECT count(*) FROM memory_events WHERE user_id=$1", members["api"]["id"])
            EVIDENCE.check("mistakes.priority-persists-without-event-mutation", priority["is_priority"] is True and event_count_after == event_count_before, before=event_count_before, after=event_count_after)
        mastered = client.request("PATCH", f"/memory/words/{first_state}/master", label="word-master", token=api_token, expect=200).json()
        restored = client.request("PATCH", f"/memory/words/{first_state}/restore", label="word-restore", token=api_token, expect=200).json()
        restored_due = datetime.fromisoformat(restored["due_at"].replace("Z", "+00:00"))
        EVIDENCE.check("mastered.restore-recomputes-due-time", mastered["status"] == "mastered" and restored["status"] == "relearning" and restored_due > datetime.now(UTC), mastered_status=mastered["status"], restored_status=restored["status"])

        member_session = client.request("GET", f"/memory/sessions/{flash_session_id}", label="member-own-session", token=api_token, expect=200).json()
        foreign_session = client.request("GET", f"/memory/sessions/{flash_session_id}", label="admin-foreign-session", token=admin_token)
        foreign_state = client.request("PATCH", f"/memory/words/{first_state}/master", label="admin-foreign-state", token=admin_token)
        admin_events = client.request("GET", "/learning/events", label="admin-events", token=admin_token, params={"limit": 100}, expect=200).json()
        admin_mistakes = client.request("GET", "/memory/mistakes", label="admin-mistakes", token=admin_token, params={"limit": 50}, expect=200).json()
        admin_stats = client.request("GET", "/learning/stats", label="admin-stats", token=admin_token, expect=200).json()
        EVIDENCE.check("privacy.member-owns-session", member_session["session_id"] == flash_session_id, session_id=flash_session_id)
        EVIDENCE.check("privacy.admin-session-404", foreign_session.status_code == 404 and foreign_session.json().get("code") == "MEMORY_SESSION_NOT_FOUND", status=foreign_session.status_code)
        EVIDENCE.check("privacy.admin-state-write-404", foreign_state.status_code == 404, status=foreign_state.status_code)
        EVIDENCE.check("privacy.admin-events-mistakes-empty", admin_events["items"] == [] and admin_mistakes["items"] == [] and admin_stats["total_reviews"] == 0, events=len(admin_events["items"]), mistakes=len(admin_mistakes["items"]), reviews=admin_stats["total_reviews"])

        pre_switch_today = today(client, api_token, label="today-before-wordbook-switch")
        activate(client, api_token, small["id"], label="member-api-activate-small")
        switched_today = today(client, api_token, label="today-after-wordbook-switch")
        EVIDENCE.check("wordbook-switch.today-keeps-original-snapshot", switched_today["wordbook_id"] == primary["id"] and switched_today["new_words"]["target"] == pre_switch_today["new_words"]["target"], wordbook_id=str(switched_today["wordbook_id"]), target=switched_today["new_words"]["target"], expected_target=pre_switch_today["new_words"]["target"])
        old_session = client.request("GET", f"/memory/sessions/{flash_session_id}", label="old-session-after-switch", token=api_token, expect=200).json()
        EVIDENCE.check("wordbook-switch.old-session-remains-readable", old_session["wordbook_id"] == primary["id"], wordbook_id=str(old_session["wordbook_id"]))
        mismatch_session_response = client.request("POST", "/memory/sessions", label="new-session-after-switch", token=api_token, json={"module": "choice", "wordbook_id": primary["id"]})
        EVIDENCE.check("wordbook-switch.explicit-old-wordbook-rejected", mismatch_session_response.status_code == 409 and mismatch_session_response.json().get("code") == "WORDBOOK_NOT_ACTIVE", status=mismatch_session_response.status_code)
        switched_session = create_session(client, api_token, "choice", label="new-choice-after-switch")
        session_book_mismatches = await count(pg, "SELECT count(*) FROM memory_session_items msi JOIN memory_sessions ms ON ms.id = msi.session_id JOIN wordbook_entries we ON we.id = msi.entry_id WHERE ms.id = $1 AND we.wordbook_id <> ms.wordbook_id", switched_session["session_id"])
        state_book_mismatches = await count(pg, "SELECT count(*) FROM user_word_states uws JOIN wordbook_entries we ON we.id = uws.entry_id WHERE uws.user_id = $1 AND uws.wordbook_id <> we.wordbook_id", members["api"]["id"])
        EVIDENCE.check("wordbook-switch.new-session-uses-active-book", switched_session["wordbook_id"] == small["id"], expected=small["id"], actual=str(switched_session["wordbook_id"]))
        EVIDENCE.check("wordbook-switch.session-items-belong-to-session-book", session_book_mismatches == 0, mismatches=session_book_mismatches, session_id=str(switched_session["session_id"]))
        EVIDENCE.check("wordbook-switch.user-states-belong-to-entry-book", state_book_mismatches == 0, mismatches=state_book_mismatches)

        small_token = members["small"]["token"]
        activate(client, small_token, small["id"], label="member-small-activate")
        patch_profile(client, small_token, {"daily_new_words": 5, "daily_study_minutes": 15}, label="member-small-profile")
        small_today = ensure_today(client, small_token, label="member-small-today")
        EVIDENCE.check("today.small-book-insufficient-new-words", small_today["new_words"]["target"] == 2 and small_today["new_word_reason"] == "INSUFFICIENT_NEW_WORDS", target=small_today["new_words"]["target"], reason=small_today["new_word_reason"])
        small_choice = create_session(client, small_token, "choice", label="small-choice-session")
        EVIDENCE.check("choice.option-count-less-than-four", small_choice["card"]["option_count"] == 2 and len(small_choice["card"]["options"]) == 2, option_count=small_choice["card"]["option_count"])
        complete_session(client, small_token, str(small_choice["session_id"]), label="small-choice-complete")

        ui_token = members["ui"]["token"]
        activate(client, ui_token, primary["id"], label="member-ui-activate")
        patch_profile(client, ui_token, {"daily_new_words": 8, "daily_study_minutes": 15}, label="member-ui-profile")
        ensure_today(client, ui_token, label="member-ui-today")
        client.request("PUT", "/memory/config", label="member-ui-config", token=ui_token, json={"flashcard_enabled": True, "choice_enabled": True, "spelling_enabled": True, "preferences": {"spelling_mode": "first_letter", "choice_prompt": "definition"}}, expect=200)

        browser_state = {
            "web_base_url": os.environ.get("LIVE_WEB_BASE_URL", "http://127.0.0.1:8091"),
            "run_id": RUN_ID,
            "member_ui": {"username": members["ui"]["username"], "password": members["ui"]["password"]},
            "member_small": {"username": members["small"]["username"], "password": members["small"]["password"]},
            "primary": {"id": primary["id"], "name": primary["name"]},
            "small": {"id": small["id"], "name": small["name"]},
            "word_map": word_map(primary),
            "small_word_map": word_map(small),
        }
        state_path = RUNTIME_ENV.parent / "phase_b_browser.json"
        state_path.write_text(json.dumps(browser_state, ensure_ascii=False, indent=2), encoding="utf-8")
        browser_result = await run_browser(state_path)
        EVIDENCE.artifacts["browser"] = browser_result
        browser_checks = browser_result.get("checks", [])
        EVIDENCE.check("browser.acceptance.phase-b", browser_result.get("status") == "PASS" and browser_result.get("exit_code") == 0 and all(item.get("status") == "PASS" for item in browser_checks), status=browser_result.get("status"), exit_code=browser_result.get("exit_code"), checks=len(browser_checks))

        cleanup_ids = {
            "primary": await snapshot_cleanup_ids(pg, primary["id"]),
            "small": await snapshot_cleanup_ids(pg, small["id"]),
        }
        for book in (primary, small):
            delete = client.request("DELETE", f"/wordbooks/{book['id']}", label=f"delete-{book['name']}", token=admin_token, idempotency_key=key("delete"), json={"confirm_name": book["name"]}, expect=202).json()
            job = poll_job(client, admin_token, delete["job_id"], label=f"delete-{book['name']}")
            EVIDENCE.check(f"delete.{book['name']}.succeeds", job["status"] == "succeeded", job_id=str(job["job_id"]), result=job.get("result"))
        for name, book in (("primary", primary), ("small", small)):
            residuals = await residual_counts(pg, wordbook_id=book["id"], **cleanup_ids[name])
            EVIDENCE.check(f"delete.{name}.database-zero-residual", all(value == 0 for value in residuals.values()), residuals=residuals)
        artifacts = subprocess.run(["wslc", "exec", "a30-m2core-worker", "sh", "-lc", "find /app/var/wordbooks -type f -printf '%f\\n' | sort"], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False).stdout.splitlines()
        EVIDENCE.check("delete.shared-volume-artifacts-empty", artifacts == [], files=artifacts[:20])
        for member_name in ("api", "ui", "small"):
            response = client.request("GET", "/learning/today", label=f"today-after-delete-{member_name}", token=members[member_name]["token"])
            EVIDENCE.check(f"delete.{member_name}.today-requires-active-book", response.status_code == 409 and response.json().get("code") == "ACTIVE_WORDBOOK_REQUIRED", status=response.status_code)
        deleted_session = client.request("GET", f"/memory/sessions/{flash_session_id}", label="session-after-delete", token=api_token)
        EVIDENCE.check("delete.memory-session-gone", deleted_session.status_code == 404, status=deleted_session.status_code)

        EVIDENCE.check("api.acceptance.all-phase-b-scenarios-completed", all(item["status"] == "PASS" for item in EVIDENCE.checks), checks=len(EVIDENCE.checks), requests=len(EVIDENCE.network))
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
