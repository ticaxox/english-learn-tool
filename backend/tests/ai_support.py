from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from uuid import uuid4

import httpx

TEST_PASSWORD = "Valid-Test-Pass-123!"
LOGIN_PATH = "/api/v1/auth/login"
PROVIDERS_PATH = "/api/v1/admin/ai/providers"
PROMPTS_PATH = "/api/v1/admin/ai/prompts"
JOBS_PATH = "/api/v1/ai/jobs"
USAGE_PATH = "/api/v1/ai/usage/me"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def login(client: httpx.AsyncClient, username: str) -> dict[str, str]:
    response = await client.post(
        LOGIN_PATH,
        json={"username": username, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return bearer(response.json()["access_token"])


async def create_provider(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    base_url: str,
    name: str = "Primary",
    model_id: str = "fake-model",
    api_key: str = "sk-test-secret-1234",
    is_default: bool = True,
    priority: int = 10,
) -> dict[str, Any]:
    response = await client.post(
        PROVIDERS_PATH,
        headers=headers,
        json={
            "name": name,
            "base_url": base_url,
            "api_key": api_key,
            "model_id": model_id,
            "is_default": is_default,
            "priority": priority,
            "timeout_seconds": 5,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def practice_context(*, count: int = 3) -> tuple[dict[str, Any], list[str]]:
    entry_ids = [str(uuid4()) for _ in range(count)]
    return (
        {
            "practice_type": "fill_blank",
            "count": count,
            "source": "whole_book",
            "wordbook_id": str(uuid4()),
            "target_entry_ids": entry_ids,
        },
        entry_ids,
    )


def practice_output(entry_ids: list[str]) -> dict[str, Any]:
    items = []
    for index, entry_id in enumerate(entry_ids):
        items.append(
            {
                "id": f"q{index + 1}",
                "sentence": f"The ____ is useful for learning number {index + 1}.",
                "sentence_zh": "这个空对学习很有用。",
                "options": [
                    {"id": "a", "text": "word", "text_zh": "单词"},
                    {"id": "b", "text": "ship", "text_zh": "船"},
                    {"id": "c", "text": "stone", "text_zh": "石头"},
                    {"id": "d", "text": "cloud", "text_zh": "云"},
                ],
                "correct_option_id": "a",
                "explanation": "The context points to a learning word.",
                "target_entry_ids": [entry_id],
            }
        )
    return {"practice_type": "fill_blank", "items": items}


class FakeProviderServer:
    def __init__(self) -> None:
        self.responses: list[tuple[int, dict[str, Any] | str]] = []
        self.requests: list[dict[str, Any]] = []
        self.models = ["fake-model", "fake-model-2"]
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                return

            def _send(self, status: int, body: dict[str, Any] | str) -> None:
                encoded = (
                    body.encode("utf-8")
                    if isinstance(body, str)
                    else json.dumps(body, ensure_ascii=False).encode("utf-8")
                )
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def do_GET(self) -> None:  # noqa: N802
                owner.requests.append(
                    {"method": "GET", "path": self.path, "headers": dict(self.headers)}
                )
                if self.path.endswith("/models"):
                    self._send(200, {"data": [{"id": model} for model in owner.models]})
                    return
                self._send(404, {"error": "not found"})

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                owner.requests.append(
                    {
                        "method": "POST",
                        "path": self.path,
                        "headers": dict(self.headers),
                        "body": body,
                    }
                )
                if not owner.responses:
                    self._send(500, {"error": "no scripted response"})
                    return
                status, response = owner.responses.pop(0)
                if isinstance(response, dict) and "choices" not in response:
                    response = {"choices": [{"message": {"content": json.dumps(response)}}]}
                self._send(status, response)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_port}/v1"

    def start(self) -> FakeProviderServer:
        self.thread.start()
        return self

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)

    def queue_json(self, status: int, payload: dict[str, Any]) -> None:
        self.responses.append((status, payload))


@contextmanager
def fake_provider_server() -> Iterator[FakeProviderServer]:
    server = FakeProviderServer().start()
    try:
        yield server
    finally:
        server.close()
