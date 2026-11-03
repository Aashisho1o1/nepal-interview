"""Per-session dynamic variables for hosted interviewer agents (ElevenLabs, and later
LiveAvatar's ElevenLabs plugin).

Only confirmed facts are used, values are short plain text, and every figure in the
funding summary is computed here in code: the agent never does currency arithmetic.
Values are data, not instructions; the agent prompt must say so.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from .facts import first_value
from .funding import FundingSummary, describe_for_interviewer

# LiveAvatar's documented limits (50 variables, keys <= 64, values <= 1000 chars);
# ElevenLabs accepts the same shape. Truncate defensively for both.
MAX_VARS = 50
MAX_KEY = 64
MAX_VALUE = 1000

NOT_PROVIDED = "not provided"


def _text(v: Any) -> str:
    if v is None or v == "":
        return NOT_PROVIDED
    if isinstance(v, dict):
        return "; ".join(f"{k}: {x}" for k, x in v.items() if x not in (None, ""))
    if isinstance(v, (list, tuple)):
        return "; ".join(_text(x) for x in v)
    return " ".join(str(v).split())


def _intake(v: Any) -> str:
    try:
        return date.fromisoformat(str(v)).strftime("%B %Y")
    except ValueError:
        return _text(v)


def _yearly_income(facts: dict[str, Any]) -> str:
    v = first_value(facts, "funding.sponsor_income")
    if not isinstance(v, dict) or not v.get("annual_amount"):
        return NOT_PROVIDED
    try:
        amount = f"{float(str(v['annual_amount']).replace(',', '')):,.0f}"
    except ValueError:
        return NOT_PROVIDED
    return f"{str(v.get('currency') or '').upper()} {amount} per year".strip()


def build_dynamic_variables(
    *,
    session_id: str,
    student_name: str,
    facts: dict[str, Any],
    funding: FundingSummary | None,
    practice_seconds: int,
    question_count: int = 3,
) -> dict[str, str]:
    minutes = max(1, round(practice_seconds / 60))
    out = {
        "session_id": session_id,
        "student_first_name": (student_name or "").split(" ")[0] or "there",
        "university": _text(first_value(facts, "program.university")),
        "course": _text(first_value(facts, "program.course")),
        "intake": _intake(first_value(facts, "program.start_date")),
        # Pre-CAS happens before a CAS is issued; never ask the student for one.
        "home_country": _text(first_value(facts, "student.home_country")),
        # Reported as given; it is not savings and is never used in funding arithmetic.
        "family_income": _yearly_income(facts),
        "cas_status": _text(first_value(facts, "uk.cas_status", "not yet issued")),
        "funding_summary": (
            " ".join(describe_for_interviewer(funding).split()) if funding else NOT_PROVIDED
        ),
        "academic_summary": _text(first_value(facts, "academic.history")),
        "accommodation_plan": _text(first_value(facts, "uk.accommodation_plan")),
        "english_test": _text(first_value(facts, "academic.english_test")),
        "interview_format": f"{question_count} questions, {minutes} minutes",
    }
    clean: dict[str, str] = {}
    for k, v in list(out.items())[:MAX_VARS]:
        clean[k[:MAX_KEY]] = v[:MAX_VALUE]
    return clean
