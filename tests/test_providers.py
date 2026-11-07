"""Provider layer: the LiveAvatar embed (video) and the ElevenLabs agent (voice).

Switching provider never changes the invariants: auth, one live session, quota
reservation and single settlement, the server-owned clock, teardown, ratings.
"""

from __future__ import annotations

import asyncio

from conftest import (
    EMBED,
    HERO_ENV,
    VIDEO,
    VIDEO_SECONDS,
    VOICE,
    age_session,
    balance,
    media_ready,
    ready_student,
    start,
)
from interview_api.config import Settings
from interview_api.providers import load_registry
from interview_api.reconcile import reconcile_once

# --------------------------------------------------------------------------- registry


def test_registry_offers_only_configured_valid_providers():
    s = Settings(database_url="unused")
    none = load_registry(s, env={})
    assert none.order == []
    assert "missing env: LIVEAVATAR_EMBED_URL" in none.disabled[VIDEO]
    assert "ELEVENLABS_AGENT_ID" in none.disabled[VOICE]
    both = load_registry(s, env=HERO_ENV)
    assert both.order == [VIDEO, VOICE]
    assert both.frame_origins() == ["https://embed.liveavatar.com"]
    bad = load_registry(s, env={**HERO_ENV, "LIVEAVATAR_EMBED_URL": "https://evil.example/x"})
    assert "allowed_hosts" in bad.disabled[VIDEO] and bad.order == [VOICE]
    plain = load_registry(
        s, env={**HERO_ENV, "LIVEAVATAR_EMBED_URL": EMBED.replace("https", "http")}
    )
    assert "https" in plain.disabled[VIDEO]
    only = load_registry(s, env={**HERO_ENV, "ENABLED_PROVIDERS": VOICE})
    assert only.order == [VOICE]


async def test_provider_list_hides_vendors_and_respects_kill_switch(make_env):
    env = await make_env()
    c = await ready_student(env)
    ps = (await c.get("/api/providers")).json()
    assert [p["id"] for p in ps] == [VIDEO, VOICE]
    for p in ps:  # neutral labels; no vendor name, no embed URL before a session is reserved
        assert set(p) == {"id", "label", "modality", "data_note", "capabilities"}
        assert "heygen" not in p["label"].lower() and "embed.liveavatar" not in str(p)
    off = await make_env(video_tier_enabled=False)
    c2 = await ready_student(off)
    assert [p["id"] for p in (await c2.get("/api/providers")).json()] == [VOICE]
    assert (await start(c2, VIDEO)).status_code == 503


# --------------------------------------------------------------------------- embed


async def test_embed_session_reserves_quota_and_returns_iframe_launch(make_env):
    env = await make_env()
    c = await ready_student(env)
    r = await start(c, VIDEO)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["mode"] == "avatar"
    launch = s["launch"]
    assert launch["kind"] == "iframe" and launch["url"] == EMBED
    assert launch["origin"] == "https://embed.liveavatar.com"
    assert "microphone" in launch["allow"]
    assert (await balance(c))["reserved"] == VIDEO_SECONDS
    # The one-live-session rule holds across providers.
    r2 = await start(c, VOICE)
    assert r2.status_code == 409 and r2.json()["error"] == "session_already_live"
    assert (await start(c, "nope")).json()["error"] == "provider_not_available"


async def test_browser_drives_the_clock(make_env):
    env = await make_env()
    a = await ready_student(env, "a@synthetic.test", "A")
    b = await ready_student(env, "b@synthetic.test", "B")
    sid = (await start(a, VIDEO)).json()["session_id"]
    path = f"/api/sessions/{sid}/client-events"
    ev = await media_ready(a, sid, {"trigger": "interaction"})
    assert ev["live"] and ev["practice_ends_at"]
    assert (await media_ready(a, sid))["practice_ends_at"] == ev["practice_ends_at"]  # once
    assert (await a.post(path, json={"kind": "heartbeat"})).status_code == 200
    assert (await b.post(path, json={"kind": "heartbeat"})).status_code == 404  # not B's
    big = {"kind": "metric", "payload": {"x": "y" * 5000}}
    assert (await a.post(path, json=big)).status_code == 413
    ok = await a.post(path, json={"kind": "metric", "payload": {"rtt_ms": 120}})
    assert ok.status_code == 200


async def test_ending_embed_settles_once(make_env):
    env = await make_env()
    c = await ready_student(env)
    sid = (await start(c, VIDEO)).json()["session_id"]
    await age_session(env, sid, ready_ago_s=100)
    ends = await asyncio.gather(*[c.post(f"/api/sessions/{sid}/end") for _ in range(5)])
    assert {e.json()["charged_premium_seconds"] for e in ends} == {100}
    assert (await balance(c))["consumed"] == 100
    row = (await env.sql("SELECT vendor_closed_at FROM interview_sessions"))[0]
    assert row["vendor_closed_at"] is not None


async def test_reconciler_gives_browser_heartbeats_slack(make_env):
    env = await make_env(client_heartbeat_timeout_s=90)
    c = await ready_student(env, "a@synthetic.test", "A")
    d = await ready_student(env, "d@synthetic.test", "D")
    s1 = (await start(c, VIDEO)).json()["session_id"]
    s2 = (await start(d, VIDEO)).json()["session_id"]
    await age_session(env, s1, ready_ago_s=120, heartbeat_ago_s=60)  # within 90 s: still live
    await age_session(env, s2, ready_ago_s=200, heartbeat_ago_s=100)  # tab died
    rep = await reconcile_once(env.pool, env.s, env.registry)
    assert rep["stale_active"] == 1
    rows = {str(r["id"]): r for r in await env.sql("SELECT * FROM interview_sessions")}
    assert rows[s1]["status"] == "active"
    assert rows[s2]["status"] == "completed" and rows[s2]["charged_premium_seconds"] == 100
    assert rep["graded"] == 0  # no transcript from a static embed: nothing to grade


async def test_rating_after_session_for_any_provider(make_env):
    env = await make_env()
    a = await ready_student(env, "a@synthetic.test", "A")
    b = await ready_student(env, "b@synthetic.test", "B")
    sid = (await start(a, VIDEO)).json()["session_id"]
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


async def test_end_reason_is_recorded_for_comparison(make_env):
    env = await make_env()
    c = await ready_student(env)
    sid = (await start(c, VIDEO)).json()["session_id"]
    assert (await c.post(f"/api/sessions/{sid}/end?reason=bogus")).status_code == 422
    r = await c.post(f"/api/sessions/{sid}/end?reason=deadline")
    assert r.json()["end_reason"] == "deadline"
