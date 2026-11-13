"""Bugs found in the pre-launch review, each reproduced first and kept as a regression test."""

from __future__ import annotations

import asyncio

import pytest

from conftest import login_student, ready_student, start
from test_video_providers import ENV, LITE, Vendors


async def test_a_launch_that_finishes_after_the_session_ended_is_withheld_and_stopped(make_env):
    """The student ends a session (or it is refunded) while the vendor is still creating
    it. The late launch must not reach the student and must be stopped at the vendor."""
    vendors = Vendors()
    env = await make_env(provider_env=ENV, provider_http=vendors.client)
    c = await ready_student(env)

    starting = asyncio.create_task(start(c, LITE))
    await asyncio.sleep(0.02)  # the vendor is now creating the session (it takes 50 ms)
    [sess] = (await c.get("/api/sessions")).json()
    assert (await c.post(f"/api/sessions/{sess['id']}/end")).status_code == 200

    r = await starting
    assert r.status_code == 409 and r.json()["error"] == "session_ended"
    [stop] = vendors.to("/v1/sessions/stop")
    assert b"la-1" in stop.content


async def test_successful_sign_ins_are_rate_limited_per_network(make_env):
    env = await make_env()
    await login_student(env, "a@synthetic.test", "Student A")
    codes = []
    async with env.client() as c:
        for _ in range(70):
            r = await c.post(
                "/api/auth/login",
                json={"email": "a@synthetic.test", "password": "pw-for-tests-123"},
            )
            codes.append(r.status_code)
    assert 429 in codes


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


async def test_a_corrected_fact_cannot_grow_without_limit(make_env):
    env = await make_env()
    c = await login_student(env, "a@synthetic.test", "Student A")
    facts = (await c.get("/api/profile/facts")).json()
    f = next(x for x in facts if isinstance(x["value_json"], dict))
    r = await c.patch(
        f"/api/profile/facts/{f['ref']}",
        json={"status": "corrected", "value": {"label": "x" * 1_000_000}},
    )
    assert r.status_code == 422


@pytest.mark.parametrize("bad", ["1e1000000", "-1e1000000"])
def test_huge_exponents_are_input_errors(bad):
    from interview_core.funding import FundingInputError, _amount

    with pytest.raises(FundingInputError):
        _amount(bad, "test")


async def test_simultaneous_first_snapshots_both_succeed(make_env):
    env = await make_env()
    async with env.client() as c:
        await c.post(
            "/api/auth/signup",
            json={"name": "New", "email": "new@example.test", "password": "long-enough-pw"},
        )
        rs = await asyncio.gather(*(c.post("/api/profile/snapshot") for _ in range(4)))
    assert [r.status_code for r in rs] == [200] * 4
