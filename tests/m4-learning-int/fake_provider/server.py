#!/usr/bin/env python3
"""Controlled OpenAI-compatible provider for M4 QA. Synthetic data only."""

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
    fallback = entry_ids[0] if entry_ids else "00000000-0000-4000-8000-000000000001"
    if practice_type == "fill_blank":
        items = []
        for index in range(count):
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
                    "target_entry_ids": [
                        entry_ids[index % len(entry_ids)] if entry_ids else fallback
                    ],
                }
            )
        return {"practice_type": practice_type, "items": items}
    if practice_type == "reading":
        questions = []
        for index in range(count):
            questions.append(
                {
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
                }
            )
        return {
            "practice_type": practice_type,
            "items": [
                {
                    "id": "p1",
                    "article": " ".join(["word"] * 200),
                    "article_zh": "文章",
                    "questions": questions,
                    "target_entry_ids": [fallback],
                }
            ],
        }
    if practice_type == "translation":
        return {
            "practice_type": practice_type,
            "items": [
                {
                    "id": f"t{index}",
                    "source_text": f"Translate sentence {index}.",
                    "source_language": "en",
                    "target_language": "zh",
                    "reference_translation": f"参考译文 {index}",
                    "target_entry_ids": [
                        entry_ids[index % len(entry_ids)] if entry_ids else fallback
                    ],
                }
                for index in range(count)
            ],
        }
    return {
        "practice_type": "writing",
        "items": [
            {
                "id": "w1",
                "prompt": "Write about a harbor.",
                "requirements": ["Use at least 50 words."],
                "reference_essay": "The harbor is busy.",
                "target_entry_ids": [fallback],
            }
        ],
    }


def _grading_output(context: dict[str, Any]) -> dict[str, Any]:
    practice_type = context.get("practice_type", "translation")
    items = context.get("items", [])
    score = 55.0 if practice_type == "translation" else 80.0
    return {
        "items": [
            {
                "question_id": item["question_id"],
                "total_score": score,
                "dimensions": [
                    {"name": "Accuracy", "score": score * 0.5, "max_score": 50},
                    {"name": "Coherence", "score": score * 0.5, "max_score": 50},
                ],
                "errors": [],
                "suggestions": ["Add one concrete detail."],
                "reference_content": "参考改进内容",
            }
            for item in items
        ],
    }


def _coach_output(context: dict[str, Any]) -> dict[str, Any]:
    message = str(context.get("user_message", ""))
    if "25" in message or "调整今日计划" in message:
        return {
            "message": "我会把今日新词目标调整为 25，学习时长调整为 45 分钟。",
            "actions": [
                {
                    "action_type": "adjust_daily_plan",
                    "parameters": {"new_words": 25, "study_minutes": 45},
                    "summary": "把今日新词目标调整为 25，学习时长调整为 45 分钟。",
                }
            ],
        }
    if "通知" in message:
        return {
            "message": "我会按你的要求调整学习提醒。",
            "actions": [
                {
                    "action_type": "adjust_notification_preferences",
                    "parameters": {"categories": {"ai_action": False}, "daily_limit": 2},
                    "summary": "调整学习提醒偏好。",
                }
            ],
        }
    return {
        "message": "先完成今日到期复习，再学习新词并做一组短文阅读。",
        "actions": [],
    }


def _challenge_output(context: dict[str, Any]) -> dict[str, Any]:
    new_ids = [str(value) for value in context.get("new_entry_ids", [])]
    due_ids = [str(value) for value in context.get("due_entry_ids", [])]
    target = int(context.get("target_minutes", 30))
    all_ids = new_ids or due_ids
    if not all_ids:
        all_ids = ["00000000-0000-4000-8000-000000000001"]

    main_minutes = max(3, target)
    first_minutes = max(1, min(120, main_minutes // 3))
    second_minutes = max(1, min(120, main_minutes // 3))
    boss_minutes = max(1, min(120, main_minutes - first_minutes - second_minutes))
    if boss_minutes < 1:
        boss_minutes = 1

    nodes: list[dict[str, Any]] = []
    if due_ids:
        nodes.append(
            {
                "id": "review-1",
                "node_type": "REVIEW",
                "title": "到期复习回廊",
                "description": "复习今日到期的服务端词条。",
                "estimated_minutes": first_minutes,
                "word_entry_ids": due_ids,
                "order": 1,
            }
        )
        nodes.append(
            {
                "id": "new-1",
                "node_type": "NEW_WORDS",
                "title": "今日新词营地",
                "description": "学习今日计划中的全部新词。",
                "estimated_minutes": second_minutes,
                "word_entry_ids": new_ids or due_ids,
                "order": 2,
            }
        )
    else:
        nodes.append(
            {
                "id": "new-1",
                "node_type": "NEW_WORDS",
                "title": "今日新词营地",
                "description": "学习今日计划中的全部新词。",
                "estimated_minutes": first_minutes,
                "word_entry_ids": new_ids,
                "order": 1,
            }
        )
        nodes.append(
            {
                "id": "drill-1",
                "node_type": "WORD_DRILL",
                "title": "词义选择训练",
                "description": "用服务端选项巩固今日词条。",
                "estimated_minutes": second_minutes,
                "word_entry_ids": new_ids,
                "drill_mode": "choice",
                "order": 2,
            }
        )

    nodes.append(
        {
            "id": "boss-1",
            "node_type": "BOSS",
            "title": "终点挑战",
            "description": "完成今日混合填空挑战。",
            "estimated_minutes": boss_minutes,
            "word_entry_ids": all_ids,
            "practice_type": "fill_blank",
            "practice_count": 5,
            "order": 3,
        }
    )
    nodes.append(
        {
            "id": "optional-1",
            "node_type": "OPTIONAL_SIDE",
            "title": "可选复习支线",
            "description": "不影响主线顺序的额外巩固。",
            "estimated_minutes": 3,
            "word_entry_ids": all_ids[: min(3, len(all_ids))],
            "optional": True,
            "order": 100,
        }
    )
    return {
        "version": "challenge-plan-v1",
        "title": "QA 今日闯关",
        "summary": "先完成今日词条训练，再挑战终点。",
        "nodes": nodes,
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
    schema_name = ((body.get("response_format") or {}).get("json_schema") or {}).get("name") or ""
    if (
        schema_name == "subjective_grading"
        or "Grading" in schema_name
        or schema_name == "PracticeGradingBatchOutput"
    ):
        output = _grading_output(context)
    elif schema_name in {"JsonRepairOutput", "json_repair"}:
        output = {"corrected": {"ok": True}}
    elif schema_name == "coach_reply":
        output = _coach_output(context)
    elif schema_name == "challenge_plan":
        output = _challenge_output(context)
    else:
        output = _generation_output(context)
    return {
        "status": 200,
        "body": {"choices": [{"message": {"content": json.dumps(output, ensure_ascii=False)}}]},
    }


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
            self._send(200, {"data": [{"id": "fake-m4-model"}, {"id": "fake-m4-backup"}]})
        elif self.path.endswith("/control/stats"):
            with LOCK:
                self._send(
                    200,
                    {
                        "request_count": len(STATE["requests"]),
                        "requests": STATE["requests"][-100:],
                        "modes": STATE["modes"],
                        "default_mode": STATE["default_mode"],
                    },
                )
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
                STATE["modes"] = {
                    str(key): str(value) for key, value in (body.get("modes") or {}).items()
                }
            self._send(200, {"status": "configured", "modes": STATE["modes"]})
            return
        if not self.path.endswith("/v1/chat/completions"):
            self._send(404, {"error": "not found"})
            return
        schema_name = ((body.get("response_format") or {}).get("json_schema") or {}).get(
            "name"
        ) or ""
        user_text = next(
            (
                item.get("content", "")
                for item in body.get("messages", [])
                if item.get("role") == "user"
            ),
            "",
        )
        with LOCK:
            STATE["requests"].append(
                {
                    "path": self.path,
                    "schema": schema_name,
                    "auth_present": bool(auth),
                    "content_sha256": hashlib.sha256(user_text.encode("utf-8")).hexdigest(),
                    "at": time.time(),
                }
            )
        response = _completion(body, auth)
        self._send(response["status"], response["body"])


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 18080), Handler).serve_forever()
