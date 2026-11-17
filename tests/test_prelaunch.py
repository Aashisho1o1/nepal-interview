"""Bugs found in the pre-launch review, each reproduced first and kept as a regression test."""

from __future__ import annotations

import asyncio

import pytest

from conftest import age_session, login_student, media_ready, ready_student, start
from interview_api import plans
from test_video_providers import ENV, LITE, Vendors


async def test_a_launch_that_finishes_after_the_session_ended_is_withheld_and_stopped(make_env):
    """The student ends a session (or it is refunded) while the vendor is still creating
    it. The late launch must not reach the student and must be stopped at the vendor."""
    vendors = Vendors()
    env = await make_env(provider_env=ENV, provider_http=vendors.client)
    c = await ready_student(env)

    starting = asyncio.create_task(start(c, LITE))
    while not vendors.calls:  # wait until the vendor is creating the session (it takes 50 ms)
        await asyncio.sleep(0.005)
    [sess] = (await c.get("/api/sessions")).json()
    assert (await c.post(f"/api/sessions/{sess['id']}/end")).status_code == 200

    r = await starting
    assert r.status_code == 409 and r.json()["error"] == "session_ended"
    [stop] = vendors.to("/v1/sessions/stop")
    assert b"la-1" in stop.content


async def test_a_failed_stop_of_a_late_launch_is_left_for_the_reconciler(make_env):
    vendors = Vendors(stop_status=500)
    env = await make_env(provider_env=ENV, provider_http=vendors.client)
    c = await ready_student(env)
    starting = asyncio.create_task(start(c, LITE))
    while not vendors.calls:
        await asyncio.sleep(0.005)
    [sess] = (await c.get("/api/sessions")).json()
    await c.post(f"/api/sessions/{sess['id']}/end")
    assert (await starting).status_code == 409
    [row] = await env.sql(
        "SELECT vendor_ref, vendor_closed_at, launch_json FROM interview_sessions"
    )
    assert row["vendor_ref"] == "la-1" and row["vendor_closed_at"] is None  # retried later
    assert row["launch_json"] is None


async def test_successful_sign_ins_are_rate_limited_per_account(make_env):
    env = await make_env()
    await login_student(env, "a@synthetic.test", "Student A")  # the first of 8 allowed
    codes = []
    async with env.client() as c:
        for _ in range(10):
            r = await c.post(
                "/api/auth/login",
                json={"email": "a@synthetic.test", "password": "pw-for-tests-123"},
            )
            codes.append(r.status_code)
    assert codes == [200] * 7 + [429] * 3


async def test_parallel_wrong_passwords_cannot_exceed_the_per_account_limit(make_env):
    env = await make_env()
    await login_student(env, "a@synthetic.test", "Student A")
    async with env.client() as c:
        rs = await asyncio.gather(
            *(
                c.post("/api/auth/login", json={"email": "a@synthetic.test", "password": f"x{i}"})
                for i in range(20)
            )
        )
    # The sign-in above used 1 of the 8 attempts.
    assert sorted(r.status_code for r in rs) == [401] * 7 + [429] * 13


async def test_correct_sign_ins_from_one_network_do_not_block_each_other(make_env):
    env = await make_env()
    for i in range(35):  # more than the per-network limit on failures
        await login_student(env, f"s{i}@synthetic.test", f"Student {i}")


async def test_parallel_sign_ups_cannot_exceed_the_network_limit(make_env):
    env = await make_env(signups_per_network_per_hour=5)
    async with env.client() as c:
        rs = await asyncio.gather(
            *(
                c.post(
                    "/api/auth/signup",
                    json={"name": "N", "email": f"p{i}@example.test", "password": "long-enough-pw"},
                )
                for i in range(15)
            )
        )
    assert sum(r.status_code == 200 for r in rs) == 5


async def test_parallel_wrong_promo_codes_cannot_exceed_five_guesses(make_env):
    env = await make_env()
    c = await ready_student(env)
    rs = await asyncio.gather(
        *(c.post("/api/promo/redeem", json={"code": f"GUESS{i}"}) for i in range(15))
    )
    assert sum(r.status_code == 404 for r in rs) == 5


async def test_a_room_can_redeem_a_right_code_at_once(make_env):
    from interview_api import plans

    env = await make_env()
    await env.sql(
        "INSERT INTO promo_codes (code_hash, label, premium_seconds, basic_seconds, valid_days) "
        "VALUES (%s, 'seminar', 0, 120, 30)",
        (plans.code_hash("SEMINAR"),),
    )
    students = [await ready_student(env, f"r{i}@synthetic.test", f"R {i}") for i in range(8)]
    rs = await asyncio.gather(
        *(c.post("/api/promo/redeem", json={"code": "SEMINAR"}) for c in students)
    )
    assert [r.status_code for r in rs] == [200] * 8


async def test_a_detail_cannot_grow_without_limit(make_env):
    env = await make_env()
    c = await login_student(env, "a@synthetic.test", "Student A")
    r = await c.put("/api/profile/details", json={"english_test": "x" * 1_000})  # cap is 400
    assert r.status_code == 422


@pytest.mark.parametrize("bad", ["1e1000000", "-1e1000000"])
def test_huge_exponents_are_input_errors(bad):
    from interview_core.funding import FundingInputError, _amount

    with pytest.raises(FundingInputError):
        _amount(bad, "test")


async def test_simultaneous_first_snapshots_both_succeed(make_env):
    env = await make_env()
    c = await login_student(env, "a@synthetic.test", "A")  # no snapshot yet
    rs = await asyncio.gather(*(start(c) for _ in range(4)))
    assert sorted(r.status_code for r in rs) == [200, 409, 409, 409]  # one live session


# ---------------------------------------------------------------- round 1 (2026-11-17)


async def test_a_huge_request_body_is_refused_before_it_is_read_in_full(make_env):
    env = await make_env()
    async with env.client() as c:
        r = await c.post("/api/auth/login", content=b'{"email":"' + b"a" * 100_000 + b'"}')
        assert r.status_code == 413

        async def chunks():  # streamed, so there is no Content-Length to check up front
            for _ in range(20):
                yield b"a" * 8_000

        r = await c.post(
            "/api/auth/login", content=chunks(), headers={"content-type": "application/json"}
        )
    assert r.status_code == 413 and r.headers["cache-control"] == "no-store"


async def test_the_clock_reply_gives_seconds_left_so_the_phone_clock_does_not_matter(make_env):
    env = await make_env()
    c = await ready_student(env)
    sid = (await start(c)).json()["session_id"]
    assert 115 < (await media_ready(c, sid))["seconds_left"] <= 120

    async def heartbeat():
        r = await c.post(f"/api/sessions/{sid}/client-events", json={"kind": "heartbeat"})
        return r.json()

    await age_session(env, sid, ready_ago_s=100)  # of 120 s
    assert 15 < (await heartbeat())["seconds_left"] <= 20
    await age_session(env, sid, ready_ago_s=200)
    reply = await heartbeat()
    assert reply["seconds_left"] == 0 and reply["live"] is True  # until it is ended
    await c.post(f"/api/sessions/{sid}/end")
    assert (await heartbeat())["live"] is False


async def test_a_media_ready_after_the_end_does_not_start_the_clock(make_env):
    env = await make_env()
    c = await ready_student(env)
    sid = (await start(c)).json()["session_id"]
    assert (await c.post(f"/api/sessions/{sid}/end")).status_code == 200
    assert (await media_ready(c, sid))["live"] is False
    [row] = await env.sql("SELECT media_ready_at FROM interview_sessions")
    assert row["media_ready_at"] is None


async def test_typos_from_one_network_do_not_block_a_room_from_a_right_code(make_env):
    env = await make_env()
    await env.sql(
        "INSERT INTO promo_codes (code_hash, label, premium_seconds, basic_seconds, valid_days) "
        "VALUES (%s,'room',120,0,30)",
        (plans.code_hash("LEEDS2027"),),
    )
    for i in range(5):  # five students mistype it on the venue Wi-Fi
        s = await login_student(env, f"t{i}@synthetic.test", "T", entitlements={})
        assert (await s.post("/api/promo/redeem", json={"code": "LEEDS2072"})).status_code == 404
    late = await login_student(env, "late@synthetic.test", "L", entitlements={})
    assert not await env.sql("SELECT 1 FROM entitlements")  # {} means no starting time
    assert (await late.post("/api/promo/redeem", json={"code": "LEEDS2027"})).status_code == 200


async def test_many_accounts_guessing_codes_from_one_network_are_blocked(make_env):
    env = await make_env()
    for i in range(10):  # each account's 5 wrong codes: 50 for the network, its limit
        s = await login_student(env, f"g{i}@synthetic.test", "G", entitlements={})
        for j in range(5):
            r = await s.post("/api/promo/redeem", json={"code": f"GUESS{i}{j}"})
            assert r.status_code == 404
    fresh = await login_student(env, "fresh@synthetic.test", "F", entitlements={})
    assert (await fresh.post("/api/promo/redeem", json={"code": "GUESS"})).status_code == 429


async def test_saving_unchanged_details_does_not_add_a_snapshot(make_env):
    env = await make_env()
    c = await login_student(env, "a@synthetic.test", "A", entitlements={})
    details = {"university": "Leeds", "tuition_gbp": "18500", "savings_gbp": "0"}  # 0 = none
    first = await c.put("/api/profile/details", json=details)
    second = await c.put("/api/profile/details", json=details)
    assert first.status_code == second.status_code == 200
    assert first.json()["version"] == second.json()["version"]

    # New funding rules give the same details a new result, which is saved.
    await env.sql("UPDATE profile_snapshots SET funding_json='{}'")
    third = await c.put("/api/profile/details", json=details)
    assert third.json()["version"] == first.json()["version"] + 1

    await env.sql("UPDATE profile_snapshots SET version=version+998")  # now 999 and 1000
    r = await c.put("/api/profile/details", json={**details, "savings_gbp": "100"})
    assert r.status_code == 429


async def test_funds_without_costs_are_refused_and_a_paid_deposit_is_on_time(make_env):
    env = await make_env()
    c = await login_student(env, "a@synthetic.test", "A", entitlements={})
    r = await c.put("/api/profile/details", json={"savings_gbp": "20000"})
    assert r.status_code == 422 and "tuition" in r.json()["detail"]
    # The deposit is dated today, after this start month, but it is paid, so on time.
    r = await c.put(
        "/api/profile/details",
        json={"tuition_gbp": "18500", "deposit_gbp": "5000", "start_month": "2020-01"},
    )
    assert r.status_code == 200
    assert not any("after your programme starts" in q for q in r.json()["funding"]["questions"])


async def test_ending_a_session_twice_stops_the_vendor_once(make_env):
    vendors = Vendors()
    env = await make_env(provider_env=ENV, provider_http=vendors.client)
    c = await ready_student(env)
    sid = (await start(c, LITE)).json()["session_id"]
    for _ in range(2):
        assert (await c.post(f"/api/sessions/{sid}/end")).status_code == 200
    assert len(vendors.to("/v1/sessions/stop")) == 1
