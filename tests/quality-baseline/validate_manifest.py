#!/usr/bin/env python3
"""Validate the T-QA-001 acceptance-gate manifest.

This is a traceability gate, not a substitute for application tests. It verifies
that every gate has an owner, test layer, preconditions, data, command and
evidence policy. With an evidence root, it also checks that claimed evidence
exists. Use ``--require-final-pass`` only for final MVP acceptance.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ALLOWED_STATUSES = {"PASS", "CONDITIONAL", "FAIL", "BLOCKED", "NOT_RUN"}
ALLOWED_SCOPES = {"stage", "final"}
REQUIRED_FIELDS = (
    "id",
    "title",
    "source",
    "scope",
    "layer",
    "owner",
    "preconditions",
    "data",
    "command",
    "evidence",
    "status",
    "reason",
)


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("manifest root must be an object")
    return payload


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _non_empty_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(_non_empty_string(item) for item in value)


def validate_manifest(
    manifest: dict[str, Any],
    *,
    workspace_root: Path | None = None,
) -> tuple[list[str], Counter[str]]:
    errors: list[str] = []
    counts: Counter[str] = Counter()

    if manifest.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if not _non_empty_string(manifest.get("task")):
        errors.append("task must identify the owning task")

    gates = manifest.get("gates")
    if not isinstance(gates, list) or not gates:
        return errors + ["gates must be a non-empty list"], counts

    seen_ids: set[str] = set()
    for index, gate in enumerate(gates):
        label = f"gates[{index}]"
        if not isinstance(gate, dict):
            errors.append(f"{label} must be an object")
            continue

        missing = [field for field in REQUIRED_FIELDS if field not in gate]
        if missing:
            errors.append(f"{label} missing fields: {', '.join(missing)}")
            continue

        gate_id = gate["id"]
        if not _non_empty_string(gate_id):
            errors.append(f"{label}.id must be a non-empty string")
        elif gate_id in seen_ids:
            errors.append(f"duplicate gate id: {gate_id}")
        else:
            seen_ids.add(gate_id)

        for field in ("title", "layer", "owner", "reason"):
            if not _non_empty_string(gate[field]):
                errors.append(f"{label}.{field} must be a non-empty string")

        for field in ("source", "preconditions", "data", "command", "evidence"):
            if not _non_empty_list(gate[field]):
                errors.append(f"{label}.{field} must be a non-empty string list")

        scope = gate["scope"]
        if not _non_empty_string(scope) or scope not in ALLOWED_SCOPES:
            errors.append(f"{label}.scope must be one of {sorted(ALLOWED_SCOPES)}")

        status = gate["status"]
        if not _non_empty_string(status) or status not in ALLOWED_STATUSES:
            errors.append(f"{label}.status must be one of {sorted(ALLOWED_STATUSES)}")
        else:
            counts[status] += 1

        status_valid = isinstance(status, str) and status in ALLOWED_STATUSES
        if status_valid and status in {"PASS", "CONDITIONAL"}:
            evidence = gate["evidence"]
            if not _non_empty_list(evidence):
                errors.append(f"{label} claims {status} without evidence")
            elif workspace_root is not None:
                for relative in evidence:
                    candidate = workspace_root / relative
                    if not candidate.is_file():
                        errors.append(f"{label} evidence missing: {relative}")

        if status_valid and status == "CONDITIONAL" and not _non_empty_list(gate.get("conditions")):
            errors.append(f"{label} is CONDITIONAL but has no non-empty conditions list")

    return errors, counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).with_name("acceptance-gates.json"),
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        help="Workspace root used to resolve ai-workspace evidence paths.",
    )
    parser.add_argument(
        "--require-final-pass",
        action="store_true",
        help="Fail unless every final-scope gate is PASS.",
    )
    args = parser.parse_args(argv)

    try:
        manifest = load_manifest(args.manifest)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"MANIFEST_LOAD_ERROR: {exc}", file=sys.stderr)
        return 2

    errors, counts = validate_manifest(manifest, workspace_root=args.workspace_root)
    if args.require_final_pass:
        not_ready = [
            gate["id"]
            for gate in manifest.get("gates", [])
            if isinstance(gate, dict)
            and gate.get("scope") == "final"
            and gate.get("status") != "PASS"
        ]
        if not_ready:
            errors.append("final gates not PASS: " + ", ".join(not_ready))

    for status in sorted(ALLOWED_STATUSES):
        print(f"{status}={counts.get(status, 0)}")
    print(f"gates={sum(counts.values())}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        print("RESULT=FAIL")
        return 1

    print("RESULT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
