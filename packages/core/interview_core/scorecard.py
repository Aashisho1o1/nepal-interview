"""Scorecard contract and strict validation.

Whatever produces feedback (rules or a model), nothing is shown to a student until it
passes `validate_scorecard`. Validation rejects unknown keys, invalid enum values,
quotes that are not verbatim in the cited student turn, timestamps outside the turn
or session, document references outside the student's snapshot, and forbidden
claims (approval predictions, honesty or emotion inferences).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from . import RUBRIC_VERSION, SCORECARD_SCHEMA_VERSION

Category = Literal[
    "question_relevance",
    "factual_consistency",
    "funding_explanation",
    "course_understanding",
    "concise_delivery",
    "task_completion",
]
Severity = Literal["strength", "needs_practice", "needs_clarification", "document_mismatch"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Finding(_Strict):
    category: Category
    severity: Severity
    observed_quote: str = Field(min_length=1, max_length=600)
    turn_id: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    document_refs: list[str] = Field(default_factory=list, max_length=8)
    explanation: str = Field(min_length=1, max_length=600)
    next_action: str = Field(min_length=1, max_length=400)
    requires_counselor_review: bool
    clearer_phrasing_example: str | None = Field(default=None, max_length=400)


class Scorecard(_Strict):
    schema_version: Literal["1.0"]
    rubric_version: str
    track: Literal["uk_pre_cas"]
    session_id: str
    assessment_scope: Literal["practice_feedback_only"]
    transcript_quality: Literal["good", "adequate", "poor", "insufficient"]
    findings: list[Finding] = Field(max_length=20)
    practice_tasks: list[str] = Field(max_length=10)
    unknowns: list[str] = Field(max_length=20)
    human_review_status: Literal["not_reviewed", "reviewed", "edited"]


@dataclass(frozen=True)
class TurnRecord:
    turn_id: str
    speaker: str  # "student" | "interviewer"
    text: str
    start_ms: int
    end_ms: int
    canceled: bool = False


@dataclass(frozen=True)
class ValidationContext:
    session_id: str
    track: str
    snapshot_refs: frozenset[str]
    turns: tuple[TurnRecord, ...]
    session_duration_ms: int


class ScorecardError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


# Claims the product must never make. Matched case-insensitively on all free text.
FORBIDDEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "approval prediction",
        re.compile(
            r"\b(will|would|should|likely|unlikely|going\s+to|expect\w*\s+to|bound\s+to)\b"
            r"[^.]{0,30}\b(approved|refused|rejected|denied|granted|approval|refusal)\b",
            re.I,
        ),
    ),
    ("approval prediction", re.compile(r"\bvisa\s+(approval|refusal|rejection|denial)\b", re.I)),
    (
        "approval chance",
        re.compile(
            r"\b(chance|chances|probability|likelihood|odds)\b[^.]{0,40}\b(visa|approv|refus|success)",
            re.I,
        ),
    ),
    ("percentage claim", re.compile(r"\b\d{1,3}\s?%")),
    ("visa success claim", re.compile(r"\bvisa\s+(success|approval)\s+(rate|score)\b", re.I)),
    (
        "honesty inference",
        re.compile(
            r"\b(lying|liar|lied|dishonest\w*|deceptive|untruthful|not\s+telling\s+the\s+truth|"
            r"credibility\s+score)\b",
            re.I,
        ),
    ),
    (
        "emotion inference",
        re.compile(
            r"\b(nervous|anxious|anxiety|stressed|scared|afraid|fearful|emotional|"
            r"seemed\s+confident|sounded\s+confident|lack(ed)?\s+confidence|tremb\w*|"
            r"shaky\s+voice)\b",
            re.I,
        ),
    ),
)

_WS = re.compile(r"\s+")


def _norm(s: str) -> str:
    s = s.replace("’", "'").replace("“", '"').replace("”", '"')
    return _WS.sub(" ", s).strip().strip(".,;:!?\"'").lower()


def _forbidden_hits(text: str) -> list[str]:
    return [name for name, pat in FORBIDDEN_PATTERNS if pat.search(text)]


def validate_scorecard(raw: object, ctx: ValidationContext) -> Scorecard:
    try:
        card = Scorecard.model_validate(raw)
    except ValidationError as e:
        raise ScorecardError(
            [f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()]
        ) from e

    errors: list[str] = []
    if card.session_id != ctx.session_id:
        errors.append("session_id does not match the session being graded")
    if card.track != ctx.track:
        errors.append("track does not match the session track")
    if card.schema_version != SCORECARD_SCHEMA_VERSION:
        errors.append("unsupported schema_version")
    if card.rubric_version != RUBRIC_VERSION:
        errors.append("unexpected rubric_version")
    if card.human_review_status != "not_reviewed":
        errors.append("an automatic report cannot claim human review")

    turns = {t.turn_id: t for t in ctx.turns}
    for i, f in enumerate(card.findings):
        where = f"findings[{i}]"
        t = turns.get(f.turn_id)
        if t is None:
            errors.append(f"{where}.turn_id {f.turn_id!r} not in transcript")
            continue
        if t.speaker != "student":
            errors.append(f"{where} quotes an interviewer turn; findings must cite the student")
        if t.canceled:
            errors.append(f"{where} cites a canceled turn")
        q = _norm(f.observed_quote)
        if not q or q not in _norm(t.text):
            errors.append(f"{where}.observed_quote is not verbatim in turn {f.turn_id}")
        if f.end_ms < f.start_ms:
            errors.append(f"{where} end_ms before start_ms")
        slack = 1000
        if f.start_ms < t.start_ms - slack or f.end_ms > t.end_ms + slack:
            errors.append(f"{where} timestamps fall outside turn {f.turn_id}")
        if f.end_ms > ctx.session_duration_ms + slack:
            errors.append(f"{where} timestamps fall outside the session")
        bad_refs = [r for r in f.document_refs if r not in ctx.snapshot_refs]
        if bad_refs:
            errors.append(f"{where}.document_refs outside the student's snapshot: {bad_refs}")
        for text in (f.explanation, f.next_action, f.clearer_phrasing_example or ""):
            for hit in _forbidden_hits(text):
                errors.append(f"{where} contains a forbidden claim ({hit})")

    for j, text in enumerate([*card.practice_tasks, *card.unknowns]):
        for hit in _forbidden_hits(text):
            errors.append(f"tasks/unknowns[{j}] contains a forbidden claim ({hit})")

    if errors:
        raise ScorecardError(errors)
    return card
