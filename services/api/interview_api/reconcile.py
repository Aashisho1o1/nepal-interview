"""Reconciliation: reclaim expired reservations and close orphaned media.

Run as a separate long-lived process (`python -m interview_api.reconcile --loop`) or
call `reconcile_once` from tests. Each step is idempotent.

1. Live sessions that never became ready within the startup budget -> settle as
   failed startup (full refund) and delete the room.
2. Live sessions past their hard deadline + teardown grace, or whose agent heartbeat
   stopped -> settle using the last heartbeat as the end, delete the room.
3. Ended sessions whose room is not confirmed deleted -> delete it.
4. LiveKit rooms with our prefix that map to no live session -> delete (orphans).
5. Ended sessions with no feedback after a grace period -> grade what exists.
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from .config import Settings, get_settings
from .feedback import grade_session
from .quota import settle_session

log = logging.getLogger("interview_api.reconcile")


async def _mark_room_closed(pool, session_id) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE interview_sessions SET room_closed_at = now() WHERE id=%s "
            "AND room_closed_at IS NULL",
            (session_id,),
        )


async def close_room(pool, media, sess, registry=None) -> bool:
    """Stop whatever is still running for this session at the media provider.

    LiveKit sessions: delete our room. Embedded/hosted providers: ask the provider to
    end its conversation if it can (Tavus), otherwise there is nothing server-side to
    stop (static embeds rely on the browser unmounting and the vendor's own cap).
    """
    transport = (sess.get("providers") or {}).get("transport", "livekit")
    if transport == "livekit":
        if media is None:
            return False
        ok = await media.delete_room(sess["room_name"])
    else:
        prov = registry.providers.get(sess.get("provider_id")) if registry else None
        ok = await prov.close(sess) if prov else True
    if ok:
        await _mark_room_closed(pool, sess["id"])
    return ok


async def reconcile_once(
    pool, media, s: Settings, *, registry=None, feedback_grace_s: int = 120
) -> dict:
    report = {
        "startup_timeouts": 0,
        "stale_active": 0,
        "rooms_closed": 0,
        "orphans": 0,
        "graded": 0,
    }
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
                 OR COALESCE(last_heartbeat_at, media_ready_at) < now() - make_interval(secs =>
                    CASE WHEN providers->>'transport' = 'livekit' THEN %s ELSE %s END))""",
            (s.teardown_grace_s, s.heartbeat_timeout_s, s.client_heartbeat_timeout_s),
        )
        stale = await cur.fetchall()

    for sess in startup:
        await settle_session(pool, s, sess["id"], "reconciled_startup_timeout")
        await close_room(pool, media, sess, registry)
        report["startup_timeouts"] += 1
    for sess in stale:
        await settle_session(pool, s, sess["id"], "reconciled_stale", use_heartbeat_as_end=True)
        await close_room(pool, media, sess, registry)
        report["stale_active"] += 1

    async with pool.connection() as conn:
        cur = await conn.execute(
            """SELECT * FROM interview_sessions WHERE status IN ('completed','failed')
               AND room_closed_at IS NULL AND ended_at > now() - interval '1 day'"""
        )
        unclosed = await cur.fetchall()
        cur = await conn.execute(
            "SELECT room_name FROM interview_sessions WHERE status IN ('created','active')"
        )
        live_rooms = {r["room_name"] for r in await cur.fetchall()}
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
        if await close_room(pool, media, sess, registry):
            report["rooms_closed"] += 1
    try:
        for room in await media.list_rooms() if media is not None else []:
            if room not in live_rooms:
                async with pool.connection() as conn:
                    cur = await conn.execute(
                        "SELECT id FROM interview_sessions WHERE room_name=%s", (room,)
                    )
                    known = await cur.fetchone()
                if await media.delete_room(room):
                    report["orphans"] += 1
                    if known:
                        await _mark_room_closed(pool, known["id"])
    except Exception:
        log.warning("listing rooms failed; orphan sweep skipped", exc_info=True)
    for sid in ungraded:
        await grade_session(pool, s, sid)
        report["graded"] += 1
    return report


async def _main(loop: bool, interval: int) -> None:
    from .db import make_pool
    from .media import LiveKitMedia
    from .providers import load_registry

    s = get_settings()
    pool = make_pool(s.database_url, max_size=4)
    await pool.open()
    try:
        media = LiveKitMedia(s)
    except RuntimeError as e:
        log.warning("LiveKit not configured (%s); only embed/hosted sessions reconciled", e)
        media = None
    registry = load_registry(s, media)
    try:
        while True:
            report = await reconcile_once(pool, media, s, registry=registry)
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
