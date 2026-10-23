#!/usr/bin/env python3
"""Check an ARQ worker health key through the Redis protocol without heavy imports."""

from __future__ import annotations

import os
import socket
import ssl
import sys
from urllib.parse import unquote, urlsplit


def encode_command(*parts: str) -> bytes:
    encoded = [part.encode("utf-8") for part in parts]
    chunks = [f"*{len(encoded)}\r\n".encode("ascii")]
    for part in encoded:
        chunks.extend((f"${len(part)}\r\n".encode("ascii"), part, b"\r\n"))
    return b"".join(chunks)


def read_line(stream) -> bytes:
    line = stream.readline()
    if not line.endswith(b"\r\n"):
        raise ConnectionError("incomplete Redis response")
    return line[:-2]


def read_reply(stream) -> object:
    prefix = stream.read(1)
    if prefix == b"+":
        return read_line(stream).decode("utf-8")
    if prefix == b"-":
        raise ConnectionError(read_line(stream).decode("utf-8", "replace"))
    if prefix == b":":
        return int(read_line(stream))
    if prefix == b"$":
        length = int(read_line(stream))
        if length < 0:
            return None
        payload = stream.read(length)
        if stream.read(2) != b"\r\n":
            raise ConnectionError("incomplete Redis bulk response")
        return payload
    if prefix == b"*":
        count = int(read_line(stream))
        if count < 0:
            return None
        return [read_reply(stream) for _ in range(count)]
    raise ConnectionError("unsupported Redis response")


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        print("usage: check_arq_health.py <redis-health-key>", file=sys.stderr)
        return 2
    redis_url = os.environ.get("REDIS_URL", "").strip()
    parsed = urlsplit(redis_url)
    if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
        print("REDIS_URL is not configured with a supported Redis URL", file=sys.stderr)
        return 2
    port = parsed.port or 6379
    timeout = 2.0
    try:
        raw = socket.create_connection((parsed.hostname, port), timeout=timeout)
        stream = (
            ssl.create_default_context().wrap_socket(raw, server_hostname=parsed.hostname)
            if parsed.scheme == "rediss"
            else raw
        )
        with stream:
            stream.settimeout(timeout)
            reader = stream.makefile("rb")
            if parsed.password is not None:
                username = unquote(parsed.username) if parsed.username else ""
                password = unquote(parsed.password)
                command = ("AUTH", password) if not username else ("AUTH", username, password)
                stream.sendall(encode_command(*command))
                read_reply(reader)
            database = int((parsed.path or "/0").strip("/") or "0")
            if database:
                stream.sendall(encode_command("SELECT", str(database)))
                read_reply(reader)
            stream.sendall(encode_command("EXISTS", sys.argv[1].strip()))
            exists = read_reply(reader)
    except Exception as exc:  # noqa: BLE001 - container health output stays non-secret
        print(f"Redis health check failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    if exists != 1:
        print(f"ARQ health key is absent: {sys.argv[1].strip()}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
