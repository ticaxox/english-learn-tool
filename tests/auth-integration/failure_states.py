#!/usr/bin/env python3
"""Probe authentication dependency failure without treating it as success."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx


def now() -> str:
    return datetime.now(UTC).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=("redis-down",), required=True)
    args = parser.parse_args()

    evidence_dir = Path(os.environ["EVIDENCE_DIR"]).resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    api_base = os.environ.get("LIVE_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    run_id = os.environ.get("LIVE_RUN_ID", f"a30-failure-{uuid4().hex[:12]}")
    request_id = f"{run_id}-login"

    record: dict[str, object] = {
        "run_id": run_id,
        "scenario": args.scenario,
        "started_at": now(),
        "api_base_url": api_base,
        "request_id_sent": request_id,
    }
    checks: list[dict[str, object]] = []

    def check(name: str, passed: bool, **details: object) -> None:
        checks.append(
            {"name": name, "status": "PASS" if passed else "FAIL", "details": details}
        )

    try:
        with httpx.Client(
            base_url=api_base, timeout=8.0, follow_redirects=False
        ) as client:
            response = client.post(
                "/api/v1/auth/login",
                headers={"X-Request-ID": request_id},
                json={
                    "username": "qa_dependency_probe",
                    "password": "Not-A-Real-Password-9!",
                },
            )

        try:
            body = response.json()
        except ValueError:
            body = {"body_type": "non-json", "text_prefix": response.text[:200]}

        header_request_id = response.headers.get("X-Request-ID")
        body_request_id = body.get("request_id") if isinstance(body, dict) else None
        code = body.get("code") if isinstance(body, dict) else None
        faked_success = 200 <= response.status_code < 300
        non_success = not faked_success
        request_id_preserved = (
            header_request_id == request_id and body_request_id == request_id
        )
        structured_error = (
            isinstance(body, dict) and bool(code) and bool(body_request_id)
        )
        explicit_dependency_failure = response.status_code in {503, 504} or code in {
            "AUTH_DEPENDENCY_UNAVAILABLE",
            "SERVICE_UNAVAILABLE",
            "DEPENDENCY_UNAVAILABLE",
        }

        record.update(
            {
                "finished_at": now(),
                "http_status": response.status_code,
                "code": code,
                "header_request_id": header_request_id,
                "body_request_id": body_request_id,
                "response_keys": sorted(body.keys()) if isinstance(body, dict) else [],
                "faked_success": faked_success,
                "request_id_preserved": request_id_preserved,
                "structured_error": structured_error,
                "explicit_dependency_failure": explicit_dependency_failure,
            }
        )

        check(
            "redis-down: login does not return a success status",
            non_success,
            http_status=response.status_code,
        )
        check(
            "redis-down: request id is preserved in header and body",
            request_id_preserved,
        )
        check("redis-down: response is a structured error", structured_error, code=code)
        record["classification"] = (
            "EXPLICIT_DEPENDENCY_FAILURE"
            if explicit_dependency_failure
            else "GENERIC_INTERNAL_ERROR"
        )
    except httpx.HTTPError as exc:  # network failure is also a fail-closed outcome
        record.update(
            {
                "finished_at": now(),
                "network_error": f"{type(exc).__name__}: {exc}",
                "faked_success": False,
                "classification": "TRANSPORT_FAILURE",
            }
        )
        check("redis-down: transport failure is fail-closed", True)
        check("redis-down: request id preserved in a structured response", False)

    record["checks"] = checks
    record["status"] = (
        "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL"
    )
    output = evidence_dir / "failure-state-result.json"
    output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(record, ensure_ascii=False, indent=2))
    print(f"RESULT={output}")
    return 0 if record["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
