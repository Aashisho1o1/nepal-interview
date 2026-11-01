"""Session API: auth, isolation, quota races, settlement, cleanup, reconciliation."""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from livekit import api

from conftest import confirm_all_and_snapshot, login_student, settings
from interview_api.media import LiveKitMedia
from interview_api.reconcile import reconcile_once

AVATAR = {"track": "us_f1", "format_id": "pressure_drill_3m", "mode": "avatar"}
VOICE = {**AVATAR, "mode": "voice"}


def key() -> dict:
    return {"idempotency-key": uuid.uuid4().hex}


async def ready_student(env, email="a@synthetic.test", name="Student A", **kw):
    c = await login_student(env, email, name, **kw)
    await confirm_all_and_snapshot(c)
    return c


async def start(c, body=AVATAR, headers=None):
    return await c.post("/api/sessions", json=body, headers=headers or key())


async def age_session(
    env,
    sid,
    ready_ago_s: int,
    fallback_after_s: int | None = None,
    heartbeat_ago_s: int | None = None,
):
    """Simulate elapsed time by moving server timestamps into the past."""
    await env.sql(
        """UPDATE interview_sessions SET status='active',
             media_ready_at = now() - make_interval(secs => %s),
             practice_ends_at = now() - make_interval(secs => %s) + make_interval(secs => practice_seconds),
             last_heartbeat_at = now() - make_interval(secs => %s),
             fallback_at = CASE WHEN %s::int IS NULL THEN NULL
                           ELSE now() - make_interval(secs => %s) + make_interval(secs => %s::int) END
           WHERE id=%s""",
        (
            ready_ago_s,
            ready_ago_s,
            heartbeat_ago_s if heartbeat_ago_s is not None else 0,
            fallback_after_s,
            ready_ago_s,
            fallback_after_s,
            sid,
        ),
    )


async def balance(c, bucket="premium_seconds"):
    return (await c.get("/api/me")).json()["balances"][bucket]


# ---------------------------------------------------------------- authentication


async def test_token_issuance_requires_authentication(make_env):
    env = await make_env()
    async with env.client() as c:
        assert (await start(c)).status_code == 401
        c.cookies.set("ni_session", "forged")
        assert (await start(c)).status_code == 401
    assert env.media.minted == []
    async with env.client() as c:
        for path in ("/internal/sessions/x/config", "/internal/sessions/x/events"):
            r = await (c.get(path) if path.endswith("config") else c.post(path, json={}))
            assert r.status_code == 401
        r = await c.get("/internal/sessions/x/config", headers={"authorization": "Bearer wrong"})
        assert r.status_code == 401


async def test_login_rejects_bad_password_and_foreign_origin(make_env):
    env = await make_env()
    await login_student(env, "a@synthetic.test", "A")
    async with env.client() as c:
        r = await c.post("/api/auth/login", json={"email": "a@synthetic.test", "password": "nope"})
        assert r.status_code == 401
        r = await c.post(
            "/api/auth/login",
            headers={"origin": "https://evil.example"},
            json={"email": "a@synthetic.test", "password": "pw-for-tests-123"},
        )
        assert r.status_code == 403


async def test_livekit_token_is_short_lived_room_scoped_and_dispatches_agent():
    s = settings(
        livekit_url="wss://example.livekit.cloud",
        livekit_api_key="APIkey",
        livekit_api_secret="s" * 40,
    )
    url, jwt = LiveKitMedia(s).mint_join_token(
        room="ni-abc", identity="student-1", name="A", session_id="sess-1"
    )
    claims = api.TokenVerifier("APIkey", "s" * 40).verify(jwt)
    assert claims.identity == "student-1"
    assert claims.video.room == "ni-abc" and claims.video.room_join
    assert list(claims.video.can_publish_sources) == ["microphone"]
    assert not claims.video.room_admin and not claims.video.room_create
    rc = claims.room_config
    assert rc.max_participants == 3
    assert rc.agents[0].agent_name == s.agent_name
    assert json.loads(rc.agents[0].metadata) == {"session_id": "sess-1"}
    import jwt as pyjwt  # pyjwt is a livekit-api dependency

    raw = pyjwt.decode(jwt, options={"verify_signature": False})
    assert raw["exp"] - raw["nbf"] <= 90


# ---------------------------------------------------------------- facts & isolation


async def test_cannot_start_without_confirmed_snapshot_and_corrections_keep_shape(make_env):
    env = await make_env()
    c = await login_student(env, "a@synthetic.test", "A")
    r = await start(c)
    assert r.status_code == 409 and r.json()["error"] == "no_snapshot"
    r = await c.patch(
        "/api/profile/facts/fund-loan", json={"status": "corrected", "value": {"new_key": "x"}}
    )
    assert r.status_code == 422
    r = await c.patch(
        "/api/profile/facts/fund-loan",
        json={"status": "corrected", "value": {"available_by": "2027-07-15"}},
    )
    assert r.status_code == 200
    snap = await confirm_all_and_snapshot(c)
    assert snap["funding"]["gap_minor"] == 0
    assert snap["missing"]["us_f1"] == []
    # A rejected fact leaves the snapshot and blocks the session.
    await c.patch("/api/profile/facts/program-course", json={"status": "rejected"})
    snap2 = (await c.post("/api/profile/snapshot")).json()
    assert "program.course" in snap2["missing"]["us_f1"]
    r = await start(c)
    assert r.status_code == 409 and r.json()["error"] == "facts_incomplete"


async def test_no_cross_student_access(make_env):
    env = await make_env()
    a = await ready_student(env, "a@synthetic.test", "A")
    b = await ready_student(env, "b@synthetic.test", "B")
    sid = (await start(a)).json()["session_id"]
    for path in (f"/api/sessions/{sid}", f"/api/sessions/{sid}/feedback"):
        assert (await b.get(path)).status_code == 404
    assert (await b.post(f"/api/sessions/{sid}/end")).status_code == 404
    assert (await b.get("/api/sessions/not-a-uuid")).status_code == 404
    assert (await b.get("/api/sessions")).json() == []
    # B correcting "their" fund-loan must not touch A's fact.
    await b.patch(
        "/api/profile/facts/fund-loan", json={"status": "corrected", "value": {"amount": "1.00"}}
    )
    a_loan = [f for f in (await a.get("/api/profile/facts")).json() if f["ref"] == "fund-loan"][0]
    assert a_loan["value_json"]["amount"] == "8000.00"
    assert (await a.get(f"/api/sessions/{sid}")).status_code == 200


# ---------------------------------------------------------------- quota invariants


async def test_concurrent_starts_create_exactly_one_session(make_env):
    env = await make_env()
    c = await ready_student(env)
    results = await asyncio.gather(*[start(c) for _ in range(20)])
    codes = sorted(r.status_code for r in results)
    assert codes.count(200) == 1 and codes.count(409) == 19, codes
    rows = await env.sql("SELECT count(*)::int AS n FROM interview_sessions")
    assert rows[0]["n"] == 1
    bal = await balance(c)
    assert bal["reserved"] == 180 and bal["available"] == 900 - 180


async def test_same_idempotency_key_returns_same_session(make_env):
    env = await make_env()
    c = await ready_student(env)
    h = key()
    results = await asyncio.gather(*[start(c, headers=h) for _ in range(10)])
    assert {r.status_code for r in results} == {200}
    assert len({r.json()["session_id"] for r in results}) == 1
    assert sum(r.json()["created"] for r in results) == 1


async def test_insufficient_balance_is_refused(make_env):
    env = await make_env()
    c = await ready_student(env, entitlements={"premium_seconds": 200, "basic_seconds": 0})
    sid = (await start(c)).json()["session_id"]
    await age_session(env, sid, ready_ago_s=150)
    async with env.internal() as i:
        r = await i.post(f"/internal/sessions/{sid}/finalize", json={"reason": "deadline"})
    assert r.json()["charged_premium_seconds"] == 150
    r = await start(c)
    assert r.status_code == 402 and r.json()["error"] == "insufficient_balance"
    assert (await start(c, body=VOICE)).status_code == 402


async def test_duplicate_and_concurrent_settlement_charges_once(make_env):
    env = await make_env()
    c = await ready_student(env)
    sid = (await start(c)).json()["session_id"]
    await age_session(env, sid, ready_ago_s=95)
    async with env.internal() as i:
        calls = [
            i.post(f"/internal/sessions/{sid}/finalize", json={"reason": "deadline"})
            for _ in range(8)
        ] + [c.post(f"/api/sessions/{sid}/end") for _ in range(4)]
        results = await asyncio.gather(*calls)
    assert all(r.status_code == 200 for r in results)
    charged = {r.json()["charged_premium_seconds"] for r in results}
    assert charged == {95}
    bal = await balance(c)
    assert bal["consumed"] == 95 and bal["reserved"] == 0
    rows = await env.sql(
        "SELECT count(*)::int AS n FROM audit_events WHERE action='session.settle'"
    )
    assert rows[0]["n"] == 1


async def test_failed_startup_restores_entitlement(make_env):
    env = await make_env()
    c = await ready_student(env)
    sid = (await start(c)).json()["session_id"]
    async with env.internal() as i:
        await i.post(
            f"/internal/sessions/{sid}/events",
            json={"kind": "error", "payload": {"stage": "avatar_start"}},
        )
        # Provider cost during startup is still recorded.
        await i.post(
            f"/internal/sessions/{sid}/usage",
            json={
                "events": [
                    {
                        "provider_event_id": "simli-startup",
                        "provider": "simli",
                        "meter": "simli.avatar_seconds",
                        "quantity": "12",
                        "unit": "second",
                    }
                ]
            },
        )
        r = await i.post(f"/internal/sessions/{sid}/finalize", json={"reason": "startup_failed"})
    body = r.json()
    assert body["status"] == "failed" and body["charged_premium_seconds"] == 0
    bal = await balance(c)
    assert bal["consumed"] == 0 and bal["reserved"] == 0 and bal["available"] == 900
    led = await env.sql("SELECT cost_usd_micros FROM usage_ledger WHERE session_id=%s", (sid,))
    assert led[0]["cost_usd_micros"] == 2000  # 12 s * 0.000166667 USD


async def test_no_student_speech_is_refunded(make_env):
    env = await make_env()
    c = await ready_student(env)
    sid = (await start(c)).json()["session_id"]
    await age_session(env, sid, ready_ago_s=40)
    async with env.internal() as i:
        r = await i.post(f"/internal/sessions/{sid}/finalize", json={"reason": "no_input"})
    assert r.json()["charged_premium_seconds"] == 0 and r.json()["waived_seconds"] == 40


async def test_avatar_fallback_bills_voice_time_at_basic_rate(make_env):
    env = await make_env()
    c = await ready_student(env)
    sid = (await start(c)).json()["session_id"]
    await age_session(env, sid, ready_ago_s=120, fallback_after_s=50)
    async with env.internal() as i:
        await i.post(
            f"/internal/sessions/{sid}/turns",
            json={
                "turns": [
                    {
                        "turn_id": "u1",
                        "sequence": 1,
                        "speaker": "student",
                        "text": "Hello there",
                        "start_ms": 1000,
                        "end_ms": 2000,
                    }
                ]
            },
        )
        r = await i.post(f"/internal/sessions/{sid}/finalize", json={"reason": "deadline"})
    b = r.json()
    assert (b["charged_premium_seconds"], b["charged_basic_seconds"]) == (50, 70)
    assert (await balance(c))["consumed"] == 50
    assert (await balance(c, "basic_seconds"))["consumed"] == 70


async def test_deadline_caps_charge_at_practice_length(make_env):
    env = await make_env()
    c = await ready_student(env)
    sid = (await start(c)).json()["session_id"]
    await age_session(env, sid, ready_ago_s=600)  # agent overran; student pays 180 max
    async with env.internal() as i:
        await i.post(
            f"/internal/sessions/{sid}/turns",
            json={
                "turns": [
                    {
                        "turn_id": "u1",
                        "sequence": 1,
                        "speaker": "student",
                        "text": "Hi",
                        "start_ms": 1000,
                        "end_ms": 2000,
                    }
                ]
            },
        )
        r = await i.post(f"/internal/sessions/{sid}/finalize", json={"reason": "deadline"})
    assert r.json()["charged_premium_seconds"] == 180


# ---------------------------------------------------------------- lifecycle


async def test_full_session_lifecycle_with_feedback(make_env):
    env = await make_env()
    c = await ready_student(env)
    r = await start(c)
    assert r.status_code == 200
    s = r.json()
    sid = s["session_id"]
    assert s["participant_token"] and "not a simulation" in s["disclosure"]
    assert env.media.minted[-1]["session_id"] == sid
    assert env.media.minted[-1]["identity"].startswith("student-")

    async with env.internal() as i:
        cfg = (await i.get(f"/internal/sessions/{sid}/config")).json()
        assert cfg["practice_seconds"] == 180 and cfg["mode"] == "avatar"
        instr = cfg["policy"]["instructions"]
        assert "USD 28,000.00" in instr and "Example State University" in instr
        ev = (
            await i.post(
                f"/internal/sessions/{sid}/events",
                json={"kind": "media_ready", "payload": {"display": "avatar"}},
            )
        ).json()
        assert ev["live"] and ev["practice_ends_at"]
        again = (
            await i.post(
                f"/internal/sessions/{sid}/events", json={"kind": "media_ready", "payload": {}}
            )
        ).json()
        assert again["practice_ends_at"] == ev["practice_ends_at"]  # idempotent

        turns = [
            ("t1", "interviewer", "Why this course?", False),
            (
                "t2",
                "student",
                "I want to study data science because I worked as a developer.",
                False,
            ),
            ("t3", "interviewer", "Who is paying for", True),
            ("t4", "student", "My father will pay. He has savings of 20,000 dollars.", False),
        ]
        payload = {
            "turns": [
                {
                    "turn_id": t,
                    "sequence": n,
                    "speaker": sp,
                    "text": tx,
                    "start_ms": n * 3000,
                    "end_ms": n * 3000 + 2500,
                    "canceled": cx,
                }
                for n, (t, sp, tx, cx) in enumerate(turns, 1)
            ]
        }
        assert (await i.post(f"/internal/sessions/{sid}/turns", json=payload)).status_code == 200
        assert (await i.post(f"/internal/sessions/{sid}/turns", json=payload)).status_code == 200
        usage = {
            "events": [
                {
                    "provider_event_id": "lk-session",
                    "provider": "livekit",
                    "meter": "livekit.agent_session_seconds",
                    "quantity": "60",
                    "unit": "second",
                },
                {
                    "provider_event_id": "oai-1",
                    "provider": "openai",
                    "meter": "openai.gpt-realtime.output_audio_tokens",
                    "quantity": "1234",
                    "unit": "token",
                },
            ]
        }
        assert (await i.post(f"/internal/sessions/{sid}/usage", json=usage)).json() == {
            "inserted": 2,
            "duplicates": 0,
        }
        assert (await i.post(f"/internal/sessions/{sid}/usage", json=usage)).json() == {
            "inserted": 0,
            "duplicates": 2,
        }
        assert (await i.post(f"/internal/sessions/{sid}/transcript-complete")).status_code == 409
        await age_session(env, sid, ready_ago_s=60)
        fin = (
            await i.post(f"/internal/sessions/{sid}/finalize", json={"reason": "deadline"})
        ).json()
        assert fin["status"] == "completed" and fin["charged_premium_seconds"] == 60
        assert (await i.get(f"/internal/sessions/{sid}/config")).status_code == 410
        assert (await i.post(f"/internal/sessions/{sid}/transcript-complete")).json()[
            "status"
        ] == "queued"

    fb = (await c.get(f"/api/sessions/{sid}/feedback")).json()
    assert fb["feedback"]["status"] == "ready", fb
    report = fb["feedback"]["report"]
    assert report["assessment_scope"] == "practice_feedback_only"
    turn_ids = {t["turn_id"] for t in fb["turns"]}
    assert all(f["turn_id"] in turn_ids for f in report["findings"])
    assert any(
        f["category"] == "funding_explanation" and f["severity"] == "strength"
        for f in report["findings"]
    )
    assert [t["canceled"] for t in fb["turns"]] == [False, False, True, False]
    led = await env.sql("SELECT meter, cost_usd_micros FROM usage_ledger ORDER BY meter")
    assert led[0]["cost_usd_micros"] == 10000  # 60 s LiveKit at planning rate
    assert led[1]["cost_usd_micros"] is None  # OpenAI unpriced until verified


async def test_browser_exit_beacon_settles_and_closes_room(make_env):
    env = await make_env()
    c = await ready_student(env)
    s = (await start(c)).json()
    await age_session(env, s["session_id"], ready_ago_s=30)
    # sendBeacon posts text/plain with cookies and no custom headers.
    r = await c.post(
        f"/api/sessions/{s['session_id']}/end",
        content=b"",
        headers={"content-type": "text/plain;charset=UTF-8"},
    )
    assert r.status_code == 200 and r.json()["end_reason"] == "student_ended"
    room = (await env.sql("SELECT room_name, room_closed_at FROM interview_sessions"))[0]
    assert room["room_name"] in env.media.deleted and room["room_closed_at"] is not None
    r2 = await c.post(f"/api/sessions/{s['session_id']}/end")
    assert r2.json()["end_reason"] == "student_ended"
    # A new session can start once the old one is settled.
    assert (await start(c)).status_code == 200


async def test_kill_switch_disabled_track_and_rate_limit(make_env):
    env = await make_env(avatar_enabled=False, max_starts_per_10min=2)
    c = await ready_student(env)
    r = await start(c)
    assert r.status_code == 503 and r.json()["error"] == "avatar_unavailable"
    r = await start(c, body={**AVATAR, "track": "uk_pre_cas", "format_id": "short_drill_3m"})
    assert r.status_code in (409, 503)
    for _ in range(2):
        sid = (await start(c, body=VOICE)).json()["session_id"]
        await c.post(f"/api/sessions/{sid}/end")
    r = await start(c, body=VOICE)
    assert r.status_code == 429


async def test_disabled_track_refused_when_avatar_enabled(make_env):
    env = await make_env()
    c = await ready_student(env)
    r = await start(c, body={**AVATAR, "track": "uk_pre_cas", "format_id": "short_drill_3m"})
    assert r.status_code == 409 and r.json()["error"] == "track_not_available"


# ---------------------------------------------------------------- reconciliation


async def test_reconciler_reclaims_startup_timeouts_stale_sessions_and_orphans(make_env):
    env = await make_env(startup_budget_avatar_s=1, teardown_grace_s=1, heartbeat_timeout_s=20)
    a = await ready_student(env, "a@synthetic.test", "A")
    b = await ready_student(env, "b@synthetic.test", "B")
    sa = (await start(a)).json()["session_id"]
    sb = (await start(b)).json()["session_id"]
    await env.sql(
        "UPDATE interview_sessions SET created_at = now() - interval '1 minute' WHERE id=%s", (sa,)
    )
    # B's agent crashed: ready 100 s ago, last heartbeat 70 s ago.
    await age_session(env, sb, ready_ago_s=100, heartbeat_ago_s=70)
    await env.sql(
        """INSERT INTO interview_turns VALUES (%s,'u1',1,'student','hello there',0,1000,
                     false,'{}')""",
        (sb,),
    )
    env.media.rooms.add("ni-orphan-from-crash")
    env.media.fail_delete = True
    rep = await reconcile_once(env.pool, env.media, env.s, feedback_grace_s=0)
    assert rep["startup_timeouts"] == 1 and rep["stale_active"] == 1
    rows = {r["id"]: r for r in await env.sql("SELECT * FROM interview_sessions")}
    assert rows[uuid.UUID(sa)]["status"] == "failed"
    assert rows[uuid.UUID(sa)]["charged_premium_seconds"] == 0
    assert rows[uuid.UUID(sb)]["charged_premium_seconds"] == 30  # until last heartbeat
    assert all(r["room_closed_at"] is None for r in rows.values())  # deletes failed
    env.media.fail_delete = False
    rep2 = await reconcile_once(env.pool, env.media, env.s, feedback_grace_s=0)
    assert rep2["rooms_closed"] == 2 and rep2["orphans"] >= 1
    assert "ni-orphan-from-crash" in env.media.deleted
    rows = await env.sql("SELECT room_closed_at FROM interview_sessions")
    assert all(r["room_closed_at"] is not None for r in rows)
    assert (await balance(a))["available"] == 900
    assert (await balance(b))["consumed"] == 30
    rep3 = await reconcile_once(env.pool, env.media, env.s, feedback_grace_s=0)
    assert rep3 == {
        "startup_timeouts": 0,
        "stale_active": 0,
        "rooms_closed": 0,
        "orphans": 0,
        "graded": 0,
    }


@pytest.mark.parametrize("n_students", [5])
async def test_many_students_in_parallel_do_not_interfere(make_env, n_students):
    env = await make_env()
    clients = [await ready_student(env, f"s{i}@synthetic.test", f"S{i}") for i in range(n_students)]
    results = await asyncio.gather(*[start(c) for c in clients for _ in range(4)])
    ok = [r for r in results if r.status_code == 200]
    assert len(ok) == n_students
    rows = await env.sql("SELECT count(DISTINCT student_id)::int AS n FROM interview_sessions")
    assert rows[0]["n"] == n_students


async def test_cumulative_usage_only_increases(make_env):
    env = await make_env()
    c = await ready_student(env)
    sid = (await start(c)).json()["session_id"]

    def ev(q):
        return {
            "events": [
                {
                    "provider_event_id": "cum:livekit.agent_session_seconds",
                    "provider": "livekit",
                    "meter": "livekit.agent_session_seconds",
                    "quantity": q,
                    "unit": "second",
                    "cumulative": True,
                }
            ]
        }

    async with env.internal() as i:
        for q in ("30", "60", "45", "90"):
            await i.post(f"/internal/sessions/{sid}/usage", json=ev(q))
    rows = await env.sql("SELECT quantity, cost_usd_micros FROM usage_ledger")
    assert len(rows) == 1 and rows[0]["quantity"] == 90 and rows[0]["cost_usd_micros"] == 15000
