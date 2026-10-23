#!/usr/bin/env python3
"""Validate the merged production and lightweight Compose contract."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

DIGEST_RE = re.compile(r"^.+@sha256:[0-9a-f]{64}$")
APP_SERVICES = ("migrate", "api", "worker", "scheduler", "frontend", "reverse-proxy")
ACTIVE_SERVICES = ("postgres", "redis", "api", "worker", "scheduler", "frontend", "reverse-proxy")
PROTECTED_PORTS = {80, 443, 30000}


class ContractError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _service(config: dict[str, Any], name: str) -> dict[str, Any]:
    service = config.get("services", {}).get(name)
    require(isinstance(service, dict), f"missing service: {name}")
    return service


def _memory_limit(service: dict[str, Any], name: str) -> int:
    try:
        value = int(service.get("mem_limit"))
    except (TypeError, ValueError):
        raise ContractError(f"{name} must have a numeric memory limit") from None
    require(value > 0, f"{name} must have a positive memory limit")
    return value


def validate_production_config(config: dict[str, Any], memory_budget_mb: int) -> None:
    require(isinstance(config, dict), "config must be an object")
    require(memory_budget_mb > 0, "memory budget must be positive")
    for name in (*APP_SERVICES, "postgres", "redis"):
        service = _service(config, name)
        require(
            isinstance(service.get("image"), str) and DIGEST_RE.fullmatch(service["image"]) is not None,
            f"{name} image must be digest-pinned",
        )
        logging = service.get("logging", {})
        options = logging.get("options", {}) if isinstance(logging, dict) else {}
        require(options.get("max-size") == "10m", f"{name} must use 10m log rotation")
        require(str(options.get("max-file")) == "3", f"{name} must retain three rotated logs")

    api_image = _service(config, "api")["image"]
    require(_service(config, "worker")["image"] == api_image, "worker must reuse the API image digest")
    require(_service(config, "scheduler")["image"] == api_image, "scheduler must reuse the API image digest")

    for name in ("postgres", "redis"):
        require(not _service(config, name).get("ports"), f"{name} must not publish host ports")

    edge = _service(config, "reverse-proxy")
    ports = edge.get("ports") or []
    require(len(ports) == 1, "reverse proxy must publish exactly one port")
    port = ports[0]
    require(port.get("host_ip") == "127.0.0.1", "reverse proxy must bind loopback only")
    published = int(port.get("published", 0))
    require(published not in PROTECTED_PORTS, "reverse proxy must not use ports 80/443/30000")

    for name in APP_SERVICES:
        service = _service(config, name)
        require(service.get("read_only") is True, f"{name} must keep a read-only root filesystem")
        require("ALL" in (service.get("cap_drop") or []), f"{name} must drop all capabilities")
        security_opt = service.get("security_opt") or []
        require(
            "no-new-privileges:true" in security_opt,
            f"{name} must keep no-new-privileges",
        )

    tunnel = config.get("services", {}).get("cloudflared")
    if tunnel is not None:
        require(isinstance(tunnel, dict), "cloudflared service must be an object")
        require(
            isinstance(tunnel.get("image"), str) and DIGEST_RE.fullmatch(tunnel["image"]) is not None,
            "cloudflared image must be digest-pinned",
        )
        require(not tunnel.get("ports"), "cloudflared must not publish host ports")
        require(tunnel.get("read_only") is True, "cloudflared must keep a read-only root filesystem")
        require("ALL" in (tunnel.get("cap_drop") or []), "cloudflared must drop all capabilities")
        require(
            "no-new-privileges:true" in (tunnel.get("security_opt") or []),
            "cloudflared must keep no-new-privileges",
        )
        command = tunnel.get("command") or []
        require(
            "--url" in command and "http://reverse-proxy:8080" in command,
            "cloudflared must tunnel only to the internal reverse proxy",
        )
        logging = tunnel.get("logging", {})
        options = logging.get("options", {}) if isinstance(logging, dict) else {}
        require(options.get("max-size") == "10m", "cloudflared must use 10m log rotation")
        require(str(options.get("max-file")) == "3", "cloudflared must retain three rotated logs")

    total_bytes = sum(_memory_limit(_service(config, name), name) for name in ACTIVE_SERVICES)
    if tunnel is not None:
        total_bytes += _memory_limit(tunnel, "cloudflared")
    require(
        total_bytes <= memory_budget_mb * 1024 * 1024,
        f"active memory limits {total_bytes} bytes exceed {memory_budget_mb} MiB budget",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config_json", type=Path)
    parser.add_argument("--memory-budget-mb", type=int, default=528)
    args = parser.parse_args(argv)
    try:
        config = json.loads(args.config_json.read_text(encoding="utf-8"))
        validate_production_config(config, args.memory_budget_mb)
    except (OSError, json.JSONDecodeError, ContractError, ValueError) as exc:
        print(f"production contract validation failed: {exc}", file=sys.stderr)
        return 1
    print("Production Compose contract is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
