#!/usr/bin/env python3
"""M2-CORE-INT-001 Phase A live acceptance runner.

Real HTTP against the isolated FastAPI container, real PostgreSQL 16 and Redis
containers, a real ARQ business worker container, and one shared writable
wordbook volume mounted into the API, worker, and scheduler containers.
No ASGI fakes, in-memory databases, or mocked providers are used.

Credentials are read from the environment only and are never written to the
evidence files.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import asyncpg
import httpx
from pypdf import PdfReader

API_BASE_URL = os.environ.get("LIVE_API_BASE_URL", "http://127.0.0.1:8090").rstrip("/")
PG_DSN = os.environ["LIVE_PG_DSN"]
EVIDENCE_DIR = Path(os.environ["EVIDENCE_DIR"]).resolve()
RUN_ID = os.environ.get("LIVE_RUN_ID", f"a30-m2core-{uuid.uuid4().hex[:12]}")
ADMIN_USERNAME = os.environ["LIVE_ADMIN_USERNAME"]
ADMIN_PASSWORD = os.environ["LIVE_ADMIN_PASSWORD"]
MEMBER_USERNAME = os.environ.get("LIVE_MEMBER_USERNAME", "qa_m2core_member")
# Synthetic fixture credential for the disposable local QA member account only.
# Generated secrets (admin password, DB password, JWT secret) are never hardcoded.
MEMBER_PASSWORD = os.environ.get("LIVE_MEMBER_PASSWORD", "Qa-M2Core-Member-2026!x")
WORKER_CONTAINER = os.environ.get("LIVE_WORKER_CONTAINER", "a30-m2core-worker")
STORAGE_CONTAINER = os.environ.get("LIVE_STORAGE_CONTAINER", "a30-m2core-worker")
STORAGE_PATH = os.environ.get("LIVE_STORAGE_PATH", "/app/var/wordbooks")
API_PREFIX = "/api/v1"

RUN_DIR = EVIDENCE_DIR / "results" / RUN_ID
DOWNLOAD_DIR = RUN_DIR / "downloads"
RUN_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

CSV_SOURCE = (
    "headword,phonetic,part_of_speech,definition_en,definition_zh,example,example_translation,source\n"
    "abandon,/\u0259\u02c8b\u00e6nd\u0259n/,verb,to leave behind,"
    "\u653e\u5f03,He abandoned the plan.,\u4ed6\u653e\u5f03\u4e86\u8ba1\u5212\u3002,livemint\n"
    "brief,/bri\u02d0f/,adj,lasting a short time,\u77ed\u6682\u7684,"
    "A brief pause.,\u77ed\u6682\u7684\u505c\u987f\u3002,livemint\n"
    "candid,/\u02c8k\u00e6nd\u026ad/,adj,honest and direct,"
    "\u5766\u7387\u7684,A candid reply.,\u5766\u7387\u7684\u56de\u7b54\u3002,livemint\n"
)


class CheckFailure(RuntimeError):
    pass


class Evidence:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []
        self.network: list[dict[str, Any]] = []
        self.artifacts: dict[str, Any] = {}
        self.started_at = datetime.now(UTC).isoformat()

    def check(self, name: str, passed: bool, *, request_id: str | None = None, **details: Any) -> None:
        entry = {
            "name": name,
            "status": "PASS" if passed else "FAIL",
            "request_id": request_id,
            "details": details,
        }
        self.checks.append(entry)
        print(f"[{'PASS' if passed else 'FAIL'}] {name} request_id={request_id or '-'}")
        if not passed:
            raise CheckFailure(f"{name}: {json.dumps(details, ensure_ascii=False, default=str)[:900]}")

    def note(self, name: str, **details: Any) -> None:
        self.checks.append(
            {
                "name": name,
                "status": "INFO",
                "request_id": None,
                "details": details,
            }
        )
        print(f"[INFO] {name}")

    def finish(self, error: str | None = None) -> dict[str, Any]:
        failed = [item for item in self.checks if item["status"] == "FAIL"]
        return {
            "task": "M2-CORE-INT-001",
            "phase": "A",
            "run_id": RUN_ID,
            "started_at": self.started_at,
            "finished_at": datetime.now(UTC).isoformat(),
            "status": "FAIL" if error or failed else "PASS",
            "error": error,
            "api_base_url": API_BASE_URL,
            "checks": self.checks,
            "network": self.network,
            "artifacts": self.artifacts,
        }


EVIDENCE = Evidence()


def safe_body(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {"content_type": response.headers.get("content-type")}
    if not isinstance(body, dict):
        return {"body_type": type(body).__name__}
    summary: dict[str, Any] = {"keys": sorted(body.keys())}
    for key in ("code", "status", "job_id", "wordbook_id", "cleanup_status", "detail"):
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
    return summary


class Client:
    def __init__(self) -> None:
        self.http = httpx.Client(base_url=API_BASE_URL + API_PREFIX, timeout=120.0)
        self.entries: list[dict[str, Any]] = []

    def close(self) -> None:
        self.http.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        label: str,
        token: str | None = None,
        idempotency_key: str | None = None,
        expect: int | tuple[int, ...] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}) or {})
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        started = time.perf_counter()
        response = self.http.request(method, path, headers=headers, **kwargs)
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        entry = {
            "label": label,
            "method": method,
            "path": path,
            "status_code": response.status_code,
            "request_id": response.headers.get("X-Request-ID"),
            "duration_ms": elapsed,
            "body": safe_body(response),
        }
        if "content-type" in response.headers and response.headers["content-type"].startswith(
            "application/octet-stream"
        ):
            entry["body"] = {"bytes": len(response.content)}
        self.entries.append(entry)
        EVIDENCE.network.append(entry)
        if expect is not None:
            allowed = expect if isinstance(expect, tuple) else (expect,)
            if response.status_code not in allowed:
                raise CheckFailure(
                    f"{label}: expected {allowed} got {response.status_code} "
                    f"{response.text[:700]}"
                )
        return response


def new_key(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def poll_job(
    client: Client,
    job_id: str,
    token: str,
    *,
    label: str,
    timeout: float = 120.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    seen: list[str] = []
    while time.monotonic() < deadline:
        body = client.request(
            "GET", f"/wordbooks/jobs/{job_id}", label=f"{label}-poll", token=token, expect=200
        ).json()
        status = body["status"]
        if not seen or seen[-1] != status:
            seen.append(status)
        if status in {"succeeded", "failed", "cancelled"}:
            body["_observed_statuses"] = seen
            return body
        time.sleep(0.5)
    raise CheckFailure(f"{label}: job {job_id} did not finish within {timeout}s ({seen})")


# --------------------------------------------------------------------------- helpers


def docker(args: list[str], *, label: str, check: bool = True) -> str:
    result = subprocess.run(
        ["wslc", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    EVIDENCE.artifacts.setdefault("docker_calls", []).append(
        {
            "label": label,
            "argv": ["wslc", *[a if len(a) <= 200 else a[:200] + "..." for a in args]],
            "returncode": result.returncode,
            "stdout_head": (result.stdout or "")[:400],
            "stderr_head": (result.stderr or "")[:400],
        }
    )
    if check and result.returncode != 0:
        raise CheckFailure(f"docker {label} failed: {(result.stderr or result.stdout)[:600]}")
    return result.stdout


def container_files(prefix: str) -> list[str]:
    out = docker(
        ["exec", STORAGE_CONTAINER, "sh", "-lc", f"ls -1 {STORAGE_PATH} 2>/dev/null || true"],
        label=f"ls-{prefix}",
    )
    names = [line.strip() for line in out.splitlines() if line.strip()]
    return [name for name in names if name.startswith(prefix)]


async def db_connect() -> asyncpg.Connection:
    return await asyncpg.connect(PG_DSN)


async def scalar(conn: asyncpg.Connection, query: str, *args: Any) -> Any:
    return await conn.fetchval(query, *args)


async def row_count(conn: asyncpg.Connection, query: str, *args: Any) -> int:
    return int(await conn.fetchval(query, *args) or 0)


def write_json(name: str, payload: Any) -> str:
    path = RUN_DIR / name
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return str(path.relative_to(RUN_DIR))


def upload_preview(
    client: Client,
    token: str,
    *,
    label: str,
    filename: str,
    payload: bytes,
    visibility: str,
    name: str,
    mime: str = "text/csv",
    description: str | None = None,
) -> dict[str, Any]:
    data = {"visibility": visibility, "name": name}
    if description:
        data["description"] = description
    response = client.request(
        "POST",
        "/wordbooks/import/preview",
        label=label,
        token=token,
        files={"file": (filename, payload, mime)},
        data=data,
        expect=201,
    )
    return response.json()


def remap_preview(
    client: Client,
    token: str,
    preview: dict[str, Any],
    *,
    label: str,
    mapping: dict[str, str | None] | None = None,
    ignored_columns: list[str] | None = None,
    expect: int | tuple[int, ...] = 200,
) -> httpx.Response:
    return client.request(
        "PATCH",
        f"/wordbooks/import/previews/{preview['preview_id']}",
        label=label,
        token=token,
        json={
            "preview_token": preview["preview_token"],
            "mapping": mapping if mapping is not None else preview["mapping"],
            "ignored_columns": (
                ignored_columns if ignored_columns is not None else preview["ignored_columns"]
            ),
        },
        expect=expect,
    )


def confirm_import(
    client: Client,
    token: str,
    preview: dict[str, Any],
    *,
    label: str,
    name: str,
    visibility: str,
    idempotency_key: str,
    expect: int | tuple[int, ...] = 202,
) -> httpx.Response:
    return client.request(
        "POST",
        "/wordbooks/import",
        label=label,
        token=token,
        idempotency_key=idempotency_key,
        json={
            "preview_id": preview["preview_id"],
            "preview_token": preview["preview_token"],
            "preview_hash": preview["preview_hash"],
            "name": name,
            "visibility": visibility,
        },
        expect=expect,
    )


# --------------------------------------------------------------------- scenarios


def _login(client: Client, username: str, password: str, *, label: str) -> httpx.Response:
    return client.request(
        "POST", "/auth/login", label=label, json={"username": username, "password": password}
    )


def _ensure_password_rotated(
    client: Client,
    username: str,
    initial_password: str,
    *,
    label_prefix: str,
) -> dict[str, Any]:
    """Log in and force the first-login password rotation exactly once.

    A rerun against the same database finds the rotated password already in
    place, which is what makes two consecutive runs without a manual reset a
    meaningful state-isolation check.
    """

    response = _login(client, username, initial_password, label=f"{label_prefix}-login")
    rotated_password = initial_password + ".Rotated1"
    already_rotated = False
    if response.status_code != 200:
        response = _login(
            client, username, rotated_password, label=f"{label_prefix}-login-rotated"
        )
        already_rotated = True
        if response.status_code != 200:
            raise CheckFailure(
                f"{label_prefix}-login: expected 200 got {response.status_code} "
                f"{response.text[:400]}"
            )
    session = response.json()

    if session["user"]["must_change_password"]:
        client.request(
            "POST",
            "/auth/change-password",
            label=f"{label_prefix}-change-password",
            token=session["access_token"],
            json={"old_password": initial_password, "new_password": rotated_password},
            expect=204,
        )
        session = _login(
            client, username, rotated_password, label=f"{label_prefix}-relogin"
        ).json()
        already_rotated = False

    EVIDENCE.check(
        f"auth.{label_prefix}.login-completes-password-rotation",
        bool(session.get("access_token"))
        and session["user"]["must_change_password"] is False
        and (session["user"]["role"] in {"admin", "member"}),
        user_role=session["user"]["role"],
        rotated_on_this_run=not already_rotated,
        password_already_rotated=already_rotated,
        csrf_token_present=bool(session.get("csrf_token")),
    )
    return {"session": session, "password": rotated_password, "already_rotated": already_rotated}


def scenario_auth(client: Client) -> dict[str, Any]:
    fresh = _login(client, ADMIN_USERNAME, ADMIN_PASSWORD, label="admin-login-initial")
    if fresh.status_code == 200 and fresh.json()["user"]["must_change_password"]:
        pending = client.request(
            "GET",
            "/wordbooks",
            label="admin-list-before-password-change",
            token=fresh.json()["access_token"],
            expect=403,
        ).json()
        EVIDENCE.check(
            "auth.password-change-required.blocks.business-endpoints",
            pending.get("code") == "AUTH_PASSWORD_CHANGE_REQUIRED",
            code=pending.get("code"),
        )
    else:
        EVIDENCE.note(
            "auth.password-change-required.blocks-business-endpoints.skipped-on-rerun",
            reason="the administrator password was already rotated by the first run",
            status_code=fresh.status_code,
        )

    rotated = _ensure_password_rotated(
        client, ADMIN_USERNAME, ADMIN_PASSWORD, label_prefix="admin"
    )
    session = rotated["session"]

    anonymous = client.request(
        "GET", "/wordbooks", label="anonymous-list", expect=401
    ).json()
    EVIDENCE.check(
        "auth.anonymous.requests.rejected",
        anonymous.get("code") == "UNAUTHORIZED",
        code=anonymous.get("code"),
    )
    return {"admin_token": session["access_token"], "admin_csrf": session["csrf_token"]}


def scenario_member(client: Client, admin_token: str) -> dict[str, Any]:
    existing = client.request(
        "GET",
        "/admin/users?search=" + MEMBER_USERNAME,
        label="admin-lookup-member",
        token=admin_token,
        expect=200,
    ).json()
    match = [
        item for item in existing["items"] if item["username"].casefold() == MEMBER_USERNAME.casefold()
    ]
    if match:
        member_id = match[0]["id"]
        EVIDENCE.note(
            "admin.create-member.reused-existing-account-on-rerun",
            member_id=member_id,
            username=MEMBER_USERNAME,
        )
    else:
        created = client.request(
            "POST",
            "/admin/users",
            label="admin-create-member",
            token=admin_token,
            json={
                "username": MEMBER_USERNAME,
                "display_name": "QA M2 Core Member",
                "role": "member",
                "password": MEMBER_PASSWORD,
                "department": "QA",
                "learning_group": "m2core",
            },
            expect=201,
        ).json()
        member_id = created["user"]["id"]
        EVIDENCE.check(
            "admin.create-member.persisted",
            created["user"]["role"] == "member"
            and created["user"]["must_change_password"] is True,
            member_id=member_id,
            temporary_password_present=bool(created.get("temporary_password")),
        )

    rotated = _ensure_password_rotated(
        client, MEMBER_USERNAME, MEMBER_PASSWORD, label_prefix="member"
    )
    EVIDENCE.check(
        "member.account.is-active-member",
        rotated["session"]["user"]["role"] == "member",
        member_id=member_id,
    )
    return {"member_token": rotated["session"]["access_token"], "member_id": member_id}


def scenario_admin_csv_chain(
    client: Client,
    admin_token: str,
    *,
    name: str,
) -> dict[str, Any]:
    preview = upload_preview(
        client,
        admin_token,
        label="admin-csv-preview",
        filename="qa-m2core-org.csv",
        payload=CSV_SOURCE.encode("utf-8"),
        visibility="organization",
        name=name,
        description="Phase A organization wordbook",
    )
    EVIDENCE.check(
        "wordbook.csv.preview.detects-format-and-columns",
        preview["detected_format"] == "csv"
        and preview["encoding"] == "utf-8"
        and preview["delimiter"] == ","
        and preview["columns"] == [
            "headword",
            "phonetic",
            "part_of_speech",
            "definition_en",
            "definition_zh",
            "example",
            "example_translation",
            "source",
        ]
        and preview["total_rows"] == 3
        and preview["valid_rows"] == 3
        and preview["error_count"] == 0,
        detected_format=preview["detected_format"],
        encoding=preview["encoding"],
        delimiter=preview["delimiter"],
        columns=preview["columns"],
        total_rows=preview["total_rows"],
        valid_rows=preview["valid_rows"],
        error_count=preview["error_count"],
        preview_id=str(preview["preview_id"]),
    )
    EVIDENCE.check(
        "wordbook.csv.preview.samples-structurally-normalized",
        preview["sample_rows"]
        and preview["sample_rows"][0]["headword"] == "abandon"
        and preview["sample_rows"][0]["definitions"][0]["definition_zh"] == "\u653e\u5f03",
        sample_headword=preview["sample_rows"][0]["headword"],
        sample_phonetic=preview["sample_rows"][0]["phonetic"],
    )
    EVIDENCE.check(
        "wordbook.csv.preview.reports-extra-column-without-guessing",
        preview["ignored_columns"] == []
        and "source" in preview["columns"]
        and "source" not in set(value for value in preview["mapping"].values() if value),
        ignored_columns=preview["ignored_columns"],
        mapped_sources=sorted(value for value in preview["mapping"].values() if value),
    )

    # Real mapping change: the operator explicitly ignores the trailing "source"
    # column, which proves the PATCH remap path and the rotated preview_hash.
    mapping = dict(preview["mapping"])
    remapped = remap_preview(
        client,
        admin_token,
        preview,
        label="admin-csv-remap",
        mapping=mapping,
        ignored_columns=["source"],
    ).json()
    EVIDENCE.check(
        "wordbook.csv.remap.rotates-preview-hash",
        remapped["mapping"]["headword"] == "headword"
        and remapped["ignored_columns"] == ["source"]
        and len(remapped["preview_hash"]) == 64,
        preview_hash_sha256=len(remapped["preview_hash"]),
    )

    stale_hash = "0" * 64
    mismatch = client.request(
        "POST",
        "/wordbooks/import",
        label="admin-csv-confirm-stale-hash",
        token=admin_token,
        idempotency_key=new_key("qa-mismatch"),
        json={
            "preview_id": remapped["preview_id"],
            "preview_token": remapped["preview_token"],
            "preview_hash": stale_hash,
            "name": name,
            "visibility": "organization",
        },
        expect=409,
    ).json()
    EVIDENCE.check(
        "wordbook.csv.confirm.rejects-stale-preview-hash",
        mismatch.get("code") == "WORDBOOK_PREVIEW_MISMATCH",
        code=mismatch.get("code"),
    )

    import_key = new_key("qa-org-import")
    confirm = confirm_import(
        client,
        admin_token,
        remapped,
        label="admin-csv-confirm",
        name=name,
        visibility="organization",
        idempotency_key=import_key,
    ).json()
    EVIDENCE.check(
        "wordbook.csv.confirm.queues-import-job",
        confirm["kind"] == "import" and confirm["status"] == "queued",
        job_id=str(confirm["job_id"]),
        wordbook_id=str(confirm["wordbook_id"]),
    )

    replay = confirm_import(
        client,
        admin_token,
        remapped,
        label="admin-csv-confirm-idempotent-replay",
        name=name,
        visibility="organization",
        idempotency_key=import_key,
    ).json()
    EVIDENCE.check(
        "wordbook.csv.confirm.same-key-same-body.returns-same-job",
        replay["job_id"] == confirm["job_id"],
        first_job=str(confirm["job_id"]),
        replay_job=str(replay["job_id"]),
    )

    conflict = confirm_import(
        client,
        admin_token,
        remapped,
        label="admin-csv-confirm-idempotency-conflict",
        name=name + " renamed",
        visibility="organization",
        idempotency_key=import_key,
        expect=409,
    ).json()
    EVIDENCE.check(
        "wordbook.csv.confirm.same-key-different-body.conflicts",
        conflict.get("code") == "IDEMPOTENCY_CONFLICT",
        code=conflict.get("code"),
    )

    job = poll_job(client, confirm["job_id"], admin_token, label="admin-csv-import")
    EVIDENCE.check(
        "wordbook.csv.import.job-succeeds",
        job["status"] == "succeeded" and job["progress"] == 100,
        job_id=str(job["job_id"]),
        observed_statuses=job["_observed_statuses"],
        result=job["result"],
        cleanup_status=job["cleanup_status"],
    )
    EVIDENCE.check(
        "wordbook.csv.import.persists-entries-definitions-examples",
        job["result"].get("entry_count") == 3
        and job["result"].get("definition_count") == 3
        and job["result"].get("example_count") == 3,
        result=job["result"],
    )

    wordbook_id = str(job["wordbook_id"])
    detail = client.request(
        "GET", f"/wordbooks/{wordbook_id}", label="admin-csv-detail", token=admin_token, expect=200
    ).json()
    EVIDENCE.check(
        "wordbook.csv.detail.returns-ordered-entries",
        detail["total_entries"] == 3
        and [entry["headword"] for entry in detail["entries"]]
        == ["abandon", "brief", "candid"]
        and detail["entries"][0]["phonetic"] == "/\u0259\u02c8b\u00e6nd\u0259n/"
        and detail["entries"][0]["definitions"][0]["examples"][0]["example_zh"]
        == "\u4ed6\u653e\u5f03\u4e86\u8ba1\u5212\u3002",
        total_entries=detail["total_entries"],
        headwords=[entry["headword"] for entry in detail["entries"]],
        status=detail["wordbook"]["status"],
    )

    activation = client.request(
        "POST",
        f"/wordbooks/{wordbook_id}/activate",
        label="admin-csv-activate",
        token=admin_token,
        expect=200,
    ).json()
    EVIDENCE.check(
        "wordbook.organization.activate.sets-primary",
        activation["is_active"] is True and activation["wordbook_id"] == wordbook_id,
        activated_at=activation["activated_at"],
    )

    active_list = client.request(
        "GET", "/wordbooks", label="admin-list-after-activate", token=admin_token, expect=200
    ).json()
    active_item = next(item for item in active_list["items"] if item["id"] == wordbook_id)
    EVIDENCE.check(
        "wordbook.organization.list.reflects-active-primary",
        active_item["is_active"] is True and active_item["entry_count"] == 3,
        entry_count=active_item["entry_count"],
    )
    return {"wordbook_id": wordbook_id, "name": name, "detail": detail}


def scenario_exports(client: Client, admin_token: str, org: dict[str, Any]) -> dict[str, Any]:
    wordbook_id = org["wordbook_id"]
    results: dict[str, Any] = {}

    for fmt in ("csv", "txt", "pdf"):
        key = new_key(f"qa-export-{fmt}")
        requested = client.request(
            "POST",
            f"/wordbooks/{wordbook_id}/export",
            label=f"admin-export-{fmt}-request",
            token=admin_token,
            idempotency_key=key,
            json={"format": fmt},
            expect=202,
        ).json()
        replay = client.request(
            "POST",
            f"/wordbooks/{wordbook_id}/export",
            label=f"admin-export-{fmt}-idempotent-replay",
            token=admin_token,
            idempotency_key=key,
            json={"format": fmt},
            expect=202,
        ).json()
        EVIDENCE.check(
            f"wordbook.export.{fmt}.same-key-same-body.returns-same-job",
            requested["job_id"] == replay["job_id"],
            format=fmt,
            job_id=str(requested["job_id"]),
            replay_job=str(replay["job_id"]),
        )

        job = poll_job(client, requested["job_id"], admin_token, label=f"admin-export-{fmt}")
        EVIDENCE.check(
            f"wordbook.export.{fmt}.job-succeeds",
            job["status"] == "succeeded" and bool(job["download_url"]),
            format=fmt,
            job_id=str(job["job_id"]),
            result=job["result"],
            download_expires_at=job["download_expires_at"],
        )

        download = client.request(
            "GET",
            f"/exports/{job['job_id']}/download",
            label=f"admin-export-{fmt}-download",
            token=admin_token,
            expect=200,
        )
        content = download.content
        suffix = {"csv": ".csv", "txt": ".txt", "pdf": ".pdf"}[fmt]
        (DOWNLOAD_DIR / f"organization-{fmt}{suffix}").write_bytes(content)
        disposition = download.headers.get("content-disposition", "")
        EVIDENCE.check(
            f"wordbook.export.{fmt}.download.is-attachment",
            "attachment" in disposition
            and download.headers.get("x-content-type-options") == "nosniff"
            and "no-store" in download.headers.get("cache-control", ""),
            format=fmt,
            bytes=len(content),
            content_type=download.headers.get("content-type"),
            disposition=disposition[:160],
        )
        results[fmt] = {"bytes": len(content), "job_id": str(job["job_id"])}

    csv_text = (DOWNLOAD_DIR / "organization-csv.csv").read_bytes().decode("utf-8-sig")
    csv_lines = [line for line in csv_text.splitlines() if line.strip()]
    EVIDENCE.check(
        "wordbook.export.csv.content.round-trips-utf8",
        csv_lines[0].startswith("headword,phonetic,part_of_speech")
        and len(csv_lines) == 4
        and "\u653e\u5f03" in csv_text
        and "/\u0259\u02c8b\u00e6nd\u0259n/" in csv_text,
        rows=len(csv_lines) - 1,
        header=csv_lines[0],
    )

    txt_text = (DOWNLOAD_DIR / "organization-txt.txt").read_bytes().decode("utf-8")
    EVIDENCE.check(
        "wordbook.export.txt.content.includes-zh-and-ipa",
        "1. abandon" in txt_text
        and "/\u0259\u02c8b\u00e6nd\u0259n/" in txt_text
        and "ZH: \u653e\u5f03" in txt_text
        and "EX-ZH: \u4ed6\u653e\u5f03\u4e86\u8ba1\u5212\u3002" in txt_text,
        characters=len(txt_text),
    )

    reader = PdfReader(io.BytesIO((DOWNLOAD_DIR / "organization-pdf.pdf").read_bytes()))
    pdf_text = "".join(page.extract_text() or "" for page in reader.pages)
    EVIDENCE.check(
        "wordbook.export.pdf.embeds-cjk-font-glyphs",
        "abandon" in pdf_text
        and "\u653e\u5f03" in pdf_text
        and "\u77ed\u6682\u7684" in pdf_text
        and "/\u0259\u02c8b\u00e6nd\u0259n/" in pdf_text,
        pages=len(reader.pages),
        extracted_characters=len(pdf_text),
        sample=pdf_text[:180].replace("\n", " | "),
    )

    expired_job = results["pdf"]["job_id"]
    return {"exports": results, "expired_probe_job": expired_job}


async def scenario_export_authorization(
    client: Client,
    member_token: str,
    admin_token: str,
    export_probe: dict[str, Any],
    pg: asyncpg.Connection,
) -> dict[str, Any]:
    """Short-lived download authorization: owner/admin only, 410 after expiry."""
    job_id = uuid.UUID(str(export_probe["expired_probe_job"]))

    foreign = client.request(
        "GET",
        f"/exports/{job_id}/download",
        label="member-downloads-admin-export",
        token=member_token,
        expect=404,
    ).json()
    EVIDENCE.check(
        "wordbook.export.download.hidden-from-other-member",
        foreign.get("code") == "WORDBOOK_JOB_NOT_FOUND",
        code=foreign.get("code"),
    )

    foreign_job = client.request(
        "GET",
        f"/exports/{job_id}",
        label="member-reads-admin-export-job",
        token=member_token,
        expect=404,
    ).json()
    EVIDENCE.check(
        "wordbook.export.job.hidden-from-other-member",
        foreign_job.get("code") == "WORDBOOK_JOB_NOT_FOUND",
        code=foreign_job.get("code"),
    )

    past = datetime.now(UTC) - timedelta(minutes=5)
    await pg.execute(
        "update wordbook_jobs set download_expires_at = $2 where id = $1",
        job_id,
        past,
    )
    forced = await scalar(
        pg, "select download_expires_at from wordbook_jobs where id = $1", job_id
    )
    EVIDENCE.check(
        "wordbook.export.download.expiry.forced-to-past",
        forced < datetime.now(UTC),
        job_id=str(job_id),
        forced_expires_at=forced.isoformat(),
    )

    expired = client.request(
        "GET",
        f"/exports/{job_id}/download",
        label="owner-downloads-expired-export",
        token=admin_token,
        expect=410,
    ).json()
    EVIDENCE.check(
        "wordbook.export.download.expired.returns-410",
        expired.get("code") == "EXPORT_DOWNLOAD_EXPIRED",
        code=expired.get("code"),
    )

    expired_job = client.request(
        "GET",
        f"/exports/{job_id}",
        label="owner-reads-expired-export-job",
        token=admin_token,
        expect=200,
    ).json()
    EVIDENCE.check(
        "wordbook.export.job.expired.hides-download-url",
        expired_job.get("download_url") is None,
        download_url=expired_job.get("download_url"),
        status=expired_job.get("status"),
    )
    return {"job_id": str(job_id)}


def scenario_member_private(
    client: Client,
    member_token: str,
    admin_token: str,
    *,
    json_name: str,
    txt_name: str,
) -> dict[str, Any]:
    # Import JSON rows are flat documents (a top-level array or {"words": [...]})
    # whose keys are matched through the same field-mapping table as CSV.
    json_payload = json.dumps(
        [
            {
                "headword": "diligent",
                "phonetic": "/\u02c8d\u026al\u026ad\u0292\u0259nt/",
                "part_of_speech": "adj",
                "definition_en": "showing careful and persistent effort",
                "definition_zh": "\u52e4\u594b\u7684",
                "example": "A diligent student.",
                "example_translation": "\u4e00\u4e2a\u52e4\u594b\u7684\u5b66\u751f\u3002",
            },
            {
                "headword": "eager",
                "phonetic": "/\u02c8i\u02d0\u0261\u0259/",
                "part_of_speech": "adj",
                "definition_en": "wanting to do something very much",
                "definition_zh": "\u70ed\u5207\u7684",
                "example": "Eager to learn.",
                "example_translation": "\u6e34\u671b\u5b66\u4e60\u3002",
            },
        ],
        ensure_ascii=False,
    ).encode("utf-8")

    preview = upload_preview(
        client,
        member_token,
        label="member-json-preview",
        filename="qa-m2core-private.json",
        payload=json_payload,
        visibility="private",
        name=json_name,
        mime="application/json",
    )
    EVIDENCE.check(
        "wordbook.json.preview.detects-private-format",
        preview["detected_format"] == "json"
        and preview["requested_visibility"] == "private"
        and preview["valid_rows"] == 2
        and preview["error_count"] == 0,
        detected_format=preview["detected_format"],
        encoding=preview["encoding"],
        valid_rows=preview["valid_rows"],
        error_count=preview["error_count"],
    )

    remapped = remap_preview(client, member_token, preview, label="member-json-remap").json()
    confirm = confirm_import(
        client,
        member_token,
        remapped,
        label="member-json-confirm",
        name=json_name,
        visibility="private",
        idempotency_key=new_key("qa-private-json"),
    ).json()
    json_job = poll_job(client, confirm["job_id"], member_token, label="member-json-import")
    EVIDENCE.check(
        "wordbook.json.private-import.succeeds",
        json_job["status"] == "succeeded" and json_job["result"].get("entry_count") == 2,
        job_id=str(json_job["job_id"]),
        result=json_job["result"],
    )
    json_book_id = str(json_job["wordbook_id"])

    # TXT wordbooks are parsed as headerless tab-separated rows in canonical
    # field order: headword, phonetic, part_of_speech, definition_en,
    # definition_zh, example, example_translation.
    gb18030_txt = (
        "frugal\t/\u02c8fru\u02d0\u0261\u0259l/\tadj\tcareful with money\t\u8282\u4fed\u7684\t"
        "A frugal household.\t\u4e00\u4e2a\u8282\u4fed\u7684\u5bb6\u5ead\u3002\n"
        "grasp\t/\u0261r\u0251\u02d0sp/\tverb\tto understand fully\t\u9886\u4f1a\t"
        "I grasped the idea.\t\u6211\u9886\u4f1a\u4e86\u8fd9\u4e2a\u60f3\u6cd5\u3002\n"
    )
    txt_payload = gb18030_txt.encode("gb18030")
    txt_preview = upload_preview(
        client,
        member_token,
        label="member-gb18030-txt-preview",
        filename="qa-m2core-private.txt",
        payload=txt_payload,
        visibility="private",
        name=txt_name,
        mime="text/plain",
    )
    EVIDENCE.check(
        "wordbook.txt.gb18030.preview.decodes-chinese",
        txt_preview["detected_format"] == "txt"
        and txt_preview["encoding"] == "gb18030"
        and txt_preview["valid_rows"] >= 1,
        detected_format=txt_preview["detected_format"],
        encoding=txt_preview["encoding"],
        valid_rows=txt_preview["valid_rows"],
        error_count=txt_preview["error_count"],
        warnings=txt_preview["warning_count"],
    )

    txt_remapped = remap_preview(
        client, member_token, txt_preview, label="member-gb18030-txt-remap"
    ).json()
    txt_confirm = confirm_import(
        client,
        member_token,
        txt_remapped,
        label="member-gb18030-txt-confirm",
        name=txt_name,
        visibility="private",
        idempotency_key=new_key("qa-private-txt"),
    ).json()
    txt_job = poll_job(client, txt_confirm["job_id"], member_token, label="member-txt-import")
    EVIDENCE.check(
        "wordbook.txt.gb18030.private-import.succeeds",
        txt_job["status"] == "succeeded",
        job_id=str(txt_job["job_id"]),
        result=txt_job["result"],
    )
    txt_book_id = str(txt_job["wordbook_id"])
    txt_detail = client.request(
        "GET", f"/wordbooks/{txt_book_id}", label="member-txt-detail", token=member_token, expect=200
    ).json()
    headwords = [entry["headword"] for entry in txt_detail["entries"]]
    EVIDENCE.check(
        "wordbook.txt.gb18030.detail.round-trips-chinese",
        "frugal" in headwords
        and any(
            definition["definition_zh"] == "\u8282\u4fed\u7684"
            for entry in txt_detail["entries"]
            for definition in entry["definitions"]
        ),
        headwords=headwords,
    )

    member_activation = client.request(
        "POST",
        f"/wordbooks/{txt_book_id}/activate",
        label="member-txt-activate",
        token=member_token,
        expect=200,
    ).json()
    EVIDENCE.check(
        "wordbook.private.member-activate.succeeds",
        member_activation["is_active"] is True and member_activation["wordbook_id"] == txt_book_id,
        wordbook_id=txt_book_id,
    )

    admin_detail = client.request(
        "GET",
        f"/wordbooks/{json_book_id}",
        label="admin-read-member-private",
        token=admin_token,
        expect=404,
    ).json()
    EVIDENCE.check(
        "wordbook.private.admin-cannot-read.body",
        admin_detail.get("code") == "WORDBOOK_NOT_FOUND",
        code=admin_detail.get("code"),
    )

    admin_list = client.request(
        "GET", "/wordbooks", label="admin-list-private-visibility", token=admin_token, expect=200
    ).json()
    hidden = [item for item in admin_list["items"] if item["visibility"] == "private"]
    EVIDENCE.check(
        "wordbook.private.admin-list.omits-other-members-books",
        all(item["id"] not in {json_book_id, txt_book_id} for item in admin_list["items"]),
        admin_visible_private_count=len(hidden),
        admin_visible_ids=[item["id"] for item in hidden],
    )

    member_org_attempt = client.request(
        "POST",
        "/wordbooks/import/preview",
        label="member-organization-preview-forbidden",
        token=member_token,
        files={"file": ("qa-org-attempt.csv", CSV_SOURCE.encode("utf-8"), "text/csv")},
        data={"visibility": "organization", "name": "member must not create org"},
        expect=403,
    ).json()
    EVIDENCE.check(
        "wordbook.organization.member-cannot-import",
        member_org_attempt.get("code") == "FORBIDDEN",
        code=member_org_attempt.get("code"),
    )

    member_list = client.request(
        "GET", "/wordbooks", label="member-list-own-books", token=member_token, expect=200
    ).json()
    EVIDENCE.check(
        "wordbook.private.member-list.shows-own-and-organization",
        {item["id"] for item in member_list["items"]} >= {json_book_id, txt_book_id}
        and all(
            item["visibility"] == "organization" or item["owner_id"] is not None
            for item in member_list["items"]
        ),
        item_count=len(member_list["items"]),
    )
    return {
        "json_book_id": json_book_id,
        "txt_book_id": txt_book_id,
        "member_id": None,
    }


async def scenario_preview_expiry(
    client: Client,
    admin_token: str,
    pg: asyncpg.Connection,
) -> dict[str, Any]:
    preview = upload_preview(
        client,
        admin_token,
        label="expiry-csv-preview",
        filename="qa-expiry.csv",
        payload=CSV_SOURCE.encode("utf-8"),
        visibility="organization",
        name="QA Expiry Probe Organization",
    )
    preview_id = preview["preview_id"]

    original = await scalar(
        pg, "select expires_at from wordbook_import_previews where id = $1", preview_id
    )
    past = datetime.now(UTC) - timedelta(hours=2)
    await pg.execute(
        "update wordbook_import_previews set expires_at = $2 where id = $1", preview_id, past
    )
    forced = await scalar(
        pg, "select expires_at from wordbook_import_previews where id = $1", preview_id
    )
    EVIDENCE.check(
        "wordbook.preview.expiry.forced-to-past",
        forced < datetime.now(UTC),
        preview_id=str(preview_id),
        original_ttl_hours=round((original - datetime.now(UTC)).total_seconds() / 3600, 2),
        forced_expires_at=forced.isoformat(),
    )

    remap = remap_preview(
        client, admin_token, preview, label="expiry-remap-after-expiry", expect=410
    ).json()
    EVIDENCE.check(
        "wordbook.preview.expiry.blocks-remap-with-410",
        remap.get("code") == "WORDBOOK_PREVIEW_EXPIRED",
        code=remap.get("code"),
    )

    confirm = confirm_import(
        client,
        admin_token,
        preview,
        label="expiry-confirm-after-expiry",
        name="QA Expiry Probe Organization",
        visibility="organization",
        idempotency_key=new_key("qa-expiry"),
        expect=410,
    ).json()
    EVIDENCE.check(
        "wordbook.preview.expiry.blocks-confirm-with-410",
        confirm.get("code") == "WORDBOOK_PREVIEW_EXPIRED",
        code=confirm.get("code"),
    )

    status = await scalar(
        pg, "select status from wordbook_import_previews where id = $1", preview_id
    )
    EVIDENCE.check(
        "wordbook.preview.expiry.persists-expired-status",
        status == "expired",
        status=status,
    )
    return {"preview_id": str(preview_id)}


async def scenario_delete_midflight(
    client: Client,
    admin_token: str,
    org: dict[str, Any],
    pg: asyncpg.Connection,
) -> dict[str, Any]:
    wordbook_id = org["wordbook_id"]
    docker(["stop", WORKER_CONTAINER], label="stop-worker-for-delete-409")
    try:
        # The exact-name rule is evaluated before any state change, so probe it while
        # the wordbook is still ready.
        wrong_name = client.request(
            "DELETE",
            f"/wordbooks/{wordbook_id}",
            label="delete-wrong-confirm-name",
            token=admin_token,
            idempotency_key=new_key("qa-org-delete-bad"),
            json={"confirm_name": "not the real name"},
            expect=400,
        ).json()
        EVIDENCE.check(
            "wordbook.delete.rejects-wrong-organization-name",
            wrong_name.get("code") == "WORDBOOK_NAME_CONFIRMATION_REQUIRED",
            code=wrong_name.get("code"),
        )

        deleted = client.request(
            "DELETE",
            f"/wordbooks/{wordbook_id}",
            label="admin-delete-organization",
            token=admin_token,
            idempotency_key=new_key("qa-org-delete"),
            json={"confirm_name": org["name"]},
            expect=202,
        ).json()
        EVIDENCE.check(
            "wordbook.delete.organization.queues-cleanup",
            deleted["kind"] == "delete" and deleted["status"] == "queued",
            job_id=str(deleted["job_id"]),
        )

        db_status = await scalar(pg, "select status from wordbooks where id = $1", wordbook_id)
        EVIDENCE.check(
            "wordbook.delete.marks-deleting-before-return",
            db_status == "deleting",
            db_status=db_status,
        )

        blocked_activate = client.request(
            "POST",
            f"/wordbooks/{wordbook_id}/activate",
            label="delete-in-progress-activate",
            token=admin_token,
            expect=409,
        ).json()
        EVIDENCE.check(
            "wordbook.delete.blocks-activation-with-409",
            blocked_activate.get("code") == "WORDBOOK_NOT_READY",
            code=blocked_activate.get("code"),
        )

        blocked_export = client.request(
            "POST",
            f"/wordbooks/{wordbook_id}/export",
            label="delete-in-progress-export",
            token=admin_token,
            idempotency_key=new_key("qa-delete-export"),
            json={"format": "csv"},
            expect=409,
        ).json()
        EVIDENCE.check(
            "wordbook.delete.blocks-export-with-409",
            blocked_export.get("code") == "WORDBOOK_NOT_READY",
            code=blocked_export.get("code"),
        )

        blocked_patch = client.request(
            "PATCH",
            f"/wordbooks/{wordbook_id}",
            label="delete-in-progress-patch",
            token=admin_token,
            json={"name": "should not apply"},
            expect=409,
        ).json()
        EVIDENCE.check(
            "wordbook.delete.blocks-metadata-patch-with-409",
            blocked_patch.get("code") == "WORDBOOK_DELETING",
            code=blocked_patch.get("code"),
        )

        blocked_detail = client.request(
            "GET",
            f"/wordbooks/{wordbook_id}",
            label="delete-in-progress-detail",
            token=admin_token,
            expect=200,
        ).json()
        EVIDENCE.check(
            "wordbook.delete.hides-entries-immediately",
            blocked_detail["total_entries"] == 3
            and blocked_detail["wordbook"]["status"] == "deleting",
            total_entries=blocked_detail["total_entries"],
            status=blocked_detail["wordbook"]["status"],
        )

        repeat = client.request(
            "DELETE",
            f"/wordbooks/{wordbook_id}",
            label="delete-repeat-same-book",
            token=admin_token,
            idempotency_key=new_key("qa-org-delete-repeat"),
            json={"confirm_name": org["name"]},
            expect=202,
        ).json()
        EVIDENCE.check(
            "wordbook.delete.repeat-returns-existing-job",
            repeat["job_id"] == deleted["job_id"],
            first=str(deleted["job_id"]),
            repeat=str(repeat["job_id"]),
        )

        return {"delete_job_id": str(deleted["job_id"])}
    finally:
        docker(["start", WORKER_CONTAINER], label="start-worker-after-delete-409")


async def scenario_worker_down_queue(
    client: Client,
    admin_token: str,
    pg: asyncpg.Connection,
    *,
    name: str,
) -> dict[str, Any]:
    preview = upload_preview(
        client,
        admin_token,
        label="queue-csv-preview",
        filename="qa-queue.csv",
        payload=CSV_SOURCE.encode("utf-8"),
        visibility="organization",
        name=name,
    )
    remapped = remap_preview(client, admin_token, preview, label="queue-csv-remap").json()
    docker(["stop", WORKER_CONTAINER], label="stop-worker-for-queue-probe")
    try:
        confirm = confirm_import(
            client,
            admin_token,
            remapped,
            label="queue-confirm-with-worker-down",
            name=name,
            visibility="organization",
            idempotency_key=new_key("qa-queue-import"),
        ).json()
        EVIDENCE.check(
            "wordbook.queue.import-accepted-while-worker-down",
            confirm["status"] == "queued",
            job_id=str(confirm["job_id"]),
        )

        time.sleep(8)
        parked = client.request(
            "GET",
            f"/wordbooks/jobs/{confirm['job_id']}",
            label="queue-job-still-queued",
            token=admin_token,
            expect=200,
        ).json()
        db_state = await scalar(
            pg,
            "select status || ':' || attempts from wordbook_jobs where id = $1",
            confirm["job_id"],
        )
        EVIDENCE.check(
            "wordbook.queue.job-stays-queued-without-worker",
            parked["status"] == "queued" and parked["progress"] == 0,
            api_status=parked["status"],
            api_progress=parked["progress"],
            db_state=db_state,
        )

        queued_keys = docker(
            ["exec", "a30-m2core-redis", "redis-cli", "-n", "0", "zcard", "english-learn:wordbooks"],
            label="redis-queue-depth",
        ).strip()
        EVIDENCE.check(
            "wordbook.queue.arq-entry-present-in-redis",
            queued_keys.isdigit() and int(queued_keys) >= 1,
            arq_queue_depth=queued_keys,
        )
    finally:
        docker(["start", WORKER_CONTAINER], label="start-worker-for-queue-recovery")

    recovered = poll_job(
        client, confirm["job_id"], admin_token, label="queue-recovery", timeout=180.0
    )
    EVIDENCE.check(
        "wordbook.queue.job-recovers-after-worker-restart",
        recovered["status"] == "succeeded"
        and recovered["result"].get("entry_count") == 3,
        job_id=str(recovered["job_id"]),
        observed_statuses=recovered["_observed_statuses"],
        result=recovered["result"],
    )
    return {"wordbook_id": str(recovered["wordbook_id"]), "job_id": str(recovered["job_id"])}


async def scenario_ghost_data(
    client: Client,
    admin_token: str,
    org: dict[str, Any],
    delete_job_id: str,
    pg: asyncpg.Connection,
) -> dict[str, Any]:
    wordbook_id = org["wordbook_id"]
    job = poll_job(client, delete_job_id, admin_token, label="delete-job", timeout=180.0)
    EVIDENCE.check(
        "wordbook.delete.job-succeeds",
        job["status"] == "succeeded" and job["cleanup_status"] == "completed",
        job_id=str(job["job_id"]),
        result=job["result"],
        cleanup_status=job["cleanup_status"],
    )

    counts = {
        "wordbooks": await row_count(
            pg, "select count(*) from wordbooks where id = $1 and status = 'deleted'", wordbook_id
        ),
        "entries": await row_count(
            pg, "select count(*) from wordbook_entries where wordbook_id = $1", wordbook_id
        ),
        "definitions": await row_count(
            pg,
            "select count(*) from wordbook_definitions d "
            "join wordbook_entries e on e.id = d.entry_id where e.wordbook_id = $1",
            wordbook_id,
        ),
        "examples": await row_count(
            pg,
            "select count(*) from wordbook_examples x "
            "join wordbook_definitions d on d.id = x.definition_id "
            "join wordbook_entries e on e.id = d.entry_id where e.wordbook_id = $1",
            wordbook_id,
        ),
        "activations": await row_count(
            pg, "select count(*) from wordbook_activations where wordbook_id = $1", wordbook_id
        ),
        "previews": await row_count(
            pg, "select count(*) from wordbook_import_previews where wordbook_id = $1", wordbook_id
        ),
        "other_jobs": await row_count(
            pg,
            "select count(*) from wordbook_jobs where wordbook_id = $1 and id <> $2",
            wordbook_id,
            delete_job_id,
        ),
        "delete_jobs": await row_count(
            pg, "select count(*) from wordbook_jobs where wordbook_id = $1 and kind = 'delete'",
            wordbook_id,
        ),
    }
    EVIDENCE.check(
        "wordbook.delete.leaves-no-ghost-rows",
        counts["wordbooks"] == 1
        and counts["entries"] == 0
        and counts["definitions"] == 0
        and counts["examples"] == 0
        and counts["activations"] == 0
        and counts["previews"] == 0
        and counts["other_jobs"] == 0
        and counts["delete_jobs"] == 1,
        counts=counts,
    )

    tombstone = await pg.fetchrow(
        "select name, description, status, metadata from wordbooks where id = $1", wordbook_id
    )
    EVIDENCE.check(
        "wordbook.delete.keeps-minimal-tombstone",
        tombstone["status"] == "deleted"
        and tombstone["description"] is None
        and json.loads(tombstone["metadata"] or "{}") == {"deleted": True},
        status=tombstone["status"],
        description_is_null=tombstone["description"] is None,
        metadata=json.loads(tombstone["metadata"] or "{}"),
    )

    detail = client.request(
        "GET", f"/wordbooks/{wordbook_id}", label="deleted-detail", token=admin_token, expect=404
    ).json()
    EVIDENCE.check(
        "wordbook.delete.hidden-from-detail",
        detail.get("code") == "WORDBOOK_NOT_FOUND",
        code=detail.get("code"),
    )

    listing = client.request(
        "GET", "/wordbooks", label="deleted-list", token=admin_token, expect=200
    ).json()
    EVIDENCE.check(
        "wordbook.delete.hidden-from-list",
        all(item["id"] != wordbook_id for item in listing["items"]),
        remaining=len(listing["items"]),
    )

    leftover = container_files("wordbook-")
    EVIDENCE.check(
        "wordbook.delete.removes-shared-volume-artifacts",
        leftover == [],
        storage_path=STORAGE_PATH,
        leftover_prefix_wordbook=leftover,
    )

    export_leftovers = container_files("export-")
    EVIDENCE.check(
        "wordbook.delete.removes-related-export-artifacts",
        export_leftovers == [],
        leftover_export_files=export_leftovers,
    )
    return {"counts": counts}


def scenario_cors_and_security(client: Client, admin_token: str) -> dict[str, Any]:
    preflight = client.http.request(
        "OPTIONS",
        "/wordbooks/import",
        headers={
            "Origin": "http://127.0.0.1:4180",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type,idempotency-key",
        },
    )
    allowed = preflight.headers.get("access-control-allow-headers", "").lower()
    EVIDENCE.network.append(
        {
            "label": "cors-preflight-import",
            "method": "OPTIONS",
            "path": "/wordbooks/import",
            "status_code": preflight.status_code,
            "request_id": preflight.headers.get("X-Request-ID"),
            "body": {"allow_headers": allowed},
        }
    )
    EVIDENCE.check(
        "cors.preflight.allows-idempotency-key",
        preflight.status_code in (200, 204)
        and "idempotency-key" in allowed
        and preflight.headers.get("access-control-allow-origin") == "http://127.0.0.1:4180"
        and preflight.headers.get("access-control-allow-credentials") == "true",
        status_code=preflight.status_code,
        allow_headers=allowed,
        allow_origin=preflight.headers.get("access-control-allow-origin"),
        allow_credentials=preflight.headers.get("access-control-allow-credentials"),
    )

    export_preflight = client.http.request(
        "OPTIONS",
        "/exports/00000000-0000-0000-0000-000000000000/download",
        headers={
            "Origin": "http://127.0.0.1:4180",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    EVIDENCE.check(
        "cors.preflight.allows-export-download",
        export_preflight.status_code in (200, 204)
        and export_preflight.headers.get("access-control-allow-origin")
        == "http://127.0.0.1:4180",
        status_code=export_preflight.status_code,
    )

    empty = client.request(
        "POST",
        "/wordbooks/import/preview",
        label="security-empty-file",
        token=admin_token,
        files={"file": ("empty.csv", b"", "text/csv")},
        data={"visibility": "organization", "name": "empty"},
        expect=422,
    ).json()
    EVIDENCE.check(
        "security.empty-file.rejected",
        empty.get("code") == "IMPORT_FILE_EMPTY",
        code=empty.get("code"),
    )

    bad_ext = client.request(
        "POST",
        "/wordbooks/import/preview",
        label="security-unsupported-extension",
        token=admin_token,
        files={"file": ("payload.exe", b"MZ\x90\x00binary", "application/octet-stream")},
        data={"visibility": "organization", "name": "exe"},
        expect=415,
    ).json()
    EVIDENCE.check(
        "security.unsupported-extension.rejected",
        bad_ext.get("code") == "IMPORT_FILE_TYPE_UNSUPPORTED",
        code=bad_ext.get("code"),
    )

    html = client.request(
        "POST",
        "/wordbooks/import/preview",
        label="security-html-payload",
        token=admin_token,
        files={"file": ("page.csv", b"<html><script>alert(1)</script></html>", "text/csv")},
        data={"visibility": "organization", "name": "html"},
        expect=415,
    ).json()
    EVIDENCE.check(
        "security.html-script-payload.rejected",
        html.get("code") == "IMPORT_UNSAFE_CONTENT",
        code=html.get("code"),
    )

    traversal = client.request(
        "POST",
        "/wordbooks/import/preview",
        label="security-path-traversal-filename",
        token=admin_token,
        files={"file": ("../../etc/evil.csv", CSV_SOURCE.encode("utf-8"), "text/csv")},
        data={"visibility": "organization", "name": "traversal"},
        expect=(422, 400),
    ).json()
    EVIDENCE.check(
        "security.path-traversal-filename.rejected",
        traversal.get("code") in {"WORDBOOK_FILE_NAME_INVALID", "IMPORT_FILE_NAME_INVALID"},
        code=traversal.get("code"),
    )

    oversized = b"headword,definition_en,definition_zh\n" + b"a" * (10 * 1024 * 1024 + 64)
    too_large = client.request(
        "POST",
        "/wordbooks/import/preview",
        label="security-oversized-file",
        token=admin_token,
        files={"file": ("huge.csv", oversized, "text/csv")},
        data={"visibility": "organization", "name": "huge"},
        expect=413,
    ).json()
    EVIDENCE.check(
        "security.oversized-file.rejected-with-413",
        too_large.get("code") == "IMPORT_FILE_TOO_LARGE",
        code=too_large.get("code"),
    )

    traversal_export = client.request(
        "GET",
        "/exports/../../etc/passwd/download",
        label="security-export-download-traversal",
        token=admin_token,
        expect=(404, 405),
    )
    EVIDENCE.check(
        "security.export-download.path-traversal.not-served",
        traversal_export.status_code in {404, 405},
        status_code=traversal_export.status_code,
    )
    return {}


# --------------------------------------------------------------------------- main


async def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    client = Client()
    pg: asyncpg.Connection | None = None
    result: dict[str, Any]
    try:
        pg = await db_connect()

        EVIDENCE.artifacts["environment"] = {
            "postgres_version": (await scalar(pg, "select version()")).split(" on ")[0],
            "api_base_url": API_BASE_URL,
            "storage_container": STORAGE_CONTAINER,
            "storage_path": STORAGE_PATH,
            "worker_container": WORKER_CONTAINER,
            "containers": docker(["ps", "--format", "json"], label="container-inventory"),
        }
        openapi = client.request("GET", "/openapi.json", label="openapi", expect=200).json()
        EVIDENCE.check(
            "contract.openapi.surface-is-frozen",
            openapi["openapi"] == "3.1.0"
            and len(openapi["paths"]) == 24
            and len(openapi["components"]["schemas"]) == 42,
            openapi=openapi["openapi"],
            paths=len(openapi["paths"]),
            schemas=len(openapi["components"]["schemas"]),
        )

        ready_body = httpx.get(
            f"{API_BASE_URL}/health/ready", timeout=30.0
        ).json()
        EVIDENCE.check(
            "health.readiness.database-and-redis-ok",
            ready_body["status"] == "ready"
            and ready_body["components"]["database"]["status"] == "ok"
            and ready_body["components"]["redis"]["status"] == "ok",
            database_latency_ms=ready_body["components"]["database"]["latency_ms"],
            redis_latency_ms=ready_body["components"]["redis"]["latency_ms"],
        )

        session = scenario_auth(client)
        member = scenario_member(client, session["admin_token"])
        EVIDENCE.artifacts["member_id"] = member["member_id"]

        org = scenario_admin_csv_chain(
            client,
            session["admin_token"],
            name=f"QA Phase A Organization {stamp}",
        )
        EVIDENCE.artifacts["organization_wordbook_id"] = org["wordbook_id"]

        export_probe = scenario_exports(client, session["admin_token"], org)
        EVIDENCE.artifacts["exports"] = export_probe["exports"]

        await scenario_export_authorization(
            client,
            member["member_token"],
            session["admin_token"],
            export_probe,
            pg,
        )

        private_books = scenario_member_private(
            client,
            member["member_token"],
            session["admin_token"],
            json_name=f"QA Phase A Private JSON {stamp}",
            txt_name=f"QA Phase A Private TXT {stamp}",
        )
        EVIDENCE.artifacts["private_json_wordbook_id"] = private_books["json_book_id"]
        EVIDENCE.artifacts["private_txt_wordbook_id"] = private_books["txt_book_id"]

        await scenario_preview_expiry(client, session["admin_token"], pg)
        scenario_cors_and_security(client, session["admin_token"])

        queued = await scenario_worker_down_queue(
            client,
            session["admin_token"],
            pg,
            name=f"QA Phase A Queue Recovery {stamp}",
        )
        EVIDENCE.artifacts["queue_recovery_wordbook_id"] = queued["wordbook_id"]

        delete_probe = await scenario_delete_midflight(
            client, session["admin_token"], org, pg
        )
        await scenario_ghost_data(
            client, session["admin_token"], org, delete_probe["delete_job_id"], pg
        )

        EVIDENCE.check(
            "api.acceptance.all-scenarios-completed",
            True,
            checks=len(EVIDENCE.checks),
            requests=len(EVIDENCE.network),
        )
        result = EVIDENCE.finish()
        status = 0
    except CheckFailure as exc:
        result = EVIDENCE.finish(error=f"CheckFailure: {exc}")
        status = 1
    except Exception as exc:  # pragma: no cover - defensive evidence capture
        import traceback

        traceback.print_exc()
        result = EVIDENCE.finish(error=f"{type(exc).__name__}: {exc}")
        status = 1
    finally:
        if pg is not None:
            await pg.close()
        client.close()

    path = RUN_DIR / "api-acceptance.json"
    path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(f"\nRESULT={result['status']} evidence={path}")
    if result["status"] != "PASS":
        print(f"ERROR: {result['error']}")
    return status


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
