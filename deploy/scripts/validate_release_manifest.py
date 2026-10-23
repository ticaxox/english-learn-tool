#!/usr/bin/env python3
"""Validate a release manifest and optionally render digest-pinned variables."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shlex
import sys
from pathlib import Path
from typing import Any

RELEASE_RE = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-[0-9A-Za-z.-]+)?$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:([0-9a-f]{64})$")
APP_IMAGE_KEYS = ("api", "frontend", "reverse_proxy")
APP_IMAGE_NAMES = {
    "api": "english-learn-api",
    "frontend": "english-learn-frontend",
    "reverse_proxy": "english-learn-reverse-proxy",
}
RUNTIME_IMAGE_KEYS = ("postgres", "redis", "cloudflared")
RUNTIME_IMAGE_EXPECTED = {
    "postgres": ("postgres:16-alpine", "docker.io/library/postgres:16-alpine"),
    "redis": ("redis:7-alpine", "docker.io/library/redis:7-alpine"),
    "cloudflared": ("cloudflare/cloudflared:2026.10.3", "docker.io/cloudflare/cloudflared:2026.10.3"),
}
REQUIRED_KEYS = {
    "schema_version",
    "release",
    "source_commit",
    "created_at",
    "platform",
    "images",
    "runtime_images",
}


class ManifestError(ValueError):
    pass


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ManifestError(f"{label} must be an object")
    return value


def _split_digest(value: Any, label: str) -> tuple[str, str]:
    if not isinstance(value, str):
        raise ManifestError(f"{label} must be a string")
    if "@sha256:" not in value:
        raise ManifestError(f"{label} must be digest-pinned with @sha256:")
    name, digest = value.rsplit("@", 1)
    match = DIGEST_RE.fullmatch(digest)
    if not match or set(match.group(1)) == {"0"}:
        raise ManifestError(f"{label} has an invalid or placeholder sha256 digest")
    return name, digest


def _parse_timestamp(value: Any) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ManifestError("created_at must be an ISO-8601 UTC timestamp ending in Z")
    try:
        dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ManifestError("created_at is not a valid ISO-8601 timestamp") from exc


def _parse_app_image_ref(key: str, value: Any) -> tuple[str, str]:
    name, digest = _split_digest(value, f"images.{key}")
    if ":" in name.rsplit("/", 1)[-1]:
        raise ManifestError(f"images.{key} must not include a mutable tag")
    parts = name.split("/")
    if len(parts) != 3 or parts[0] != "ghcr.io":
        raise ManifestError(f"images.{key} must use ghcr.io/<owner>/<image>")
    if parts[-1] != APP_IMAGE_NAMES[key]:
        raise ManifestError(f"images.{key} must reference {APP_IMAGE_NAMES[key]}")
    return parts[1], digest


def _parse_runtime_image_ref(key: str, value: Any) -> str:
    name, _ = _split_digest(value, f"runtime_images.{key}")
    allowed = RUNTIME_IMAGE_EXPECTED[key]
    if name not in allowed:
        raise ManifestError(f"runtime_images.{key} must use {' or '.join(allowed)}")
    return value


def validate_manifest(
    data: Any, *, expected_release: str | None = None, expected_commit: str | None = None
) -> dict[str, str]:
    manifest = _require_object(data, "manifest")
    missing = REQUIRED_KEYS - manifest.keys()
    extra = manifest.keys() - REQUIRED_KEYS
    if missing:
        raise ManifestError(f"missing manifest keys: {', '.join(sorted(missing))}")
    if extra:
        raise ManifestError(f"unexpected manifest keys: {', '.join(sorted(extra))}")
    if manifest["schema_version"] != 1:
        raise ManifestError("schema_version must be 1")
    release = manifest["release"]
    if not isinstance(release, str) or not RELEASE_RE.fullmatch(release):
        raise ManifestError("release must be a semantic version such as v0.1.0 or v0.1.0-rc.1")
    commit = manifest["source_commit"]
    if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
        raise ManifestError("source_commit must be a lowercase 40-character Git SHA")
    if expected_release is not None and release != expected_release:
        raise ManifestError(f"release mismatch: expected {expected_release}, got {release}")
    if expected_commit is not None and commit != expected_commit:
        raise ManifestError(f"source commit mismatch: expected {expected_commit}, got {commit}")
    _parse_timestamp(manifest["created_at"])
    if manifest["platform"] != "linux/amd64":
        raise ManifestError("platform must be linux/amd64 for the current release pipeline")

    images = _require_object(manifest["images"], "images")
    if set(images) != set(APP_IMAGE_KEYS):
        raise ManifestError("images must contain exactly api, frontend and reverse_proxy")
    owners = {_parse_app_image_ref(key, images[key])[0] for key in APP_IMAGE_KEYS}
    if len(owners) != 1:
        raise ManifestError("all application images must use the same GHCR owner")

    runtime_images = _require_object(manifest["runtime_images"], "runtime_images")
    if set(runtime_images) != set(RUNTIME_IMAGE_KEYS):
        raise ManifestError("runtime_images must contain exactly postgres and redis")
    for key in RUNTIME_IMAGE_KEYS:
        _parse_runtime_image_ref(key, runtime_images[key])

    return {
        "RELEASE_VERSION": release,
        "RELEASE_COMMIT": commit,
        "API_IMAGE": images["api"],
        "FRONTEND_IMAGE": images["frontend"],
        "REVERSE_PROXY_IMAGE": images["reverse_proxy"],
        "POSTGRES_IMAGE": runtime_images["postgres"],
        "REDIS_IMAGE": runtime_images["redis"],
        "CLOUDFLARED_IMAGE": runtime_images["cloudflared"],
    }


def render_env(values: dict[str, str]) -> str:
    return "".join(f"{key}={shlex.quote(value)}\n" for key, value in values.items())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--expected-release")
    parser.add_argument("--expected-commit")
    parser.add_argument("--write-env", type=Path)
    args = parser.parse_args(argv)

    try:
        data = json.loads(args.manifest.read_text(encoding="utf-8"))
        values = validate_manifest(
            data,
            expected_release=args.expected_release,
            expected_commit=args.expected_commit,
        )
    except (OSError, json.JSONDecodeError, ManifestError) as exc:
        print(f"release manifest validation failed: {exc}", file=sys.stderr)
        return 2

    if args.write_env:
        args.write_env.parent.mkdir(parents=True, exist_ok=True)
        args.write_env.write_text(render_env(values), encoding="utf-8")
        os.chmod(args.write_env, 0o600)
        print(f"release environment written to {args.write_env}")
    else:
        print(f"release manifest valid: {values['RELEASE_VERSION']} ({values['RELEASE_COMMIT']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
