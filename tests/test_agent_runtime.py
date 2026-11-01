"""Agent runtime rules, run without LiveKit Cloud or provider keys.

The adapter tests construct real livekit-agents 1.8.9 objects (no network) to check
our code against the actual installed API rather than our assumptions about it.
"""

from __future__ import annotations

import asyncio
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-used")
os.environ.setdefault("SIMLI_API_KEY", "simli-test-not-used")
os.environ.setdefault("SIMLI_FACE_ID", "face-test")

from livekit.agents import AgentSession  # noqa: E402
from livekit.agents.metrics.usage import LLMModelUsage  # noqa: E402
from livekit.agents.voice.io import AudioOutput, AudioOutputCapabilities  # noqa: E402

from interview_agent.adapters import (  # noqa: E402
    CascadeVoice,
    OpenAIRealtimeVoice,
    PortraitRenderer,
    SimliRenderer,
    start_with_fallback,
)
from interview_agent.runtime import (  # noqa: E402
    SilencePolicy,
    Teardown,
    TimingMeter,
    TurnRecorder,
    WallClock,
    percentile,
    usage_events,
)


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


# ---------------------------------------------------------------- teardown


async def test_teardown_runs_once_under_concurrent_exits_and_survives_failures():
    calls: list[str] = []

    async def ok(name):
        calls.append(name)

    async def boom():
        calls.append("finalize")
        raise RuntimeError("api down")

    async def hang():
        calls.append("close_avatar")
        await asyncio.sleep(10)

    td = Teardown()
    steps = [
        ("flush", lambda: ok("flush"), 1),
        ("finalize", boom, 1),
        ("close_avatar", hang, 0.05),
        ("close_voice", lambda: ok("close_voice"), 1),
        ("delete_room", lambda: ok("delete_room"), 1),
    ]
    reasons = ["deadline", "student_left", "job_shutdown", "avatar_lost", "hard_deadline"]
    results = await asyncio.gather(*[td.run(r, steps) for r in reasons])
    assert results.count(True) == 1
    assert calls == ["flush", "finalize", "close_avatar", "close_voice", "delete_room"]
    assert td.reason == "deadline"
    assert dict(td.results)["finalize"].startswith("error")
    assert dict(td.results)["close_avatar"] == "timeout"
    assert dict(td.results)["delete_room"] == "ok"  # later steps still ran
    assert await td.run("again", steps) is False and len(calls) == 5


# ---------------------------------------------------------------- turns


def test_turn_recorder_marks_interrupted_interviewer_turns_and_times_from_practice_start():
    r = TurnRecorder(practice_start_epoch=1000.0)
    r.add(
        item_id="a1",
        role="assistant",
        text="Why this university?",
        interrupted=False,
        created_at=1001.0,
        metrics={"started_speaking_at": 1000.5, "stopped_speaking_at": 1002.0},
    )
    r.add(
        item_id="u1",
        role="user",
        text="Because of the data science lab.",
        interrupted=False,
        created_at=1006.0,
        metrics={
            "started_speaking_at": 1003.0,
            "stopped_speaking_at": 1005.5,
            "end_of_turn_delay": 0.4,
        },
    )
    r.add(
        item_id="a2",
        role="assistant",
        text="And who is paying for",
        interrupted=True,
        created_at=1007.0,
    )
    r.add(item_id="x", role="system", text="ignored", interrupted=False, created_at=1008.0)
    r.add(item_id="e", role="user", text="   ", interrupted=False, created_at=1008.0)
    turns = r.take_pending()
    assert [t["turn_id"] for t in turns] == ["a1", "u1", "a2"]
    assert turns[0]["start_ms"] == 500 and turns[0]["end_ms"] == 2000
    assert turns[1]["speaker"] == "student" and turns[1]["start_ms"] == 3000
    assert turns[1]["metrics"]["end_of_turn_delay"] == 0.4
    assert turns[2]["canceled"] is True and turns[1]["canceled"] is False
    r.mark_sent(turns)
    assert r.take_pending() == [] and r.student_turns == 1
    # A later update for an already-sent item is resent with the same id and sequence.
    r.add(
        item_id="a2",
        role="assistant",
        text="And who is paying",
        interrupted=True,
        created_at=1007.0,
    )
    again = r.take_pending()
    assert again[0]["turn_id"] == "a2" and again[0]["sequence"] == 3


# ---------------------------------------------------------------- timing


def test_timing_meter_measures_response_and_interruption_stop():
    clk = Clock()
    m = TimingMeter(clock=clk)
    m.on_agent_state("listening")
    m.on_user_state("speaking")
    clk.t += 2.0
    m.on_user_state("listening")
    clk.t += 0.9
    m.on_agent_state("thinking")
    clk.t += 0.3
    ev = m.on_agent_state("speaking")
    assert ev == {"kind": "latency", "payload": {"response_ms": 1200}}
    clk.t += 1.0
    m.on_user_state("speaking")  # student cuts in
    clk.t += 0.35
    ev = m.on_agent_state("listening")
    assert ev == {"kind": "interruption", "payload": {"stop_signal_ms": 350}}
    assert m.interruptions == 1
    assert percentile([100, 200, 300, 400], 0.5) == 250
    assert percentile([], 0.9) is None


def test_silence_prompts_once_then_ends_and_speech_resets():
    s = SilencePolicy()
    assert s.on_user_state("away") == "prompt"
    assert s.on_user_state("speaking") is None
    assert s.on_user_state("away") == "prompt"  # reset by speech
    assert s.on_user_state("listening") is None
    assert s.on_user_state("away") == "end"


# ---------------------------------------------------------------- usage


def test_usage_events_are_cumulative_and_named_by_provider_and_model():
    u = LLMModelUsage(
        provider="openai",
        model="gpt-realtime",
        input_audio_tokens=1200,
        output_audio_tokens=800,
        input_cached_text_tokens=0,
    )
    ev = usage_events([u], {"livekit.agent_session_seconds": 61.25, "simli.avatar_seconds": 59.0})
    meters = {e["meter"]: e for e in ev}
    assert meters["openai.gpt-realtime.input_audio_tokens"]["quantity"] == "1200.0"
    assert "openai.gpt-realtime.input_cached_text_tokens" not in meters  # zero omitted
    assert meters["simli.avatar_seconds"]["unit"] == "second"
    assert all(e["cumulative"] and e["provider_event_id"] == f"cum:{e['meter']}" for e in ev)


def test_wall_clock():
    clk = Clock()
    w = WallClock(clock=clk)
    assert w.seconds == 0
    w.start()
    clk.t += 5
    w.stop()
    clk.t += 5
    assert w.seconds == 5


# ---------------------------------------------------------------- adapters vs real livekit


class _FakeAvatarOut(AudioOutput):
    def __init__(self):
        super().__init__(label="fake-avatar", capabilities=AudioOutputCapabilities(pause=False))

    async def capture_frame(self, frame):
        pass

    def flush(self):
        pass

    def clear_buffer(self):
        pass


class _FailingAvatar:
    name = "simli"
    identity = "simli-avatar-agent"

    def __init__(self, mode):
        self.mode, self.closed = mode, False

    async def start(self, session, room, *, join_timeout_s):
        session.output.audio = _FakeAvatarOut()  # what the plugin does on success
        if self.mode == "raise":
            raise ConnectionError("simli unreachable")
        return False, "simli_join_timeout"

    async def aclose(self):
        self.closed = True


@pytest.mark.parametrize("mode", ["timeout", "raise"])
async def test_avatar_failure_falls_back_to_single_voice_stream(mode):
    session = AgentSession()
    bad = _FailingAvatar(mode)
    renderer, display, reason = await start_with_fallback(
        bad, session, room=None, join_timeout_s=0.1
    )
    assert isinstance(renderer, PortraitRenderer) and display == "portrait"
    assert reason in ("simli_join_timeout", "avatar_error:ConnectionError")
    assert bad.closed
    # The avatar audio route is removed, so RoomIO will publish the agent's own track:
    # one audio stream, never both.
    assert session.output.audio is None


async def test_portrait_mode_never_starts_an_avatar():
    session = AgentSession()
    r, display, reason = await start_with_fallback(
        PortraitRenderer(), session, None, join_timeout_s=1
    )
    assert display == "portrait" and reason is None


def test_simli_config_carries_vendor_side_caps():
    r = SimliRenderer(max_session_s=240, max_idle_s=60)
    body = r.cfg.create_json()
    assert body["maxSessionLength"] == 240 and body["maxIdleTime"] == 60
    assert body["faceId"] == "face-test"


async def test_voice_adapters_build_against_installed_livekit():
    kw = OpenAIRealtimeVoice().session_kwargs(max_session_s=240)
    s = AgentSession(
        **kw,
        turn_handling={
            "interruption": {"resume_false_interruption": False},
            "user_turn_limit": {"max_duration": 60},
        },
        user_away_timeout=15,
    )
    assert s is not None
    assert set(CascadeVoice().session_kwargs(max_session_s=1)) == {"stt", "llm", "tts"}
