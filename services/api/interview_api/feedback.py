"""Post-session grading job. Feedback is rendered only after validation."""

from __future__ import annotations

import asyncio
import logging
import math

from psycopg.types.json import Jsonb

from interview_core.funding import empty_funding, funding_or_none
from interview_core.grading import OpenAIChatGrader, RulesGrader, grade_with_repair, make_context
from interview_core.scorecard import ScorecardError, TurnRecord

from .config import Settings

log = logging.getLogger("interview_api.feedback")


def make_grader(s: Settings):
    if s.grader == "openai":
        if not (s.openai_api_key and s.grader_model):
            raise RuntimeError("GRADER=openai needs OPENAI_API_KEY and GRADER_MODEL")
        return OpenAIChatGrader(s.openai_api_key, s.grader_model)
    return RulesGrader()


async def grade_session(pool, s: Settings, session_id) -> dict:
    async with pool.connection() as conn:
        async with conn.transaction():
            cur = await conn.execute(
                "SELECT status FROM feedback_reports WHERE session_id=%s FOR UPDATE", (session_id,)
            )
            row = await cur.fetchone()
            if row and row["status"] == "ready":
                return {"status": "ready", "skipped": True}
            await conn.execute(
                """INSERT INTO feedback_reports (session_id, status) VALUES (%s,'pending')
                   ON CONFLICT (session_id) DO UPDATE SET status='pending', updated_at=now()""",
                (session_id,),
            )
        cur = await conn.execute(
            """SELECT s.*, p.confirmed_facts_json FROM interview_sessions s
               JOIN profile_snapshots p ON p.id = s.snapshot_id WHERE s.id=%s""",
            (session_id,),
        )
        sess = await cur.fetchone()
        cur = await conn.execute(
            "SELECT * FROM interview_turns WHERE session_id=%s ORDER BY sequence, start_ms",
            (session_id,),
        )
        turns = [
            TurnRecord(
                t["turn_id"], t["speaker"], t["text"], t["start_ms"], t["end_ms"], t["canceled"]
            )
            for t in await cur.fetchall()
        ]

    snapshot = sess["confirmed_facts_json"]
    funding = funding_or_none(snapshot) or empty_funding()
    end = sess["ended_at"] or sess["practice_ends_at"]
    duration_ms = (
        math.ceil((end - sess["media_ready_at"]).total_seconds() * 1000)
        if sess["media_ready_at"] and end
        else 0
    )
    ctx = make_context(str(session_id), sess["track"], snapshot, turns, duration_ms)
    grader_name = s.grader
    try:
        grader = make_grader(s)
        grader_name = grader.name
        card, _raw, attempts = await asyncio.to_thread(
            grade_with_repair, grader, ctx, snapshot, funding
        )
        status, payload, err = "ready", card.model_dump(), None
    except ScorecardError as e:
        status, payload, err, attempts = "failed", None, "; ".join(e.errors[:10]), 2
    except Exception as e:  # provider error: recoverable failure, queued for review
        log.exception("grading failed")
        status, payload, err, attempts = "failed", None, f"grader error: {e!r}"[:500], 1

    async with pool.connection() as conn:
        await conn.execute(
            """UPDATE feedback_reports SET status=%s, grader=%s, schema_version=%s,
                   rubric_version=%s, attempts=%s, validated_json=%s, last_error=%s, updated_at=now()
               WHERE session_id=%s""",
            (
                status,
                grader_name,
                payload and payload["schema_version"],
                payload and payload["rubric_version"],
                attempts,
                Jsonb(payload) if payload else None,
                err,
                session_id,
            ),
        )
    return {"status": status, "error": err}
