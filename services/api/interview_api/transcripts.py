"""Transcript and vendor-usage ingestion.

Hosted interviewers send their transcript after the call (ElevenLabs post-call
webhook; LiveAvatar transcript endpoint). Whatever the source, the turns land here,
idempotently, and grading is queued once the session is settled.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from interview_core.pricing import PriceTable

from .config import Settings
from .feedback import grade_session


class Turn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    turn_id: str = Field(max_length=80)
    sequence: int
    speaker: Literal["student", "interviewer"]
    text: str = Field(max_length=8000)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    canceled: bool = False
    metrics: dict = Field(default_factory=dict)


class UsageEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_event_id: str = Field(max_length=200)
    provider: str = Field(max_length=40)
    meter: str = Field(max_length=120)
    quantity: Decimal = Field(ge=0)
    unit: str = Field(max_length=20)
    # Cumulative meters are re-sent with the running total so a crash loses little;
    # the stored quantity only ever increases.
    cumulative: bool = False


async def store_turns(conn, session_id, turns: list[Turn]) -> int:
    """Upsert turns by (session, turn_id). Re-sending the same turns is harmless."""
    for t in turns:
        await conn.execute(
            """INSERT INTO interview_turns (session_id, turn_id, sequence, speaker, text,
                 start_ms, end_ms, canceled, metrics) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (session_id, turn_id) DO UPDATE SET text=EXCLUDED.text,
                 end_ms=EXCLUDED.end_ms, canceled=EXCLUDED.canceled, metrics=EXCLUDED.metrics""",
            (
                session_id,
                t.turn_id,
                t.sequence,
                t.speaker,
                t.text,
                t.start_ms,
                max(t.end_ms, t.start_ms),
                t.canceled,
                Jsonb(t.metrics),
            ),
        )
    return len(turns)


async def record_usage(conn, prices: PriceTable, session_id, events: list[UsageEvent]) -> dict:
    """Append vendor usage to the ledger, priced from the versioned table when a price
    is known. Duplicate event ids are ignored; cumulative meters keep the maximum."""
    inserted = 0
    for u in events:
        cost = prices.cost_usd_micros(u.meter, u.quantity)
        conflict = (
            "DO UPDATE SET quantity=EXCLUDED.quantity, cost_usd_micros=EXCLUDED.cost_usd_micros, "
            "price_version=EXCLUDED.price_version WHERE usage_ledger.quantity < EXCLUDED.quantity"
            if u.cumulative
            else "DO NOTHING"
        )
        cur = await conn.execute(
            "INSERT INTO usage_ledger (session_id, provider_event_id, provider, meter, "
            "quantity, unit, cost_usd_micros, price_version) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
            f"ON CONFLICT (session_id, provider_event_id) {conflict} RETURNING id",
            (
                session_id,
                u.provider_event_id,
                u.provider,
                u.meter,
                u.quantity,
                u.unit,
                cost,
                prices.version if cost is not None else None,
            ),
        )
        inserted += 1 if await cur.fetchone() else 0
    return {"inserted": inserted, "duplicates": len(events) - inserted}


async def ingest_transcript(pool, s: Settings, session_id, turns: list[Turn]) -> dict[str, Any]:
    """Store a vendor's transcript and grade it if the session has already settled.
    If it has not (transcript arrived first), the reconciler grades it after settlement."""
    async with pool.connection() as conn, conn.transaction():
        cur = await conn.execute("SELECT status FROM interview_sessions WHERE id=%s", (session_id,))
        sess = await cur.fetchone()
        if not sess:
            return {"status": "unknown_session"}
        stored = await store_turns(conn, session_id, turns)
    if sess["status"] == "completed":
        grading = await grade_session(pool, s, session_id)
        return {"status": "graded", "stored": stored, "grading": grading}
    return {"status": "stored", "stored": stored, "session_status": sess["status"]}
