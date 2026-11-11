"""Session API: browser endpoints under /api (cookie auth, same origin as the website:
Vercel routes /api/* here, locally the Next.js dev proxy does). Vendor keys never leave
this process."""

import asyncio
import hmac
import json
import logging
import re
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from interview_core import POLICY_VERSION
from interview_core.dynamic_vars import build_dynamic_variables
from interview_core.facts import Fact, build_snapshot, missing_required
from interview_core.funding import FundingInputError, compute_funding, funding_or_none
from interview_core.pricing import load_price_table
from interview_core.tracks import TRACKS, get_track

from . import details, plans
from .accounts import provision_student
from .auth import (
    COOKIE,
    DUMMY_HASH,
    RateLimiter,
    check_origin,
    client_ip,
    create_login,
    current_student,
    hash_password,
    token_hash,
    verify_password,
)
from .config import Settings, get_settings
from .db import RECONCILE_LOCK, apply_schema, audit, make_pool
from .providers import LaunchContext, ProviderError, load_registry
from .quota import QuotaError, balances, settle_session, start_session
from .reconcile import close_vendor, reconcile_once

log = logging.getLogger("interview_api")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SIGNUP_PACKAGE = "signup-trial-v1"
# Browser-reported events kept per session; a normal call sends about twenty.
MAX_EVENTS_PER_SESSION = 300


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def create_app(
    settings: Settings | None = None,
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
        if s.apply_schema_on_start:
            await apply_schema(app.state.pool)
        app.state.providers = load_registry(s, env=provider_env, http=provider_http)
        yield
        if pool is None:
            await app.state.pool.close()

    docs = {} if s.api_docs else {"docs_url": None, "redoc_url": None, "openapi_url": None}
    app = FastAPI(title="Nepal interview session API", lifespan=lifespan, **docs)
    app.state.settings = s
    app.state.prices = load_price_table(s.price_table_path)
    app.state.limiter = RateLimiter(max_hits=8, window_s=600)  # failed logins per email
    app.state.login_ip = RateLimiter(max_hits=30, window_s=600)  # failed logins per network
    app.state.signups = RateLimiter(max_hits=5, window_s=3600)  # new accounts per network
    # Every sign-up attempt, counted before the password is hashed: hashing is the
    # expensive step, so failed attempts must not be free.
    app.state.signup_tries = RateLimiter(max_hits=20, window_s=3600)
    # Wrong promo codes: per student and per network, so codes can't be guessed.
    app.state.code_tries = RateLimiter(max_hits=5, window_s=3600)

    @app.exception_handler(QuotaError)
    async def _quota_err(_req, e: QuotaError):
        return JSONResponse(
            {"error": e.code, "message": e.message, **e.extra}, status_code=e.status
        )

    @app.middleware("http")
    async def _no_store(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):  # personal data: never cached
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    def origin_guard(request: Request) -> None:
        check_origin(request, s.allowed_origins)

    # ------------------------------------------------------------------ auth
    class LoginBody(Strict):
        email: str = Field(max_length=200)
        password: str = Field(max_length=200)

    @app.post("/api/auth/login", dependencies=[Depends(origin_guard)])
    async def login(body: LoginBody, request: Request, response: Response):
        key = body.email.strip().lower()
        ip = f"ip:{client_ip(request)}"
        if app.state.limiter.blocked(key) or app.state.login_ip.blocked(ip):
            raise HTTPException(429, "too many attempts")
        async with app.state.pool.connection() as conn:
            cur = await conn.execute("SELECT id, password_hash FROM users WHERE email=%s", (key,))
            user = await cur.fetchone()
        # Off the event loop (scrypt is slow by design), and always run, so the reply
        # takes as long for an unknown email as for a wrong password.
        ok = await asyncio.to_thread(
            verify_password, body.password, user["password_hash"] if user else DUMMY_HASH
        )
        if not (user and ok):
            app.state.limiter.hit(key)
            app.state.login_ip.hit(ip)
            raise HTTPException(401, "invalid email or password")
        async with app.state.pool.connection() as conn, conn.transaction():
            raw, exp = await create_login(conn, user["id"], s.login_ttl_hours)
            await audit(conn, str(user["id"]), "auth.login", "user", str(user["id"]))
        _set_login_cookie(response, raw, exp)
        return {"ok": True}

    def _set_login_cookie(response: Response, raw: str, exp: datetime) -> None:
        response.set_cookie(
            COOKIE,
            raw,
            httponly=True,
            secure=s.cookie_secure,
            samesite="lax",
            expires=exp,
            path="/",
        )

    class SignupBody(Strict):
        name: str = Field(max_length=80)
        email: str = Field(max_length=200)
        password: str = Field(max_length=200)

    @app.post("/api/auth/signup", dependencies=[Depends(origin_guard)])
    async def signup(body: SignupBody, request: Request, response: Response):
        if not s.signup_enabled:
            raise HTTPException(403, "Sign-up is closed right now.")
        name = " ".join(body.name.split())
        email = body.email.strip().lower()
        if not name:
            raise HTTPException(422, "Enter your name.")
        if not EMAIL_RE.match(email):
            raise HTTPException(422, "Enter a valid email address.")
        if len(body.password) < 8:
            raise HTTPException(422, "Use a password of at least 8 characters.")
        ip = client_ip(request)
        if app.state.signups.blocked(ip) or app.state.signup_tries.blocked(ip):
            raise HTTPException(429, "Too many new accounts from this network. Try again later.")
        app.state.signup_tries.hit(ip)
        pw_hash = await asyncio.to_thread(hash_password, body.password)
        async with app.state.pool.connection() as conn, conn.transaction():
            cur = await conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (%s,%s) "
                "ON CONFLICT (email) DO NOTHING RETURNING id",
                (email, pw_hash),
            )
            user = await cur.fetchone()
            if user is None:
                raise HTTPException(
                    409, "An account with this email already exists. Sign in instead."
                )
            # Practice time comes from the free plan (plans.py), granted day by day.
            await provision_student(conn, user["id"], name, {}, SIGNUP_PACKAGE)
            raw, exp = await create_login(conn, user["id"], s.login_ttl_hours)
            await audit(conn, str(user["id"]), "auth.signup", "user", str(user["id"]))
        app.state.signups.hit(ip)
        _set_login_cookie(response, raw, exp)
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
            await plans.ensure_free_grants(conn, st["student_id"], s)
            bal = await balances(conn, st["student_id"])
        return {
            "email": st["email"],
            "display_name": st["display_name"],
            "is_synthetic": st["is_synthetic"],
            "balances": bal,
            # Length of one session per interviewer type, to show sessions left.
            "session_seconds": {"avatar": plans.VIDEO_SECONDS, "voice": plans.VOICE_SECONDS},
            "video_available": s.video_tier_enabled,
            "voice_available": s.voice_tier_enabled,
        }

    class CodeBody(Strict):
        code: str = Field(max_length=64)

    @app.post("/api/promo/redeem", dependencies=[Depends(origin_guard)])
    async def redeem_code(body: CodeBody, request: Request, st=Depends(current_student)):
        keys = (f"student:{st['student_id']}", f"ip:{client_ip(request)}")
        if any(app.state.code_tries.blocked(k) for k in keys):
            raise HTTPException(429, "Too many tries. Wait an hour and try again.")
        try:
            async with app.state.pool.connection() as conn, conn.transaction():
                granted = await plans.redeem(conn, st["student_id"], body.code)
                await audit(
                    conn, str(st["user_id"]), "promo.redeem", "student", str(st["student_id"])
                )
        except HTTPException as e:
            if e.status_code == 404:  # only wrong codes count as guesses
                for k in keys:
                    app.state.code_tries.hit(k)
            raise
        return granted

    @app.get("/api/providers")
    async def list_providers(st=Depends(current_student)):
        """Providers offered to this student, in display order. Vendor names hidden."""
        reg = app.state.providers
        return [p.spec.public() for p in reg.enabled() if _tier_enabled(p.spec.modality)]

    def _tier_enabled(modality: str) -> bool:
        return s.video_tier_enabled if modality == "avatar" else s.voice_tier_enabled

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

    async def _new_snapshot(conn, student_id) -> dict:
        """Freeze the student's confirmed facts into a new snapshot version. Call inside a
        transaction."""
        cur = await conn.execute(
            "SELECT * FROM extracted_facts WHERE student_id=%s FOR UPDATE", (student_id,)
        )
        rows = await cur.fetchall()
        cur = await conn.execute(
            "SELECT COALESCE(MAX(version),0)+1 AS v FROM profile_snapshots WHERE student_id=%s",
            (student_id,),
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
        cur = await conn.execute(
            "INSERT INTO profile_snapshots (student_id, version, confirmed_facts_json, "
            "funding_json) VALUES (%s,%s,%s,%s) RETURNING *",
            (student_id, version, Jsonb(snap), Jsonb(funding)),
        )
        return await cur.fetchone()

    def _snapshot_out(row) -> dict:
        return {
            "version": row["version"],
            "funding": row["funding_json"],
            "missing": {
                t.id: missing_required(t, row["confirmed_facts_json"]) for t in TRACKS.values()
            },
        }

    @app.post("/api/profile/snapshot", dependencies=[Depends(origin_guard)])
    async def create_snapshot(st=Depends(current_student)):
        async with app.state.pool.connection() as conn, conn.transaction():
            row = await _new_snapshot(conn, st["student_id"])
        return _snapshot_out(row)

    @app.get("/api/profile/details")
    async def get_details(st=Depends(current_student)):
        async with app.state.pool.connection() as conn:
            cur = await conn.execute(
                "SELECT ref, field_name, value_json, confirmation_status FROM extracted_facts "
                "WHERE student_id=%s",
                (st["student_id"],),
            )
            values = details.from_facts(await cur.fetchall())
        if not values["name"]:
            values["name"] = st["display_name"]
        return values

    @app.put("/api/profile/details", dependencies=[Depends(origin_guard)])
    async def put_details(body: details.Details, st=Depends(current_student)):
        async with app.state.pool.connection() as conn, conn.transaction():
            await details.save(conn, st["student_id"], body)
            row = await _new_snapshot(conn, st["student_id"])
            await audit(
                conn, str(st["user_id"]), "profile.details", "student", str(st["student_id"])
            )
        return _snapshot_out(row)

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
        provider_id: str = Field(max_length=64)
        format_id: str | None = None  # optional: each interviewer type has one format

    @app.post("/api/sessions", dependencies=[Depends(origin_guard)])
    async def start(body: StartBody, request: Request, st=Depends(current_student)):
        reg = app.state.providers
        try:
            prov = reg.get(body.provider_id)
        except KeyError as e:
            raise QuotaError(
                422, "provider_not_available", "That interviewer is not available."
            ) from e
        mode = prov.spec.modality
        if not _tier_enabled(mode):
            raise QuotaError(
                503,
                "tier_unavailable",
                "The video interviewer is paused right now. Try voice practice."
                if mode == "avatar"
                else "The voice interviewer is paused right now.",
            )
        try:
            track = get_track(body.track)
            fmt = track.format(body.format_id) if body.format_id else track.format_for(mode)
        except KeyError as e:
            raise HTTPException(422, "unknown track or format") from e
        if fmt.modality != mode:
            raise HTTPException(422, "that format is for the other interviewer")
        key = request.headers.get("idempotency-key", "")
        # No details needed: a student who skipped the form practises on an empty
        # snapshot and the interviewer asks about what it doesn't know.
        async with app.state.pool.connection() as conn, conn.transaction():
            await plans.ensure_free_grants(conn, st["student_id"], s)
            snap = await _latest_snapshot(conn, st["student_id"])
            if not snap:
                snap = await _new_snapshot(conn, st["student_id"])
        facts = snap["confirmed_facts_json"]
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
        startup = s.startup_budget_avatar_s if mode == "avatar" else s.startup_budget_voice_s
        ctx = LaunchContext(
            session_id=str(sess["id"]),
            student_id=str(st["student_id"]),
            student_name=st["display_name"],
            practice_seconds=sess["practice_seconds"],
            max_vendor_seconds=startup + sess["practice_seconds"] + s.closing_grace_s,
            dynamic_variables=build_dynamic_variables(
                session_id=str(sess["id"]),
                student_name=st["display_name"],
                facts=facts,
                funding=funding_or_none(facts),
                practice_seconds=sess["practice_seconds"],
            ),
        )
        try:
            launch = (
                await _launch_once(prov, sess, ctx) if prov.stateful else await prov.launch(ctx)
            )
        except ProviderError as e:
            log.warning("provider %s launch failed: %s", prov.spec.id, e)
            await settle_session(app.state.pool, s, sess["id"], "provider_launch_failed")
            raise QuotaError(
                502,
                "provider_failed",
                "The interviewer could not start. Nothing was charged; please try again.",
            ) from e
        launch = {k: v for k, v in launch.items() if k != "vendor_ref"}
        out = {
            "session_id": str(sess["id"]),
            "created": res.created,
            "launch": launch,
            "mode": sess["mode"],
            "practice_seconds": sess["practice_seconds"],
            "hard_deadline_at": sess["hard_deadline_at"].isoformat(),
            "disclosure": fmt.disclosure,
        }
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
        launch = await prov.launch(ctx)
        async with app.state.pool.connection() as conn:
            await conn.execute(
                "UPDATE interview_sessions SET launch_json=%s, vendor_ref=%s WHERE id=%s",
                (Jsonb(launch), launch.get("vendor_ref"), sess["id"]),
            )
        return launch

    async def _own_session(conn, session_id: str, student_id, *, lock: bool = False):
        """The student's own session; `lock` holds the row for the transaction."""
        try:
            sid = UUID(session_id)
        except ValueError:
            raise HTTPException(404, "session not found") from None
        cur = await conn.execute(
            "SELECT * FROM interview_sessions WHERE id=%s AND student_id=%s"
            + (" FOR UPDATE" if lock else ""),
            (sid, student_id),
        )
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
            "status",
            "practice_seconds",
            "created_at",
            "media_ready_at",
            "practice_ends_at",
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
            "agent_ended",
        ] = "student_ended",
        st=Depends(current_student),
    ):
        """Called by the End button, the browser deadline, and navigator.sendBeacon on
        page exit. The reason (query string) feeds the provider comparison."""
        async with app.state.pool.connection() as conn:
            sess = await _own_session(conn, session_id, st["student_id"])
        out = await settle_session(app.state.pool, s, sess["id"], reason)
        await close_vendor(app.state.pool, sess, app.state.providers)
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
            "provider": {"transcripts": bool(caps.get("transcripts", False))},
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

    # ------------------------------------------------------------------ team review
    async def team_member(st=Depends(current_student)):
        # 404, not 403: students should not learn that the page exists.
        if st["role"] != "admin":
            raise HTTPException(404, "not found")
        return st

    @app.get("/api/team/sessions", dependencies=[Depends(team_member)])
    async def team_sessions(limit: int = 200):
        """Recent sessions from every student with their rating, feedback and
        transcript, so the founders can see how practice went. Read-only."""
        limit = max(1, min(limit, 500))
        async with app.state.pool.connection() as conn:
            cur = await conn.execute(
                """SELECT s.id, s.created_at, s.mode, s.status, s.end_reason,
                          s.practice_seconds, s.media_ready_at, s.ended_at,
                          p.display_name AS name, u.email,
                          r.realism, r.reply_speed, r.audio_video_ok, r.would_use_again,
                          r.comment, f.status AS feedback_status, f.validated_json AS feedback
                   FROM interview_sessions s
                   JOIN student_profiles p ON p.id = s.student_id
                   JOIN users u ON u.id = p.user_id
                   LEFT JOIN session_ratings r ON r.session_id = s.id
                   LEFT JOIN feedback_reports f ON f.session_id = s.id
                   ORDER BY s.created_at DESC LIMIT %s""",
                (limit,),
            )
            rows = await cur.fetchall()
            cur = await conn.execute(
                """SELECT session_id, speaker, text FROM interview_turns
                   WHERE session_id = ANY(%s) AND NOT canceled
                   ORDER BY session_id, sequence, start_ms""",
                ([r["id"] for r in rows],),
            )
            turns: dict = {}
            for t in await cur.fetchall():
                turns.setdefault(t["session_id"], []).append(
                    {"speaker": t["speaker"], "text": t["text"]}
                )
        out = []
        for r in rows:
            ready, ended = r.pop("media_ready_at"), r.pop("ended_at")
            out.append(
                {
                    **r,
                    "id": str(r["id"]),
                    "talked_seconds": int((ended - ready).total_seconds())
                    if ready and ended
                    else None,
                    "turns": turns.get(r["id"], []),
                }
            )
        return out

    # ------------------------------------------------------------------ shared session events
    async def _apply_event(conn, sess, kind: str, payload: dict, source: str):
        """Lifecycle events reported by the student's browser (and settlement by the API)."""
        # Capped per session, so a client cannot fill the table; the clock and
        # heartbeat below still apply.
        await conn.execute(
            """INSERT INTO session_events (session_id, kind, payload, source)
               SELECT %s::uuid, %s::text, %s::jsonb, %s::text
               WHERE (SELECT count(*) FROM session_events
                      WHERE session_id=%s) < %s""",
            (sess["id"], kind, Jsonb(payload), source, sess["id"], MAX_EVENTS_PER_SESSION),
        )
        live = sess["status"] in ("created", "active")
        if kind == "media_ready" and live and sess["media_ready_at"] is None:
            now = datetime.now(UTC)
            ends = min(
                now + timedelta(seconds=sess["practice_seconds"]),
                sess["hard_deadline_at"] - timedelta(seconds=s.closing_grace_s),
            )
            cur = await conn.execute(
                """UPDATE interview_sessions SET status='active', media_ready_at=%s,
                   practice_ends_at=%s, last_heartbeat_at=%s WHERE id=%s RETURNING *""",
                (now, ends, now, sess["id"]),
            )
            sess = await cur.fetchone()
        elif kind == "heartbeat" and live:
            await conn.execute(
                "UPDATE interview_sessions SET last_heartbeat_at=now() WHERE id=%s", (sess["id"],)
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
        """Browser-reported lifecycle: the practice clock starts on the first
        media_ready, heartbeats keep the session live, metrics are stored for review."""
        if len(json.dumps(body.payload)) > 4000:
            raise HTTPException(413, "payload too large")
        async with app.state.pool.connection() as conn, conn.transaction():
            sess = await _own_session(conn, session_id, st["student_id"], lock=True)
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

    # Called every minute by Vercel Cron (see vercel.json). Each step is idempotent; the
    # lock stops an overlapping or duplicate delivery from running alongside.
    @app.get("/api/internal/reconcile", include_in_schema=False)
    async def cron_reconcile(request: Request):
        given = request.headers.get("authorization", "")
        if not s.cron_secret or not hmac.compare_digest(
            given.encode(), f"Bearer {s.cron_secret}".encode()
        ):
            raise HTTPException(401, "unauthorized")
        pool = app.state.pool
        async with pool.connection() as conn, conn.transaction():
            cur = await conn.execute(
                "SELECT pg_try_advisory_xact_lock(%s) AS ok", (RECONCILE_LOCK,)
            )
            if not (await cur.fetchone())["ok"]:
                return {"skipped": "already running"}
            report = await reconcile_once(pool, s, app.state.providers)
        if any(report.values()):
            log.info("reconcile", extra=report)
        return report

    @app.get("/livez")
    async def livez():
        return {"ok": True}

    @app.get("/healthz")
    async def healthz():
        """Readiness: the process is up and the database answers."""
        try:
            async with app.state.pool.connection(timeout=2) as conn:
                await conn.execute("SELECT 1")
        except Exception:
            log.exception("health check: database unavailable")
            return JSONResponse({"ok": False}, status_code=503)
        return {"ok": True}

    return app
