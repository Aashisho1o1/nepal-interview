"""Session API. Browser endpoints under /api (cookie auth); agent endpoints under
/internal (bearer service token, never proxied to the browser)."""

import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from interview_core import POLICY_VERSION
from interview_core.facts import Fact, build_snapshot, missing_required
from interview_core.funding import FundingInputError, compute_funding
from interview_core.policy import DefaultPolicy
from interview_core.pricing import load_price_table
from interview_core.tracks import TRACKS, get_track

from .auth import (
    COOKIE,
    LoginLimiter,
    check_origin,
    create_login,
    current_student,
    require_internal,
    token_hash,
    verify_password,
)
from .config import Settings, get_settings
from .db import apply_schema, audit, make_pool
from .feedback import grade_session
from .quota import QuotaError, balances, settle_session, start_session
from .reconcile import close_room

log = logging.getLogger("interview_api")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def create_app(settings: Settings | None = None, media=None, pool=None) -> FastAPI:
    s = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.pool = pool or make_pool(s.database_url)
        await app.state.pool.open()
        await apply_schema(app.state.pool)
        if app.state.media is None:
            from .media import FakeMedia, LiveKitMedia

            if s.media_backend == "fake":
                log.warning("MEDIA_BACKEND=fake: join tokens are not usable; UI testing only")
                app.state.media = FakeMedia()
            else:
                app.state.media = LiveKitMedia(s)
        yield
        if pool is None:
            await app.state.pool.close()

    app = FastAPI(title="Nepal interview session API", lifespan=lifespan)
    app.state.settings = s
    app.state.media = media
    app.state.prices = load_price_table(s.price_table_path)
    app.state.limiter = LoginLimiter()
    app.state.policy = DefaultPolicy()

    @app.exception_handler(QuotaError)
    async def _quota_err(_req, e: QuotaError):
        return JSONResponse(
            {"error": e.code, "message": e.message, **e.extra}, status_code=e.status
        )

    def origin_guard(request: Request) -> None:
        check_origin(request, s.allowed_origins)

    # ------------------------------------------------------------------ auth
    class LoginBody(Strict):
        email: str = Field(max_length=200)
        password: str = Field(max_length=200)

    @app.post("/api/auth/login", dependencies=[Depends(origin_guard)])
    async def login(body: LoginBody, request: Request, response: Response):
        key = body.email.strip().lower()
        if app.state.limiter.blocked(key):
            raise HTTPException(429, "too many attempts")
        async with app.state.pool.connection() as conn:
            cur = await conn.execute("SELECT * FROM users WHERE email=%s", (key,))
            user = await cur.fetchone()
            if not user or not verify_password(body.password, user["password_hash"]):
                app.state.limiter.fail(key)
                raise HTTPException(401, "invalid email or password")
            raw, exp = await create_login(conn, user["id"], s.login_ttl_hours)
            await audit(conn, str(user["id"]), "auth.login", "user", str(user["id"]))
        response.set_cookie(
            COOKIE,
            raw,
            httponly=True,
            secure=s.cookie_secure,
            samesite="lax",
            expires=exp,
            path="/",
        )
        return {"ok": True}

    @app.post("/api/auth/logout", dependencies=[Depends(origin_guard)])
    async def logout(request: Request, response: Response):
        raw = request.cookies.get(COOKIE)
        if raw:
            async with app.state.pool.connection() as conn:
                await conn.execute(
                    "UPDATE auth_sessions SET revoked_at=now() WHERE token_hash=%s",
                    (token_hash(raw),),
                )
        response.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    @app.get("/api/me")
    async def me(st=Depends(current_student)):
        async with app.state.pool.connection() as conn:
            bal = await balances(conn, st["student_id"])
        return {
            "email": st["email"],
            "display_name": st["display_name"],
            "is_synthetic": st["is_synthetic"],
            "balances": bal,
            "avatar_available": s.avatar_enabled,
            "sessions_enabled": s.sessions_enabled,
        }

    @app.get("/api/tracks")
    async def tracks():
        return [
            {
                "id": t.id,
                "label": t.label,
                "stage": t.stage,
                "enabled": t.enabled,
                "required_facts": list(t.required_facts),
                "must_not_require": list(t.must_not_require),
                "formats": [f.__dict__ for f in t.formats],
                "notes": list(t.notes),
            }
            for t in TRACKS.values()
        ]

    # ------------------------------------------------------------------ facts
    @app.get("/api/profile/facts")
    async def list_facts(st=Depends(current_student)):
        async with app.state.pool.connection() as conn:
            cur = await conn.execute(
                "SELECT ref, field_name, value_json, source_label, source_snippet, "
                "confirmation_status FROM extracted_facts WHERE student_id=%s ORDER BY field_name, ref",
                (st["student_id"],),
            )
            return await cur.fetchall()

    class FactUpdate(Strict):
        status: Literal["confirmed", "corrected", "rejected"]
        value: Any | None = None

    def _same_shape(old: Any, new: Any) -> bool:
        if isinstance(old, dict):
            return (
                isinstance(new, dict)
                and set(new) <= set(old)
                and all(isinstance(v, (str, int, bool, type(None))) for v in new.values())
            )
        return type(old) is type(new) and (not isinstance(new, str) or len(new) <= 400)

    @app.patch("/api/profile/facts/{ref}", dependencies=[Depends(origin_guard)])
    async def update_fact(ref: str, body: FactUpdate, st=Depends(current_student)):
        async with app.state.pool.connection() as conn, conn.transaction():
            cur = await conn.execute(
                "SELECT * FROM extracted_facts WHERE student_id=%s AND ref=%s FOR UPDATE",
                (st["student_id"], ref),
            )
            f = await cur.fetchone()
            if f is None:
                raise HTTPException(404, "fact not found")
            value = f["value_json"]
            if body.status == "corrected":
                if body.value is None or not _same_shape(value, body.value):
                    raise HTTPException(422, "corrected value must keep the original shape")
                value = {**value, **body.value} if isinstance(value, dict) else body.value
            await conn.execute(
                "UPDATE extracted_facts SET confirmation_status=%s, value_json=%s, updated_at=now() "
                "WHERE id=%s",
                (body.status, Jsonb(value), f["id"]),
            )
            await audit(conn, str(st["user_id"]), f"fact.{body.status}", "fact", ref)
        return {"ok": True}

    @app.post("/api/profile/snapshot", dependencies=[Depends(origin_guard)])
    async def create_snapshot(st=Depends(current_student)):
        async with app.state.pool.connection() as conn, conn.transaction():
            cur = await conn.execute(
                "SELECT * FROM extracted_facts WHERE student_id=%s FOR UPDATE", (st["student_id"],)
            )
            rows = await cur.fetchall()
            cur = await conn.execute(
                "SELECT COALESCE(MAX(version),0)+1 AS v FROM profile_snapshots WHERE student_id=%s",
                (st["student_id"],),
            )
            version = (await cur.fetchone())["v"]
            facts = [
                Fact(
                    r["ref"],
                    r["field_name"],
                    r["value_json"],
                    r["source_label"],
                    r["source_snippet"],
                    r["confirmation_status"],
                )
                for r in rows
            ]
            snap = build_snapshot(facts, version)
            try:
                funding = compute_funding(snap).to_dict()
            except FundingInputError as e:
                funding = {"error": str(e)}
            await conn.execute(
                "INSERT INTO profile_snapshots (student_id, version, confirmed_facts_json, "
                "funding_json) VALUES (%s,%s,%s,%s)",
                (st["student_id"], version, Jsonb(snap), Jsonb(funding)),
            )
        return {
            "version": version,
            "funding": funding,
            "missing": {t.id: missing_required(t, snap) for t in TRACKS.values()},
        }

    async def _latest_snapshot(conn, student_id):
        cur = await conn.execute(
            "SELECT * FROM profile_snapshots WHERE student_id=%s ORDER BY version DESC LIMIT 1",
            (student_id,),
        )
        return await cur.fetchone()

    @app.get("/api/profile/snapshot")
    async def get_snapshot(st=Depends(current_student)):
        async with app.state.pool.connection() as conn:
            snap = await _latest_snapshot(conn, st["student_id"])
        if not snap:
            return {"version": None}
        facts = snap["confirmed_facts_json"]
        return {
            "version": snap["version"],
            "facts": facts["facts"],
            "funding": snap["funding_json"],
            "missing": {t.id: missing_required(t, facts) for t in TRACKS.values()},
        }

    # ------------------------------------------------------------------ sessions
    class StartBody(Strict):
        track: str
        format_id: str
        mode: Literal["avatar", "voice"]

    @app.post("/api/sessions", dependencies=[Depends(origin_guard)])
    async def start(body: StartBody, request: Request, st=Depends(current_student)):
        if not s.sessions_enabled:
            raise HTTPException(503, "Practice sessions are paused.")
        if body.mode == "avatar" and not s.avatar_enabled:
            raise QuotaError(
                503,
                "avatar_unavailable",
                "The avatar is unavailable right now. Choose voice practice.",
            )
        try:
            track = get_track(body.track)
            fmt = track.format(body.format_id)
        except KeyError as e:
            raise HTTPException(422, "unknown track or format") from e
        if not track.enabled:
            raise QuotaError(409, "track_not_available", f"{track.label} is not available yet.")
        key = request.headers.get("idempotency-key", "")
        async with app.state.pool.connection() as conn:
            snap = await _latest_snapshot(conn, st["student_id"])
        if not snap:
            raise QuotaError(409, "no_snapshot", "Confirm your facts before practising.")
        missing = missing_required(track, snap["confirmed_facts_json"])
        if missing or "error" in snap["funding_json"]:
            raise QuotaError(
                409, "facts_incomplete", "Some required facts are not confirmed.", missing=missing
            )
        providers = {
            "voice": s.voice_engine,
            "avatar": "simli" if body.mode == "avatar" else None,
            "transport": "livekit",
            "grader": s.grader,
        }
        res = await start_session(
            app.state.pool,
            s,
            student_id=st["student_id"],
            idempotency_key=key,
            track=track.id,
            format_id=fmt.id,
            mode=body.mode,
            practice_seconds=fmt.practice_seconds,
            snapshot_id=snap["id"],
            providers=providers,
            policy_version=POLICY_VERSION,
        )
        sess = res.session
        if sess["status"] not in ("created", "active") or sess["hard_deadline_at"] <= datetime.now(
            UTC
        ):
            raise QuotaError(
                409, "session_ended", "That session has already ended.", session_id=str(sess["id"])
            )
        server_url, token = app.state.media.mint_join_token(
            room=sess["room_name"],
            identity=f"student-{st['student_id']}",
            name=st["display_name"],
            session_id=str(sess["id"]),
        )
        return {
            "session_id": str(sess["id"]),
            "created": res.created,
            "server_url": server_url,
            "participant_token": token,
            "mode": sess["mode"],
            "practice_seconds": sess["practice_seconds"],
            "hard_deadline_at": sess["hard_deadline_at"].isoformat(),
            "disclosure": fmt.disclosure,
        }

    async def _own_session(conn, session_id: str, student_id):
        try:
            cur = await conn.execute(
                "SELECT * FROM interview_sessions WHERE id=%s AND student_id=%s",
                (session_id, student_id),
            )
        except Exception as e:  # malformed UUID
            raise HTTPException(404, "session not found") from e
        sess = await cur.fetchone()
        if not sess:
            # Same response whether it does not exist or belongs to someone else.
            raise HTTPException(404, "session not found")
        return sess

    def _public(sess) -> dict:
        keys = (
            "id",
            "track",
            "format_id",
            "mode",
            "display",
            "status",
            "practice_seconds",
            "created_at",
            "media_ready_at",
            "practice_ends_at",
            "fallback_at",
            "ended_at",
            "end_reason",
            "charged_premium_seconds",
            "charged_basic_seconds",
            "waived_seconds",
        )
        return {k: (str(sess[k]) if k == "id" else sess[k]) for k in keys}

    @app.get("/api/sessions")
    async def list_sessions(st=Depends(current_student)):
        async with app.state.pool.connection() as conn:
            cur = await conn.execute(
                "SELECT * FROM interview_sessions WHERE student_id=%s ORDER BY created_at DESC "
                "LIMIT 20",
                (st["student_id"],),
            )
            return [_public(r) for r in await cur.fetchall()]

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str, st=Depends(current_student)):
        async with app.state.pool.connection() as conn:
            return _public(await _own_session(conn, session_id, st["student_id"]))

    @app.post("/api/sessions/{session_id}/end", dependencies=[Depends(origin_guard)])
    async def end_session(session_id: str, st=Depends(current_student)):
        """Called by the End button and by navigator.sendBeacon on page exit."""
        async with app.state.pool.connection() as conn:
            sess = await _own_session(conn, session_id, st["student_id"])
        out = await settle_session(app.state.pool, s, sess["id"], "student_ended")
        await close_room(app.state.pool, app.state.media, sess)
        return _public(out)

    @app.get("/api/sessions/{session_id}/feedback")
    async def get_feedback(session_id: str, st=Depends(current_student)):
        async with app.state.pool.connection() as conn:
            sess = await _own_session(conn, session_id, st["student_id"])
            cur = await conn.execute(
                "SELECT * FROM feedback_reports WHERE session_id=%s", (sess["id"],)
            )
            fb = await cur.fetchone()
            cur = await conn.execute(
                "SELECT turn_id, sequence, speaker, text, start_ms, end_ms, canceled "
                "FROM interview_turns WHERE session_id=%s ORDER BY sequence, start_ms",
                (sess["id"],),
            )
            turns = await cur.fetchall()
        return {
            "session": _public(sess),
            "turns": turns,
            "feedback": None
            if not fb
            else {
                "status": fb["status"],
                "report": fb["validated_json"],
                "review_status": fb["review_status"],
                "error": "Feedback could not be generated and has been queued for review."
                if fb["status"] == "failed"
                else None,
            },
        }

    # ------------------------------------------------------------------ internal (agent)
    internal = [Depends(require_internal)]

    async def _session_any(conn, session_id: str):
        cur = await conn.execute("SELECT * FROM interview_sessions WHERE id=%s", (session_id,))
        sess = await cur.fetchone()
        if not sess:
            raise HTTPException(404, "session not found")
        return sess

    @app.get("/internal/sessions/{session_id}/config", dependencies=internal)
    async def agent_config(session_id: str):
        async with app.state.pool.connection() as conn:
            sess = await _session_any(conn, session_id)
            cur = await conn.execute(
                "SELECT * FROM profile_snapshots WHERE id=%s", (sess["snapshot_id"],)
            )
            snap = await cur.fetchone()
        if sess["status"] not in ("created", "active"):
            raise HTTPException(410, "session is not live")
        track = get_track(sess["track"])
        fmt = track.format(sess["format_id"])
        facts = snap["confirmed_facts_json"]
        bundle = app.state.policy.build(track, fmt, facts, compute_funding(facts))
        startup = (
            s.startup_budget_avatar_s if sess["mode"] == "avatar" else s.startup_budget_voice_s
        )
        return {
            "session_id": str(sess["id"]),
            "room_name": sess["room_name"],
            "student_identity": f"student-{sess['student_id']}",
            "track": sess["track"],
            "mode": sess["mode"],
            "providers": sess["providers"],
            "practice_seconds": sess["practice_seconds"],
            "startup_budget_s": startup,
            "closing_grace_s": s.closing_grace_s,
            "hard_deadline_at": sess["hard_deadline_at"].timestamp(),
            "policy": bundle.to_dict(),
        }

    class EventBody(Strict):
        kind: Literal[
            "agent_joined",
            "media_ready",
            "fallback_to_voice",
            "heartbeat",
            "latency",
            "interruption",
            "state",
            "error",
            "room_deleted",
            "provider_closed",
        ]
        payload: dict = Field(default_factory=dict)

    @app.post("/internal/sessions/{session_id}/events", dependencies=internal)
    async def agent_event(session_id: str, body: EventBody):
        async with app.state.pool.connection() as conn, conn.transaction():
            cur = await conn.execute(
                "SELECT * FROM interview_sessions WHERE id=%s FOR UPDATE", (session_id,)
            )
            sess = await cur.fetchone()
            if not sess:
                raise HTTPException(404, "session not found")
            await conn.execute(
                "INSERT INTO session_events (session_id, kind, payload, source) VALUES (%s,%s,%s,'agent')",
                (session_id, body.kind, Jsonb(body.payload)),
            )
            live = sess["status"] in ("created", "active")
            if body.kind == "media_ready" and live and sess["media_ready_at"] is None:
                now = datetime.now(UTC)
                ends = min(
                    now + timedelta(seconds=sess["practice_seconds"]),
                    sess["hard_deadline_at"] - timedelta(seconds=s.closing_grace_s),
                )
                cur = await conn.execute(
                    """UPDATE interview_sessions SET status='active', media_ready_at=%s,
                       practice_ends_at=%s, last_heartbeat_at=%s, display=%s WHERE id=%s RETURNING *""",
                    (now, ends, now, body.payload.get("display", sess["display"]), session_id),
                )
                sess = await cur.fetchone()
            elif body.kind == "fallback_to_voice" and live and sess["fallback_at"] is None:
                # Before media is ready, a fallback is a voice session from the start;
                # it is still settled from the premium reservation at zero premium seconds.
                await conn.execute(
                    "UPDATE interview_sessions SET fallback_at=now(), display='portrait' WHERE id=%s",
                    (session_id,),
                )
            elif body.kind == "heartbeat" and live:
                await conn.execute(
                    "UPDATE interview_sessions SET last_heartbeat_at=now() WHERE id=%s",
                    (session_id,),
                )
            elif body.kind == "room_deleted":
                await conn.execute(
                    "UPDATE interview_sessions SET room_closed_at=COALESCE(room_closed_at, now()) "
                    "WHERE id=%s",
                    (session_id,),
                )
        return {
            "status": sess["status"],
            "live": sess["status"] in ("created", "active"),
            "practice_ends_at": sess["practice_ends_at"].timestamp()
            if sess["practice_ends_at"]
            else None,
        }

    class TurnIn(Strict):
        turn_id: str = Field(max_length=80)
        sequence: int
        speaker: Literal["student", "interviewer"]
        text: str = Field(max_length=8000)
        start_ms: int = Field(ge=0)
        end_ms: int = Field(ge=0)
        canceled: bool = False
        metrics: dict = Field(default_factory=dict)

    class TurnsBody(Strict):
        turns: list[TurnIn] = Field(max_length=200)

    @app.post("/internal/sessions/{session_id}/turns", dependencies=internal)
    async def agent_turns(session_id: str, body: TurnsBody):
        async with app.state.pool.connection() as conn, conn.transaction():
            await _session_any(conn, session_id)
            for t in body.turns:
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
        return {"stored": len(body.turns)}

    class UsageIn(Strict):
        provider_event_id: str = Field(max_length=200)
        provider: str = Field(max_length=40)
        meter: str = Field(max_length=120)
        quantity: Decimal = Field(ge=0)
        unit: str = Field(max_length=20)
        # Cumulative meters are re-sent with the running total (e.g. every heartbeat) so a
        # crash loses little; the stored quantity only ever increases.
        cumulative: bool = False

    class UsageBody(Strict):
        events: list[UsageIn] = Field(max_length=100)

    @app.post("/internal/sessions/{session_id}/usage", dependencies=internal)
    async def agent_usage(session_id: str, body: UsageBody):
        prices = app.state.prices
        inserted = 0
        async with app.state.pool.connection() as conn, conn.transaction():
            await _session_any(conn, session_id)
            for u in body.events:
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
        return {"inserted": inserted, "duplicates": len(body.events) - inserted}

    class FinalizeBody(Strict):
        reason: str = Field(max_length=60)

    @app.post("/internal/sessions/{session_id}/finalize", dependencies=internal)
    async def agent_finalize(session_id: str, body: FinalizeBody):
        out = await settle_session(app.state.pool, s, session_id, body.reason)
        return {**_public(out), "already_settled": out["already_settled"]}

    @app.post("/internal/sessions/{session_id}/transcript-complete", dependencies=internal)
    async def transcript_complete(session_id: str, background: BackgroundTasks):
        async with app.state.pool.connection() as conn:
            sess = await _session_any(conn, session_id)
        if sess["status"] in ("created", "active"):
            raise HTTPException(409, "settle the session first")
        if sess["status"] == "failed":
            return {"status": "skipped", "reason": "session never started"}
        background.add_task(grade_session, app.state.pool, s, sess["id"])
        return {"status": "queued"}

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    return app
