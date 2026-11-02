"""Side-by-side comparison of interview providers from real sessions.

    DATABASE_URL=... python scripts/provider_comparison.py [--since 2026-11-01]

Same yardstick for every provider: did it start, how long until the student could
talk, did it drop, what did students say (ratings), and what did it cost us. Turn
latency is only available for our own LiveKit pipeline (agent-measured); for
embeds/hosted vendors, the "reply speed" rating is the comparable signal.
"""

from __future__ import annotations

import argparse
import os
import statistics
from collections import Counter, defaultdict

import psycopg
from psycopg.rows import dict_row

DROPS = ("reconciled_stale", "disconnected", "settled_elsewhere", "avatar_lost", "page_exit")


def med(xs):
    xs = [x for x in xs if x is not None]
    return f"{statistics.median(xs):,.0f}" if xs else "—"


def pct(n, d):
    return f"{100 * n / d:.0f}%" if d else "—"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="1970-01-01")
    a = ap.parse_args()
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as c:
        sessions = c.execute(
            "SELECT * FROM interview_sessions WHERE created_at >= %s", (a.since,)
        ).fetchall()
        ids = [s["id"] for s in sessions]
        events = c.execute(
            "SELECT session_id, kind, source, payload FROM session_events WHERE session_id = ANY(%s)",
            (ids,),
        ).fetchall()
        ratings = c.execute(
            "SELECT * FROM session_ratings WHERE session_id = ANY(%s)", (ids,)
        ).fetchall()
        costs = c.execute(
            "SELECT session_id, SUM(cost_usd_micros) AS micros FROM usage_ledger "
            "WHERE session_id = ANY(%s) GROUP BY session_id",
            (ids,),
        ).fetchall()

    prov_of = {s["id"]: s["provider_id"] for s in sessions}
    by: dict[str, dict] = defaultdict(lambda: defaultdict(list))
    for s in sessions:
        p = by[s["provider_id"]]
        p["sessions"].append(s)
        if s["media_ready_at"]:
            p["server_ready_ms"].append(
                (s["media_ready_at"] - s["created_at"]).total_seconds() * 1000
            )
    for e in events:
        p = by[prov_of[e["session_id"]]]
        pl = e["payload"] or {}
        if e["kind"] == "media_ready" and e["source"] == "client":
            p["client_ready_ms"].append(pl.get("ready_ms"))
            p["load_ms"].append(pl.get("load_ms"))
        if e["kind"] == "latency":
            p["response_ms"].append(pl.get("response_ms"))
        if e["kind"] == "metric" and "vendor_message" in pl:
            p["vendor_messages"].append(pl["vendor_message"])
    for r in ratings:
        by[prov_of[r["session_id"]]]["ratings"].append(r)
    for row in costs:
        if row["micros"] is not None:
            by[prov_of[row["session_id"]]]["cost"].append(row["micros"] / 1e6)

    print(f"# Provider comparison (since {a.since})\n")
    print(
        "| Provider | Sessions | Started | Failed start | Dropped | Ready (ms, p50) | "
        "Reply latency (ms, p50) | Realism (1-5) | Reply speed felt OK | A/V OK | Would use again | "
        "Billed min | Our cost/session (milli-USD, p50) |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for pid, p in sorted(by.items()):
        ss = p["sessions"]
        n = len(ss)
        started = sum(1 for s in ss if s["media_ready_at"])
        failed = sum(1 for s in ss if s["status"] == "failed")
        dropped = sum(1 for s in ss if (s["end_reason"] or "") in DROPS)
        rs = p["ratings"]
        speed_ok = sum(1 for r in rs if r["reply_speed"] in ("instant", "slight_pause"))
        billed = sum(
            (s["charged_premium_seconds"] or 0) + (s["charged_basic_seconds"] or 0) for s in ss
        )
        ready = p["client_ready_ms"] or p["server_ready_ms"]
        realism = f"{statistics.mean(r['realism'] for r in rs):.1f} (n={len(rs)})" if rs else "—"
        cost = med([x * 1000 for x in p["cost"]]) if p["cost"] else "— (vendor bill)"
        cells = [
            pid,
            n,
            pct(started, n),
            failed,
            dropped,
            med(ready),
            med(p["response_ms"]),
            realism,
            pct(speed_ok, len(rs)),
            pct(sum(r["audio_video_ok"] for r in rs), len(rs)),
            pct(sum(r["would_use_again"] for r in rs), len(rs)),
            f"{billed / 60:.1f}",
            cost,
        ]
        print("| " + " | ".join(str(x) for x in cells) + " |")
    print("\nOur cost column covers our own pipeline only; vendors that bill us")
    print("directly (embeds, Tavus) must be reconciled from their dashboards.\n")
    for pid, p in sorted(by.items()):
        comments = [r["comment"] for r in p["ratings"] if r["comment"]]
        reasons = Counter(s["end_reason"] for s in p["sessions"])
        print(f"## {pid}")
        print(f"- end reasons: {dict(reasons)}")
        if p["vendor_messages"]:
            print(f"- vendor events seen: {sorted(set(p['vendor_messages']))}")
        for cmt in comments[:10]:
            print(f"- “{cmt}”")
        print()


if __name__ == "__main__":
    main()
