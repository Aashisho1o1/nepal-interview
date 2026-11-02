"""Atomic reservation and idempotent settlement of interview seconds.

Invariants (tested in tests/test_api.py):
* A student has at most one live session (partial unique index).
* Reservation happens under a row lock on the entitlement, so concurrent starts can
  never reserve more than is available.
* Settlement happens once: the session row is locked and a settled session returns
  its stored result.
* Charged seconds: whole seconds rounded down, from media-ready to the end, capped at
  the reservation. Startup is never charged to the student. Provider startup costs
  are still recorded in usage_ledger.
* Failed startup (media never ready) and very short sessions with no student speech
  are refunded in full.
* After an avatar->voice fallback, avatar seconds are charged to the premium bucket
  and voice seconds to the basic bucket, up to its balance; any remainder is waived.
"""

from __future__ import annotations

import math
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from psycopg import errors
from psycopg.types.json import Jsonb

from .config import Settings
from .db import audit

LIVE = ("created", "active")


class QuotaError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra


@dataclass
class StartResult:
    session: dict
    created: bool


async def balances(conn, student_id) -> dict[str, dict]:
    cur = await conn.execute(
        """SELECT e.bucket,
                  COALESCE(SUM(e.granted_seconds),0)::int AS granted,
                  COALESCE(SUM(e.consumed_seconds),0)::int AS consumed,
                  COALESCE(SUM((SELECT COALESCE(SUM(r.reserved_seconds),0) FROM usage_reservations r
                               WHERE r.entitlement_id = e.id AND r.state='active')),0)::int AS reserved
           FROM entitlements e WHERE e.student_id=%s AND e.expires_at > now()
           GROUP BY e.bucket""",
        (student_id,),
    )
    out = {
        "premium_seconds": {"granted": 0, "consumed": 0, "reserved": 0},
        "basic_seconds": {"granted": 0, "consumed": 0, "reserved": 0},
    }
    for r in await cur.fetchall():
        out[r["bucket"]] = {k: r[k] for k in ("granted", "consumed", "reserved")}
    for v in out.values():
        v["available"] = v["granted"] - v["consumed"] - v["reserved"]
    return out


async def _lock_entitlement(conn, student_id, bucket: str, need: int):
    cur = await conn.execute(
        """SELECT * FROM entitlements WHERE student_id=%s AND bucket=%s AND expires_at > now()
           ORDER BY expires_at, id FOR UPDATE""",
        (student_id, bucket),
    )
    rows = await cur.fetchall()
    for e in rows:
        cur = await conn.execute(
            "SELECT COALESCE(SUM(reserved_seconds),0)::int AS r FROM usage_reservations "
            "WHERE entitlement_id=%s AND state='active'",
            (e["id"],),
        )
        reserved = (await cur.fetchone())["r"]
        avail = e["granted_seconds"] - e["consumed_seconds"] - reserved
        if avail >= need:
            return e, avail
    return None, 0


async def start_session(
    pool,
    s: Settings,
    *,
    student_id,
    idempotency_key: str,
    track: str,
    format_id: str,
    mode: str,
    practice_seconds: int,
    snapshot_id,
    providers: dict,
    policy_version: str,
    provider_id: str,
) -> StartResult:
    if not (8 <= len(idempotency_key) <= 128):
        raise QuotaError(400, "bad_idempotency_key", "Idempotency-Key must be 8-128 characters")
    bucket = "premium_seconds" if mode == "avatar" else "basic_seconds"
    budget = s.startup_budget_avatar_s if mode == "avatar" else s.startup_budget_voice_s
    for _attempt in range(2):
        async with pool.connection() as conn:
            try:
                async with conn.transaction():
                    cur = await conn.execute(
                        "SELECT * FROM interview_sessions WHERE student_id=%s AND idempotency_key=%s",
                        (student_id, idempotency_key),
                    )
                    existing = await cur.fetchone()
                    if existing:
                        return StartResult(existing, False)

                    cur = await conn.execute(
                        "SELECT count(*)::int AS n FROM interview_sessions WHERE student_id=%s "
                        "AND created_at > now() - interval '10 minutes'",
                        (student_id,),
                    )
                    if (await cur.fetchone())["n"] >= s.max_starts_per_10min:
                        raise QuotaError(
                            429,
                            "rate_limited",
                            "Too many session starts. Please wait a few minutes.",
                        )

                    ent, _avail = await _lock_entitlement(
                        conn, student_id, bucket, practice_seconds
                    )
                    if ent is None:
                        raise QuotaError(
                            402,
                            "insufficient_balance",
                            f"Not enough {bucket.replace('_', ' ')} for this session.",
                        )

                    now = datetime.now(UTC)
                    hard_deadline = now + timedelta(
                        seconds=budget + practice_seconds + s.closing_grace_s
                    )
                    room = f"{s.room_prefix}{secrets.token_hex(12)}"
                    cur = await conn.execute(
                        """INSERT INTO interview_sessions
                           (student_id, snapshot_id, idempotency_key, track, format_id, mode, display,
                            providers, policy_version, room_name, status, practice_seconds,
                            hard_deadline_at, provider_id)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'created',%s,%s,%s) RETURNING *""",
                        (
                            student_id,
                            snapshot_id,
                            idempotency_key,
                            track,
                            format_id,
                            mode,
                            "avatar" if mode == "avatar" else "portrait",
                            Jsonb(providers),
                            policy_version,
                            room,
                            practice_seconds,
                            hard_deadline,
                            provider_id,
                        ),
                    )
                    sess = await cur.fetchone()
                    await conn.execute(
                        """INSERT INTO usage_reservations
                           (entitlement_id, session_id, reserved_seconds, state, expires_at)
                           VALUES (%s,%s,%s,'active',%s)""",
                        (
                            ent["id"],
                            sess["id"],
                            practice_seconds,
                            hard_deadline + timedelta(seconds=s.teardown_grace_s),
                        ),
                    )
                    await audit(
                        conn,
                        str(student_id),
                        "session.reserve",
                        "interview_session",
                        str(sess["id"]),
                        {"bucket": bucket, "seconds": practice_seconds},
                    )
                    return StartResult(sess, True)
            except errors.UniqueViolation as e:
                # Either a concurrent request with the same key won (retry returns it),
                # or another live session exists.
                if "one_live_session_per_student" in str(e):
                    async with pool.connection() as c2:
                        cur = await c2.execute(
                            "SELECT id FROM interview_sessions WHERE student_id=%s AND status = ANY(%s)",
                            (student_id, list(LIVE)),
                        )
                        live = await cur.fetchone()
                    raise QuotaError(
                        409,
                        "session_already_live",
                        "You already have a session in progress.",
                        session_id=str(live["id"]) if live else None,
                    ) from e
                continue
    raise QuotaError(409, "conflict", "Could not start the session; retry.")


async def settle_session(
    pool, s: Settings, session_id, reason: str, *, use_heartbeat_as_end: bool = False
) -> dict:
    async with pool.connection() as conn, conn.transaction():
        cur = await conn.execute(
            "SELECT * FROM interview_sessions WHERE id=%s FOR UPDATE", (session_id,)
        )
        sess = await cur.fetchone()
        if sess is None:
            raise QuotaError(404, "not_found", "session not found")
        if sess["status"] not in LIVE:
            return {**sess, "already_settled": True}

        now = datetime.now(UTC)
        ready = sess["media_ready_at"]
        status = "completed"
        premium = basic = waived = 0
        note = None
        if ready is None:
            status = "failed"
            note = "failed_startup_refund"
            end = now
        else:
            end = min(now, sess["practice_ends_at"] or now, sess["hard_deadline_at"])
            if use_heartbeat_as_end:
                end = min(end, sess["last_heartbeat_at"] or ready)
            total = max(0, math.floor((end - ready).total_seconds()))
            total = min(total, sess["practice_seconds"])

            cur = await conn.execute(
                "SELECT count(*)::int AS n FROM interview_turns WHERE session_id=%s "
                "AND speaker='student' AND length(trim(text)) > 0",
                (session_id,),
            )
            student_turns = (await cur.fetchone())["n"]
            if student_turns == 0 and total <= s.no_input_refund_s:
                waived, note = total, "no_student_speech_refund"
            elif sess["mode"] == "avatar":
                if sess["fallback_at"] is not None:
                    avatar_s = max(0, math.floor((sess["fallback_at"] - ready).total_seconds()))
                    premium = min(avatar_s, total)
                    voice_s = total - premium
                    cur = await conn.execute(
                        """SELECT id, granted_seconds - consumed_seconds -
                                  (SELECT COALESCE(SUM(reserved_seconds),0) FROM usage_reservations r
                                   WHERE r.entitlement_id = e.id AND r.state='active') AS avail
                           FROM entitlements e WHERE student_id=%s AND bucket='basic_seconds'
                           AND expires_at > now() ORDER BY expires_at, id FOR UPDATE""",
                        (sess["student_id"],),
                    )
                    remaining = voice_s
                    for e in await cur.fetchall():
                        take = min(remaining, max(0, int(e["avail"])))
                        if take:
                            await conn.execute(
                                "UPDATE entitlements SET consumed_seconds = consumed_seconds + %s "
                                "WHERE id=%s",
                                (take, e["id"]),
                            )
                            basic += take
                            remaining -= take
                    waived = remaining
                else:
                    premium = total
            else:
                basic = total

        reserved_bucket_charge = premium if sess["mode"] == "avatar" else basic
        cur = await conn.execute(
            """UPDATE usage_reservations SET state='settled', settled_seconds=%s, settled_at=now()
               WHERE session_id=%s AND state='active' RETURNING entitlement_id""",
            (reserved_bucket_charge, session_id),
        )
        res = await cur.fetchone()
        if res and reserved_bucket_charge:
            await conn.execute(
                "UPDATE entitlements SET consumed_seconds = consumed_seconds + %s WHERE id=%s",
                (reserved_bucket_charge, res["entitlement_id"]),
            )

        cur = await conn.execute(
            """UPDATE interview_sessions SET status=%s, ended_at=%s, end_reason=%s,
                   charged_premium_seconds=%s, charged_basic_seconds=%s, waived_seconds=%s
               WHERE id=%s RETURNING *""",
            (status, end, reason, premium, basic, waived, session_id),
        )
        out = await cur.fetchone()
        await conn.execute(
            "INSERT INTO session_events (session_id, kind, payload, source) VALUES (%s,%s,%s,%s)",
            (
                session_id,
                "settled",
                Jsonb(
                    {
                        "reason": reason,
                        "note": note,
                        "premium": premium,
                        "basic": basic,
                        "waived": waived,
                    }
                ),
                "api",
            ),
        )
        await audit(
            conn,
            "system",
            "session.settle",
            "interview_session",
            str(session_id),
            {"reason": reason, "premium": premium, "basic": basic, "waived": waived, "note": note},
        )
        return {**out, "already_settled": False, "settlement_note": note}
