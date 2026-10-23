#!/usr/bin/env python3
"""Write metadata-only deployment or rollback evidence from a release manifest."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path

from validate_release_manifest import validate_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile", choices=("production", "lightweight"), required=True)
    parser.add_argument("--edge-bind", required=True)
    parser.add_argument("--edge-port", type=int, required=True)
    parser.add_argument("--rollback-from", type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    values = validate_manifest(manifest)
    receipt = {
        "schema_version": 1,
        "event": "rollback" if args.rollback_from else "deploy",
        "recorded_at": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
        "release": values["RELEASE_VERSION"],
        "source_commit": values["RELEASE_COMMIT"],
        "profile": args.profile,
        "edge": {"bind": args.edge_bind, "port": args.edge_port},
        "images": {
            "api": values["API_IMAGE"],
            "frontend": values["FRONTEND_IMAGE"],
            "reverse_proxy": values["REVERSE_PROXY_IMAGE"],
            "postgres": values["POSTGRES_IMAGE"],
            "redis": values["REDIS_IMAGE"],
            "cloudflared": values["CLOUDFLARED_IMAGE"],
        },
    }
    if args.rollback_from:
        previous = json.loads(args.rollback_from.read_text(encoding="utf-8"))
        previous_values = validate_manifest(previous)
        receipt["rollback_from_release"] = previous_values["RELEASE_VERSION"]
        receipt["rollback_from_source_commit"] = previous_values["RELEASE_COMMIT"]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(args.output, 0o600)
    print(f"deployment evidence written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
