from __future__ import annotations

from app.services.ai_validation import validate_task_output
from app.services.practice import _answer_matches
from tests.ai_support import practice_output


def test_objective_answer_matching_accepts_option_id_and_case_insensitive_text() -> None:
    options = [{"id": "a", "text": "Harbor"}]
    assert _answer_matches("a", "a", options)
    assert _answer_matches("  HARBOR ", "a", options)
    assert not _answer_matches("ship", "a", options)


def test_openapi_publishes_answer_safe_practice_contract(app) -> None:
    document = app.openapi()
    paths = document["paths"]
    expected = {
        "/api/v1/practice/sessions",
        "/api/v1/practice/sessions/{session_id}",
        "/api/v1/practice/sessions/{session_id}/start",
        "/api/v1/practice/sessions/{session_id}/draft",
        "/api/v1/practice/sessions/{session_id}/regenerate",
        "/api/v1/practice/sessions/{session_id}/submit",
        "/api/v1/practice/sessions/{session_id}/result",
        "/api/v1/practice/records",
        "/api/v1/practice/mistakes",
        "/api/v1/practice/records/{session_id}",
        "/api/v1/practice/records/bulk",
        "/api/v1/practice/events",
    }
    assert expected.issubset(paths)
    public_question = document["components"]["schemas"]["PracticeQuestionPublic"]["properties"]
    assert "correct_option_id" not in public_question
    assert "explanation" not in public_question
    assert "reference_translation" not in public_question
    assert "reference_essay" not in public_question
    session_schema = document["components"]["schemas"]["PracticeSessionResponse"]["properties"]
    assert "draft_answers" in session_schema
    assert document["openapi"] == "3.1.0"


def test_difficulty_practice_allows_empty_target_entry_ids() -> None:
    entry_ids = ["11111111-1111-4111-8111-111111111111"] * 3
    output = practice_output(entry_ids)
    for item in output["items"]:
        item["target_entry_ids"] = []
    context = {
        "practice_type": "fill_blank",
        "count": 3,
        "source": "difficulty",
        "difficulty": "CET4",
        "wordbook_id": None,
        "target_entry_ids": [],
    }
    result, summary = validate_task_output(
        task_type="practice_generation",
        context=context,
        raw_text=__import__("json").dumps(output),
    )
    assert result["practice_type"] == "fill_blank"
    assert summary["item_count"] == 3


def test_a_citation_without_passages_is_dropped_not_crashed() -> None:
    # Hand-written practice carries no retrieved passages, so the citation
    # helper must survive having none.
    from app.services.practice import _citation_text

    assert _citation_text(1, None) is None
    assert _citation_text(1, []) is None
    assert _citation_text(None, ["[1] A passage"]) is None
    assert _citation_text(2, ["[1] A passage"]) is None
    assert _citation_text(1, ["[1] A passage\nbody"]) == "[1] A passage"
