"""Session API: auth, isolation, quota races, settlement, cleanup, reconciliation.

Every test goes through the providers students actually get (the LiveAvatar embed
for video, the ElevenLabs agent for voice). None needs a vendor to be reachable: the
browser reports the lifecycle and the server owns the clock and the credits.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from conftest import (
    VIDEO_SECONDS,
    VOICE,
    VOICE_SECONDS,
    age_session,
    balance,
    confirm_all_and_snapshot,
    key,
    login_student,
    media_ready,
    ready_student,
    start,
)
from interview_api.reconcile import reconcile_once
from interview_api.transcripts import Turn, UsageEvent, ingest_transcript, record_usage


def turn(i: int, speaker: str, text: str, canceled: bool = False) -> Turn:
    return Turn(
        turn_id=f"t{i}",
        sequence=i,
        speaker=speaker,
        text=text,
        start_ms=i * 3000,
        end_ms=i * 3000 + 2500,
        canceled=canceled,
    )


async def end(c, sid: str, reason: str | None = None):
    q = f"?reason={reason}" if reason else ""
    return await c.post(f"/api/sessions/{sid}/end{q}")


# ---------------------------------------------------------------- authentication


async def test_start_requires_authentication_and_leaks_no_vendor_credential(make_env):
    env = await make_env()
    async with env.client() as c:
        r = await start(c)
        assert r.status_code == 401 and "launch" not in r.text
        assert (await c.get("/api/providers")).status_code == 401
        c.cookies.set("ni_session", "forged")
        assert (await start(c, VOICE)).status_code == 401


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
    assert snap["missing"]["uk_pre_cas"] == []
    # A rejected fact leaves the snapshot and blocks the session.
    await c.patch("/api/profile/facts/program-course", json={"status": "rejected"})
    snap2 = (await c.post("/api/profile/snapshot")).json()
    assert "program.course" in snap2["missing"]["uk_pre_cas"]
    r = await start(c)
    assert r.status_code == 409 and r.json()["error"] == "facts_incomplete"


async def test_no_cross_student_access(make_env):
    env = await make_env()
    a = await ready_student(env, "a@synthetic.test", "A")
    b = await ready_student(env, "b@synthetic.test", "B")
    sid = (await start(a)).json()["session_id"]
    for path in (f"/api/sessions/{sid}", f"/api/sessions/{sid}/feedback"):
        assert (await b.get(path)).status_code == 404
    assert (await end(b, sid)).status_code == 404
    assert (await b.get("/api/sessions/not-a-uuid")).status_code == 404
    assert (await b.get("/api/sessions")).json() == []
    # B correcting "their" fund-loan must not touch A's fact.
    await b.patch(
        "/api/profile/facts/fund-loan", json={"status": "corrected", "value": {"amount": "1.00"}}
    )
    a_loan = [f for f in (await a.get("/api/profile/facts")).json() if f["ref"] == "fund-loan"][0]
    assert a_loan["value_json"]["amount"] == "8500.00"
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
    assert bal["reserved"] == VIDEO_SECONDS and bal["available"] == 900 - VIDEO_SECONDS


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
    ents = {"premium_seconds": VIDEO_SECONDS + 20, "basic_seconds": 0}
    c = await ready_student(env, entitlements=ents)
    sid = (await start(c)).json()["session_id"]
    await age_session(env, sid, ready_ago_s=150)
    assert (await end(c, sid, "deadline")).json()["charged_premium_seconds"] == 150
    r = await start(c)
    assert r.status_code == 402 and r.json()["error"] == "insufficient_balance"
    assert (await start(c, VOICE)).status_code == 402


async def test_duplicate_and_concurrent_settlement_charges_once(make_env):
    env = await make_env()
    c = await ready_student(env)
    sid = (await start(c)).json()["session_id"]
    await age_session(env, sid, ready_ago_s=95)
    # End button, deadline tick and page-exit beacon can all fire at once.
    results = await asyncio.gather(
        *[end(c, sid) for _ in range(8)], *[end(c, sid, "deadline") for _ in range(4)]
    )
    assert all(r.status_code == 200 for r in results)
    assert {r.json()["charged_premium_seconds"] for r in results} == {95}
    bal = await balance(c)
    assert bal["consumed"] == 95 and bal["reserved"] == 0
    rows = await env.sql(
        "SELECT count(*)::int AS n FROM audit_events WHERE action='session.settle'"
    )
    assert rows[0]["n"] == 1


async def test_failed_connection_restores_entitlement(make_env):
    env = await make_env()
    c = await ready_student(env)
    sid = (await start(c, VOICE)).json()["session_id"]
    assert (await balance(c, "basic_seconds"))["reserved"] == VOICE_SECONDS
    # The browser never reached media_ready: nothing is charged.
    r = await end(c, sid, "connect_failed")
    body = r.json()
    assert body["status"] == "failed" and body["charged_basic_seconds"] == 0
    bal = await balance(c, "basic_seconds")
    assert bal["consumed"] == 0 and bal["reserved"] == 0 and bal["available"] == 900


async def test_no_student_speech_is_refunded(make_env):
    env = await make_env()
    c = await ready_student(env)
    sid = (await start(c, VOICE)).json()["session_id"]
    await age_session(env, sid, ready_ago_s=40)
    r = await end(c, sid)
    assert r.json()["charged_basic_seconds"] == 0 and r.json()["waived_seconds"] == 40


async def test_deadline_caps_charge_at_practice_length(make_env):
    env = await make_env()
    c = await ready_student(env)
    sid = (await start(c)).json()["session_id"]
    await age_session(env, sid, ready_ago_s=600)  # vendor overran; the student pays the format
    await ingest_transcript(env.pool, env.s, sid, [turn(1, "student", "Hi")])
    r = await end(c, sid, "deadline")
    assert r.json()["charged_premium_seconds"] == VIDEO_SECONDS


# ---------------------------------------------------------------- lifecycle

TURNS = [
    turn(1, "interviewer", "Why this course?"),
    turn(2, "student", "I want to study data science because I worked as a developer."),
    turn(3, "interviewer", "Who is paying for", canceled=True),
    turn(4, "student", "My father will pay. He has savings of 15,000 pounds."),
]


async def test_full_voice_session_lifecycle_with_feedback(make_env):
    env = await make_env()
    c = await ready_student(env)
    r = await start(c, VOICE)
    assert r.status_code == 200, r.text
    s = r.json()
    sid = s["session_id"]
    assert s["mode"] == "voice" and s["practice_seconds"] == VOICE_SECONDS
    assert "not" in s["disclosure"].lower()  # every format says what it is not
    launch = s["launch"]
    assert launch["kind"] == "elevenlabs"
    dv = launch["dynamic_variables"]
    assert dv["session_id"] == sid and dv["university"] == "Example University"
    assert "GBP 28,006.00" in dv["funding_summary"]  # precomputed, never left to the agent

    ev = await media_ready(c, sid)
    assert ev["live"] and ev["practice_ends_at"]
    assert (await media_ready(c, sid))["practice_ends_at"] == ev["practice_ends_at"]  # once
    hb = await c.post(f"/api/sessions/{sid}/client-events", json={"kind": "heartbeat"})
    assert hb.json()["live"]

    # The vendor's transcript can arrive while the call is still live; storing it is
    # idempotent and grading waits for settlement.
    assert (await ingest_transcript(env.pool, env.s, sid, TURNS))["status"] == "stored"
    assert (await ingest_transcript(env.pool, env.s, sid, TURNS))["status"] == "stored"
    rows = await env.sql(
        "SELECT count(*)::int AS n FROM interview_turns WHERE session_id=%s", (sid,)
    )
    assert rows[0]["n"] == 4
    usage = [
        UsageEvent(
            provider_event_id="el-call-1",
            provider="elevenlabs",
            meter="elevenlabs.agent_seconds",
            quantity=60,
            unit="second",
        )
    ]
    async with env.pool.connection() as conn:
        assert await record_usage(conn, env.app.state.prices, sid, usage) == {
            "inserted": 1,
            "duplicates": 0,
        }
        assert await record_usage(conn, env.app.state.prices, sid, usage) == {
            "inserted": 0,
            "duplicates": 1,
        }

    await age_session(env, sid, ready_ago_s=60)
    fin = (await end(c, sid, "deadline")).json()
    assert fin["status"] == "completed" and fin["charged_basic_seconds"] == 60
    assert (await balance(c, "basic_seconds"))["consumed"] == 60

    # Settled with a transcript and no feedback yet: the reconciler grades it.
    rep = await reconcile_once(env.pool, env.s, env.registry, feedback_grace_s=0)
    assert rep["graded"] == 1
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
    led = await env.sql("SELECT quantity, cost_usd_micros FROM usage_ledger")
    assert led[0]["quantity"] == 60 and led[0]["cost_usd_micros"] is None  # unpriced until invoiced


async def test_transcript_arriving_after_settlement_is_graded_immediately(make_env):
    env = await make_env()
    c = await ready_student(env)
    sid = (await start(c, VOICE)).json()["session_id"]
    await age_session(env, sid, ready_ago_s=90)
    await end(c, sid)
    out = await ingest_transcript(env.pool, env.s, sid, TURNS)
    assert out["status"] == "graded" and out["stored"] == 4
    fb = (await c.get(f"/api/sessions/{sid}/feedback")).json()
    assert fb["feedback"]["status"] == "ready"
    assert await ingest_transcript(env.pool, env.s, uuid.uuid4(), TURNS) == {
        "status": "unknown_session"
    }


async def test_browser_exit_beacon_settles_and_marks_vendor_closed(make_env):
    env = await make_env()
    c = await ready_student(env)
    sid = (await start(c)).json()["session_id"]
    await age_session(env, sid, ready_ago_s=30)
    # sendBeacon posts text/plain with cookies and no custom headers.
    r = await c.post(
        f"/api/sessions/{sid}/end",
        content=b"",
        headers={"content-type": "text/plain;charset=UTF-8"},
    )
    assert r.status_code == 200 and r.json()["end_reason"] == "student_ended"
    row = (await env.sql("SELECT vendor_closed_at FROM interview_sessions"))[0]
    assert row["vendor_closed_at"] is not None
    assert (await end(c, sid)).json()["end_reason"] == "student_ended"  # idempotent
    assert (await start(c)).status_code == 200  # a new session can start once settled


async def test_kill_switch_disabled_track_and_rate_limit(make_env):
    env = await make_env(video_tier_enabled=False, max_starts_per_10min=2)
    c = await ready_student(env)
    r = await start(c)
    assert r.status_code == 503 and r.json()["error"] == "tier_unavailable"
    for _ in range(2):
        sid = (await start(c, VOICE)).json()["session_id"]
        await end(c, sid)
    assert (await start(c, VOICE)).status_code == 429


async def test_unknown_track_or_format_is_refused(make_env):
    env = await make_env()
    c = await ready_student(env)
    assert (await start(c, track="ukvi", format_id="interview_5m")).status_code == 422
    assert (await start(c, track="uk_pre_cas", format_id="drill_3m")).status_code == 422


# ---------------------------------------------------------------- reconciliation


async def test_reconciler_reclaims_startup_timeouts_and_stale_sessions(make_env):
    env = await make_env(
        startup_budget_avatar_s=1, teardown_grace_s=1, client_heartbeat_timeout_s=20
    )
    a = await ready_student(env, "a@synthetic.test", "A")
    b = await ready_student(env, "b@synthetic.test", "B")
    sa = (await start(a)).json()["session_id"]
    sb = (await start(b, VOICE)).json()["session_id"]
    await env.sql(
        "UPDATE interview_sessions SET created_at = now() - interval '1 minute' WHERE id=%s", (sa,)
    )
    # B's tab died: ready 100 s ago, last heartbeat 70 s ago, transcript already stored.
    await age_session(env, sb, ready_ago_s=100, heartbeat_ago_s=70)
    await ingest_transcript(env.pool, env.s, sb, [turn(1, "student", "hello there")])
    rep = await reconcile_once(env.pool, env.s, env.registry, feedback_grace_s=0)
    assert rep == {"startup_timeouts": 1, "stale_active": 1, "closed": 0, "graded": 1}
    rows = {r["id"]: r for r in await env.sql("SELECT * FROM interview_sessions")}
    assert rows[uuid.UUID(sa)]["status"] == "failed"
    assert rows[uuid.UUID(sa)]["charged_premium_seconds"] == 0
    assert rows[uuid.UUID(sb)]["status"] == "completed"
    assert rows[uuid.UUID(sb)]["charged_basic_seconds"] == 30  # until the last heartbeat
    assert all(r["vendor_closed_at"] is not None for r in rows.values())
    assert (await balance(a))["available"] == 900
    assert (await balance(b, "basic_seconds"))["consumed"] == 30
    rep2 = await reconcile_once(env.pool, env.s, env.registry, feedback_grace_s=0)
    assert rep2 == {"startup_timeouts": 0, "stale_active": 0, "closed": 0, "graded": 0}


@pytest.mark.parametrize("n_students", [5])
async def test_many_students_in_parallel_do_not_interfere(make_env, n_students):
    env = await make_env()
    clients = [await ready_student(env, f"s{i}@synthetic.test", f"S{i}") for i in range(n_students)]
    results = await asyncio.gather(*[start(c) for c in clients for _ in range(4)])
    ok = [r for r in results if r.status_code == 200]
    assert len(ok) == n_students
    rows = await env.sql("SELECT count(DISTINCT student_id)::int AS n FROM interview_sessions")
    assert rows[0]["n"] == n_students


# ---------------------------------------------------------------- vendor usage ledger


async def test_cumulative_usage_only_increases(make_env):
    env = await make_env()
    c = await ready_student(env)
    sid = (await start(c, VOICE)).json()["session_id"]

    def ev(q):
        return [
            UsageEvent(
                provider_event_id="cum:elevenlabs.agent_seconds",
                provider="elevenlabs",
                meter="elevenlabs.agent_seconds",
                quantity=q,
                unit="second",
                cumulative=True,
            )
        ]

    async with env.pool.connection() as conn:
        for q in (30, 60, 45, 90):
            await record_usage(conn, env.app.state.prices, sid, ev(q))
    rows = await env.sql("SELECT quantity FROM usage_ledger")
    assert len(rows) == 1 and rows[0]["quantity"] == 90
