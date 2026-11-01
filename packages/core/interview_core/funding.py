"""Deterministic funding arithmetic over confirmed facts.

The language model never does currency maths. It receives this summary, which is
computed with Decimal from confirmed facts only, and the questions it raises.

Rules:
* First-year requirement = annual costs + one-time costs, in the cost currency.
* Scholarships are subtracted only if the cost figure did not already deduct them.
* Funds are counted once per account reference (joint balances are not doubled).
* A fund in another currency is converted only with a confirmed FX rate fact;
  otherwise it is excluded from the total and flagged.
* Sponsor income is reported separately. Annual income is not available savings and
  is never subtracted from the requirement.
* A fund with no confirmed availability date, or one available after the programme
  start date, is counted in the identified total but flagged for an availability
  question.
* The output never says the funds are "sufficient" for a visa. "Covered on paper"
  means only that the confirmed arithmetic gap is zero.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from .facts import facts_by_field, first_value

CENT = Decimal("0.01")


class FundingInputError(ValueError):
    pass


def _amount(raw: Any, where: str) -> Decimal:
    if isinstance(raw, bool) or raw is None:
        raise FundingInputError(f"{where}: amount missing")
    try:
        d = Decimal(str(raw).replace(",", "").strip())
    except InvalidOperation as e:
        raise FundingInputError(f"{where}: amount {raw!r} is not a number") from e
    if d < 0:
        raise FundingInputError(f"{where}: amount is negative")
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def _minor(d: Decimal) -> int:
    return int((d.quantize(CENT, rounding=ROUND_HALF_UP) * 100).to_integral_value())


def _date(raw: Any) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


@dataclass
class Line:
    ref: str
    label: str
    amount_minor: int
    currency: str
    counted: bool
    note: str = ""


@dataclass
class FundingSummary:
    currency: str
    required_minor: int
    scholarships_deducted_minor: int
    net_required_minor: int
    identified_funds_minor: int
    available_by_start_minor: int
    gap_minor: int
    surplus_minor: int
    status: str  # covered_on_paper | gap | incomplete
    cost_lines: list[Line] = field(default_factory=list)
    scholarship_lines: list[Line] = field(default_factory=list)
    fund_lines: list[Line] = field(default_factory=list)
    sponsor_income: list[dict[str, Any]] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _fmt(minor: int, currency: str) -> str:
    return f"{currency} {Decimal(minor) / 100:,.2f}"


def compute_funding(snapshot: dict[str, Any]) -> FundingSummary:
    by_field = facts_by_field(snapshot)
    costs = by_field.get("funding.costs", [])
    if not costs:
        raise FundingInputError("no confirmed cost facts")

    currencies = {str(c["value"].get("currency", "")).upper() for c in costs}
    if len(currencies) != 1 or "" in currencies:
        raise FundingInputError("cost facts must share exactly one currency")
    cur = currencies.pop()

    flags: list[str] = []
    incomplete = False
    questions: list[str] = []
    refs: list[str] = []

    fx: dict[tuple[str, str], tuple[Decimal, str]] = {}
    for f in by_field.get("funding.fx_rates", []):
        v = f["value"]
        rate = _amount(v.get("rate"), f["ref"])
        if rate == 0:
            continue
        key = (str(v.get("from", "")).upper(), str(v.get("to", "")).upper())
        fx[key] = (Decimal(str(v.get("rate")).replace(",", "")), f["ref"])

    def convert(amount: Decimal, from_cur: str) -> tuple[Decimal | None, str | None]:
        if from_cur == cur:
            return amount, None
        if (from_cur, cur) in fx:
            rate, ref = fx[(from_cur, cur)]
            return (amount * rate).quantize(CENT, rounding=ROUND_HALF_UP), ref
        return None, None

    # Costs
    required = Decimal(0)
    cost_lines: list[Line] = []
    for c in costs:
        v = c["value"]
        amt = _amount(v.get("amount"), c["ref"])
        period = v.get("period", "annual")
        if period not in ("annual", "one_time"):
            flags.append(f"Cost '{v.get('label')}' has period {period!r}; not counted.")
            cost_lines.append(Line(c["ref"], str(v.get("label")), _minor(amt), cur, False))
            continue
        required += amt
        refs.append(c["ref"])
        cost_lines.append(Line(c["ref"], str(v.get("label")), _minor(amt), cur, True, period))

    # Scholarships
    deducted = Decimal(0)
    sch_lines: list[Line] = []
    for s in by_field.get("funding.scholarships", []):
        v = s["value"]
        amt = _amount(v.get("amount"), s["ref"])
        s_cur = str(v.get("currency", "")).upper()
        conv, fx_ref = convert(amt, s_cur)
        if v.get("already_deducted"):
            sch_lines.append(
                Line(
                    s["ref"],
                    str(v.get("label")),
                    _minor(amt),
                    s_cur,
                    False,
                    "already deducted in the cost figure; not subtracted again",
                )
            )
            continue
        if conv is None:
            incomplete = True
            flags.append(f"Scholarship '{v.get('label')}' is in {s_cur} with no confirmed rate.")
            sch_lines.append(
                Line(
                    s["ref"],
                    str(v.get("label")),
                    _minor(amt),
                    s_cur,
                    False,
                    "needs confirmed exchange rate",
                )
            )
            continue
        deducted += conv
        refs.append(s["ref"])
        if fx_ref:
            refs.append(fx_ref)
        sch_lines.append(Line(s["ref"], str(v.get("label")), _minor(conv), cur, True))

    net_required = max(required - deducted, Decimal(0))

    # Funds
    start = _date(first_value(snapshot, "program.start_date"))
    seen_accounts: dict[str, str] = {}
    identified = Decimal(0)
    on_time = Decimal(0)
    fund_lines: list[Line] = []
    for f in by_field.get("funding.funds", []):
        v = f["value"]
        label = str(v.get("label") or v.get("kind") or "fund")
        amt = _amount(v.get("amount"), f["ref"])
        f_cur = str(v.get("currency", "")).upper()
        acct = str(v.get("account_ref") or "").strip()
        if acct and acct in seen_accounts:
            flags.append(
                f"'{label}' uses the same account reference as '{seen_accounts[acct]}'; "
                "counted once."
            )
            fund_lines.append(
                Line(f["ref"], label, _minor(amt), f_cur, False, "duplicate account reference")
            )
            continue
        conv, fx_ref = convert(amt, f_cur)
        if conv is None:
            incomplete = True
            flags.append(f"'{label}' is in {f_cur} with no confirmed exchange rate; not counted.")
            fund_lines.append(
                Line(f["ref"], label, _minor(amt), f_cur, False, "needs confirmed exchange rate")
            )
            continue
        if acct:
            seen_accounts[acct] = label
        identified += conv
        refs.append(f["ref"])
        if fx_ref:
            refs.append(fx_ref)
        avail = _date(v.get("available_by"))
        note = ""
        if avail is None:
            note = "availability date not confirmed"
            questions.append(f"How and when will the {label.lower()} be available when needed?")
        elif start and avail > start:
            note = f"available {avail.isoformat()}, after programme start {start.isoformat()}"
            questions.append(
                f"The {label.lower()} is shown as available after your programme starts. "
                "How will you cover costs until then?"
            )
        else:
            on_time += conv
        if v.get("kind") == "loan" and not v.get("sanction_confirmed", False):
            questions.append(f"Has the {label.lower()} been sanctioned, and for what amount?")
        fund_lines.append(Line(f["ref"], label, _minor(conv), cur, True, note))

    sponsor = []
    for s in by_field.get("funding.sponsor_income", []):
        v = s["value"]
        sponsor.append(
            {
                "ref": s["ref"],
                "earner": v.get("earner"),
                "annual_amount_minor": _minor(_amount(v.get("annual_amount"), s["ref"])),
                "currency": str(v.get("currency", "")).upper(),
                "note": "Annual income is reported separately and is not subtracted from "
                "the requirement.",
            }
        )
    if sponsor:
        questions.append("How does your sponsor's income relate to the funds you will use?")

    gap = max(net_required - identified, Decimal(0))
    surplus = max(identified - net_required, Decimal(0))
    if incomplete:
        status = "incomplete"
    elif gap > 0:
        status = "gap"
        questions.insert(0, f"How will you cover the remaining {_fmt(_minor(gap), cur)}?")
    else:
        status = "covered_on_paper"

    # Deduplicate while keeping order.
    questions = list(dict.fromkeys(questions))
    return FundingSummary(
        currency=cur,
        required_minor=_minor(required),
        scholarships_deducted_minor=_minor(deducted),
        net_required_minor=_minor(net_required),
        identified_funds_minor=_minor(identified),
        available_by_start_minor=_minor(on_time),
        gap_minor=_minor(gap),
        surplus_minor=_minor(surplus),
        status=status,
        cost_lines=cost_lines,
        scholarship_lines=sch_lines,
        fund_lines=fund_lines,
        sponsor_income=sponsor,
        flags=flags,
        questions=questions,
        refs=list(dict.fromkeys(refs)),
    )


def describe_for_interviewer(s: FundingSummary) -> str:
    """Plain text summary for the prompt. Figures are pre-computed; no maths left."""
    lines = [
        f"First-year costs: {_fmt(s.required_minor, s.currency)}.",
        f"Scholarships subtracted: {_fmt(s.scholarships_deducted_minor, s.currency)}.",
        f"Amount to fund: {_fmt(s.net_required_minor, s.currency)}.",
        f"Funds identified in confirmed facts: {_fmt(s.identified_funds_minor, s.currency)}.",
        f"Arithmetic gap: {_fmt(s.gap_minor, s.currency)} (status: {s.status}).",
    ]
    for ln in s.fund_lines:
        if ln.counted:
            extra = f" ({ln.note})" if ln.note else ""
            lines.append(f"- {ln.label}: {_fmt(ln.amount_minor, ln.currency)}{extra}.")
    for sp in s.sponsor_income:
        lines.append(
            f"- Sponsor income ({sp['earner']}): "
            f"{_fmt(sp['annual_amount_minor'], sp['currency'])} per year, a separate fact."
        )
    for fl in s.flags:
        lines.append(f"- Note: {fl}")
    return "\n".join(lines)
