from __future__ import annotations

import json
from uuid import uuid4

import pytest

from app.services.ai_validation import validate_task_output


def _context() -> dict:
    return {
        "local_date": "2026-10-23",
        "target_minutes": 30,
        "new_entry_ids": [str(uuid4()), str(uuid4())],
        "due_entry_ids": [str(uuid4())],
        "allowed_practice_types": ["fill_blank", "reading"],
        "allowed_drill_modes": ["choice", "spelling"],
    }


def _output(context: dict) -> dict:
    new_ids = context["new_entry_ids"]
    due_ids = context["due_entry_ids"]
    return {
        "version": "challenge-plan-v1",
        "title": "今日闯关",
        "summary": "完成今日计划。",
        "nodes": [
            {
                "id": "review",
                "node_type": "REVIEW",
                "title": "复习",
                "description": "复习到期词。",
                "estimated_minutes": 8,
                "word_entry_ids": due_ids,
                "order": 1,
            },
            {
                "id": "new",
                "node_type": "NEW_WORDS",
                "title": "新词",
                "description": "学习新词。",
                "estimated_minutes": 10,
                "word_entry_ids": new_ids,
                "order": 2,
            },
            {
                "id": "boss",
                "node_type": "BOSS",
                "title": "终点",
                "description": "完成小测。",
                "estimated_minutes": 12,
                "word_entry_ids": new_ids + due_ids,
                "practice_type": "fill_blank",
                "practice_count": 5,
                "order": 3,
            },
        ],
    }


def test_challenge_contract_validates_schema_and_business_rules() -> None:
    context = _context()
    result, summary = validate_task_output(
        task_type="challenge_plan",
        context=context,
        raw_text=json.dumps(_output(context)),
    )
    assert len(result["nodes"]) == 3
    assert summary["node_count"] == 3

    too_short = _output(context)
    too_short["nodes"][0]["estimated_minutes"] = 1
    with pytest.raises(ValueError, match="AI_CHALLENGE_MINUTES_OUT_OF_RANGE"):
        validate_task_output(
            task_type="challenge_plan", context=context, raw_text=json.dumps(too_short)
        )

    missing_due = _output(context)
    missing_due["nodes"][0]["word_entry_ids"] = []
    with pytest.raises(ValueError, match="AI_DUE_WORD_COVERAGE_INCOMPLETE"):
        validate_task_output(
            task_type="challenge_plan", context=context, raw_text=json.dumps(missing_due)
        )

    html = _output(context)
    html["nodes"][0]["title"] = "<b>复习</b>"
    with pytest.raises(ValueError, match="AI_HTML_NOT_ALLOWED"):
        validate_task_output(task_type="challenge_plan", context=context, raw_text=json.dumps(html))


async def test_openapi_publishes_challenge_contract(app) -> None:
    document = app.openapi()
    paths = document["paths"]
    expected = {
        "/api/v1/challenges/today",
        "/api/v1/challenges/today/generate",
        "/api/v1/challenges/history",
        "/api/v1/challenges/jobs/{job_id}",
        "/api/v1/challenges/{challenge_id}",
        "/api/v1/challenges/{challenge_id}/nodes/{node_id}",
        "/api/v1/challenges/{challenge_id}/nodes/{node_id}/start",
        "/api/v1/challenges/{challenge_id}/nodes/{node_id}/boss-submit",
    }
    assert expected.issubset(paths)
    assert "ChallengePlanResponse" in document["components"]["schemas"]
    assert "ChallengeNodeResponse" in document["components"]["schemas"]
    assert "ChallengeBossSubmitResponse" in document["components"]["schemas"]
