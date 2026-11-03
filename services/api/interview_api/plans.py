"""Free plan and promo codes. Both only add rows to `entitlements`; reserving and
charging time is unchanged (quota.py).

Free plan, per student, on Nepal calendar days:
- voice: `free_voice_sessions_per_day` sessions every day;
- video: one session a day on each of the account's first `free_video_days` days.
Each day's grant expires at the next midnight, so unused time never carries over. A
session already running keeps its reservation past midnight.

Promo codes: one shared code for many students, created with
`python -m interview_api.plans create ...`. Each student can redeem a code once.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
from datetime import UTC, datetime, time, timedelta, timezone

from fastapi import HTTPException

from interview_core.tracks import UK_PRE_CAS

from .config import Settings

NEPAL = timezone(timedelta(hours=5, minutes=45))  # no daylight saving
VIDEO_SECONDS = UK_PRE_CAS.format_for("avatar").practice_seconds
VOICE_SECONDS = UK_PRE_CAS.format_for("voice").practice_seconds


async def ensure_free_grants(conn, student_id, s: Settings, now: datetime | None = None) -> None:
    """Idempotent: add today's free grants if they're missing."""
    now = now or datetime.now(UTC)
    today = now.astimezone(NEPAL).date()
    midnight = datetime.combine(today + timedelta(days=1), time(0), NEPAL)
    grants = []
    if s.free_voice_sessions_per_day > 0:
        grants.append(
            ("basic_seconds", s.free_voice_sessions_per_day * VOICE_SECONDS, "free-voice")
        )
    if s.free_video_days > 0:
        cur = await conn.execute(
            "SELECT created_at FROM student_profiles WHERE id=%s", (student_id,)
        )
        joined = (await cur.fetchone())["created_at"].astimezone(NEPAL).date()
        if 0 <= (today - joined).days < s.free_video_days:
            grants.append(("premium_seconds", VIDEO_SECONDS, "free-video"))
    for bucket, seconds, kind in grants:
        await conn.execute(
            """INSERT INTO entitlements (student_id, bucket, package_version, granted_seconds,
                 expires_at) VALUES (%s,%s,%s,%s,%s)
               ON CONFLICT (student_id, bucket, package_version) DO NOTHING""",
            (student_id, bucket, f"{kind}:{today.isoformat()}", seconds, midnight),
        )


def normalize(code: str) -> str:
    return "".join(code.split()).upper()


def code_hash(code: str) -> str:
    return hashlib.sha256(normalize(code).encode()).hexdigest()


async def redeem(conn, student_id, code: str) -> dict:
    """Grant a code's time to this student. Raises HTTPException with a message the
    student can read. Call inside a transaction."""
    cur = await conn.execute(
        "SELECT * FROM promo_codes WHERE code_hash=%s FOR UPDATE", (code_hash(code),)
    )
    promo = await cur.fetchone()
    now = datetime.now(UTC)
    if not promo or not promo["active"] or (promo["expires_at"] and promo["expires_at"] <= now):
        raise HTTPException(404, "That code isn't valid. Check it and try again.")
    if promo["max_uses"] is not None and promo["uses"] >= promo["max_uses"]:
        raise HTTPException(410, "That code has been fully used.")
    cur = await conn.execute(
        "INSERT INTO promo_redemptions (code_id, student_id) VALUES (%s,%s) "
        "ON CONFLICT DO NOTHING RETURNING code_id",
        (promo["id"], student_id),
    )
    if await cur.fetchone() is None:
        raise HTTPException(409, "You've already used this code.")
    await conn.execute("UPDATE promo_codes SET uses = uses + 1 WHERE id=%s", (promo["id"],))
    expires = now + timedelta(days=promo["valid_days"])
    for bucket in ("premium_seconds", "basic_seconds"):
        if promo[bucket]:
            await conn.execute(
                """INSERT INTO entitlements (student_id, bucket, package_version,
                     granted_seconds, expires_at) VALUES (%s,%s,%s,%s,%s)""",
                (student_id, bucket, f"promo:{promo['id']}", promo[bucket], expires),
            )
    return {
        "video_sessions": promo["premium_seconds"] // VIDEO_SECONDS,
        "voice_sessions": promo["basic_seconds"] // VOICE_SECONDS,
        "valid_days": promo["valid_days"],
    }


# ---------------------------------------------------------------- admin command


async def _cli(a: argparse.Namespace) -> None:
    from .config import get_settings
    from .db import apply_schema, make_pool

    pool = make_pool(get_settings().database_url, max_size=2)
    await pool.open()
    await apply_schema(pool)
    async with pool.connection() as conn:
        if a.cmd == "create":
            expires = (
                datetime.combine(datetime.fromisoformat(a.until).date(), time(23, 59), NEPAL)
                if a.until
                else None
            )
            await conn.execute(
                """INSERT INTO promo_codes (code_hash, label, premium_seconds, basic_seconds,
                     valid_days, max_uses, expires_at) VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (
                    code_hash(a.code),
                    a.label,
                    a.video_sessions * VIDEO_SECONDS,
                    a.voice_sessions * VOICE_SECONDS,
                    a.days,
                    a.max_uses,
                    expires,
                ),
            )
            print(
                f"Created {normalize(a.code)} ({a.label}). Only its hash is stored: keep the code."
            )
        elif a.cmd == "disable":
            cur = await conn.execute(
                "UPDATE promo_codes SET active=false WHERE code_hash=%s RETURNING label",
                (code_hash(a.code),),
            )
            print("Disabled." if await cur.fetchone() else "No such code.")
        else:
            cur = await conn.execute("SELECT * FROM promo_codes ORDER BY created_at")
            for r in await cur.fetchall():
                cap = r["max_uses"] or "no cap"
                print(
                    f"{r['label']}: {r['uses']} used ({cap}), "
                    f"{r['premium_seconds'] // VIDEO_SECONDS} video + "
                    f"{r['basic_seconds'] // VOICE_SECONDS} voice sessions for {r['valid_days']} "
                    f"days, {'active' if r['active'] else 'disabled'}, "
                    f"expires {r['expires_at'] or 'never'}"
                )
    await pool.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="python -m interview_api.plans")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create", help="create a shared promo code")
    c.add_argument("code", help="what students type, e.g. LEEDS2027 (case and spaces ignored)")
    c.add_argument("--label", required=True, help="who it's for, e.g. 'Kathmandu seminar'")
    c.add_argument("--video-sessions", type=int, default=0)
    c.add_argument("--voice-sessions", type=int, default=0)
    c.add_argument("--days", type=int, default=30, help="how long the granted time lasts")
    c.add_argument("--max-uses", type=int, default=None, help="cap on students; omit for none")
    c.add_argument("--until", default=None, help="last day it can be redeemed, YYYY-MM-DD")
    d = sub.add_parser("disable", help="stop a code from being redeemed")
    d.add_argument("code")
    sub.add_parser("list", help="list codes (labels only; codes are not stored)")
    asyncio.run(_cli(ap.parse_args()))
