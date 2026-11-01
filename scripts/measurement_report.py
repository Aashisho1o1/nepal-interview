"""Measured latency, interruption, reliability and cost across real sessions.

    DATABASE_URL=... python scripts/measurement_report.py [--since 2026-11-01] [--fx 160]

Everything printed here comes from rows the agent and API recorded. Meters without a
verified price are listed as unpriced instead of estimated. Use this, not the
handoff's planning table, before setting paid allowances.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
from decimal import Decimal

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "agent"))
from interview_agent.runtime import percentile  # noqa: E402


def pct(values, p):
    v = percentile(values, p)
    return "—" if v is None else f"{v:,.0f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="1970-01-01")
    ap.add_argument("--fx", type=Decimal, default=None, help="NPR per USD for reporting")
    a = ap.parse_args()
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as c:
        sessions = c.execute(
            "SELECT * FROM interview_sessions WHERE created_at >= %s ORDER BY created_at",
            (a.since,),
        ).fetchall()
        ids = [s["id"] for s in sessions]
        events = c.execute(
            "SELECT session_id, kind, payload, at FROM session_events WHERE session_id = ANY(%s)",
            (ids,),
        ).fetchall()
        ledger = c.execute(
            "SELECT session_id, meter, quantity, unit, cost_usd_micros FROM usage_ledger "
            "WHERE session_id = ANY(%s)",
            (ids,),
        ).fetchall()

    if not sessions:
        print("No sessions recorded yet.")
        return

    by_kind: dict[str, list] = {}
    for e in events:
        by_kind.setdefault(e["kind"], []).append(e)
    response = [e["payload"]["response_ms"] for e in by_kind.get("latency", [])]
    stops = [e["payload"]["stop_signal_ms"] for e in by_kind.get("interruption", [])]
    startup = [
        (s["media_ready_at"] - s["created_at"]).total_seconds() * 1000
        for s in sessions
        if s["media_ready_at"]
    ]
    started = [s for s in sessions if s["media_ready_at"]]
    fallbacks = [s for s in sessions if s["fallback_at"]]
    failed = [s for s in sessions if s["status"] == "failed"]
    unclosed = [
        s for s in sessions if s["status"] in ("completed", "failed") and not s["room_closed_at"]
    ]
    teardowns = [
        e["payload"].get("teardown", [])
        for e in by_kind.get("state", [])
        if "teardown" in e["payload"]
    ]
    bad_steps = [step for td in teardowns for step in td if step[1] != "ok"]

    print(f"# Measurement report ({len(sessions)} sessions since {a.since})\n")
    print("## Reliability")
    print(f"- started (media ready): {len(started)} / {len(sessions)}")
    print(f"- failed startups (refunded): {len(failed)}")
    print(f"- avatar -> voice fallbacks: {len(fallbacks)}")
    print(f"- ended sessions with room not confirmed closed: {len(unclosed)}")
    print(f"- teardown steps not ok: {len(bad_steps)} {bad_steps[:5]}")
    reasons = statistics.multimode([s["end_reason"] for s in sessions if s["end_reason"]] or ["—"])
    print(f"- most common end reason: {reasons}")
    print("\n## Latency (ms; agent-side signals)")
    print(
        f"- request -> media ready: p50 {pct(startup, 0.5)}, p95 {pct(startup, 0.95)} (n={len(startup)})"
    )
    print(
        f"- student stops -> interviewer speaking: p50 {pct(response, 0.5)}, p95 {pct(response, 0.95)} (n={len(response)})"
    )
    print(
        f"- interruption -> interviewer stop signal: p50 {pct(stops, 0.5)}, p95 {pct(stops, 0.95)} (n={len(stops)})"
    )
    print("  Audible latency also includes network and playout; verify on devices.")

    print("\n## Provider usage and cost")
    per_session: dict = {}
    unpriced: dict[str, Decimal] = {}
    totals: dict[str, Decimal] = {}
    for row in ledger:
        totals[row["meter"]] = totals.get(row["meter"], Decimal(0)) + row["quantity"]
        if row["cost_usd_micros"] is None:
            unpriced[row["meter"]] = unpriced.get(row["meter"], Decimal(0)) + row["quantity"]
        else:
            per_session[row["session_id"]] = (
                per_session.get(row["session_id"], 0) + row["cost_usd_micros"]
            )
    for m, q in sorted(totals.items()):
        print(f"- {m}: {q:,.3f}")
    costs = sorted(v / 1_000_000 for v in per_session.values())
    if costs:
        line = (
            f"- priced cost per session (USD): p50 {percentile(costs, 0.5):.4f}, "
            f"p90 {percentile(costs, 0.9):.4f}, max {max(costs):.4f}"
        )
        if a.fx:
            line += f"; p90 NPR {Decimal(str(percentile(costs, 0.9))) * a.fx:,.2f} at {a.fx}/USD"
        print(line)
    if unpriced:
        print(f"- UNPRICED meters (excluded from cost above): {', '.join(sorted(unpriced))}")


if __name__ == "__main__":
    main()
