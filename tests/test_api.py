"""Session API: auth, isolation, quota races, settlement, cleanup, reconciliation.

Every test goes through the providers students actually get (the LiveAvatar embed
for video, the ElevenLabs agent for voice). None needs a vendor to be reachable: the
browser reports the lifecycle and the server owns the clock and the credits.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta

import httpx
import pytest

from conftest import (
    ORIGIN,
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
from interview_api import plans
from interview_api.config import get_settings
from interview_api.db import RECONCILE_LOCK
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


async def test_students_can_practise_with_no_details_and_corrections_keep_shape(make_env):
    env = await make_env()
    c = await login_student(env, "a@synthetic.test", "Asha Student")
    # No details checked, no snapshot: practice still starts, on an empty snapshot.
    r = await start(c, VOICE)
    assert r.status_code == 200, r.text
    dv = r.json()["launch"]["dynamic_variables"]
    assert dv["student_first_name"] == "Asha"
    assert dv["university"] == dv["family_income"] == dv["funding_summary"] == "not provided"
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


QUICK = {
    "name": "Sita Rai",
    "university": "University of Leeds",
    "course": "MSc Data Science",
    "home_country": "Nepal",
    "family_income_npr": "18,00,000",
}


async def test_about_you_quick_details_reach_the_interviewer(make_env):
    env = await make_env(free_voice_sessions_per_day=1, free_video_days=3)
    async with env.client() as c:
        assert (await signup(c, name="Sita")).status_code == 200
        # A new account starts with only its name.
        assert (await c.get("/api/profile/facts")).json() == []
        assert (await c.get("/api/profile/details")).json()["name"] == "Sita"
        r = await c.put("/api/profile/details", json=QUICK)
        assert r.status_code == 200, r.text
        assert "error" in r.json()["funding"]  # no costs given: no funding table
        got = (await c.get("/api/profile/details")).json()
        assert {k: got[k] for k in QUICK} == {**QUICK, "family_income_npr": "1800000"}
        assert (await c.get("/api/me")).json()["display_name"] == "Sita Rai"
        dv = (await start(c, VOICE)).json()["launch"]["dynamic_variables"]
        assert dv["student_first_name"] == "Sita"
        assert dv["university"] == "University of Leeds"
        assert dv["course"] == "MSc Data Science"
        assert dv["home_country"] == "Nepal"
        assert dv["family_income"] == "NPR 1,800,000 per year"
        assert dv["funding_summary"] == "not provided"
    # Another student sees none of it.
    async with env.client() as other:
        assert (await signup(other, email="other@example.test", name="Ram")).status_code == 200
        theirs = (await other.get("/api/profile/details")).json()
        assert theirs["university"] == "" and theirs["name"] == "Ram"


async def test_full_bio_computes_funding_and_saving_replaces_values(make_env):
    env = await make_env()
    async with env.client() as c:
        assert (await signup(c)).status_code == 200
        bio = {
            **QUICK,
            "start_month": "2027-09",
            "tuition_gbp": "18500",
            "living_gbp": "12006",
            "scholarship_gbp": "2500",
            "deposit_gbp": "5000",
            "savings_gbp": "15000",
            "loan_gbp": "8500",
            "english_test": "IELTS 6.5",
        }
        f = (await c.put("/api/profile/details", json=bio)).json()["funding"]
        assert f["required_minor"] == 3_050_600 and f["net_required_minor"] == 2_800_600
        assert f["identified_funds_minor"] == 2_850_000 and f["gap_minor"] == 0
        # Saving again replaces values, it never adds them up twice; a cleared field goes.
        f = (
            await c.put(
                "/api/profile/details", json={**bio, "tuition_gbp": "20000", "loan_gbp": ""}
            )
        ).json()["funding"]
        assert f["required_minor"] == 3_200_600
        assert f["identified_funds_minor"] == 2_000_000
        assert (await c.get("/api/profile/details")).json()["loan_gbp"] == ""
        for bad in ({"tuition_gbp": "a lot"}, {"tuition_gbp": "-5"}, {"start_month": "Sept"}):
            assert (await c.put("/api/profile/details", json=bad)).status_code == 422


async def test_demo_account_form_starts_from_example_facts_and_saving_replaces_them(make_env):
    env = await make_env()
    c = await login_student(env, "a@synthetic.test", "A")
    got = (await c.get("/api/profile/details")).json()
    assert got["university"] == "Example University" and got["tuition_gbp"] == "18500"
    f = (await c.put("/api/profile/details", json={**got, "living_gbp": "10000"})).json()["funding"]
    # Example tuition 18,500 replaced by the same typed value, not added to it.
    assert f["required_minor"] == 2_850_000


async def test_session_with_no_details_still_gets_feedback(make_env):
    env = await make_env()
    c = await login_student(env, "a@synthetic.test", "A")
    sid = (await start(c, VOICE)).json()["session_id"]
    await age_session(env, sid, ready_ago_s=90)
    await end(c, sid)
    out = await ingest_transcript(env.pool, env.s, sid, TURNS)
    assert out["status"] == "graded"
    fb = (await c.get(f"/api/sessions/{sid}/feedback")).json()
    assert fb["feedback"]["status"] == "ready"


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
    await age_session(env, sid, ready_ago_s=100)
    assert (await end(c, sid, "deadline")).json()["charged_premium_seconds"] == 100
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
    env = await make_env(no_input_refund_s=60)
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
    assert launch["kind"] == "voice_call"
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
    assert (await start(c, track="ukvi")).status_code == 422
    assert (await start(c, format_id="voice_2m")).status_code == 422  # video with voice format
    assert (await start(c, track="uk_pre_cas", format_id="drill_3m")).status_code == 422


# ---------------------------------------------------------------- sign-up


async def signup(c, email="new@example.test", name="  Sita   Rai ", password="long-enough-pw"):
    return await c.post(
        "/api/auth/signup", json={"name": name, "email": email, "password": password}
    )


async def test_signup_creates_a_signed_in_student_who_can_practise(make_env):
    env = await make_env(free_voice_sessions_per_day=1, free_video_days=3)
    async with env.client() as c:
        r = await signup(c, email="New@Example.TEST")
        assert r.status_code == 200, r.text
        me = (await c.get("/api/me")).json()  # the sign-up also signed them in
        assert me["email"] == "new@example.test"
        assert me["display_name"] == "Sita Rai"
        # Day one of the free plan: one video and one voice session.
        assert me["balances"]["premium_seconds"]["available"] == VIDEO_SECONDS
        assert me["balances"]["basic_seconds"]["available"] == VOICE_SECONDS
        assert (await start(c, VOICE)).status_code == 200  # no details needed
        # The new password works for a normal sign-in.
        out = env.client()
        r = await out.post(
            "/api/auth/login", json={"email": "new@example.test", "password": "long-enough-pw"}
        )
        assert r.status_code == 200


async def test_signup_rejects_duplicates_bad_input_and_foreign_origins(make_env):
    env = await make_env()
    async with env.client() as c:
        assert (await signup(c)).status_code == 200
        r = await signup(c, email="NEW@example.test", password="another-password")
        assert r.status_code == 409
        assert "already exists" in r.json()["detail"]
        assert (await signup(c, email="b@example.test", password="short")).status_code == 422
        assert (await signup(c, email="not-an-email")).status_code == 422
        assert (await signup(c, email="c@example.test", name="   ")).status_code == 422
    # The existing account's password was not replaced by the duplicate attempt.
    async with env.client() as c:
        r = await c.post(
            "/api/auth/login", json={"email": "new@example.test", "password": "another-password"}
        )
        assert r.status_code == 401
    foreign = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=env.app),
        base_url=ORIGIN,
        headers={"origin": "https://evil.test"},
    )
    async with foreign:
        assert (await signup(foreign, email="d@example.test")).status_code == 403


async def test_same_origin_requests_pass_without_configuring_the_address(make_env):
    """The deployed site's address needn't be in ALLOWED_ORIGINS: the proxy reports the
    host the browser opened, and the Origin must match it."""
    env = await make_env()  # ALLOWED_ORIGINS is only http://test
    site = "practice.up.railway.app"

    async def try_signup(origin: str, forwarded_host: str, email: str) -> int:
        c = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=env.app),
            base_url="http://api.railway.internal:8000",
            headers={"origin": origin, "x-forwarded-host": forwarded_host},
        )
        async with c:
            return (await signup(c, email=email)).status_code

    assert await try_signup(f"https://{site}", site, "a@example.test") == 200
    assert await try_signup("https://evil.test", site, "b@example.test") == 403
    assert await try_signup(f"https://{site}.evil.test", site, "c@example.test") == 403


async def test_signup_is_rate_limited_per_network_and_can_be_closed(make_env):
    env = await make_env()
    async with env.client() as c:
        for i in range(5):
            assert (await signup(c, email=f"u{i}@example.test")).status_code == 200
        r = await signup(c, email="u5@example.test")
        assert r.status_code == 429
    closed = await make_env(signup_enabled=False)
    async with closed.client() as c:
        assert (await signup(c)).status_code == 403


# ---------------------------------------------------------------- free plan and codes


async def _student_id(env, email):
    rows = await env.sql(
        "SELECT p.id FROM student_profiles p JOIN users u ON u.id=p.user_id WHERE u.email=%s",
        (email,),
    )
    return rows[0]["id"]


async def test_free_plan_one_voice_a_day_and_video_on_the_first_three_days(make_env):
    env = await make_env(free_voice_sessions_per_day=1, free_video_days=3)
    async with env.client() as c:
        assert (await signup(c)).status_code == 200
        sid = (await start(c, VOICE)).json()["session_id"]
        await age_session(env, sid, ready_ago_s=170)  # they talked for almost all of it
        await end(c, sid)
        r = await start(c, VOICE)  # today's free voice session is used
        assert r.status_code == 402 and "Come back tomorrow" in r.json()["message"]
    student = await _student_id(env, "new@example.test")
    joined = (await env.sql("SELECT created_at FROM student_profiles WHERE id=%s", (student,)))[0][
        "created_at"
    ]
    async with env.pool.connection() as conn:
        for day in (0, 0, 1, 2, 3, 10):  # day 0 twice: grants are idempotent
            await plans.ensure_free_grants(conn, student, env.s, now=joined + timedelta(days=day))
    rows = await env.sql(
        "SELECT bucket, package_version, granted_seconds, expires_at FROM entitlements "
        "WHERE student_id=%s",
        (student,),
    )
    video = [r for r in rows if r["bucket"] == "premium_seconds"]
    voice = [r for r in rows if r["bucket"] == "basic_seconds"]
    assert len(video) == 3 and all(r["granted_seconds"] == VIDEO_SECONDS for r in video)
    assert len(voice) == 5 and all(r["granted_seconds"] == VOICE_SECONDS for r in voice)
    for r in rows:  # each grant ends at the next midnight in Nepal
        local = r["expires_at"].astimezone(plans.NEPAL)
        assert (local.hour, local.minute) == (0, 0)
        assert local.date().isoformat() > r["package_version"].split(":")[1]


NO_CREDIT = {"premium_seconds": 0, "basic_seconds": 0}


async def _make_code(env, code="LEEDS2027", video=3, voice=10, max_uses=None, active=True):
    await env.sql(
        "INSERT INTO promo_codes (code_hash, label, premium_seconds, basic_seconds, valid_days, "
        "max_uses, active) VALUES (%s,'test',%s,%s,30,%s,%s)",
        (plans.code_hash(code), video * VIDEO_SECONDS, voice * VOICE_SECONDS, max_uses, active),
    )


async def test_shared_code_grants_once_per_student_up_to_its_cap(make_env):
    env = await make_env()
    await _make_code(env, max_uses=2)
    a = await login_student(env, "a@synthetic.test", "A", entitlements=NO_CREDIT)
    r = await a.post("/api/promo/redeem", json={"code": "  leeds 2027 "})  # case/spaces ignored
    assert r.status_code == 200, r.text
    assert r.json() == {"video_sessions": 3, "voice_sessions": 10, "valid_days": 30}
    assert (await balance(a))["available"] == 3 * VIDEO_SECONDS
    assert (await balance(a, "basic_seconds"))["available"] == 10 * VOICE_SECONDS
    assert (await a.post("/api/promo/redeem", json={"code": "LEEDS2027"})).status_code == 409
    b = await login_student(env, "b@synthetic.test", "B", entitlements=NO_CREDIT)
    assert (await b.post("/api/promo/redeem", json={"code": "LEEDS2027"})).status_code == 200
    cc = await login_student(env, "c@synthetic.test", "C", entitlements=NO_CREDIT)
    r = await cc.post("/api/promo/redeem", json={"code": "LEEDS2027"})
    assert r.status_code == 410  # cap of two students reached
    assert (await balance(cc))["available"] == 0


async def test_wrong_codes_are_limited_and_disabled_codes_do_nothing(make_env):
    env = await make_env()
    await _make_code(env, code="OLDCODE", active=False)
    c = await login_student(env, "a@synthetic.test", "A", entitlements=NO_CREDIT)
    assert (await c.post("/api/promo/redeem", json={"code": "OLDCODE"})).status_code == 404
    for _ in range(4):
        assert (await c.post("/api/promo/redeem", json={"code": "GUESS"})).status_code == 404
    r = await c.post("/api/promo/redeem", json={"code": "GUESS"})
    assert r.status_code == 429 and "Too many tries" in r.json()["detail"]


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


async def test_cron_reconcile_route_needs_the_secret_and_skips_overlapping_runs(make_env):
    env = await make_env(cron_secret="s3cret-for-tests-only")
    path = "/api/internal/reconcile"
    async with env.client() as c:
        assert (await c.get(path)).status_code == 401
        assert (await c.get(path, headers={"authorization": "Bearer wrong"})).status_code == 401
        ok = {"authorization": "Bearer s3cret-for-tests-only"}
        r = await c.get(path, headers=ok)
        assert r.status_code == 200
        assert r.json() == {"startup_timeouts": 0, "stale_active": 0, "closed": 0, "graded": 0}
        # Another run holds the lock: a duplicate delivery does nothing.
        async with env.pool.connection() as conn, conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(%s)", (RECONCILE_LOCK,))
            assert (await c.get(path, headers=ok)).json() == {"skipped": "already running"}


async def test_cron_reconcile_route_is_closed_without_a_configured_secret(make_env):
    env = await make_env(cron_secret="")
    async with env.client() as c:
        r = await c.get("/api/internal/reconcile", headers={"authorization": "Bearer "})
        assert r.status_code == 401


def test_vercel_deployment_urls_are_trusted_origins(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://practice.example")
    monkeypatch.setenv("VERCEL_URL", "proj-abc123.vercel.app")
    monkeypatch.setenv("VERCEL_BRANCH_URL", "")
    monkeypatch.delenv("VERCEL_PROJECT_PRODUCTION_URL", raising=False)
    assert get_settings().allowed_origins == (
        "https://practice.example",
        "https://proj-abc123.vercel.app",
    )


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


# ---------------------------------------------------------------- team review


async def test_team_sees_every_session_with_rating_and_transcript(make_env):
    env = await make_env(team_emails=frozenset({"founder@synthetic.test"}))
    student = await ready_student(env, "a@synthetic.test", "Student A")
    founder = await ready_student(env, "founder@synthetic.test", "Founder")

    sid = (await start(student, VOICE)).json()["session_id"]
    await media_ready(student, sid)
    await ingest_transcript(env.pool, env.s, sid, TURNS)
    await age_session(env, sid, ready_ago_s=60)
    await end(student, sid)
    rating = {
        "realism": 2,
        "reply_speed": "noticeably_slow",
        "audio_video_ok": True,
        "would_use_again": False,
        "comment": "The interviewer cut me off.",
    }
    assert (await student.post(f"/api/sessions/{sid}/rating", json=rating)).status_code == 200

    # Students (and signed-out visitors) cannot tell the page exists.
    assert (await student.get("/api/team/sessions")).status_code == 404
    assert (await env.client().get("/api/team/sessions")).status_code == 401

    r = await founder.get("/api/team/sessions")
    assert r.status_code == 200, r.text
    [row] = r.json()
    assert row["id"] == sid and row["email"] == "a@synthetic.test" and row["mode"] == "voice"
    assert row["realism"] == 2 and row["comment"] == "The interviewer cut me off."
    assert row["talked_seconds"] >= 60
    assert [t["speaker"] for t in row["turns"]] == ["interviewer", "student", "student"]
