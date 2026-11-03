"""The "About you" form: five quick details and an optional full bio, saved as facts
the student typed (already confirmed: they are the source).

The form owns the fact fields below. Saving replaces every value of those fields,
including ones that came from elsewhere (the demo account's example facts), so a
figure can never be counted twice.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

SOURCE = "You entered"
_MONEY = re.compile(r"^\d{1,12}(\.\d{1,2})?$")
_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

# key -> (ref, fact field, max length)
TEXT = {
    "name": ("me-name", "student.full_name", 80),
    "home_country": ("me-country", "student.home_country", 60),
    "university": ("me-university", "program.university", 120),
    "course": ("me-course", "program.course", 120),
    "previous_degree": ("me-degree", "academic.history", 200),
    "english_test": ("me-english", "academic.english_test", 120),
    "accommodation": ("me-accommodation", "uk.accommodation_plan", 200),
}


def _cost(label: str):
    return lambda a: {"label": label, "amount": a, "currency": "GBP", "period": "annual"}


def _fund(label: str, kind: str, ref: str, **extra: Any):
    return lambda a: {
        "label": label,
        "kind": kind,
        "amount": a,
        "currency": "GBP",
        "holder": "family",
        "account_ref": ref,
        "available_by": None,
        **extra,
    }


# key -> (ref, fact field, value builder). Amounts are kept as decimal strings.
MONEY = {
    "family_income_npr": (
        "me-income",
        "funding.sponsor_income",
        lambda a: {"earner": "family", "annual_amount": a, "currency": "NPR"},
    ),
    "tuition_gbp": ("me-tuition", "funding.costs", _cost("Tuition fee")),
    "living_gbp": ("me-living", "funding.costs", _cost("Living costs")),
    "scholarship_gbp": (
        "me-scholarship",
        "funding.scholarships",
        lambda a: {
            "label": "Scholarship",
            "amount": a,
            "currency": "GBP",
            "already_deducted": False,
        },
    ),
    # Already paid, so available now.
    "deposit_gbp": (
        "me-deposit",
        "funding.funds",
        lambda a: {
            **_fund("Deposit already paid", "paid_deposit", "me-deposit")(a),
            "holder": "student",
            "available_by": datetime.now(UTC).date().isoformat(),
        },
    ),
    "savings_gbp": (
        "me-savings",
        "funding.funds",
        _fund("Family savings", "savings", "me-savings"),
    ),
    "loan_gbp": (
        "me-loan",
        "funding.funds",
        _fund("Education loan", "loan", "me-loan", sanction_confirmed=True),
    ),
}

START = ("me-start", "program.start_date")
OWNED_FIELDS = sorted(
    {f for _, f, _ in TEXT.values()} | {f for _, f, _ in MONEY.values()} | {START[1]}
)


class Details(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(None, max_length=200)
    home_country: str | None = Field(None, max_length=200)
    university: str | None = Field(None, max_length=200)
    course: str | None = Field(None, max_length=200)
    family_income_npr: str | None = Field(None, max_length=40)
    start_month: str | None = Field(None, max_length=10)
    previous_degree: str | None = Field(None, max_length=400)
    english_test: str | None = Field(None, max_length=400)
    accommodation: str | None = Field(None, max_length=400)
    tuition_gbp: str | None = Field(None, max_length=40)
    living_gbp: str | None = Field(None, max_length=40)
    scholarship_gbp: str | None = Field(None, max_length=40)
    deposit_gbp: str | None = Field(None, max_length=40)
    savings_gbp: str | None = Field(None, max_length=40)
    loan_gbp: str | None = Field(None, max_length=40)


def _clean(v: str | None) -> str:
    return " ".join((v or "").split())


def to_facts(d: Details) -> list[tuple[str, str, Any, str]]:
    """(ref, field, value, snippet) for every filled-in detail. Raises 422 on bad input."""
    out: list[tuple[str, str, Any, str]] = []
    for key, (ref, field, limit) in TEXT.items():
        v = _clean(getattr(d, key))
        if len(v) > limit:
            raise HTTPException(422, f"Keep {key.replace('_', ' ')} under {limit} characters.")
        if v:
            out.append((ref, field, v, v))
    for key, (ref, field, build) in MONEY.items():
        v = _clean(getattr(d, key)).replace(",", "")
        if not v:
            continue
        if not _MONEY.match(v) or float(v) <= 0:
            raise HTTPException(422, "Enter amounts as numbers, for example 18500.")
        amount = f"{float(v):.2f}"
        out.append((ref, field, build(amount), amount))
    month = _clean(d.start_month)
    if month:
        if not _MONTH.match(month):
            raise HTTPException(422, "Enter the start month as YYYY-MM.")
        out.append((START[0], START[1], f"{month}-01", month))
    return out


def from_facts(rows: list[dict[str, Any]]) -> dict[str, str]:
    """Current values for the form, from whatever facts the student has (typed by them,
    or the demo account's example facts). Rejected facts are left out."""
    rows = [r for r in rows if r["confirmation_status"] != "rejected"]
    rows.sort(key=lambda r: not r["ref"].startswith("me-"))  # the student's own first

    def first(field: str, pick=lambda v: True):
        return next(
            (r["value_json"] for r in rows if r["field_name"] == field and pick(r["value_json"])),
            None,
        )

    def amount(v: Any) -> str:
        if not isinstance(v, dict):
            return ""
        raw = str(v.get("amount") or v.get("annual_amount") or "")
        return raw[:-3] if raw.endswith(".00") else raw

    out = {key: str(first(field) or "") for key, (_, field, _) in TEXT.items()}
    label = lambda word: lambda v: isinstance(v, dict) and word in str(v.get("label", "")).lower()  # noqa: E731
    kind = lambda k: lambda v: isinstance(v, dict) and v.get("kind") == k  # noqa: E731
    income = first(
        "funding.sponsor_income", lambda v: isinstance(v, dict) and v.get("currency") == "NPR"
    )
    out["family_income_npr"] = amount(income)
    out["tuition_gbp"] = amount(first("funding.costs", label("tuition")))
    out["living_gbp"] = amount(first("funding.costs", label("living")))
    out["scholarship_gbp"] = amount(first("funding.scholarships"))
    out["deposit_gbp"] = amount(first("funding.funds", kind("paid_deposit")))
    out["savings_gbp"] = amount(first("funding.funds", kind("savings")))
    out["loan_gbp"] = amount(first("funding.funds", kind("loan")))
    start = str(first(START[1]) or "")
    out["start_month"] = start[:7] if re.match(r"^\d{4}-\d{2}", start) else ""
    return out


async def save(conn, student_id, d: Details) -> None:
    facts = to_facts(d)
    await conn.execute(
        "DELETE FROM extracted_facts WHERE student_id=%s AND field_name = ANY(%s)",
        (student_id, OWNED_FIELDS),
    )
    for ref, field, value, snippet in facts:
        await conn.execute(
            """INSERT INTO extracted_facts (student_id, ref, field_name, value_json,
                 source_label, source_snippet, confirmation_status)
               VALUES (%s,%s,%s,%s,%s,%s,'confirmed')""",
            (student_id, ref, field, Jsonb(value), SOURCE, snippet),
        )
    name = _clean(d.name)
    if name:
        await conn.execute(
            "UPDATE student_profiles SET display_name=%s WHERE id=%s", (name, student_id)
        )
