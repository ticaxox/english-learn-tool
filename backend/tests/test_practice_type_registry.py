"""The practice-type lists have to agree with the code behind them.

Four separate places name a practice type: the schema literal, the model's
CHECK constraint, what the AI generator is offered, and what the hand-authoring
path can store. A type that reaches a path with no handler raises KeyError at
request time, so the lists are pinned against each other here.
"""

from __future__ import annotations

import typing

from app.models.practice import PRACTICE_SESSION_TYPES, PRACTICE_TYPES
from app.schemas.ai_tasks import PracticeType
from app.services.coach_tools import AUTHORABLE_PRACTICE_TYPES
from app.services.coach_tools import PRACTICE_TYPES as TOOL_TYPES
from app.services.practice_authoring import _ITEM_TYPES

DECLARED = set(typing.get_args(PracticeType))


def _sql_list(value: str) -> set[str]:
    return {part.strip().strip("'") for part in value.split(",")}


def test_every_declared_type_is_offered_to_the_generator() -> None:
    # ``mixed`` is a session shape, not something the generator is asked for.
    assert DECLARED - {"mixed"} == set(TOOL_TYPES)


def test_the_authoring_path_only_offers_types_it_can_store() -> None:
    # A type in this list with no entry in _ITEM_TYPES is a KeyError waiting
    # for a request.
    assert set(AUTHORABLE_PRACTICE_TYPES) == set(_ITEM_TYPES)
    assert set(AUTHORABLE_PRACTICE_TYPES) <= DECLARED


def test_the_database_accepts_every_declared_session_type() -> None:
    assert DECLARED == _sql_list(PRACTICE_SESSION_TYPES)


def test_the_database_accepts_every_declared_question_type() -> None:
    # A session may be mixed; a stored question never is.
    assert DECLARED - {"mixed"} == _sql_list(PRACTICE_TYPES)
