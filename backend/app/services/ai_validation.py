from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from app.schemas.ai_tasks import (
    TASK_OUTPUT_MODELS,
    ChallengePlanContext,
    ChallengePlanOutput,
    PracticeGenerationContext,
    PracticeGenerationOutput,
    PracticeGradingBatchOutput,
    SubjectiveGradingOutput,
)

_HTML_TAG = re.compile(r"<[^>]*>")


def sanitize_untrusted_json(value: Any) -> Any:
    if isinstance(value, str):
        return re.sub(r"\s+", " ", _HTML_TAG.sub("", value)).strip()
    if isinstance(value, list):
        return [sanitize_untrusted_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): sanitize_untrusted_json(item) for key, item in value.items()}
    return value


def output_schema(task_type: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    if task_type == "subjective_grading" and context and context.get("items"):
        return PracticeGradingBatchOutput.model_json_schema()
    model = TASK_OUTPUT_MODELS[task_type]
    return model.model_json_schema()


def _uuid_set(values: list[UUID]) -> set[str]:
    return {str(value) for value in values}


def _collect_entry_ids(item: Any) -> set[str]:
    values = getattr(item, "target_entry_ids", [])
    return _uuid_set(values)


def validate_task_output(
    *,
    task_type: str,
    context: dict[str, Any],
    raw_text: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Parse, sanitize, Pydantic-validate, then enforce cross-field business rules."""
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"AI_JSON_INVALID: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("AI_JSON_OBJECT_REQUIRED")
    parsed = sanitize_untrusted_json(parsed)
    model = (
        PracticeGradingBatchOutput
        if task_type == "subjective_grading" and context.get("items")
        else TASK_OUTPUT_MODELS[task_type]
    )
    try:
        validated = model.model_validate(parsed)
    except ValidationError as exc:
        raise ValueError(f"AI_SCHEMA_INVALID: {exc.errors(include_url=False)}") from exc
    result = validated.model_dump(mode="json")

    if task_type == "practice_generation":
        practice = PracticeGenerationContext.model_validate(context)
        output = PracticeGenerationOutput.model_validate(validated)
        allowed = _uuid_set(practice.target_entry_ids)
        if output.practice_type != practice.practice_type:
            raise ValueError("AI_PRACTICE_TYPE_MISMATCH")
        if practice.practice_type == "reading":
            question_count = sum(len(item.questions) for item in output.items)
            if question_count != practice.count:
                raise ValueError("AI_QUESTION_COUNT_MISMATCH")
        elif len(output.items) != practice.count:
            raise ValueError("AI_QUESTION_COUNT_MISMATCH")
        for item in output.items:
            if not _collect_entry_ids(item).issubset(allowed):
                raise ValueError("AI_ENTRY_ID_OUT_OF_SCOPE")
    elif task_type == "challenge_plan":
        challenge = ChallengePlanContext.model_validate(context)
        output = ChallengePlanOutput.model_validate(validated)
        allowed = _uuid_set(challenge.new_entry_ids + challenge.due_entry_ids)
        node_ids: set[str] = set()
        new_word_node_ids: set[str] = set()
        for node in output.nodes:
            node_entry_ids = _uuid_set(node.word_entry_ids)
            node_ids.update(node_entry_ids)
            if node.node_type == "NEW_WORDS":
                new_word_node_ids.update(node_entry_ids)
            if not node_entry_ids.issubset(allowed):
                raise ValueError("AI_ENTRY_ID_OUT_OF_SCOPE")
        if not _uuid_set(challenge.new_entry_ids).issubset(new_word_node_ids):
            raise ValueError("AI_NEW_WORD_COVERAGE_INCOMPLETE")
        for node in output.nodes:
            if node.practice_type and node.practice_type not in challenge.allowed_practice_types:
                raise ValueError("AI_PRACTICE_TYPE_NOT_ALLOWED")
    elif task_type == "subjective_grading":
        if context.get("items"):
            output = PracticeGradingBatchOutput.model_validate(validated)
            expected_ids = {item["question_id"] for item in context["items"]}
            actual_ids = {item.question_id for item in output.items}
            if actual_ids != expected_ids:
                raise ValueError("AI_GRADING_QUESTION_IDS_MISMATCH")
            if any(not 0 <= item.total_score <= 100 for item in output.items):
                raise ValueError("AI_SCORE_OUT_OF_RANGE")
        else:
            output = SubjectiveGradingOutput.model_validate(validated)
            if not 0 <= output.total_score <= 100:
                raise ValueError("AI_SCORE_OUT_OF_RANGE")

    summary: dict[str, Any] = {}
    if task_type == "practice_generation":
        summary = {
            "practice_type": result["practice_type"],
            "item_count": len(result["items"]),
        }
        if result["practice_type"] == "reading":
            summary["question_count"] = sum(len(item["questions"]) for item in result["items"])
    elif task_type == "subjective_grading":
        if context.get("items"):
            summary = {
                "item_count": len(result["items"]),
                "average_score": round(
                    sum(item["total_score"] for item in result["items"]) / len(result["items"]), 2
                ),
            }
        else:
            summary = {"total_score": result["total_score"]}
    elif task_type == "coach_reply":
        summary = {"message_length": len(result["message"]), "action_count": len(result["actions"])}
    elif task_type == "challenge_plan":
        summary = {"node_count": len(result["nodes"])}
    elif task_type == "json_repair":
        summary = {"corrected_keys": len(result["corrected"])}
    return result, summary


def repair_prompt(invalid_text: str, error: str) -> str:
    return (
        "The previous response was not valid for the required JSON schema. "
        "Repair it and return only a valid JSON object. Do not add facts.\n"
        f"Validation error: {error[:1000]}\n"
        f"Invalid response:\n{invalid_text[:30000]}"
    )
