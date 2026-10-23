from __future__ import annotations

from app.services.practice import _answer_matches


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
