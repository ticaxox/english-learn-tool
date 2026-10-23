#!/usr/bin/env python3
"""Controlled OpenAI-compatible provider for M3 QA. Synthetic data only."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

LOCK = threading.Lock()
STATE: dict[str, Any] = {
    "default_mode": "ok",
    "modes": {},
    "requests": [],
    "repair_seen": {},
}


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def _generation_output(context: dict[str, Any]) -> dict[str, Any]:
    practice_type = context.get("practice_type", "fill_blank")
    entry_ids = [str(value) for value in context.get("target_entry_ids", [])]
    count = int(context.get("count", 3))
    if practice_type == "fill_blank":
        items = []
        for index in range(count):
            items.append({
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
                "target_entry_ids": [entry_ids[index % len(entry_ids)]],
            })
        return {"practice_type": practice_type, "items": items}
    if practice_type == "reading":
        questions = []
        for index in range(count):
            questions.append({
                "id": f"rq{index}",
                "prompt": f"What is the main idea {index + 1}?",
                "options": [
                    {"id": "a", "text": "A", "text_zh": "甲"},
                    {"id": "b", "text": "B", "text_zh": "乙"},
                    {"id": "c", "text": "C", "text_zh": "丙"},
                    {"id": "d", "text": "D", "text_zh": "丁"},
                ],
                "correct_option_id": "a",
                "explanation": "The passage supports A.",
            })
        return {
            "practice_type": practice_type,
            "items": [{
                "id": "p1",
                "article": " ".join(["word"] * 200),
                "article_zh": "文章",
                "questions": questions,
                "target_entry_ids": [entry_ids[0]],
            }],
        }
    if practice_type == "translation":
        return {
            "practice_type": practice_type,
            "items": [{
                "id": f"t{index}",
                "source_text": f"Translate sentence {index}.",
                "source_language": "en",
                "target_language": "zh",
                "reference_translation": f"参考译文 {index}",
                "target_entry_ids": [entry_ids[index % len(entry_ids)]],
            } for index in range(count)],
        }
    return {
        "practice_type": "writing",
        "items": [{
            "id": "w1",
            "prompt": "Write about a harbor.",
            "requirements": ["Use at least 50 words."],
            "reference_essay": "The harbor is busy.",
            "target_entry_ids": [entry_ids[0]],
        }],
    }


def _grading_output(context: dict[str, Any]) -> dict[str, Any]:
    practice_type = context.get("practice_type", "translation")
    items = context.get("items", [])
    score = 55.0 if practice_type == "translation" else 80.0
    return {
        "items": [{
            "question_id": item["question_id"],
            "total_score": score,
            "dimensions": [
                {"name": "Accuracy", "score": score * 0.5, "max_score": 50},
                {"name": "Coherence", "score": score * 0.5, "max_score": 50},
            ],
            "errors": [],
            "suggestions": ["Add one concrete detail."],
            "reference_content": "参考改进内容",
        } for item in items],
    }


def _completion(body: dict[str, Any], auth: str) -> dict[str, Any]:
    mode = STATE["modes"].get(auth, STATE["default_mode"])
    if mode == "repair_once":
        with LOCK:
            seen = STATE["repair_seen"].get(auth, 0)
            STATE["repair_seen"][auth] = seen + 1
        mode = "malformed" if seen == 0 else "ok"
    if mode == "fail":
        return {"status": 500, "body": {"error": {"message": "controlled failure"}}}
    if mode == "slow":
        time.sleep(3)
    if mode == "malformed":
        return {"status": 200, "body": {"choices": [{"message": {"content": "not-json"}}]}}
    messages = body.get("messages", [])
    user_content = ""
    for message in messages:
        if message.get("role") == "user":
            user_content = message.get("content", "")
    try:
        context = json.loads(user_content)
    except Exception:
        context = {}
    schema_name = (((body.get("response_format") or {}).get("json_schema") or {}).get("name") or "")
    if schema_name == "subjective_grading" or "Grading" in schema_name or schema_name == "PracticeGradingBatchOutput":
        output = _grading_output(context)
    elif schema_name in {"JsonRepairOutput", "json_repair"}:
        output = {"corrected": {"ok": True}}
    else:
        output = _generation_output(context)
    return {"status": 200, "body": {"choices": [{"message": {"content": json.dumps(output, ensure_ascii=False)}}]}}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:  # noqa: A002
        return

    def _send(self, status: int, body: Any) -> None:
        encoded = _json_bytes(body)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.endswith("/healthz"):
            self._send(200, {"status": "ok"})
        elif self.path.endswith("/v1/models"):
            self._send(200, {"data": [{"id": "fake-m3-model"}, {"id": "fake-m3-backup"}]})
        elif self.path.endswith("/control/stats"):
            with LOCK:
                self._send(200, {"request_count": len(STATE["requests"]), "requests": STATE["requests"][-50:], "modes": STATE["modes"], "default_mode": STATE["default_mode"]})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        try:
            body = json.loads(raw or "{}")
        except Exception:
            body = {}
        auth = self.headers.get("Authorization", "").replace("Bearer ", "", 1)
        if self.path.endswith("/control/reset"):
            with LOCK:
                STATE.update({"default_mode": "ok", "modes": {}, "requests": [], "repair_seen": {}})
            self._send(200, {"status": "reset"})
            return
        if self.path.endswith("/control/config"):
            with LOCK:
                STATE["default_mode"] = body.get("default_mode", "ok")
                STATE["modes"] = {str(key): str(value) for key, value in (body.get("modes") or {}).items()}
            self._send(200, {"status": "configured", "modes": STATE["modes"]})
            return
        if not self.path.endswith("/v1/chat/completions"):
            self._send(404, {"error": "not found"})
            return
        schema_name = (((body.get("response_format") or {}).get("json_schema") or {}).get("name") or "")
        user_text = next((item.get("content", "") for item in body.get("messages", []) if item.get("role") == "user"), "")
        with LOCK:
            STATE["requests"].append({
                "path": self.path,
                "schema": schema_name,
                "auth_present": bool(auth),
                "content_sha256": hashlib.sha256(user_text.encode("utf-8")).hexdigest(),
                "at": time.time(),
            })
        response = _completion(body, auth)
        self._send(response["status"], response["body"])


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 18080), Handler).serve_forever()
