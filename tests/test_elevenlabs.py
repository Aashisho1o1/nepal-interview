"""ElevenLabs voice tier: what students are offered, what the browser receives, and that
no vendor key ever leaves the server. Uses the real config/providers.json."""

from __future__ import annotations

import json

import httpx
import pytest

from conftest import balance, key, ready_student
from interview_api.config import Settings
from interview_api.providers import (
    DEFAULT_PROVIDERS_FILE,
    LaunchContext,
    ProviderError,
    load_registry,
)
from interview_core.dynamic_vars import MAX_VALUE, build_dynamic_variables
from interview_core.facts import Fact, build_snapshot
from interview_core.funding import compute_funding
from interview_core.synthetic import SYNTHETIC_FACTS

AGENT = "agent_test123"
PUBLIC_ENV = {"ELEVENLABS_AGENT_ID": AGENT, "ELEVENLABS_ALLOW_PUBLIC_AGENT": "true"}
PRIVATE_ENV = {"ELEVENLABS_AGENT_ID": AGENT, "ELEVENLABS_API_KEY": "xi-secret-key"}


def body(provider_id: str = "elevenlabs_voice") -> dict:
    return {"track": "us_f1", "format_id": "pressure_drill_3m", "provider_id": provider_id}


def ctx(**kw) -> LaunchContext:
    base = dict(
        session_id="s1",
        student_id="u1",
        student_name="Asha Synthetic",
        practice_seconds=300,
        max_vendor_seconds=340,
        dynamic_variables={"session_id": "s1", "university": "Example"},
    )
    base.update(kw)
    return LaunchContext(**base)


def token_http(calls: list, status: int = 200, payload: dict | None = None):
    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        return httpx.Response(status, json=payload if payload is not None else {"token": "tok-1"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_students_are_offered_only_elevenlabs_and_liveavatar():
    raw = json.loads(DEFAULT_PROVIDERS_FILE.read_text())
    enabled = {p["id"] for p in raw["providers"] if p.get("enabled")}
    assert enabled == {"liveavatar_embed", "elevenlabs_voice"}
    s = Settings(database_url="unused")
    env = {**PUBLIC_ENV, "LIVEAVATAR_EMBED_URL": "https://embed.liveavatar.com/v1/x"}
    reg = load_registry(s, env=env)
    assert reg.order == ["liveavatar_embed", "elevenlabs_voice"]
    assert reg.get("elevenlabs_voice").spec.label == "Voice only"


def test_voice_needs_a_key_unless_public_agent_is_explicitly_allowed():
    s = Settings(database_url="unused")
    assert "ELEVENLABS_AGENT_ID" in load_registry(s, env={}).disabled["elevenlabs_voice"]
    no_key = load_registry(s, env={"ELEVENLABS_AGENT_ID": AGENT})
    assert "ELEVENLABS_API_KEY" in no_key.disabled["elevenlabs_voice"]
    assert load_registry(s, env=PUBLIC_ENV).order == ["elevenlabs_voice"]
    assert load_registry(s, env=PRIVATE_ENV).order == ["elevenlabs_voice"]


async def test_public_agent_launch_gets_agent_id_and_never_calls_the_api():
    calls: list = []
    reg = load_registry(Settings(database_url="unused"), env=PUBLIC_ENV, http=token_http(calls))
    launch = await reg.get("elevenlabs_voice").launch(ctx())
    assert launch == {
        "kind": "elevenlabs",
        "connection_type": "webrtc",
        "agent_id": AGENT,
        "dynamic_variables": {"session_id": "s1", "university": "Example"},
    }
    assert calls == []


async def test_private_agent_gets_a_server_minted_token_and_no_key():
    calls: list = []
    env = {**PRIVATE_ENV, "ELEVENLABS_BRANCH_ID": "agtbrch_1"}
    reg = load_registry(Settings(database_url="unused"), env=env, http=token_http(calls))
    launch = await reg.get("elevenlabs_voice").launch(ctx())
    assert launch["conversation_token"] == "tok-1" and "agent_id" not in launch
    assert "xi-secret-key" not in json.dumps(launch)
    (req,) = calls
    assert req.url.path == "/v1/convai/conversation/token"
    assert req.url.params["agent_id"] == AGENT and req.url.params["branch_id"] == "agtbrch_1"
    assert req.headers["xi-api-key"] == "xi-secret-key"


@pytest.mark.parametrize("status,payload", [(401, {"detail": "bad key"}), (200, {})])
async def test_token_failure_is_a_provider_error(status, payload):
    reg = load_registry(
        Settings(database_url="unused"), env=PRIVATE_ENV, http=token_http([], status, payload)
    )
    with pytest.raises(ProviderError):
        await reg.get("elevenlabs_voice").launch(ctx())


def test_dynamic_variables_use_confirmed_facts_and_precomputed_funding():
    snap = build_snapshot(
        [Fact(r, f, v, lbl, sn, "confirmed") for r, f, v, lbl, sn in SYNTHETIC_FACTS], 1
    )
    v = build_dynamic_variables(
        session_id="abc",
        student_name="Asha Synthetic",
        facts=snap,
        funding=compute_funding(snap),
        practice_seconds=300,
    )
    assert v["session_id"] == "abc" and v["student_first_name"] == "Asha"
    assert v["university"] == "Example State University"
    assert v["intake"] == "August 2027"
    assert v["interview_format"] == "3 questions, 5 minutes"
    assert v["cas_status"] == "not yet issued"
    assert "USD" in v["funding_summary"] and "\n" not in v["funding_summary"]
    assert all(isinstance(x, str) and len(x) <= MAX_VALUE for x in v.values())


async def test_voice_session_reserves_five_minutes_and_passes_session_id(make_env):
    env = await make_env(provider_env=PUBLIC_ENV)
    async with env.client() as anon:
        assert (await anon.post("/api/sessions", json=body(), headers=key())).status_code == 401
    c = await ready_student(env)
    r = await c.post("/api/sessions", json=body(), headers=key())
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["mode"] == "voice" and s["practice_seconds"] == 300
    assert s["launch"]["kind"] == "elevenlabs"
    assert s["launch"]["dynamic_variables"]["session_id"] == s["session_id"]
    assert (await balance(c, "basic_seconds"))["reserved"] == 300
    # Browser-driven lifecycle: clock starts on connect; the agent hanging up ends it.
    sid = s["session_id"]
    ev = await c.post(
        f"/api/sessions/{sid}/client-events", json={"kind": "media_ready", "payload": {}}
    )
    assert ev.json()["practice_ends_at"]
    end = await c.post(f"/api/sessions/{sid}/end?reason=agent_ended")
    assert end.status_code == 200 and end.json()["end_reason"] == "agent_ended"
