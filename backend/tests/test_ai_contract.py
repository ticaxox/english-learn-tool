from __future__ import annotations

import json
from uuid import uuid4

import pytest

from app.services.ai_validation import validate_task_output


def _fill_output(
    entry_ids: list[str], *, duplicate_correct: bool = False, extra: bool = False
) -> dict:
    item = {
        "id": "q1",
        "sentence": "A ____ is useful.",
        "sentence_zh": "一个空是有用的。",
        "options": [
            {"id": "a", "text": "word", "text_zh": "单词"},
            {"id": "b", "text": "ship", "text_zh": "船"},
            {"id": "c", "text": "stone", "text_zh": "石头"},
            {"id": "d", "text": "cloud", "text_zh": "云"},
        ],
        "correct_option_id": "a",
        "explanation": "A word fits the context.",
        "target_entry_ids": [entry_ids[0]],
    }
    if duplicate_correct:
        item["options"][1]["id"] = "a"
    if extra:
        item["unexpected"] = True
    items = [item]
    for index in range(1, len(entry_ids)):
        copy = json.loads(json.dumps(item))
        copy["id"] = f"q{index + 1}"
        copy["target_entry_ids"] = [entry_ids[index]]
        items.append(copy)
    return {"practice_type": "fill_blank", "items": items}


def _context(entry_ids: list[str], count: int = 3) -> dict:
    return {
        "practice_type": "fill_blank",
        "count": count,
        "source": "whole_book",
        "wordbook_id": str(uuid4()),
        "target_entry_ids": entry_ids,
    }


def test_fill_blank_requires_unique_correct_option_and_valid_entity_ids() -> None:
    entry_ids = [str(uuid4()) for _ in range(3)]
    with pytest.raises(ValueError, match="AI_SCHEMA_INVALID"):
        validate_task_output(
            task_type="practice_generation",
            context=_context(entry_ids),
            raw_text=json.dumps(_fill_output(entry_ids, duplicate_correct=True)),
        )

    out_of_scope = _fill_output(entry_ids)
    out_of_scope["items"][0]["target_entry_ids"] = [str(uuid4())]
    with pytest.raises(ValueError, match="AI_ENTRY_ID_OUT_OF_SCOPE"):
        validate_task_output(
            task_type="practice_generation",
            context=_context(entry_ids),
            raw_text=json.dumps(out_of_scope),
        )


def test_schema_rejects_missing_extra_and_wrong_count() -> None:
    entry_ids = [str(uuid4()) for _ in range(3)]
    missing = _fill_output(entry_ids)
    del missing["items"][0]["sentence"]
    with pytest.raises(ValueError, match="AI_SCHEMA_INVALID"):
        validate_task_output(
            task_type="practice_generation",
            context=_context(entry_ids),
            raw_text=json.dumps(missing),
        )

    extra = _fill_output(entry_ids, extra=True)
    with pytest.raises(ValueError, match="AI_SCHEMA_INVALID"):
        validate_task_output(
            task_type="practice_generation",
            context=_context(entry_ids),
            raw_text=json.dumps(extra),
        )

    short = _fill_output(entry_ids[:2])
    with pytest.raises(ValueError, match="AI_SCHEMA_INVALID|AI_QUESTION_COUNT_MISMATCH"):
        validate_task_output(
            task_type="practice_generation",
            context=_context(entry_ids, count=3),
            raw_text=json.dumps(short),
        )


def test_reading_requires_200_words_and_matching_question_count() -> None:
    entry_ids = [str(uuid4())]
    questions = []
    for index in range(3):
        questions.append(
            {
                "id": f"rq{index}",
                "prompt": "What is the main idea?",
                "options": [
                    {"id": "a", "text": "A"},
                    {"id": "b", "text": "B"},
                    {"id": "c", "text": "C"},
                    {"id": "d", "text": "D"},
                ],
                "correct_option_id": "a",
                "explanation": "The passage supports A.",
            }
        )
    output = {
        "practice_type": "reading",
        "items": [
            {
                "id": "p1",
                "article": " ".join(["word"] * 200),
                "article_zh": "文章",
                "questions": questions,
                "target_entry_ids": [entry_ids[0]],
            }
        ],
    }
    context = {
        "practice_type": "reading",
        "count": 3,
        "source": "whole_book",
        "wordbook_id": str(uuid4()),
        "target_entry_ids": entry_ids,
    }
    result, summary = validate_task_output(
        task_type="practice_generation",
        context=context,
        raw_text=json.dumps(output),
    )
    assert result["practice_type"] == "reading"
    assert summary["question_count"] == 3

    output["items"][0]["article"] = "too short"
    with pytest.raises(ValueError, match="AI_SCHEMA_INVALID"):
        validate_task_output(
            task_type="practice_generation",
            context=context,
            raw_text=json.dumps(output),
        )


def test_challenge_plan_requires_boss_last_and_full_new_word_coverage() -> None:
    new_ids = [str(uuid4()), str(uuid4())]
    due_ids = [str(uuid4())]
    context = {
        "local_date": "2026-10-23",
        "target_minutes": 30,
        "new_entry_ids": new_ids,
        "due_entry_ids": due_ids,
        "allowed_practice_types": ["fill_blank", "reading"],
    }
    output = {
        "nodes": [
            {
                "id": "n1",
                "node_type": "REVIEW",
                "title": "Review",
                "description": "Review due words.",
                "word_entry_ids": due_ids,
                "estimated_minutes": 8,
            },
            {
                "id": "n2",
                "node_type": "NEW_WORDS",
                "title": "New words",
                "description": "Learn today's words.",
                "word_entry_ids": new_ids,
                "estimated_minutes": 15,
            },
            {
                "id": "n3",
                "node_type": "BOSS",
                "title": "Boss",
                "description": "Finish the challenge.",
                "word_entry_ids": new_ids + due_ids,
                "estimated_minutes": 7,
            },
        ]
    }
    result, summary = validate_task_output(
        task_type="challenge_plan",
        context=context,
        raw_text=json.dumps(output),
    )
    assert summary["node_count"] == 3
    assert result["nodes"][-1]["node_type"] == "BOSS"

    output["nodes"][1]["word_entry_ids"] = [new_ids[0]]
    with pytest.raises(ValueError, match="AI_NEW_WORD_COVERAGE_INCOMPLETE"):
        validate_task_output(
            task_type="challenge_plan",
            context=context,
            raw_text=json.dumps(output),
        )


def test_subjective_grading_rejects_inconsistent_dimensions() -> None:
    context = {
        "practice_type": "writing",
        "source_text": "Write about a harbor.",
        "user_answer": "The harbor is busy.",
        "exam_type": "CET4",
        "target_entry_ids": [],
    }
    output = {
        "total_score": 80,
        "dimensions": [
            {"name": "Accuracy", "score": 40, "max_score": 50},
            {"name": "Coherence", "score": 40, "max_score": 50},
        ],
        "errors": [],
        "suggestions": ["Add detail."],
        "reference_content": "The harbor is a busy place.",
    }
    result, summary = validate_task_output(
        task_type="subjective_grading",
        context=context,
        raw_text=json.dumps(output),
    )
    assert result["total_score"] == 80
    assert summary["total_score"] == 80

    output["total_score"] = 90
    with pytest.raises(ValueError, match="AI_SCHEMA_INVALID"):
        validate_task_output(
            task_type="subjective_grading",
            context=context,
            raw_text=json.dumps(output),
        )


def test_openapi_publishes_ai_admin_and_job_contracts(app) -> None:
    document = app.openapi()
    paths = document["paths"]
    expected = {
        "/api/v1/admin/ai/providers",
        "/api/v1/admin/ai/providers/{provider_id}",
        "/api/v1/admin/ai/providers/{provider_id}/test",
        "/api/v1/admin/ai/providers/{provider_id}/models",
        "/api/v1/admin/ai/prompts",
        "/api/v1/admin/ai/prompts/{prompt_key}",
        "/api/v1/admin/ai/usage",
        "/api/v1/ai/jobs",
        "/api/v1/ai/jobs/{job_id}",
        "/api/v1/ai/jobs/{job_id}/cancel",
        "/api/v1/ai/usage/me",
    }
    assert expected.issubset(paths)
    assert document["openapi"] == "3.1.0"
    assert "ProviderCreateRequest" in document["components"]["schemas"]
    assert "PracticeGenerationRequest" in document["components"]["schemas"]
    assert "ChallengePlanRequest" in document["components"]["schemas"]
