"""MCP tool definitions for the coach actions.

The same registry serves the HTTP MCP endpoint and any future in-process caller;
each tool maps one-to-one onto a whitelisted coach action.
"""

from __future__ import annotations

from typing import Any

from arq.connections import ArqRedis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.models.identity import User
from app.services.coach import apply_coach_tool

PRACTICE_TYPES = ["fill_blank", "reading", "translation", "writing"]
PRACTICE_SOURCES = ["today_new", "today_review", "memory_mistakes", "whole_book", "difficulty"]
DIFFICULTIES = ["CET4", "CET6", "POSTGRAD", "IELTS", "TOEFL"]

TOOL_SPECS: dict[str, dict[str, Any]] = {
    "adjust_daily_plan": {
        "action_type": "adjust_daily_plan",
        "description": "调整今天的新词量与学习时长；至少提供一个字段。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "new_words": {"type": "integer", "minimum": 5, "maximum": 100},
                "study_minutes": {"type": "integer", "minimum": 15, "maximum": 180},
            },
            "additionalProperties": False,
            "minProperties": 1,
        },
    },
    "start_practice": {
        "action_type": "start_practice",
        "description": "按词书或难度开始一组 AI 练习，返回练习会话 id。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "practice_type": {"type": "string", "enum": PRACTICE_TYPES},
                "source": {"type": "string", "enum": PRACTICE_SOURCES},
                "count": {"type": "integer", "minimum": 1, "maximum": 20},
                "difficulty": {"type": "string", "enum": DIFFICULTIES},
                "wordbook_id": {"type": "string", "format": "uuid"},
            },
            "required": ["practice_type", "source", "count"],
            "additionalProperties": False,
        },
    },
    "activate_wordbook": {
        "action_type": "activate_wordbook",
        "description": "把一本自己的词书设为当前主词书。",
        "inputSchema": {
            "type": "object",
            "properties": {"wordbook_id": {"type": "string", "format": "uuid"}},
            "required": ["wordbook_id"],
            "additionalProperties": False,
        },
    },
    "mark_review_focus": {
        "action_type": "mark_review_focus",
        "description": "把一个词标记为下次复习重点。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entry_id": {"type": "string", "format": "uuid"},
                "wordbook_id": {"type": "string", "format": "uuid"},
            },
            "required": ["entry_id"],
            "additionalProperties": False,
        },
    },
}


def tool_list() -> list[dict[str, Any]]:
    return [
        {"name": name, "description": spec["description"], "inputSchema": spec["inputSchema"]}
        for name, spec in TOOL_SPECS.items()
    ]


async def call_coach_tool(
    session: AsyncSession,
    pool: ArqRedis,
    user: User,
    settings: Settings,
    name: str,
    arguments: dict[str, Any] | None,
) -> dict[str, Any]:
    spec = TOOL_SPECS.get(name)
    if spec is None:
        raise AppError(
            status_code=404,
            code="MCP_TOOL_NOT_FOUND",
            message=f"Unknown tool: {name}",
        )
    if arguments is not None and not isinstance(arguments, dict):
        raise AppError(
            status_code=422,
            code="MCP_TOOL_ARGUMENTS_INVALID",
            message="Tool arguments must be an object.",
        )
    return await apply_coach_tool(
        session,
        pool,
        user,
        settings,
        str(spec["action_type"]),
        arguments or {},
    )
