"""Server-owned FSRS scheduling.

The algorithm runs only on the backend: clients submit an operation or answer, never
stability, difficulty, due timestamps, or card state. Persisted cards keep the raw FSRS
card dictionary so a later review resumes from the exact stored state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from fsrs import Card, Rating, Scheduler, State

FSRS_ALGORITHM_VERSION = "fsrs-6.3.2"
RESTORE_RETRY_DELAY = timedelta(minutes=10)

# Fuzzing would make identical inputs produce different intervals; determinism is required
# so plan snapshots, resumed sessions, and tests are reproducible.
_SCHEDULER = Scheduler(enable_fuzzing=False)

_RATINGS = {"again": Rating.Again, "good": Rating.Good}

_STATE_TO_STATUS = {
    State.Learning: "learning",
    State.Review: "review",
    State.Relearning: "relearning",
}


class UnschedulableCardError(ValueError):
    """Raised when a persisted FSRS card payload cannot be reconstructed."""


@dataclass(frozen=True)
class ReviewOutcome:
    card_payload: dict[str, Any]
    status: str
    due_at: datetime | None
    reviewed_at: datetime
    interval_days: float


def rating_for(value: str) -> Rating:
    rating = _RATINGS.get(value.lower())
    if rating is None:
        raise UnschedulableCardError(f"Unsupported rating: {value}")
    return rating


def new_card_payload() -> dict[str, Any]:
    return Card().to_dict()


def _load_card(payload: dict[str, Any] | None) -> Card:
    if not payload:
        return Card()
    try:
        return Card.from_dict(payload)
    except (KeyError, TypeError, ValueError) as exc:  # pragma: no cover - defensive
        raise UnschedulableCardError("The stored FSRS card payload is invalid.") from exc


def review(
    payload: dict[str, Any] | None,
    *,
    rating: str,
    reviewed_at: datetime,
    duration_seconds: int | None = None,
) -> ReviewOutcome:
    """Apply one FSRS review and return the new server-owned state."""

    card = _load_card(payload)
    reviewed_card, _log = _SCHEDULER.review_card(
        card,
        rating_for(rating),
        review_datetime=reviewed_at,
        review_duration=duration_seconds,
    )
    due_at = reviewed_card.due
    interval_days = 0.0
    if due_at is not None:
        interval_days = (due_at - reviewed_at).total_seconds() / 86400
    return ReviewOutcome(
        card_payload=reviewed_card.to_dict(),
        status=_STATE_TO_STATUS.get(reviewed_card.state, "learning"),
        due_at=due_at,
        reviewed_at=reviewed_at,
        interval_days=round(interval_days, 4),
    )


def restored_payload(
    payload: dict[str, Any] | None, *, now: datetime
) -> tuple[dict[str, Any], str, datetime | None]:
    """Return a safe card state for a restored word.

    A restored word must never resurface already overdue, so the stored card is replaced by a
    fresh relearning card that is due after the short relearning step.
    """

    if not payload:
        return {}, "new", None
    card = _load_card(payload)
    restored = Card(
        card_id=card.card_id,
        state=State.Relearning,
        step=0,
        stability=card.stability,
        difficulty=card.difficulty,
        due=now + RESTORE_RETRY_DELAY,
        last_review=card.last_review,
    )
    return restored.to_dict(), "relearning", restored.due
