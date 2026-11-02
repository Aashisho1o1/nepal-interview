"""Session API. Browser endpoints under /api (cookie auth); agent endpoints under
/internal (bearer service token, never proxied to the browser)."""

import asyncio
import hmac
import json
import logging
import os
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
from .providers import LaunchContext, ProviderError, load_registry
from .quota import QuotaError, balances, settle_session, start_session
from .reconcile import close_room

log = logging.getLogger("interview_api")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def create_app(
    settings: Settings | None = None,
    media=None,
    pool=None,
    *,
    provider_env: dict[str, str] | None = None,
    provider_http=None,
) -> FastAPI:
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
                try:
                    app.state.media = LiveKitMedia(s)
                except RuntimeError as e:
                    # Embed/hosted providers still work without LiveKit.
                    log.warning("LiveKit providers disabled: %s", e)
        app.state.providers = load_registry(
            s, app.state.media, env=provider_env, http=provider_http
        )
        env = os.environ if provider_env is None else provider_env
        app.state.tavus_webhook_secret = env.get("TAVUS_WEBHOOK_SECRET", "")
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

    @app.get("/api/providers")
    async def list_providers(st=Depends(current_student)):
        """Providers offered to this student, in display order. Vendor names hidden."""
        reg = app.state.providers
        return [
            p.spec.public() for p in reg.enabled() if p.spec.modality == "voice" or s.avatar_enabled
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
        # Pick a provider explicitly (testing), or let the server choose by modality.
        provider_id: str | None = Field(default=None, max_length=64)
        mode: Literal["avatar", "voice"] | None = None

    @app.post("/api/sessions", dependencies=[Depends(origin_guard)])
    async def start(body: StartBody, request: Request, st=Depends(current_student)):
        if not s.sessions_enabled:
            raise HTTPException(503, "Practice sessions are paused.")
        reg = app.state.providers
        if body.provider_id:
            try:
                prov = reg.get(body.provider_id)
            except KeyError as e:
                raise QuotaError(
                    422, "provider_not_available", "That interviewer is not available."
                ) from e
        else:
            prov = reg.default_for(body.mode or "avatar")
            if prov is None:
                raise QuotaError(503, "provider_not_available", "No interviewer is available.")
        mode = prov.spec.modality
        if mode == "avatar" and not s.avatar_enabled:
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
        facts = snap["confirmed_facts_json"]
        missing = missing_required(track, facts)
        if missing or "error" in snap["funding_json"]:
            raise QuotaError(
                409, "facts_incomplete", "Some required facts are not confirmed.", missing=missing
            )
        res = await start_session(
            app.state.pool,
            s,
            student_id=st["student_id"],
            idempotency_key=key,
            track=track.id,
            format_id=fmt.id,
            mode=mode,
            practice_seconds=fmt.practice_seconds,
            snapshot_id=snap["id"],
            providers={**prov.session_providers(), "grader": s.grader},
            policy_version=POLICY_VERSION,
            provider_id=prov.spec.id,
        )
        sess = res.session
        if sess["provider_id"] != prov.spec.id:
            # Idempotent retry of a session started with another provider.
            prov = reg.get(sess["provider_id"])
        if sess["status"] not in ("created", "active") or sess["hard_deadline_at"] <= datetime.now(
            UTC
        ):
            raise QuotaError(
                409, "session_ended", "That session has already ended.", session_id=str(sess["id"])
            )
        bundle = app.state.policy.build(track, fmt, facts, compute_funding(facts))
        startup = s.startup_budget_avatar_s if mode == "avatar" else s.startup_budget_voice_s
        ctx = LaunchContext(
            session_id=str(sess["id"]),
            room_name=sess["room_name"],
            student_id=str(st["student_id"]),
            student_name=st["display_name"],
            practice_seconds=sess["practice_seconds"],
            max_vendor_seconds=startup + sess["practice_seconds"] + s.closing_grace_s,
            instructions=bundle.instructions,
            opening_line=bundle.opening_line,
        )
        launch = await _launch_once(prov, sess, ctx) if prov.stateful else await prov.launch(ctx)
        launch = {k: v for k, v in launch.items() if k != "vendor_ref"}
        out = {
            "session_id": str(sess["id"]),
            "created": res.created,
            "provider_id": prov.spec.id,
            "launch": launch,
            "mode": sess["mode"],
            "practice_seconds": sess["practice_seconds"],
            "hard_deadline_at": sess["hard_deadline_at"].isoformat(),
            "disclosure": fmt.disclosure,
        }
        if launch["kind"] == "livekit":  # kept for older clients
            out["server_url"] = launch["server_url"]
            out["participant_token"] = launch["participant_token"]
        return out

    async def _launch_once(prov, sess, ctx: LaunchContext) -> dict:
        """Create the vendor conversation exactly once per session, even under
        concurrent idempotent retries: one request claims the launch, the others wait
        for its stored result."""
        async with app.state.pool.connection() as conn:
            cur = await conn.execute(
                "UPDATE interview_sessions SET launch_claimed_at=now() "
                "WHERE id=%s AND launch_claimed_at IS NULL RETURNING id",
                (sess["id"],),
            )
            claimed = await cur.fetchone() is not None
        if not claimed:
            for _ in range(60):
                async with app.state.pool.connection() as conn:
                    cur = await conn.execute(
                        "SELECT launch_json, status FROM interview_sessions WHERE id=%s",
                        (sess["id"],),
                    )
                    row = await cur.fetchone()
                if row["launch_json"]:
                    return row["launch_json"]
                if row["status"] not in ("created", "active"):
                    raise QuotaError(409, "session_ended", "That session could not start.")
                await asyncio.sleep(0.25)
            raise QuotaError(409, "launch_in_progress", "Still connecting; try again.")
        try:
            launch = await prov.launch(ctx)
        except ProviderError as e:
            log.warning("provider %s launch failed: %s", prov.spec.id, e)
            await settle_session(app.state.pool, s, sess["id"], "provider_launch_failed")
            raise QuotaError(
                502,
                "provider_failed",
                "The interviewer could not start. Nothing was charged; please try again.",
            ) from e
        async with app.state.pool.connection() as conn:
            await conn.execute(
                "UPDATE interview_sessions SET launch_json=%s, vendor_ref=%s WHERE id=%s",
                (Jsonb(launch), launch.get("vendor_ref"), sess["id"]),
            )
        return launch

    async def _close_media(sess) -> None:
        await close_room(app.state.pool, app.state.media, sess, app.state.providers)

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
            "provider_id",
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
    async def end_session(
        session_id: str,
        reason: Literal[
            "student_ended",
            "deadline",
            "page_exit",
            "connect_failed",
            "avatar_lost",
            "settled_elsewhere",
            "disconnected",
        ] = "student_ended",
        st=Depends(current_student),
    ):
        """Called by the End button, the browser deadline, and navigator.sendBeacon on
        page exit. The reason (query string) feeds the provider comparison."""
        async with app.state.pool.connection() as conn:
            sess = await _own_session(conn, session_id, st["student_id"])
        out = await settle_session(app.state.pool, s, sess["id"], reason)
        await _close_media(sess)
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
            cur = await conn.execute(
                "SELECT realism, reply_speed, audio_video_ok, would_use_again, comment "
                "FROM session_ratings WHERE session_id=%s",
                (sess["id"],),
            )
            rating = await cur.fetchone()
        prov = app.state.providers.providers.get(sess["provider_id"])
        caps = prov.spec.capabilities if prov else {}
        return {
            "session": _public(sess),
            "provider": {"transcripts": bool(caps.get("transcripts", True))},
            "rating": rating,
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

    # ------------------------------------------------------------------ shared session events
    async def _apply_event(conn, sess, kind: str, payload: dict, source: str):
        """One code path for lifecycle events, whether reported by our agent (LiveKit
        sessions) or by the student's browser (embedded/hosted providers)."""
        await conn.execute(
            "INSERT INTO session_events (session_id, kind, payload, source) VALUES (%s,%s,%s,%s)",
            (sess["id"], kind, Jsonb(payload), source),
        )
        live = sess["status"] in ("created", "active")
        if kind == "media_ready" and live and sess["media_ready_at"] is None:
            now = datetime.now(UTC)
            ends = min(
                now + timedelta(seconds=sess["practice_seconds"]),
                sess["hard_deadline_at"] - timedelta(seconds=s.closing_grace_s),
            )
            display = payload.get("display", sess["display"])
            if display not in ("avatar", "portrait"):
                display = sess["display"]
            cur = await conn.execute(
                """UPDATE interview_sessions SET status='active', media_ready_at=%s,
                   practice_ends_at=%s, last_heartbeat_at=%s, display=%s WHERE id=%s RETURNING *""",
                (now, ends, now, display, sess["id"]),
            )
            sess = await cur.fetchone()
        elif kind == "fallback_to_voice" and live and sess["fallback_at"] is None:
            # Before media is ready, a fallback is a voice session from the start;
            # it is still settled from the premium reservation at zero premium seconds.
            await conn.execute(
                "UPDATE interview_sessions SET fallback_at=now(), display='portrait' WHERE id=%s",
                (sess["id"],),
            )
        elif kind == "heartbeat" and live:
            await conn.execute(
                "UPDATE interview_sessions SET last_heartbeat_at=now() WHERE id=%s", (sess["id"],)
            )
        elif kind == "room_deleted":
            await conn.execute(
                "UPDATE interview_sessions SET room_closed_at=COALESCE(room_closed_at, now()) "
                "WHERE id=%s",
                (sess["id"],),
            )
        return sess

    def _event_reply(sess) -> dict:
        return {
            "status": sess["status"],
            "live": sess["status"] in ("created", "active"),
            "practice_ends_at": sess["practice_ends_at"].timestamp()
            if sess["practice_ends_at"]
            else None,
        }

    class ClientEventBody(Strict):
        kind: Literal["media_ready", "heartbeat", "metric", "media_error"]
        payload: dict = Field(default_factory=dict)

    @app.post("/api/sessions/{session_id}/client-events", dependencies=[Depends(origin_guard)])
    async def client_event(session_id: str, body: ClientEventBody, st=Depends(current_student)):
        """Browser-reported lifecycle for providers we cannot observe server-side
        (embeds, hosted vendors). For our own LiveKit sessions the agent is the source
        of truth, so the browser may only send metrics."""
        if len(json.dumps(body.payload)) > 4000:
            raise HTTPException(413, "payload too large")
        async with app.state.pool.connection() as conn, conn.transaction():
            await _own_session(conn, session_id, st["student_id"])
            cur = await conn.execute(
                "SELECT * FROM interview_sessions WHERE id=%s FOR UPDATE", (session_id,)
            )
            sess = await cur.fetchone()
            client_driven = sess["providers"].get("transport") != "livekit"
            if body.kind in ("media_ready", "heartbeat") and not client_driven:
                raise HTTPException(409, "this session's lifecycle is reported by the agent")
            sess = await _apply_event(conn, sess, body.kind, body.payload, "client")
        return _event_reply(sess)

    class RatingBody(Strict):
        realism: int = Field(ge=1, le=5)
        reply_speed: Literal["instant", "slight_pause", "noticeably_slow", "frustrating"]
        audio_video_ok: bool
        would_use_again: bool
        comment: str | None = Field(default=None, max_length=1000)

    @app.post("/api/sessions/{session_id}/rating", dependencies=[Depends(origin_guard)])
    async def rate_session(session_id: str, body: RatingBody, st=Depends(current_student)):
        async with app.state.pool.connection() as conn:
            sess = await _own_session(conn, session_id, st["student_id"])
            if sess["status"] in ("created", "active"):
                raise HTTPException(409, "rate the session after it ends")
            await conn.execute(
                """INSERT INTO session_ratings (session_id, realism, reply_speed, audio_video_ok,
                     would_use_again, comment) VALUES (%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (session_id) DO UPDATE SET realism=EXCLUDED.realism,
                     reply_speed=EXCLUDED.reply_speed, audio_video_ok=EXCLUDED.audio_video_ok,
                     would_use_again=EXCLUDED.would_use_again, comment=EXCLUDED.comment,
                     updated_at=now()""",
                (
                    sess["id"],
                    body.realism,
                    body.reply_speed,
                    body.audio_video_ok,
                    body.would_use_again,
                    body.comment,
                ),
            )
        return {"ok": True}

    # ------------------------------------------------------------------ vendor webhooks
    @app.post("/api/webhooks/tavus/{secret}")
    async def tavus_webhook(secret: str, request: Request, background: BackgroundTasks):
        """Tavus conversation callbacks. Authenticated by a secret in the callback URL
        (set TAVUS_WEBHOOK_SECRET and PUBLIC_BASE_URL)."""
        expected = app.state.tavus_webhook_secret
        if not expected or not hmac.compare_digest(secret, expected):
            raise HTTPException(404, "not found")
        try:
            data = json.loads(await request.body())
        except ValueError as e:
            raise HTTPException(400, "invalid json") from e
        ref = str(data.get("conversation_id") or "")
        event = str(data.get("event_type") or data.get("message_type") or "unknown")[:80]
        async with app.state.pool.connection() as conn:
            cur = await conn.execute(
                "SELECT * FROM interview_sessions WHERE vendor_ref=%s AND provider_id=%s",
                (ref, "tavus_conversation"),
            )
            sess = await cur.fetchone()
            if not sess:
                return {"ok": True, "ignored": "unknown conversation"}
            props = data.get("properties") or {}
            await conn.execute(
                "INSERT INTO session_events (session_id, kind, payload, source) "
                "VALUES (%s,%s,%s,'tavus')",
                (sess["id"], "vendor_event", Jsonb({"event_type": event})),
            )
            if event == "application.transcription_ready":
                seq = 0
                for msg in props.get("transcript") or []:
                    role = msg.get("role")
                    text = str(msg.get("content") or "").strip()
                    if role not in ("user", "assistant") or not text:
                        continue
                    seq += 1
                    await conn.execute(
                        """INSERT INTO interview_turns (session_id, turn_id, sequence, speaker,
                             text, start_ms, end_ms, canceled) VALUES (%s,%s,%s,%s,%s,0,0,false)
                           ON CONFLICT (session_id, turn_id) DO UPDATE SET text=EXCLUDED.text""",
                        (
                            sess["id"],
                            f"tavus-{seq}",
                            seq,
                            "student" if role == "user" else "interviewer",
                            text[:8000],
                        ),
                    )
        if event == "system.shutdown":
            await settle_session(app.state.pool, s, sess["id"], "provider_shutdown")
        if event == "application.transcription_ready":
            async with app.state.pool.connection() as conn:
                cur = await conn.execute(
                    "SELECT status FROM interview_sessions WHERE id=%s", (sess["id"],)
                )
                status = (await cur.fetchone())["status"]
            if status == "completed":
                background.add_task(grade_session, app.state.pool, s, sess["id"])
        return {"ok": True}

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
            sess = await _apply_event(conn, sess, body.kind, body.payload, "agent")
        return _event_reply(sess)

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
