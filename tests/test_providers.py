"""Provider layer: LiveAvatar embed, Tavus hosted conversation, our LiveKit pipeline.

The point of these tests is that switching provider never changes the invariants:
auth, one live session, quota reservation and single settlement, the server-owned
clock, media teardown, and ratings.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from interview_api.config import Settings
from interview_api.providers import load_registry
from interview_api.reconcile import reconcile_once
from test_api import age_session, balance, key, ready_student

EMBED = (
    "https://embed.liveavatar.com/v1/f7caa47d-4036-4c85-9aad-f9e238025ad2?orientation=horizontal"
)
EMBED_ENV = {"LIVEAVATAR_EMBED_URL": EMBED}
TAVUS_ENV = {
    "TAVUS_API_KEY": "tv-key",
    "TAVUS_FACE_ID": "face-123",
    "TAVUS_PAL_ID": "pal-9",
    "TAVUS_WEBHOOK_SECRET": "whsec-test",
    "PUBLIC_BASE_URL": "https://practice.example.com",
}


def body(provider_id: str) -> dict:
    return {"track": "us_f1", "format_id": "pressure_drill_3m", "provider_id": provider_id}


class FakeTavus:
    """Stands in for tavusapi.com. Counts conversations so we can prove exactly-once."""

    def __init__(self, fail: bool = False, delay: float = 0.0):
        self.created: list[dict] = []
        self.ended: list[str] = []
        self.fail, self.delay = fail, delay

    async def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["x-api-key"] == "tv-key"
        if request.url.path == "/v2/conversations" and request.method == "POST":
            await asyncio.sleep(self.delay)
            if self.fail:
                return httpx.Response(500, json={"error": "boom"})
            data = json.loads(request.content)
            self.created.append(data)
            n = len(self.created)
            return httpx.Response(
                200,
                json={
                    "conversation_id": f"c{n}",
                    "conversation_url": f"https://tavus.daily.co/c{n}",
                    "status": "active",
                },
            )
        if request.url.path.endswith("/end"):
            self.ended.append(request.url.path.split("/")[-2])
            return httpx.Response(200, json={})
        return httpx.Response(404)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))


# --------------------------------------------------------------------------- registry


def test_registry_offers_only_configured_valid_providers():
    s = Settings(database_url="unused")
    reg = load_registry(s, media=None, env={})
    assert reg.order == []  # nothing configured, no LiveKit
    assert "missing env: LIVEAVATAR_EMBED_URL" in reg.disabled["liveavatar_embed"]
    assert reg.disabled["livekit_simli"] == "LiveKit not configured"

    reg = load_registry(s, media=object(), env={**EMBED_ENV, **TAVUS_ENV})
    assert reg.order == ["liveavatar_embed", "tavus_conversation", "livekit_simli", "livekit_voice"]
    assert reg.frame_origins() == ["https://embed.liveavatar.com", "https://tavus.daily.co"]
    assert reg.default_for("voice").spec.id == "livekit_voice"

    bad = load_registry(s, media=None, env={"LIVEAVATAR_EMBED_URL": "https://evil.example/x"})
    assert "not in allowed_hosts" in bad.disabled["liveavatar_embed"]
    plain = load_registry(
        s, media=None, env={"LIVEAVATAR_EMBED_URL": EMBED.replace("https", "http")}
    )
    assert "must be https" in plain.disabled["liveavatar_embed"]
    only = load_registry(
        s, media=object(), env={**EMBED_ENV, "ENABLED_PROVIDERS": "liveavatar_embed"}
    )
    assert only.order == ["liveavatar_embed"]


# --------------------------------------------------------------------------- embed


async def test_provider_list_hides_vendors_and_respects_kill_switch(make_env):
    env = await make_env(provider_env=EMBED_ENV)
    async with env.client() as anon:
        assert (await anon.get("/api/providers")).status_code == 401
    c = await ready_student(env)
    listed = (await c.get("/api/providers")).json()
    assert [p["id"] for p in listed] == ["liveavatar_embed", "livekit_simli", "livekit_voice"]
    assert all("vendor" not in p and "url" not in json.dumps(p) for p in listed)
    env2 = await make_env(provider_env=EMBED_ENV, avatar_enabled=False)
    c2 = await ready_student(env2)
    assert [p["id"] for p in (await c2.get("/api/providers")).json()] == ["livekit_voice"]


async def test_embed_session_reserves_quota_and_returns_iframe_launch(make_env):
    env = await make_env(provider_env=EMBED_ENV)
    c = await ready_student(env)
    r = await c.post("/api/sessions", json=body("liveavatar_embed"), headers=key())
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["provider_id"] == "liveavatar_embed" and s["mode"] == "avatar"
    launch = s["launch"]
    assert launch["kind"] == "iframe" and launch["url"] == EMBED
    assert launch["origin"] == "https://embed.liveavatar.com"
    assert "microphone" in launch["allow"]
    assert "participant_token" not in s and env.media.minted == []  # no LiveKit involved
    assert (await balance(c))["reserved"] == 180
    # The one-live-session rule holds across providers.
    r2 = await c.post("/api/sessions", json=body("livekit_voice"), headers=key())
    assert r2.status_code == 409 and r2.json()["error"] == "session_already_live"
    assert (await c.post("/api/sessions", json=body("nope"), headers=key())).json()[
        "error"
    ] == "provider_not_available"


async def test_browser_drives_clock_for_embed_but_not_for_agent_sessions(make_env):
    env = await make_env(provider_env=EMBED_ENV)
    a = await ready_student(env, "a@synthetic.test", "A")
    b = await ready_student(env, "b@synthetic.test", "B")
    sid = (await a.post("/api/sessions", json=body("liveavatar_embed"), headers=key())).json()[
        "session_id"
    ]
    path = f"/api/sessions/{sid}/client-events"
    ev = (
        await a.post(path, json={"kind": "media_ready", "payload": {"trigger": "interaction"}})
    ).json()
    assert ev["live"] and ev["practice_ends_at"]
    again = (await a.post(path, json={"kind": "media_ready", "payload": {}})).json()
    assert again["practice_ends_at"] == ev["practice_ends_at"]  # clock starts once
    assert (await a.post(path, json={"kind": "heartbeat"})).status_code == 200
    assert (await b.post(path, json={"kind": "heartbeat"})).status_code == 404  # not B's
    big = {"kind": "metric", "payload": {"x": "y" * 5000}}
    assert (await a.post(path, json=big)).status_code == 413
    # Our own LiveKit sessions: the agent owns the lifecycle; browser may send metrics only.
    await a.post(f"/api/sessions/{sid}/end")
    sid2 = (await a.post("/api/sessions", json=body("livekit_voice"), headers=key())).json()[
        "session_id"
    ]
    p2 = f"/api/sessions/{sid2}/client-events"
    assert (await a.post(p2, json={"kind": "media_ready"})).status_code == 409
    assert (
        await a.post(p2, json={"kind": "metric", "payload": {"rtt_ms": 120}})
    ).status_code == 200


async def test_ending_embed_settles_once_without_touching_livekit(make_env):
    env = await make_env(provider_env=EMBED_ENV)
    c = await ready_student(env)
    sid = (await c.post("/api/sessions", json=body("liveavatar_embed"), headers=key())).json()[
        "session_id"
    ]
    await age_session(env, sid, ready_ago_s=100)
    ends = await asyncio.gather(*[c.post(f"/api/sessions/{sid}/end") for _ in range(5)])
    assert {e.json()["charged_premium_seconds"] for e in ends} == {100}
    assert (await balance(c))["consumed"] == 100
    row = (await env.sql("SELECT room_closed_at FROM interview_sessions"))[0]
    assert row["room_closed_at"] is not None and env.media.deleted == []


async def test_reconciler_gives_browser_heartbeats_more_slack(make_env):
    env = await make_env(
        provider_env=EMBED_ENV, heartbeat_timeout_s=45, client_heartbeat_timeout_s=90
    )
    c = await ready_student(env, "a@synthetic.test", "A")
    d = await ready_student(env, "d@synthetic.test", "D")
    s1 = (await c.post("/api/sessions", json=body("liveavatar_embed"), headers=key())).json()[
        "session_id"
    ]
    s2 = (await d.post("/api/sessions", json=body("liveavatar_embed"), headers=key())).json()[
        "session_id"
    ]
    await age_session(env, s1, ready_ago_s=120, heartbeat_ago_s=60)  # within 90 s: still live
    await age_session(env, s2, ready_ago_s=200, heartbeat_ago_s=100)  # tab died
    rep = await reconcile_once(env.pool, env.media, env.s, registry=env.app.state.providers)
    assert rep["stale_active"] == 1
    rows = {str(r["id"]): r for r in await env.sql("SELECT * FROM interview_sessions")}
    assert rows[s1]["status"] == "active"
    assert rows[s2]["status"] == "completed" and rows[s2]["charged_premium_seconds"] == 100
    assert rep["graded"] == 0  # no transcript from a static embed: nothing to grade


async def test_rating_after_session_for_any_provider(make_env):
    env = await make_env(provider_env=EMBED_ENV)
    a = await ready_student(env, "a@synthetic.test", "A")
    b = await ready_student(env, "b@synthetic.test", "B")
    sid = (await a.post("/api/sessions", json=body("liveavatar_embed"), headers=key())).json()[
        "session_id"
    ]
    rating = {
        "realism": 4,
        "reply_speed": "slight_pause",
        "audio_video_ok": True,
        "would_use_again": True,
    }
    assert (await a.post(f"/api/sessions/{sid}/rating", json=rating)).status_code == 409  # live
    await a.post(f"/api/sessions/{sid}/end")
    assert (
        await a.post(f"/api/sessions/{sid}/rating", json={**rating, "realism": 9})
    ).status_code == 422
    assert (await b.post(f"/api/sessions/{sid}/rating", json=rating)).status_code == 404
    assert (await a.post(f"/api/sessions/{sid}/rating", json=rating)).status_code == 200
    assert (
        await a.post(f"/api/sessions/{sid}/rating", json={**rating, "realism": 2})
    ).status_code == 200
    fb = (await a.get(f"/api/sessions/{sid}/feedback")).json()
    assert fb["rating"]["realism"] == 2 and fb["provider"]["transcripts"] is False
    assert fb["session"]["provider_id"] == "liveavatar_embed"


# --------------------------------------------------------------------------- Tavus


async def test_tavus_conversation_created_once_with_student_facts(make_env):
    fake = FakeTavus(delay=0.2)
    env = await make_env(provider_env=TAVUS_ENV, provider_http=fake.client())
    c = await ready_student(env)
    h = key()
    results = await asyncio.gather(
        *[c.post("/api/sessions", json=body("tavus_conversation"), headers=h) for _ in range(6)]
    )
    assert {r.status_code for r in results} == {200}, [r.text for r in results]
    assert len(fake.created) == 1  # concurrent retries never create a second conversation
    assert {r.json()["launch"]["url"] for r in results} == {"https://tavus.daily.co/c1"}
    sent = fake.created[0]
    assert sent["face_id"] == "face-123" and sent["pal_id"] == "pal-9"
    assert "Example State University" in sent["conversational_context"]  # confirmed facts
    assert "fictional" in sent["custom_greeting"]
    assert sent["properties"]["max_call_duration"] == 45 + 180 + 15
    assert sent["callback_url"] == "https://practice.example.com/api/webhooks/tavus/whsec-test"
    assert "vendor_ref" not in results[0].json()["launch"]
    sid = results[0].json()["session_id"]
    await c.post(f"/api/sessions/{sid}/end")
    assert fake.ended == ["c1"]


async def test_tavus_failure_refunds_and_reports(make_env):
    fake = FakeTavus(fail=True)
    env = await make_env(provider_env=TAVUS_ENV, provider_http=fake.client())
    c = await ready_student(env)
    r = await c.post("/api/sessions", json=body("tavus_conversation"), headers=key())
    assert r.status_code == 502 and r.json()["error"] == "provider_failed"
    bal = await balance(c)
    assert bal["reserved"] == 0 and bal["consumed"] == 0
    row = (await env.sql("SELECT status, end_reason FROM interview_sessions"))[0]
    assert row["status"] == "failed" and row["end_reason"] == "provider_launch_failed"


async def test_tavus_webhook_transcript_settlement_and_grading(make_env):
    fake = FakeTavus()
    env = await make_env(provider_env=TAVUS_ENV, provider_http=fake.client())
    c = await ready_student(env)
    sid = (await c.post("/api/sessions", json=body("tavus_conversation"), headers=key())).json()[
        "session_id"
    ]
    await age_session(env, sid, ready_ago_s=90)
    async with env.client() as vendor:
        url = "/api/webhooks/tavus/whsec-test"
        assert (await vendor.post("/api/webhooks/tavus/wrong", json={})).status_code == 404
        r = await vendor.post(url, json={"conversation_id": "c1", "event_type": "system.shutdown"})
        assert r.status_code == 200
        transcript = {
            "conversation_id": "c1",
            "event_type": "application.transcription_ready",
            "properties": {
                "transcript": [
                    {"role": "system", "content": "ignored"},
                    {"role": "assistant", "content": "Why this university?"},
                    {"role": "user", "content": "Because of its data science programme and lab."},
                    {"role": "assistant", "content": "Who is paying?"},
                    {"role": "user", "content": "My father, with savings of 20,000 dollars."},
                ]
            },
        }
        assert (await vendor.post(url, json=transcript)).status_code == 200
        assert (await vendor.post(url, json={"conversation_id": "zzz", "event_type": "x"})).json()[
            "ignored"
        ]
    sess = (await c.get(f"/api/sessions/{sid}")).json()
    assert sess["status"] == "completed" and sess["end_reason"] == "provider_shutdown"
    assert sess["charged_premium_seconds"] == 90
    fb = (await c.get(f"/api/sessions/{sid}/feedback")).json()
    assert [t["speaker"] for t in fb["turns"]] == [
        "interviewer",
        "student",
        "interviewer",
        "student",
    ]
    assert fb["feedback"]["status"] == "ready", fb["feedback"]
    assert any(f["category"] == "funding_explanation" for f in fb["feedback"]["report"]["findings"])


@pytest.mark.parametrize("mode", ["avatar", "voice"])
async def test_legacy_mode_requests_still_pick_a_provider(make_env, mode):
    env = await make_env(provider_env=EMBED_ENV)
    c = await ready_student(env)
    r = await c.post(
        "/api/sessions",
        json={"track": "us_f1", "format_id": "pressure_drill_3m", "mode": mode},
        headers=key(),
    )
    assert r.status_code == 200
    assert r.json()["provider_id"] == ("liveavatar_embed" if mode == "avatar" else "livekit_voice")


async def test_end_reason_is_recorded_for_comparison(make_env):
    env = await make_env(provider_env=EMBED_ENV)
    c = await ready_student(env)
    sid = (await c.post("/api/sessions", json=body("liveavatar_embed"), headers=key())).json()[
        "session_id"
    ]
    assert (await c.post(f"/api/sessions/{sid}/end?reason=bogus")).status_code == 422
    r = await c.post(f"/api/sessions/{sid}/end?reason=deadline")
    assert r.json()["end_reason"] == "deadline"
