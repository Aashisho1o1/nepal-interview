"""Synthetic student for development and tests. Every value here is invented.

A UK pre-CAS applicant: first-year costs GBP 30,506.00 (tuition 18,500 + nine
months' living costs 12,006), less a GBP 2,500 scholarship, leaves GBP 28,006.00 to
fund. Identified funds: a paid tuition deposit of 5,000, family savings of 15,000
and a sanctioned loan of 8,500 (no availability date yet), GBP 28,500 in total, so
the arithmetic gap is zero on paper. The sponsor's NPR 18 lakh income is a separate
fact. No CAS exists yet: pre-CAS happens before it is issued.

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
        "Example University",
        "Synthetic offer letter, page 1",
        "Institution: Example University (synthetic)",
    ),
    (
        "program-course",
        "program.course",
        "MSc Data Science",
        "Synthetic offer letter, page 1",
        "Programme: MSc Data Science (full time)",
    ),
    (
        "program-level",
        "program.level",
        "Master's",
        "Synthetic offer letter, page 1",
        "Level: Postgraduate taught (Master's)",
    ),
    (
        "program-start",
        "program.start_date",
        "2027-09-20",
        "Synthetic offer letter, page 1",
        "Start date: 20 September 2027",
    ),
    (
        "offer-conditions",
        "uk.offer_conditions",
        "Unconditional offer; CAS to be issued after the pre-CAS interview and deposit",
        "Synthetic offer letter, page 2",
        "Your offer is unconditional. A CAS will be issued after a successful credibility "
        "interview and receipt of the tuition deposit.",
    ),
    (
        "cost-tuition",
        "funding.costs",
        {"label": "Tuition fee", "amount": "18500.00", "currency": "GBP", "period": "annual"},
        "Synthetic offer letter, page 1",
        "Tuition fee: £18,500 per year",
    ),
    (
        "cost-living",
        "funding.costs",
        {
            "label": "Living costs (9 months, outside London)",
            "amount": "12006.00",
            "currency": "GBP",
            "period": "annual",
        },
        "Synthetic university cost sheet",
        "Maintenance requirement: £1,334 x 9 months = £12,006",
    ),
    (
        "scholarship-merit",
        "funding.scholarships",
        {
            "label": "International merit scholarship",
            "amount": "2500.00",
            "currency": "GBP",
            "already_deducted": False,
        },
        "Synthetic scholarship letter",
        "International merit scholarship of £2,500 for year one",
    ),
    (
        "fund-deposit",
        "funding.funds",
        {
            "label": "Tuition deposit paid",
            "kind": "paid_deposit",
            "amount": "5000.00",
            "currency": "GBP",
            "holder": "student",
            "account_ref": "SYN-DEP-001",
            "available_by": "2026-10-15",
        },
        "Synthetic deposit receipt",
        "Deposit received: £5,000.00 on 15 October 2026",
    ),
    (
        "fund-savings",
        "funding.funds",
        {
            "label": "Family savings",
            "kind": "savings",
            "amount": "15000.00",
            "currency": "GBP",
            "holder": "father",
            "account_ref": "SYN-SAV-001",
            "available_by": "2027-06-30",
        },
        "Synthetic bank letter",
        "Balance equivalent: GBP 15,000 as of 2026-10-15",
    ),
    (
        "fund-loan",
        "funding.funds",
        {
            "label": "Education loan",
            "kind": "loan",
            "amount": "8500.00",
            "currency": "GBP",
            "holder": "father",
            "account_ref": "SYN-LOAN-001",
            "available_by": None,
            "sanction_confirmed": True,
        },
        "Synthetic loan sanction letter",
        "Sanctioned education loan: GBP 8,500 equivalent",
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
        "Bachelor's in Computer Science and IT (BSc CSIT), completed 2024",
        "Synthetic transcript",
        "BSc CSIT, Tribhuvan University, 2020-2024",
    ),
    (
        "academic-gap",
        "academic.gap_explanation",
        "Worked as a junior software developer from 2024 to 2026",
        "Synthetic employment letter",
        "Employed as Junior Developer, Jan 2025 - present",
    ),
    (
        "english-test",
        "academic.english_test",
        "IELTS Academic 6.5 overall, no band below 6.0",
        "Synthetic IELTS test report form",
        "Overall band score: 6.5 (L 6.5, R 6.0, W 6.0, S 7.0)",
    ),
    (
        "accommodation",
        "uk.accommodation_plan",
        "University halls; application submitted, offer pending",
        "Synthetic accommodation application email",
        "Thank you for applying for university accommodation. Your application is being processed.",
    ),
]

# Package entitlements for the synthetic account, in seconds. These are test
# allowances, not paid package sizes: those wait for measured costs.
SYNTHETIC_ENTITLEMENTS = {"premium_seconds": 15 * 60, "basic_seconds": 15 * 60}
