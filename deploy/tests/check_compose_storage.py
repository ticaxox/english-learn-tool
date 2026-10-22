#!/usr/bin/env python3
"""Validate the merged Compose wordbook-storage contract."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

APP_SERVICES = ("api", "worker", "scheduler")
STORAGE_TARGET = "/app/var/wordbooks"
STORAGE_VOLUME = "wordbook-data"


class ContractError(RuntimeError):
    """Raised when the Compose contract is not satisfied."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _volumes(config: dict[str, Any], service: str) -> list[dict[str, Any]]:
    services = config.get("services")
    _require(isinstance(services, dict), "Compose config has no services object")
    definition = services.get(service)
    _require(isinstance(definition, dict), f"Compose service {service!r} is missing")
    volumes = definition.get("volumes") or []
    _require(isinstance(volumes, list), f"{service}.volumes must be a list")
    _require(
        all(isinstance(item, dict) for item in volumes),
        f"{service}.volumes must contain mappings",
    )
    return volumes


def _declared_volume_names(config: dict[str, Any]) -> set[str]:
    declarations = config.get("volumes")
    _require(isinstance(declarations, dict), "Compose config has no volumes object")
    names: set[str] = set()
    for key, definition in declarations.items():
        names.add(str(key))
        if isinstance(definition, dict):
            names.add(str(definition.get("name") or key))
    return names


def _declared_storage_names(config: dict[str, Any]) -> set[str]:
    declarations = config.get("volumes")
    _require(isinstance(declarations, dict), "Compose config has no volumes object")
    names: set[str] = set()
    for key, definition in declarations.items():
        if not isinstance(definition, dict):
            continue
        actual_name = definition.get("name") or key
        if key == STORAGE_VOLUME or str(actual_name).endswith(f"_{STORAGE_VOLUME}"):
            names.add(str(actual_name))
    _require(bool(names), f"Named volume {STORAGE_VOLUME!r} is not declared")
    return names


def validate(config: dict[str, Any]) -> dict[str, Any]:
    """Validate an already-resolved `docker compose config --format json` object."""

    _require(isinstance(config, dict), "Compose config must be a JSON object")
    declared_storage_names = _declared_storage_names(config)
    declared_names = _declared_volume_names(config)
    sources: list[str] = []
    services_summary: dict[str, dict[str, Any]] = {}

    for service in APP_SERVICES:
        definition = config["services"][service]
        matching = [
            volume
            for volume in _volumes(config, service)
            if volume.get("target") == STORAGE_TARGET
        ]
        _require(
            len(matching) == 1,
            f"{service} must mount exactly one volume at {STORAGE_TARGET}",
        )
        mount = matching[0]
        _require(
            mount.get("type") == "volume",
            f"{service} wordbook mount must be a named volume, not {mount.get('type')!r}",
        )
        _require(
            mount.get("read_only") is not True,
            f"{service} wordbook volume must be writable",
        )
        source = mount.get("source")
        _require(
            isinstance(source, str) and source in declared_names,
            f"{service} uses an undeclared wordbook volume source: {source!r}",
        )
        sources.append(source)

        environment = definition.get("environment") or {}
        _require(
            isinstance(environment, dict),
            f"{service}.environment must be a mapping",
        )
        _require(
            environment.get("WORDBOOK_STORAGE_DIR") == STORAGE_TARGET,
            f"{service} must set WORDBOOK_STORAGE_DIR exactly to {STORAGE_TARGET}",
        )
        _require(
            definition.get("read_only") is True,
            f"{service} must keep a read-only root filesystem",
        )
        cap_drop = definition.get("cap_drop") or []
        _require(
            isinstance(cap_drop, list)
            and "ALL" in {str(value).upper() for value in cap_drop},
            f"{service} must keep cap_drop: ALL",
        )
        security_opt = definition.get("security_opt") or []
        _require(
            isinstance(security_opt, list)
            and "no-new-privileges:true"
            in {str(value).lower() for value in security_opt},
            f"{service} must keep no-new-privileges:true",
        )
        _require(not definition.get("ports"), f"{service} must not publish a host port")
        services_summary[service] = {
            "owner_uid": 10001,
            "owner_gid": 10001,
            "mode": "0750",
            "storage_target": STORAGE_TARGET,
            "volume_source": source,
            "root_filesystem": "read-only",
            "cap_drop": "ALL",
            "no_new_privileges": True,
        }

    _require(
        len(set(sources)) == 1,
        f"api, worker and scheduler must share one volume source; got {sources!r}",
    )
    shared_source = sources[0]
    _require(
        shared_source in declared_storage_names or shared_source == STORAGE_VOLUME,
        "the shared application volume is not the declared wordbook-data volume",
    )

    # A bind mount could expose private files through an image, host path, or static
    # directory. The deployment contract permits named volumes only.
    for service, definition in config["services"].items():
        for volume in _volumes(config, service):
            _require(
                volume.get("type") == "volume",
                f"{service} uses a non-volume mount: {volume!r}",
            )

    for service in config["services"]:
        if service in APP_SERVICES:
            continue
        for volume in _volumes(config, service):
            _require(
                volume.get("target") != STORAGE_TARGET
                and volume.get("source") != shared_source,
                f"{service} must not receive the private wordbook volume",
            )

    # Only the existing reverse proxy may publish a port, and it must stay loopback-bound.
    for service, definition in config["services"].items():
        ports = definition.get("ports") or []
        if not ports:
            continue
        _require(service == "reverse-proxy", f"{service} must not publish host ports")
        for mapping in ports:
            _require(
                mapping.get("host_ip") in {"127.0.0.1", "::1"},
                "reverse-proxy publishes a non-loopback host port",
            )

    return {
        "status": "passed",
        "storage_target": STORAGE_TARGET,
        "shared_volume_source": shared_source,
        "services": services_summary,
    }


def _run_compose(env_file: Path, compose_file: Path) -> dict[str, Any]:
    command = [
        "docker",
        "compose",
        "--env-file",
        str(env_file),
        "-f",
        str(compose_file),
        "config",
        "--format",
        "json",
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr)
        raise ContractError("docker compose config failed")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ContractError("docker compose config did not return valid JSON") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=".env", type=Path)
    parser.add_argument("--compose-file", default="docker-compose.yml", type=Path)
    args = parser.parse_args()

    try:
        result = validate(_run_compose(args.env_file, args.compose_file))
    except (ContractError, OSError) as exc:
        print(f"wordbook storage contract: FAILED: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
