#!/usr/bin/env python3
"""Fail unless the requested ARQ worker health key exists in Redis."""

from __future__ import annotations

import os
import sys

from redis import Redis


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        print("usage: check_arq_health.py <redis-health-key>", file=sys.stderr)
        return 2

    redis_url = os.environ.get("REDIS_URL", "").strip()
    if not redis_url:
        print("REDIS_URL is not configured", file=sys.stderr)
        return 2

    client = Redis.from_url(
        redis_url,
        socket_connect_timeout=2,
        socket_timeout=2,
        decode_responses=True,
    )
    try:
        if not client.exists(sys.argv[1].strip()):
            print(f"ARQ health key is absent: {sys.argv[1]}", file=sys.stderr)
            return 1
    except Exception as exc:  # noqa: BLE001 - container health output stays non-secret
        print(f"Redis health check failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    finally:
        client.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
