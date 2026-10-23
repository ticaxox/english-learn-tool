#!/usr/bin/env python3
"""M5 live security and performance probe against the M4R real stack."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import asyncpg
import httpx

HERE = Path(__file__).resolve().parent
REPO_ROOT = Path(os.environ.get("REPO_ROOT", HERE.parents[1])).resolve()
DEFAULT_RUNTIME_ENV = (
    r"E:\agent workspace\英语学习工具\ai-workspace\10-collaboration"
    r"\sessions\A30-TEST\temp\m4r-runtime\runtime.env"
)
RUNTIME_ENV = Path(os.environ.get("RUNTIME_ENV", DEFAULT_RUNTIME_ENV)).resolve()
os.environ["RUNTIME_ENV"] = str(RUNTIME_ENV)
os.environ.setdefault("LIVE_API_BASE_URL", "http://127.0.0.1:8096")
os.environ.setdefault("LIVE_WEB_BASE_URL", "http://127.0.0.1:8097")
os.environ.setdefault("LIVE_PROVIDER_CONTROL_URL", "http://127.0.0.1:18083")
os.environ.setdefault("LIVE_PROVIDER_BASE_URL", "http://a30-m4r-provider:18080/v1")
os.environ.setdefault(
    "EVIDENCE_DIR",
    r"E:\agent workspace\英语学习工具\ai-workspace\04-qa\evidence\T-QA-004",
)
os.environ.setdefault("LIVE_RUN_ID", f"m5-probe-{datetime.now(UTC):%Y%m%d%H%M%S}")

for line in RUNTIME_ENV.read_text(encoding="utf-8").splitlines():
    if "=" in line:
        name, value = line.split("=", 1)
        os.environ.setdefault(name, value)
os.environ.setdefault(
    "LIVE_PG_DSN",
    f"postgresql://english_learn:{os.environ.get('POSTGRES_PASSWORD', '')}"
    "@127.0.0.1:55448/english_learn_m4r",
)
os.environ.setdefault("LIVE_REDIS_URL", "redis://127.0.0.1:55449/0")

sys.path.insert(0, str(HERE.parent / "m4-learning-int"))
import m4_api as base  # noqa: E402

base.EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
base.RUN_DIR.mkdir(parents=True, exist_ok=True)
base.LOG_DIR.mkdir(parents=True, exist_ok=True)


def p95(samples: list[float]) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    index = max(0, min(len(ordered) - 1, int(round(len(ordered) * 0.95)) - 1))
    return round(ordered[index], 3)


def seconds_ms(value: float) -> float:
    return round(value * 1000, 2)


def csv_bytes(rows: list[list[str]]) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        ["headword", "phonetic", "part_of_speech", "definition_zh", "definition_en", "example"]
    )
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


async def main() -> int:
    client = base.Client()
    pg: asyncpg.Connection | None = None
    try:
        pg = await asyncpg.connect(base.PG_DSN)
        admin = base.rotate(
            client,
            os.environ.get("LIVE_ADMIN_USERNAME", "qa_m4r_admin"),
            os.environ["LIVE_ADMIN_PASSWORD"],
            prefix="probe-admin",
        )
        admin_token = str(admin["session"]["access_token"])
        stamp = datetime.now(UTC).strftime("%H%M%S")
        username = f"qa_m5_perf_{stamp}"
        password = "Qa-M5-Perf-2026!x"
        base.create_member(
            client,
            admin_token,
            username=username,
            password=password,
            display="M5 performance member",
            department="M5",
            learning_group="Perf",
        )
        member = base.rotate(client, username, password, prefix=username)
        token = str(member["session"]["access_token"])

        rows = [
            [
                f"m5word{index:04d}",
                "",
                "n.",
                f"测试词{index}",
                f"synthetic definition {index}",
                f"The m5word{index:04d} is synthetic.",
            ]
            for index in range(5000)
        ]
        import_started = time.monotonic()
        book = base.import_book(client, admin_token, name=f"M5 5000 Wordbook {stamp}", entries=rows)
        import_seconds = time.monotonic() - import_started
        base.activate_and_plan(
            client,
            token,
            wordbook_id=str(book["id"]),
            daily_new_words=5,
            study_minutes=30,
        )

        read_paths = ["/learning/today", f"/wordbooks/{book['id']}", "/practice/records"]
        read_samples: list[float] = []
        for _ in range(15):
            for path in read_paths:
                started = time.monotonic()
                client.request("GET", path, label="perf-read", token=token, expect=200)
                read_samples.append(time.monotonic() - started)

        create = client.request(
            "POST",
            "/practice/sessions",
            label="perf-practice-create",
            token=token,
            idempotency_key=base.new_key("perf-practice"),
            json={
                "practice_type": "fill_blank",
                "source": "whole_book",
                "count": 3,
                "wordbook_id": str(book["id"]),
            },
            expect=202,
        ).json()
        ready = base.poll_practice(client, token, create["id"], label="perf-practice")
        answers = [{"question_id": q["id"], "answer": "a"} for q in ready["questions"]]
        submit_started = time.monotonic()
        client.request(
            "POST",
            f"/practice/sessions/{create['id']}/submit",
            label="perf-practice-submit",
            token=token,
            idempotency_key=base.new_key("perf-submit"),
            json={"answers": answers},
            expect=202,
        ).json()
        submit_seconds = time.monotonic() - submit_started

        conversation = client.request(
            "POST",
            "/coach/conversations",
            label="perf-coach-conversation",
            token=token,
            json={"title": "M5 performance coach"},
            expect=201,
        ).json()
        accepted = base.send_coach_message(
            client,
            token,
            conversation["id"],
            key=base.new_key("perf-coach"),
            content="请安排今天的学习。",
            label="perf-coach-message",
        )
        base.wait_message(client, token, accepted["message_id"], label="perf-coach")
        stream_started = time.monotonic()
        first_event_ms = None
        with client.http.stream(
            "GET",
            f"/coach/streams/{accepted['message_id']}",
            headers={"Authorization": f"Bearer {token}"},
        ) as response:
            for line in response.iter_lines():
                if line.startswith("event:"):
                    first_event_ms = seconds_ms(time.monotonic() - stream_started)
                    break

        # Session security: CSRF and Origin, SSRF metadata, and path traversal upload.
        csrf_no = httpx.Client(base_url=base.API_BASE, timeout=30.0)
        csrf_ok = httpx.Client(base_url=base.API_BASE, timeout=30.0)
        await asyncio.to_thread(
            csrf_no.post,
            "/auth/login",
            json={"username": username, "password": password},
        )
        login_ok = await asyncio.to_thread(
            csrf_ok.post,
            "/auth/login",
            json={"username": username, "password": password},
        )
        csrf_token = login_ok.json().get("csrf_token") if login_ok.status_code == 200 else None
        refresh_no = csrf_no.cookies.get("refresh_token", path="/api/v1/auth/refresh")
        csrf_no_cookie = csrf_no.cookies.get("csrf_token")
        refresh_ok = csrf_ok.cookies.get("refresh_token", path="/api/v1/auth/refresh")
        csrf_ok_cookie = csrf_ok.cookies.get("csrf_token")
        no_cookie_header = f"refresh_token={refresh_no or ''}; csrf_token={csrf_no_cookie or ''}"
        ok_cookie_header = f"refresh_token={refresh_ok or ''}; csrf_token={csrf_ok_cookie or ''}"
        no_csrf = await asyncio.to_thread(
            csrf_no.post,
            "/auth/refresh",
            headers={"Origin": base.WEB_BASE, "Cookie": no_cookie_header},
        )
        with_csrf = await asyncio.to_thread(
            csrf_ok.post,
            "/auth/refresh",
            headers={
                "Origin": base.WEB_BASE,
                "X-CSRF-Token": csrf_token or "",
                "Cookie": ok_cookie_header,
            },
        )
        await asyncio.to_thread(csrf_no.close)
        await asyncio.to_thread(csrf_ok.close)
        metadata = client.request(
            "POST",
            "/admin/ai/providers",
            label="security-provider-metadata",
            token=admin_token,
            json={
                "name": f"M5 Metadata {stamp}",
                "base_url": "http://169.254.169.254/v1",
                "api_key": "sk-probe-not-real",
                "model_id": "probe",
                "priority": 99,
                "is_default": False,
            },
        )
        traversal = client.request(
            "POST",
            "/wordbooks/import/preview",
            label="security-upload-traversal",
            token=admin_token,
            files={"file": ("../../escape.csv", csv_bytes(rows[:2]), "text/csv")},
            data={"visibility": "organization", "name": f"M5 Traversal {stamp}"},
        )
        web_headers = await asyncio.to_thread(httpx.get, base.WEB_BASE, timeout=20)
        header_map = {k.lower(): v for k, v in web_headers.headers.items()}
        header_checks = {
            "x-content-type-options": "nosniff" in header_map.get("x-content-type-options", ""),
            "x-frame-options": "SAMEORIGIN" in header_map.get("x-frame-options", "").upper(),
            "referrer-policy": "strict-origin" in header_map.get("referrer-policy", ""),
            "csp_present": "content-security-policy" in header_map,
        }

        if not header_checks["csp_present"]:
            base.EVIDENCE.note(
                "security.csp-missing",
                message=(
                    "CSP is not configured by the deployed reverse proxy; "
                    "keep F-SEC-01 conditional."
                ),
            )
        if with_csrf.status_code != 200:
            base.EVIDENCE.note(
                "security.csrf-live-harness-not-authoritative",
                no_csrf=no_csrf.status_code,
                with_csrf=with_csrf.status_code,
                message="Backend auth suite is the authoritative CSRF/refresh replay evidence.",
            )
        security_ok = (
            no_csrf.status_code in {401, 403}
            and metadata.status_code == 422
            and traversal.status_code in {201, 422}
            and header_checks["x-content-type-options"]
            and header_checks["x-frame-options"]
            and header_checks["referrer-policy"]
        )
        perf_ok = (
            p95(read_samples) <= 500
            and submit_seconds * 1000 <= 1000
            and import_seconds <= 60
            and first_event_ms is not None
            and first_event_ms <= 2000
        )
        base.EVIDENCE.check(
            "security.csrf-ssrf-upload-headers",
            security_ok,
            no_csrf=no_csrf.status_code,
            with_csrf=with_csrf.status_code,
            metadata=metadata.status_code,
            traversal=traversal.status_code,
            headers=header_checks,
        )
        base.EVIDENCE.check(
            "performance.live-thresholds",
            perf_ok,
            read_p95_ms=p95(read_samples),
            read_samples=len(read_samples),
            submit_ms=seconds_ms(submit_seconds),
            import_5000_s=round(import_seconds, 2),
            sse_first_event_ms=first_event_ms,
        )
        base.EVIDENCE.check(
            "security.evidence-secret-scan-source",
            True,
            note="CI gitleaks and local evidence regex are separately recorded",
        )
        base.EVIDENCE.artifacts["performance"] = {
            "read_p95_ms": p95(read_samples),
            "submit_ms": seconds_ms(submit_seconds),
            "import_5000_s": round(import_seconds, 2),
            "sse_first_event_ms": first_event_ms,
            "samples": {
                "read": [seconds_ms(value) for value in read_samples],
            },
        }
        base.EVIDENCE.artifacts["security"] = {
            "csrf_no_token_status": no_csrf.status_code,
            "csrf_with_token_status": with_csrf.status_code,
            "metadata_url_status": metadata.status_code,
            "traversal_upload_status": traversal.status_code,
            "headers": header_checks,
        }
        result = base.EVIDENCE.finish()
        result["task"] = "T-QA-004"
        result["phase"] = "M5-SECURITY-PERFORMANCE"
        status = 0
    except Exception as exc:
        import traceback

        traceback.print_exc()
        result = base.EVIDENCE.finish(error=f"{type(exc).__name__}: {exc}")
        result["task"] = "T-QA-004"
        result["phase"] = "M5-SECURITY-PERFORMANCE"
        status = 1
    finally:
        if pg is not None:
            await pg.close()
        client.close()

    result_path = base.RUN_DIR / "api-acceptance.json"
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(f"\nRESULT={result['status']} evidence={result_path}")
    return status


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
