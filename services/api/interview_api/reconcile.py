"""Reconciliation: reclaim expired reservations, stop vendor sessions, grade stragglers.

Locally, run as a long-lived process (`python -m interview_api.reconcile --loop`). On
Vercel, a cron job calls GET /api/internal/reconcile every minute instead. Each step is
idempotent.

1. Live sessions that never became ready within the startup budget -> settle as
   failed startup (full refund) and ask the vendor to stop.
2. Live sessions past their hard deadline + teardown grace, or whose browser
   heartbeats stopped -> settle using the last heartbeat as the end, ask the vendor
   to stop.
3. Ended sessions whose vendor session is not confirmed stopped -> try again.
4. Ended sessions with a transcript but no feedback after a grace period -> grade.
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from .config import Settings, get_settings
from .feedback import grade_session
from .quota import settle_session

log = logging.getLogger("interview_api.reconcile")


async def _mark_vendor_closed(pool, session_id) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE interview_sessions SET vendor_closed_at = now() WHERE id=%s "
            "AND vendor_closed_at IS NULL",
            (session_id,),
        )


async def close_vendor(pool, sess, registry) -> bool:
    """Ask the provider to stop whatever is still running for this session. Static
    embeds have nothing to stop server-side (the browser unmounts the iframe and the
    vendor's own cap is the backstop); a provider that was removed from config counts
    as closed."""
    prov = registry.providers.get(sess.get("provider_id"))
    ok = await prov.close(sess) if prov else True
    if ok:
        await _mark_vendor_closed(pool, sess["id"])
    return ok


async def reconcile_once(pool, s: Settings, registry, *, feedback_grace_s: int = 120) -> dict:
    report = {"startup_timeouts": 0, "stale_active": 0, "closed": 0, "graded": 0}
    async with pool.connection() as conn:
        cur = await conn.execute(
            """SELECT * FROM interview_sessions WHERE status='created' AND media_ready_at IS NULL
               AND now() > created_at + make_interval(secs =>
                   CASE WHEN mode='avatar' THEN %s ELSE %s END + %s)""",
            (s.startup_budget_avatar_s, s.startup_budget_voice_s, s.teardown_grace_s),
        )
        startup = await cur.fetchall()
        cur = await conn.execute(
            """SELECT * FROM interview_sessions WHERE status IN ('created','active')
               AND media_ready_at IS NOT NULL AND (
                 now() > hard_deadline_at + make_interval(secs => %s)
                 OR COALESCE(last_heartbeat_at, media_ready_at)
                    < now() - make_interval(secs => %s))""",
            (s.teardown_grace_s, s.client_heartbeat_timeout_s),
        )
        stale = await cur.fetchall()

    for sess in startup:
        await settle_session(pool, s, sess["id"], "reconciled_startup_timeout")
        await close_vendor(pool, sess, registry)
        report["startup_timeouts"] += 1
    for sess in stale:
        await settle_session(pool, s, sess["id"], "reconciled_stale", use_heartbeat_as_end=True)
        await close_vendor(pool, sess, registry)
        report["stale_active"] += 1

    async with pool.connection() as conn:
        cur = await conn.execute(
            """SELECT * FROM interview_sessions WHERE status IN ('completed','failed')
               AND vendor_closed_at IS NULL AND ended_at > now() - interval '1 day'"""
        )
        unclosed = await cur.fetchall()
        cur = await conn.execute(
            """SELECT s.id FROM interview_sessions s LEFT JOIN feedback_reports f
                 ON f.session_id = s.id
               WHERE s.status='completed' AND f.session_id IS NULL
               AND s.ended_at < now() - make_interval(secs => %s)
               AND EXISTS (SELECT 1 FROM interview_turns t WHERE t.session_id = s.id)""",
            (feedback_grace_s,),
        )
        ungraded = [r["id"] for r in await cur.fetchall()]

    for sess in unclosed:
        if await close_vendor(pool, sess, registry):
            report["closed"] += 1
    for sid in ungraded:
        await grade_session(pool, s, sid)
        report["graded"] += 1
    return report


async def _main(loop: bool, interval: int) -> None:
    from .db import make_pool
    from .providers import load_registry

    s = get_settings()
    pool = make_pool(s.database_url, max_size=4)
    await pool.open()
    registry = load_registry(s)
    try:
        while True:
            report = await reconcile_once(pool, s, registry)
            if any(report.values()):
                log.info("reconcile", extra=report)
            if not loop:
                break
            await asyncio.sleep(interval)
    finally:
        await pool.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--interval", type=int, default=15)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main(a.loop, a.interval))
