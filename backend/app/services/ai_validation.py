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
    ReadingPassage,
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


def _contains_markup(value: Any) -> bool:
    if isinstance(value, str):
        return "<" in value or ">" in value
    if isinstance(value, list):
        return any(_contains_markup(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_markup(item) for item in value.values())
    return False


def _uuid_set(values: list[UUID]) -> set[str]:
    return {str(value) for value in values}


def _target_word_map(practice: PracticeGenerationContext) -> dict[str, str]:
    return {
        str(entry): word
        for entry, word in zip(practice.target_entry_ids, practice.target_words, strict=False)
    }


def _mentions(text: str, word: str) -> bool:
    pattern = rf"\b{re.escape(word.lower())}(?:s|es|ed|d|ing)?\b"
    return re.search(pattern, text.lower()) is not None


def _item_text(item: Any) -> str:
    parts: list[str] = []
    for field in ("sentence", "article", "prompt", "source_text"):
        value = getattr(item, field, None)
        if isinstance(value, str):
            parts.append(value)
    for option in getattr(item, "options", []) or []:
        parts.append(option.text)
    for question in getattr(item, "questions", []) or []:
        parts.append(question.prompt)
        parts.extend(option.text for option in question.options)
    parts.extend(getattr(item, "requirements", []) or [])
    return "\n".join(parts)


def _collect_entry_ids(item: Any) -> set[str]:
    values = getattr(item, "target_entry_ids", [])
    return _uuid_set(values)


_CHALLENGE_PRACTICE_NODES = {"AI_PRACTICE", "BOSS"}
_CHALLENGE_PRACTICE_COUNTS = {5, 10}


def _normalize_challenge_nodes(parsed: dict[str, Any], context: dict[str, Any]) -> None:
    """Clear node attributes that the node type cannot carry.

    JSON Schema cannot say "this optional field only applies to these node
    types", so models routinely attach drill_mode to a NEW_WORDS node or
    practice_type to a WORD_DRILL node. The node type is authoritative: the
    attribute is advice, not data, so it is dropped instead of failing the map.
    """
    nodes = parsed.get("nodes")
    if not isinstance(nodes, list):
        return
    allowed_practice_types = context.get("allowed_practice_types") or []
    default_practice_type = (
        allowed_practice_types[0]
        if allowed_practice_types
        and allowed_practice_types[0] in {"fill_blank", "reading", "translation", "writing"}
        else "fill_blank"
    )
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = node.get("node_type")
        if node_type != "WORD_DRILL":
            node.pop("drill_mode", None)
        if node_type not in _CHALLENGE_PRACTICE_NODES:
            node.pop("practice_type", None)
            node.pop("practice_count", None)
        if node_type == "OPTIONAL_SIDE":
            node["optional"] = True
        else:
            node.pop("optional", None)
        if node_type == "AI_PRACTICE":
            if node.get("practice_type") not in {"fill_blank", "reading", "translation", "writing"}:
                node["practice_type"] = default_practice_type
            count = node.get("practice_count")
            if not isinstance(count, int) or count < 1 or count > 20:
                node["practice_count"] = 1 if node["practice_type"] == "writing" else 5
        if node_type == "BOSS":
            if node.get("practice_type") != "fill_blank":
                node.pop("practice_type", None)
            if node.get("practice_count") not in _CHALLENGE_PRACTICE_COUNTS:
                node.pop("practice_count", None)


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
    if task_type == "challenge_plan" and _contains_markup(parsed):
        raise ValueError("AI_HTML_NOT_ALLOWED")
    parsed = sanitize_untrusted_json(parsed)
    if task_type == "challenge_plan" and isinstance(parsed, dict):
        _normalize_challenge_nodes(parsed, context)
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
        word_map = _target_word_map(practice)
        if output.practice_type != practice.practice_type:
            raise ValueError("AI_PRACTICE_TYPE_MISMATCH")
        if practice.practice_type == "reading":
            # One passage carries the whole set: ten questions never mean two articles.
            passages = [item for item in output.items if isinstance(item, ReadingPassage)]
            if len(passages) != 1:
                raise ValueError("AI_READING_SINGLE_PASSAGE_REQUIRED")
            passage = passages[0]
            if len(passage.questions) != practice.count:
                raise ValueError("AI_QUESTION_COUNT_MISMATCH")
            if practice.article_min_words and practice.article_max_words:
                words = len(re.findall(r"\b[\w'-]+\b", passage.article))
                if not practice.article_min_words <= words <= practice.article_max_words:
                    raise ValueError(
                        "AI_ARTICLE_WORD_COUNT_OUT_OF_RANGE: "
                        f"{words} not in {practice.article_min_words}-{practice.article_max_words}"
                    )
        elif practice.practice_type == "mixed":
            question_count = sum(
                len(getattr(item, "questions", [])) or 1 for item in output.items
            )
            if question_count != practice.count:
                raise ValueError("AI_QUESTION_COUNT_MISMATCH")
        elif len(output.items) != practice.count:
            raise ValueError("AI_QUESTION_COUNT_MISMATCH")
        for item in output.items:
            item_entry_ids = _collect_entry_ids(item)
            if not item_entry_ids.issubset(allowed):
                raise ValueError("AI_ENTRY_ID_OUT_OF_SCOPE")
            if practice.source != "difficulty" and not item_entry_ids:
                raise ValueError("AI_TARGET_ENTRY_REQUIRED")
            # The learner's words must actually appear, or nothing can be marked.
            if item_entry_ids and word_map:
                words = [word_map[entry] for entry in item_entry_ids if entry in word_map]
                if words and not any(_mentions(_item_text(item), word) for word in words):
                    raise ValueError("AI_TARGET_WORD_MISSING")
    elif task_type == "challenge_plan":
        challenge = ChallengePlanContext.model_validate(context)
        output = ChallengePlanOutput.model_validate(validated)
        allowed = _uuid_set(challenge.new_entry_ids + challenge.due_entry_ids)
        node_ids: set[str] = set()
        new_word_node_ids: set[str] = set()
        review_node_ids: set[str] = set()
        main_minutes = 0
        for node in output.nodes:
            node_entry_ids = _uuid_set(node.word_entry_ids)
            node_ids.update(node_entry_ids)
            if node.node_type == "NEW_WORDS":
                new_word_node_ids.update(node_entry_ids)
            elif node.node_type == "REVIEW":
                review_node_ids.update(node_entry_ids)
            if node.node_type != "OPTIONAL_SIDE":
                main_minutes += node.estimated_minutes
            if not node_entry_ids.issubset(allowed):
                raise ValueError("AI_ENTRY_ID_OUT_OF_SCOPE")
        if not _uuid_set(challenge.new_entry_ids).issubset(new_word_node_ids):
            raise ValueError("AI_NEW_WORD_COVERAGE_INCOMPLETE")
        if challenge.due_entry_ids and not _uuid_set(challenge.due_entry_ids).issubset(
            review_node_ids
        ):
            raise ValueError("AI_DUE_WORD_COVERAGE_INCOMPLETE")
        allowed_practice_types = set(challenge.allowed_practice_types)
        for node in output.nodes:
            if node.practice_type and node.practice_type not in allowed_practice_types:
                raise ValueError("AI_PRACTICE_TYPE_NOT_ALLOWED")
            if node.drill_mode and node.drill_mode not in challenge.allowed_drill_modes:
                raise ValueError("AI_DRILL_MODE_NOT_ALLOWED")
        minimum_minutes = challenge.target_minutes * 0.8
        maximum_minutes = challenge.target_minutes * 1.2
        if not minimum_minutes <= main_minutes <= maximum_minutes:
            raise ValueError("AI_CHALLENGE_MINUTES_OUT_OF_RANGE")
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
