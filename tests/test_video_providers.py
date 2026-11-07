"""The side-by-side video cards: LiveAvatar LITE (video_a) and Keyframe (video_b), both
voiced by the same ElevenLabs agent. No vendor is called."""

from __future__ import annotations

import asyncio
import json

import httpx

from conftest import key, ready_student, start
from interview_api.config import Settings
from interview_api.providers import load_registry
from interview_api.reconcile import reconcile_once

LITE, KEYFRAME = "video_a", "video_b"
SECRETS = ("la-secret", "kf-secret", "xi-secret", "secret-id-1")
ENV = {
    "ELEVENLABS_VIDEO_AGENT_ID": "agent_video",
    "ELEVENLABS_API_KEY": "xi-secret",
    "LIVEAVATAR_API_KEY": "la-secret",
    "LIVEAVATAR_AVATAR_ID": "avatar-1",
    "LIVEAVATAR_ELEVENLABS_SECRET_ID": "secret-id-1",
    "KEYFRAME_API_KEY": "kf-secret",
    "KEYFRAME_PERSONA": "public:cosmo_persona-1.5-live",
}


class Vendors:
    """Stands in for all three vendors and records every call."""

    def __init__(self, mint_status=200, stop_status=200, mint_body=None):
        self.calls: list[httpx.Request] = []
        self.mint_status, self.stop_status, self.mint_body = mint_status, stop_status, mint_body
        self.client = httpx.AsyncClient(transport=httpx.MockTransport(self.handle))

    def to(self, path: str) -> list[httpx.Request]:
        return [c for c in self.calls if c.url.path == path]

    async def handle(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(req)
        await asyncio.sleep(0.05)  # long enough for concurrent starts to overlap
        path = req.url.path
        if path == "/v1/sessions/token":
            body = self.mint_body or {"data": {"session_id": "la-1", "session_token": "la-tok"}}
            return httpx.Response(self.mint_status, json=body)
        if path == "/v1/sessions/stop":
            return httpx.Response(self.stop_status, json={"data": None})
        if path == "/v1/sessions":
            return httpx.Response(
                200,
                json={
                    "server_url": "wss://rtc.test",
                    "participant_token": "kf-tok",
                    "agent_identity": "avatar-7",
                    "voice_agent_details": None,
                },
            )
        if path == "/v1/convai/conversation/get-signed-url":
            return httpx.Response(200, json={"signed_url": "wss://el.test/signed"})
        return httpx.Response(404)


async def student(make_env, vendors: Vendors):
    env = await make_env(provider_env=ENV, provider_http=vendors.client)
    return env, await ready_student(env)


def test_a_missing_setting_only_turns_that_card_off():
    s = Settings(database_url="unused")
    assert load_registry(s, env=ENV).order == [LITE, KEYFRAME]
    no_agent = {k: v for k, v in ENV.items() if k != "ELEVENLABS_VIDEO_AGENT_ID"}
    assert load_registry(s, env=no_agent).order == []
    no_keyframe = {k: v for k, v in ENV.items() if k != "KEYFRAME_API_KEY"}
    reg = load_registry(s, env=no_keyframe)
    assert reg.order == [LITE] and "KEYFRAME_API_KEY" in reg.disabled[KEYFRAME]


async def test_every_student_is_offered_both(make_env):
    env, c = await student(make_env, Vendors())
    assert [p["id"] for p in (await c.get("/api/providers")).json()] == [LITE, KEYFRAME]


async def test_lite_token_uses_the_agent_and_sends_no_student_details(make_env):
    vendors = Vendors()
    env, c = await student(make_env, vendors)
    r = await start(c, LITE)
    assert r.status_code == 200, r.text
    assert r.json()["launch"] == {"kind": "video_a", "session_token": "la-tok"}
    (req,) = vendors.to("/v1/sessions/token")
    assert req.headers["x-api-key"] == "la-secret"
    sent = json.loads(req.content)
    assert sent["mode"] == "LITE" and sent["avatar_id"] == "avatar-1"
    assert sent["is_sandbox"] is False
    assert (
        sent["max_session_duration"] == env.s.startup_budget_avatar_s + 120 + env.s.closing_grace_s
    )
    agent = sent["elevenlabs_agent_config"]
    assert agent["agent_id"] == "agent_video" and agent["secret_id"] == "secret-id-1"
    assert agent["dynamic_variables"]["student_first_name"] == "there"
    assert agent["dynamic_variables"]["university"] == "not provided"
    assert not any(s in json.dumps(r.json()) for s in SECRETS)


async def test_keyframe_launch_keeps_keys_here_and_details_away_from_keyframe(make_env):
    vendors = Vendors()
    env, c = await student(make_env, vendors)
    r = await start(c, KEYFRAME)
    assert r.status_code == 200, r.text
    launch = r.json()["launch"]
    assert launch["kind"] == "video_b"
    assert launch["session_details"] == {
        "server_url": "wss://rtc.test",
        "participant_token": "kf-tok",
        "agent_identity": "avatar-7",
    }
    assert launch["voice_agent"] == {
        "type": "elevenlabs",
        "agent_id": "agent_video",
        "signed_url": "wss://el.test/signed",
    }
    # The student's details go to the browser, for ElevenLabs. Keyframe gets none of them.
    assert launch["dynamic_variables"]["student_first_name"] == "Student"
    assert launch["dynamic_variables"]["university"] != "not provided"
    assert not any(s in json.dumps(launch) for s in SECRETS)
    (el,) = vendors.to("/v1/convai/conversation/get-signed-url")
    assert el.headers["xi-api-key"] == "xi-secret" and el.url.params["agent_id"] == "agent_video"
    (kf,) = vendors.to("/v1/sessions")
    assert kf.headers["authorization"] == "Bearer kf-secret"
    assert json.loads(kf.content) == {"persona_slug": ENV["KEYFRAME_PERSONA"]}


async def test_sandbox_asks_for_no_more_than_it_allows(make_env):
    vendors = Vendors()
    env = await make_env(
        provider_env={**ENV, "LIVEAVATAR_SANDBOX": "true"}, provider_http=vendors.client
    )
    c = await ready_student(env)
    assert (await start(c, LITE)).status_code == 200
    (req,) = vendors.to("/v1/sessions/token")
    sent = json.loads(req.content)
    assert sent["is_sandbox"] is True and sent["max_session_duration"] == 60


async def test_five_concurrent_starts_create_one_vendor_session(make_env):
    vendors = Vendors()
    env, c = await student(make_env, vendors)
    same = key()
    replies = await asyncio.gather(*(start(c, LITE, headers=same) for _ in range(5)))
    assert {r.status_code for r in replies} == {200}
    assert len({r.json()["session_id"] for r in replies}) == 1
    assert {r.json()["launch"]["session_token"] for r in replies} == {"la-tok"}
    assert "vendor_ref" not in replies[0].json()["launch"]
    assert len(vendors.to("/v1/sessions/token")) == 1


async def test_ending_stops_the_vendor_session(make_env):
    vendors = Vendors()
    env, c = await student(make_env, vendors)
    sid = (await start(c, LITE)).json()["session_id"]
    assert (await c.post(f"/api/sessions/{sid}/end")).status_code == 200
    (stop,) = vendors.to("/v1/sessions/stop")
    assert json.loads(stop.content) == {"session_id": "la-1", "reason": "USER_CLOSED"}
    assert stop.headers["x-api-key"] == "la-secret"


async def test_a_failed_stop_is_retried_until_it_works(make_env):
    vendors = Vendors(stop_status=503)
    env, c = await student(make_env, vendors)
    sid = (await start(c, LITE)).json()["session_id"]
    await c.post(f"/api/sessions/{sid}/end")
    reg = env.app.state.providers
    await reconcile_once(env.pool, env.s, reg)
    assert len(vendors.to("/v1/sessions/stop")) == 2  # still open: tried again
    vendors.stop_status = 200
    assert (await reconcile_once(env.pool, env.s, reg))["closed"] == 1
    assert (await reconcile_once(env.pool, env.s, reg))["closed"] == 0


async def test_a_stop_of_an_already_stopped_session_counts_as_closed(make_env):
    vendors = Vendors(stop_status=404)
    env, c = await student(make_env, vendors)
    sid = (await start(c, LITE)).json()["session_id"]
    await c.post(f"/api/sessions/{sid}/end")
    assert (await reconcile_once(env.pool, env.s, env.app.state.providers))["closed"] == 0
    assert len(vendors.to("/v1/sessions/stop")) == 1


async def test_a_bad_vendor_reply_refunds_and_the_retry_works(make_env):
    vendors = Vendors(mint_body={"data": {}})
    env, c = await student(make_env, vendors)
    r = await start(c, LITE)
    assert r.status_code == 502 and r.json()["error"] == "provider_failed"
    vendors.mint_status = 500
    assert (await start(c, LITE)).status_code == 502
    vendors.mint_status, vendors.mint_body = 200, None
    assert (await start(c, LITE)).status_code == 200  # no "session already live"
