"""Synthetic student data for milestone one. Every value here is invented.

The figures reproduce the handoff's worked example: annual cost USD 40,000 less a
USD 12,000 scholarship leaves USD 28,000, covered on paper by USD 20,000 savings and
a USD 8,000 loan. The sponsor's NPR 18 lakh income is a separate fact.

`plans.after_study` is deliberately absent: the product must not supply a student's
plans or home ties.
"""

from __future__ import annotations

from typing import Any

SYNTHETIC_STUDENT_EMAIL = "student@synthetic.test"
SYNTHETIC_STUDENT_NAME = "Asha Synthetic"

# (ref, field, value, source_label, source_snippet)
SYNTHETIC_FACTS: list[tuple[str, str, Any, str, str]] = [
    (
        "student-name",
        "student.full_name",
        SYNTHETIC_STUDENT_NAME,
        "Synthetic profile form",
        "Name: Asha Synthetic",
    ),
    (
        "program-university",
        "program.university",
        "Example State University",
        "Synthetic I-20, page 1",
        "School: Example State University (synthetic)",
    ),
    (
        "program-course",
        "program.course",
        "Master of Science in Data Science",
        "Synthetic I-20, page 1",
        "Program: Master of Science, Data Science",
    ),
    (
        "program-level",
        "program.level",
        "Master's",
        "Synthetic I-20, page 1",
        "Education level: Master's",
    ),
    (
        "program-start",
        "program.start_date",
        "2027-08-23",
        "Synthetic I-20, page 1",
        "Program start date: 23 Aug 2027",
    ),
    (
        "cost-tuition",
        "funding.costs",
        {"label": "Tuition and fees", "amount": "28000.00", "currency": "USD", "period": "annual"},
        "Synthetic I-20, page 1",
        "Tuition and fees: $28,000 (9 months)",
    ),
    (
        "cost-living",
        "funding.costs",
        {"label": "Living expenses", "amount": "12000.00", "currency": "USD", "period": "annual"},
        "Synthetic I-20, page 1",
        "Living expenses: $12,000 (9 months)",
    ),
    (
        "scholarship-merit",
        "funding.scholarships",
        {
            "label": "Merit scholarship",
            "amount": "12000.00",
            "currency": "USD",
            "already_deducted": False,
        },
        "Synthetic award letter",
        "Merit scholarship of $12,000 per year",
    ),
    (
        "fund-savings",
        "funding.funds",
        {
            "label": "Family savings",
            "kind": "savings",
            "amount": "20000.00",
            "currency": "USD",
            "holder": "father",
            "account_ref": "SYN-SAV-001",
            "available_by": "2027-06-30",
        },
        "Synthetic bank letter",
        "Balance equivalent: USD 20,000 as of 2026-10-15",
    ),
    (
        "fund-loan",
        "funding.funds",
        {
            "label": "Education loan",
            "kind": "loan",
            "amount": "8000.00",
            "currency": "USD",
            "holder": "father",
            "account_ref": "SYN-LOAN-001",
            "available_by": None,
            "sanction_confirmed": True,
        },
        "Synthetic loan sanction letter",
        "Sanctioned education loan: USD 8,000 equivalent",
    ),
    (
        "sponsor-income",
        "funding.sponsor_income",
        {"earner": "father", "annual_amount": "1800000.00", "currency": "NPR"},
        "Synthetic income certificate",
        "Annual income: NPR 18,00,000",
    ),
    (
        "academic-bachelors",
        "academic.history",
        "Bachelor's in Computer Science, completed 2024",
        "Synthetic transcript",
        "B.Sc. Computer Science, 2020-2024",
    ),
    (
        "academic-gap",
        "academic.gap_explanation",
        "Worked as a junior software developer from 2024 to 2026",
        "Synthetic employment letter",
        "Employed as Junior Developer, Jan 2025 - present",
    ),
]

# Package entitlements for the synthetic account, in seconds. These are test
# allowances, not paid package sizes: those wait for measured costs.
SYNTHETIC_ENTITLEMENTS = {"premium_seconds": 15 * 60, "basic_seconds": 15 * 60}
