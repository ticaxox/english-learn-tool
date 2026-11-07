from __future__ import annotations

import re
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ExamType = Literal["CET4", "CET6", "POSTGRAD", "IELTS", "TOEFL"]
PracticeType = Literal["fill_blank", "reading", "translation", "writing", "mixed"]
PracticeSource = Literal["today_new", "today_review", "memory_mistakes", "whole_book", "difficulty"]
ChallengeNodeType = Literal[
    "REVIEW", "NEW_WORDS", "WORD_DRILL", "AI_PRACTICE", "BOSS", "OPTIONAL_SIDE"
]
CoachActionType = Literal[
    "adjust_daily_plan",
    "adjust_notification_preferences",
    "start_practice",
    "activate_wordbook",
    "mark_review_focus",
]

_HTML_TAG = re.compile(r"<[^>]*>")


def plain_text(value: str) -> str:
    """Normalize model text and remove markup rather than rendering it later."""
    return re.sub(r"\s+", " ", _HTML_TAG.sub("", value)).strip()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PracticeGenerationContext(StrictModel):
    practice_type: PracticeType
    count: int = Field(ge=1, le=20)
    source: PracticeSource
    difficulty: ExamType | None = None
    wordbook_id: UUID | None = None
    target_entry_ids: list[UUID] = Field(default_factory=list, max_length=100)
    practice_session_id: UUID | None = None
    # Reading only: how long the single passage should be for this question count.
    article_min_words: int | None = Field(default=None, ge=60, le=2_000)
    article_max_words: int | None = Field(default=None, ge=60, le=2_000)

    @model_validator(mode="after")
    def validate_count_and_source(self) -> PracticeGenerationContext:
        allowed = {1} if self.practice_type == "writing" else {3, 5, 10, 15, 20}
        if self.count not in allowed:
            raise ValueError("count does not match the selected practice type")
        if self.source == "difficulty" and self.difficulty is None:
            raise ValueError("difficulty is required when source is difficulty")
        if self.source != "difficulty" and self.wordbook_id is None:
            raise ValueError("wordbook_id is required for a wordbook practice source")
        return self


class BatchGradingItemContext(StrictModel):
    question_id: str = Field(min_length=1, max_length=64)
    source_text: str = Field(min_length=1, max_length=20_000)
    user_answer: str = Field(min_length=1, max_length=20_000)
    exam_type: ExamType
    target_entry_ids: list[UUID] = Field(default_factory=list, max_length=100)


class SubjectiveGradingContext(StrictModel):
    practice_type: Literal["translation", "writing"]
    source_text: str = Field(min_length=1, max_length=20_000)
    user_answer: str = Field(min_length=1, max_length=20_000)
    exam_type: ExamType
    target_entry_ids: list[UUID] = Field(default_factory=list, max_length=100)
    practice_submission_id: UUID | None = None
    items: list[BatchGradingItemContext] = Field(default_factory=list, max_length=20)


class CoachHistoryTurn(StrictModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4_000)


class CoachReplyContext(StrictModel):
    user_message: str = Field(min_length=1, max_length=8_000)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=4)
    learning_summary: dict[str, Any] = Field(default_factory=dict)
    history: list[CoachHistoryTurn] = Field(default_factory=list, max_length=20)
    memory_document: str | None = Field(default=None, max_length=6_000)
    conversation_id: UUID | None = None
    message_id: UUID | None = None
    page_context: dict[str, Any] = Field(default_factory=dict)


class ChallengePlanContext(StrictModel):
    local_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    target_minutes: int = Field(ge=15, le=180)
    new_entry_ids: list[UUID] = Field(default_factory=list, max_length=200)
    due_entry_ids: list[UUID] = Field(default_factory=list, max_length=500)
    allowed_practice_types: list[PracticeType] = Field(default_factory=list)
    allowed_drill_modes: list[Literal["choice", "spelling", "flashcard"]] = Field(
        default_factory=lambda: ["choice", "spelling", "flashcard"]
    )
    plan_id: UUID | None = None
    wordbook_id: UUID | None = None
    target_new_words: int = Field(default=0, ge=0, le=200)


class JsonRepairContext(StrictModel):
    raw_text: str = Field(min_length=1, max_length=30_000)
    validation_errors: list[str] = Field(min_length=1, max_length=50)


class PracticeGenerationRequest(StrictModel):
    task_type: Literal["practice_generation"]
    context: PracticeGenerationContext


class SubjectiveGradingRequest(StrictModel):
    task_type: Literal["subjective_grading"]
    context: SubjectiveGradingContext


class CoachReplyRequest(StrictModel):
    task_type: Literal["coach_reply"]
    context: CoachReplyContext


class ChallengePlanRequest(StrictModel):
    task_type: Literal["challenge_plan"]
    context: ChallengePlanContext


class JsonRepairRequest(StrictModel):
    task_type: Literal["json_repair"]
    context: JsonRepairContext


AiJobCreateRequest = Annotated[
    PracticeGenerationRequest
    | SubjectiveGradingRequest
    | CoachReplyRequest
    | ChallengePlanRequest
    | JsonRepairRequest,
    Field(discriminator="task_type"),
]


class OptionOutput(StrictModel):
    id: str = Field(min_length=1, max_length=16)
    text: str = Field(min_length=1, max_length=1_000)
    # Every option carries a Chinese gloss so the learner can read the choices.
    text_zh: str = Field(min_length=1, max_length=1_000)

    @field_validator("id", "text", "text_zh")
    @classmethod
    def clean_text(cls, value: str) -> str:
        cleaned = plain_text(value)
        if not cleaned:
            raise ValueError("text must not be blank")
        return cleaned


class FillBlankItem(StrictModel):
    id: str = Field(min_length=1, max_length=64)
    sentence: str = Field(min_length=1, max_length=2_000)
    sentence_zh: str = Field(min_length=1, max_length=2_000)
    options: list[OptionOutput] = Field(min_length=4, max_length=4)
    correct_option_id: str = Field(min_length=1, max_length=16)
    explanation: str = Field(min_length=1, max_length=2_000)
    target_entry_ids: list[UUID] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def validate_answer(self) -> FillBlankItem:
        option_ids = [option.id for option in self.options]
        if len(set(option_ids)) != 4:
            raise ValueError("option ids must be unique")
        if option_ids.count(self.correct_option_id) != 1:
            raise ValueError("correct_option_id must reference exactly one option")
        if self.sentence.count("____") != 1:
            raise ValueError("fill-blank sentences must contain exactly one ____ blank")
        return self


class ReadingQuestion(StrictModel):
    id: str = Field(min_length=1, max_length=64)
    prompt: str = Field(min_length=1, max_length=2_000)
    options: list[OptionOutput] = Field(min_length=4, max_length=4)
    correct_option_id: str = Field(min_length=1, max_length=16)
    explanation: str = Field(min_length=1, max_length=2_000)

    @model_validator(mode="after")
    def validate_answer(self) -> ReadingQuestion:
        option_ids = [option.id for option in self.options]
        if len(set(option_ids)) != 4:
            raise ValueError("option ids must be unique")
        if option_ids.count(self.correct_option_id) != 1:
            raise ValueError("correct_option_id must reference exactly one option")
        return self


class ReadingPassage(StrictModel):
    id: str = Field(min_length=1, max_length=64)
    article: str = Field(min_length=1, max_length=20_000)
    article_zh: str = Field(min_length=1, max_length=20_000)
    # One passage carries every question of the set. Its article length is checked
    # against the count-based range in ai_validation, where the session count lives.
    questions: list[ReadingQuestion] = Field(min_length=1, max_length=20)
    target_entry_ids: list[UUID] = Field(default_factory=list, max_length=20)

    @field_validator("article", "article_zh")
    @classmethod
    def clean_article(cls, value: str) -> str:
        cleaned = plain_text(value)
        if not cleaned:
            raise ValueError("article must not be blank")
        return cleaned


class TranslationItem(StrictModel):
    id: str = Field(min_length=1, max_length=64)
    source_text: str = Field(min_length=1, max_length=5_000)
    source_language: Literal["en", "zh"]
    target_language: Literal["en", "zh"]
    reference_translation: str = Field(min_length=1, max_length=5_000)
    target_entry_ids: list[UUID] = Field(default_factory=list, max_length=20)


class WritingItem(StrictModel):
    id: str = Field(min_length=1, max_length=64)
    prompt: str = Field(min_length=1, max_length=5_000)
    requirements: list[str] = Field(min_length=1, max_length=20)
    reference_essay: str = Field(min_length=1, max_length=20_000)
    target_entry_ids: list[UUID] = Field(default_factory=list, max_length=20)


PracticeItem = FillBlankItem | ReadingPassage | TranslationItem | WritingItem


class PracticeGenerationOutput(StrictModel):
    practice_type: PracticeType
    items: list[PracticeItem] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_item_shapes(self) -> PracticeGenerationOutput:
        if self.practice_type == "mixed":
            # A mixed set may draw from every type, but the number of questions
            # must still match the count the learner picked.
            question_count = sum(
                len(item.questions) if isinstance(item, ReadingPassage) else 1
                for item in self.items
            )
            if question_count not in {3, 5, 10, 15, 20}:
                raise ValueError("practice question count must be 3, 5, 10, 15, or 20")
            return self
        expected = {
            "fill_blank": FillBlankItem,
            "reading": ReadingPassage,
            "translation": TranslationItem,
            "writing": WritingItem,
        }[self.practice_type]
        if any(not isinstance(item, expected) for item in self.items):
            raise ValueError("items do not match practice_type")
        if self.practice_type == "writing" and len(self.items) != 1:
            raise ValueError("writing practice must contain exactly one item")
        if self.practice_type in {"fill_blank", "translation"} and len(self.items) not in {
            3,
            5,
            10,
            15,
            20,
        }:
            raise ValueError("practice item count must be 3, 5, 10, 15, or 20")
        if self.practice_type == "reading":
            question_count = sum(len(item.questions) for item in self.items)
            if question_count not in {3, 5, 10, 15, 20}:
                raise ValueError("reading question count must be 3, 5, 10, 15, or 20")
        return self


class ScoreDimension(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    score: float = Field(ge=0, le=100)
    max_score: float = Field(gt=0, le=100)


class SubjectiveGradingOutput(StrictModel):
    total_score: float = Field(ge=0, le=100)
    dimensions: list[ScoreDimension] = Field(min_length=1, max_length=10)
    errors: list[str] = Field(default_factory=list, max_length=50)
    suggestions: list[str] = Field(min_length=1, max_length=50)
    reference_content: str = Field(min_length=1, max_length=20_000)
    corrected_text: str | None = Field(default=None, max_length=20_000)

    @model_validator(mode="after")
    def validate_scores(self) -> SubjectiveGradingOutput:
        if any(dimension.score > dimension.max_score for dimension in self.dimensions):
            raise ValueError("a dimension score exceeds its max_score")
        if abs(sum(dimension.max_score for dimension in self.dimensions) - 100) > 0.01:
            raise ValueError("dimension max scores must add up to 100")
        if abs(sum(dimension.score for dimension in self.dimensions) - self.total_score) > 0.01:
            raise ValueError("total_score must equal the sum of dimension scores")
        return self


class BatchGradingItemOutput(SubjectiveGradingOutput):
    question_id: str = Field(min_length=1, max_length=64)


class PracticeGradingBatchOutput(StrictModel):
    items: list[BatchGradingItemOutput] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def unique_question_ids(self) -> PracticeGradingBatchOutput:
        ids = [item.question_id for item in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("grading question ids must be unique")
        return self


class CoachAction(StrictModel):
    action_type: CoachActionType
    parameters: dict[str, Any] = Field(default_factory=dict)
    summary: str = Field(min_length=1, max_length=500)


class CoachReplyOutput(StrictModel):
    message: str = Field(min_length=1, max_length=8_000)
    actions: list[CoachAction] = Field(default_factory=list, max_length=3)

    @field_validator("message")
    @classmethod
    def clean_message(cls, value: str) -> str:
        cleaned = plain_text(value)
        if not cleaned:
            raise ValueError("message must not be blank")
        return cleaned


class ChallengeNodeOutput(StrictModel):
    id: str = Field(min_length=1, max_length=64)
    client_key: str | None = Field(default=None, min_length=1, max_length=64)
    node_type: ChallengeNodeType
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1_000)
    word_entry_ids: list[UUID] = Field(default_factory=list, max_length=200)
    estimated_minutes: int = Field(ge=1, le=120)
    optional: bool = False
    practice_type: PracticeType | None = None
    practice_count: int | None = Field(default=None, ge=1, le=20)
    drill_mode: Literal["choice", "spelling", "flashcard"] | None = None
    order: int | None = Field(default=None, ge=1, le=100)

    @field_validator("title", "description")
    @classmethod
    def safe_text(cls, value: str) -> str:
        if "<" in value or ">" in value:
            raise ValueError("challenge copy must not contain HTML")
        cleaned = plain_text(value)
        if not cleaned:
            raise ValueError("challenge copy must not be blank")
        return cleaned

    @model_validator(mode="after")
    def validate_optional_and_practice(self) -> ChallengeNodeOutput:
        if self.client_key is None:
            self.client_key = self.id
        if self.node_type == "OPTIONAL_SIDE" and not self.optional:
            raise ValueError("OPTIONAL_SIDE nodes must be optional")
        if self.optional and self.node_type != "OPTIONAL_SIDE":
            raise ValueError("only OPTIONAL_SIDE nodes may be optional")
        if self.node_type == "AI_PRACTICE" and self.practice_type is None:
            raise ValueError("AI_PRACTICE nodes require practice_type")
        if self.node_type == "AI_PRACTICE" and self.practice_count is None:
            raise ValueError("AI_PRACTICE nodes require practice_count")
        if self.node_type == "BOSS":
            if self.practice_type is None:
                self.practice_type = "fill_blank"
            if self.practice_type != "fill_blank":
                raise ValueError("BOSS nodes require fill_blank practice")
            if self.practice_count is None:
                self.practice_count = 5
            if self.practice_count not in {5, 10}:
                raise ValueError("BOSS practice_count must be 5 or 10")
        if self.node_type not in {"AI_PRACTICE", "BOSS"} and self.practice_type is not None:
            raise ValueError("practice_type is only valid on AI_PRACTICE and BOSS nodes")
        if self.node_type == "WORD_DRILL":
            if self.drill_mode is None:
                self.drill_mode = "choice"
        elif self.drill_mode is not None:
            raise ValueError("drill_mode is only valid on WORD_DRILL nodes")
        if self.practice_type is not None and self.practice_count is not None:
            allowed = {1} if self.practice_type == "writing" else {3, 5, 10, 15, 20}
            if self.practice_count not in allowed:
                raise ValueError("practice_count does not match practice_type")
        return self


class ChallengePlanOutput(StrictModel):
    version: Literal["challenge-plan-v1"] = "challenge-plan-v1"
    title: str = Field(default="今天的英语闯关", min_length=1, max_length=200)
    summary: str = Field(
        default="按顺序完成今日学习节点，最后挑战终点。", min_length=1, max_length=1_000
    )
    nodes: list[ChallengeNodeOutput] = Field(min_length=3, max_length=7)

    @field_validator("title", "summary")
    @classmethod
    def safe_plan_text(cls, value: str) -> str:
        if "<" in value or ">" in value:
            raise ValueError("challenge copy must not contain HTML")
        cleaned = plain_text(value)
        if not cleaned:
            raise ValueError("challenge copy must not be blank")
        return cleaned

    @model_validator(mode="after")
    def validate_map(self) -> ChallengePlanOutput:
        main = [node for node in self.nodes if node.node_type != "OPTIONAL_SIDE"]
        optional = [node for node in self.nodes if node.node_type == "OPTIONAL_SIDE"]
        if not 3 <= len(main) <= 6:
            raise ValueError("challenge maps require 3-6 main nodes")
        if len(optional) > 1:
            raise ValueError("challenge maps allow at most one optional side node")
        if main[-1].node_type != "BOSS":
            raise ValueError("the final main node must be BOSS")
        if any(node.node_type == "BOSS" for node in main[:-1]):
            raise ValueError("BOSS may only appear as the final main node")
        if sum(node.node_type == "AI_PRACTICE" for node in main) > 1:
            raise ValueError("at most one main AI_PRACTICE node is allowed")
        for index, node in enumerate(main, start=1):
            if node.order is None:
                node.order = index
        for node in optional:
            if node.order is None:
                node.order = 100
        orders = [node.order for node in self.nodes]
        if len(set(orders)) != len(orders):
            raise ValueError("challenge node order values must be unique")
        if len({node.client_key for node in self.nodes}) != len(self.nodes):
            raise ValueError("challenge node client keys must be unique")
        return self


class JsonRepairOutput(StrictModel):
    corrected: dict[str, Any]


TASK_OUTPUT_MODELS: dict[str, type[BaseModel]] = {
    "practice_generation": PracticeGenerationOutput,
    "subjective_grading": SubjectiveGradingOutput,
    "coach_reply": CoachReplyOutput,
    "challenge_plan": ChallengePlanOutput,
    "json_repair": JsonRepairOutput,
}
