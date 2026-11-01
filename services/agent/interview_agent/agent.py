"""LiveKit interview worker.

    uv run python -m interview_agent.agent dev     # or: lk agent dev

Each job is one interview session. The session id arrives in the dispatch metadata
of the student's server-signed join token; everything else (policy, limits, mode)
comes from the session API, never from the browser.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import Agent, AgentServer, AgentSession, CloseEvent, JobContext, cli, room_io

from .adapters import make_avatar, make_voice, start_with_fallback
from .api_client import InternalApi
from .runtime import (
    SilencePolicy,
    Teardown,
    TimingMeter,
    TurnRecorder,
    WallClock,
    sleep_until_epoch,
    usage_events,
)

load_dotenv()
log = logging.getLogger("interview_agent")

AGENT_NAME = os.getenv("LIVEKIT_AGENT_NAME", "nepal-interview-agent")
API_URL = os.getenv("SESSION_API_URL", "http://localhost:8000")
API_TOKEN = os.getenv("INTERNAL_API_TOKEN", "")
HEARTBEAT_S = 10
AWAY_TIMEOUT_S = float(os.getenv("AWAY_TIMEOUT_S", "15"))
LONG_ANSWER_S = float(os.getenv("LONG_ANSWER_S", "60"))

server = AgentServer()


class InterviewAgent(Agent):
    pass


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: JobContext) -> None:
    try:
        session_id = json.loads(ctx.job.metadata or "{}").get("session_id")
    except json.JSONDecodeError:
        session_id = None
    if not session_id or not API_TOKEN:
        log.error("job without session_id or INTERNAL_API_TOKEN; closing room")
        ctx.delete_room()
        return

    api = InternalApi(API_URL, API_TOKEN, session_id)
    try:
        cfg = await api.config()
    except Exception:
        log.exception("could not load session config; closing room")
        ctx.delete_room()
        await api.aclose()
        return
    if cfg["room_name"] != ctx.room.name:
        log.error("room mismatch for session %s", session_id)
        ctx.delete_room()
        await api.aclose()
        return

    policy = cfg["policy"]
    practice_s = int(cfg["practice_seconds"])
    startup_s = int(cfg["startup_budget_s"])
    hard_deadline = float(cfg["hard_deadline_at"])
    max_provider_s = startup_s + practice_s + int(cfg["closing_grace_s"])

    agent_clock, avatar_clock = WallClock(), WallClock()
    agent_clock.start()
    turns = TurnRecorder()
    timing = TimingMeter()
    silence = SilencePolicy()
    teardown = Teardown()
    tasks: list[asyncio.Task] = []
    closing = asyncio.Event()

    await ctx.connect()
    await _safe(api.event("agent_joined", {"worker": os.getenv("HOSTNAME", "")}))

    # Do not start paid providers until the student is actually here.
    try:
        await asyncio.wait_for(
            ctx.wait_for_participant(identity=cfg["student_identity"]),
            timeout=max(5, startup_s - 10),
        )
    except TimeoutError:
        await _finish(api, "student_never_joined", ctx, agent_clock)
        return

    voice = make_voice(cfg["providers"].get("voice") or "openai_realtime")
    session = AgentSession(
        **voice.session_kwargs(max_session_s=max_provider_s),
        # Avatars cannot pause speech, so never "resume" after a false interruption:
        # an interrupted turn stays cancelled.
        turn_handling={
            "interruption": {"resume_false_interruption": False},
            "user_turn_limit": {"max_duration": LONG_ANSWER_S},
        },
        user_away_timeout=AWAY_TIMEOUT_S,
    )
    renderer = make_avatar(cfg["mode"], max_session_s=max_provider_s, max_idle_s=60)

    async def flush_turns() -> None:
        pending = turns.take_pending()
        if pending:
            await api.turns(pending)
            turns.mark_sent(pending)

    async def send_usage() -> None:
        await api.usage(
            usage_events(
                session.usage.model_usage,
                {
                    "livekit.agent_session_seconds": agent_clock.seconds,
                    **(
                        {"simli.avatar_seconds": avatar_clock.seconds}
                        if cfg["mode"] == "avatar"
                        else {}
                    ),
                },
            )
        )

    async def close_avatar() -> None:
        await renderer.aclose()
        avatar_clock.stop()
        await _safe(api.event("provider_closed", {"provider": renderer.name}))

    async def close_voice() -> None:
        await session.aclose()
        await _safe(api.event("provider_closed", {"provider": voice.name}))

    async def delete_room() -> None:
        await ctx.delete_room()
        await _safe(api.event("room_deleted"))

    async def stop(reason: str) -> None:
        closing.set()
        for t in tasks:
            if t is not asyncio.current_task():
                t.cancel()
        agent_clock.stop()

        async def announce() -> None:
            await ctx.room.local_participant.set_attributes({"ni.ending": reason})

        await teardown.run(
            reason,
            [
                ("announce", announce, 2),
                ("flush_turns", flush_turns, 4),
                ("finalize", lambda: api.finalize(reason), 6),
                ("close_avatar", close_avatar, 6),
                ("close_voice", close_voice, 6),
                ("delete_room", delete_room, 6),
                ("flush_turns_late", flush_turns, 4),
                ("usage", send_usage, 5),
                ("transcript_complete", api.transcript_complete, 6),
                (
                    "summary",
                    lambda: api.event(
                        "state",
                        {
                            "teardown": teardown.results,
                            "reason": reason,
                            "response_ms": timing.response_latencies_ms,
                            "interruption_stop_ms": timing.interruption_stop_ms,
                            "interruptions": timing.interruptions,
                        },
                    ),
                    4,
                ),
            ],
        )
        await api.aclose()

    def stop_soon(reason: str) -> None:
        if not closing.is_set():
            asyncio.create_task(stop(reason))

    # ---- events
    @session.on("conversation_item_added")
    def _on_item(ev) -> None:
        item = ev.item
        if getattr(item, "type", None) != "message":
            return
        t = turns.add(
            item_id=item.id,
            role=item.role,
            text=item.text_content,
            interrupted=item.interrupted,
            created_at=item.created_at,
            metrics=dict(item.metrics),
        )
        if t and not closing.is_set():
            asyncio.create_task(_safe(flush_turns()))

    @session.on("agent_state_changed")
    def _on_agent_state(ev) -> None:
        out = timing.on_agent_state(ev.new_state)
        if out and not closing.is_set():
            asyncio.create_task(_safe(api.event(out["kind"], out["payload"])))

    @session.on("user_state_changed")
    def _on_user_state(ev) -> None:
        timing.on_user_state(ev.new_state)
        action = silence.on_user_state(ev.new_state)
        if closing.is_set():
            return
        if action == "prompt":
            voice.speak_exact(session, policy["silence_prompt"])
        elif action == "end":
            stop_soon("no_input")

    @session.on("user_turn_exceeded")
    def _on_long_answer(ev) -> None:
        if not closing.is_set():
            session.generate_reply(instructions=policy["long_answer_prompt"])

    @session.on("close")
    def _on_close(ev: CloseEvent) -> None:
        stop_soon(f"session_{ev.reason.value}")

    @ctx.room.on("participant_disconnected")
    def _on_left(p: rtc.RemoteParticipant) -> None:
        if p.identity == cfg["student_identity"]:
            stop_soon("student_left")
        elif renderer.identity and p.identity == renderer.identity and not closing.is_set():
            # Mid-call avatar loss ends this session; the student is offered voice.
            stop_soon("avatar_lost")

    ctx.add_shutdown_callback(lambda: stop("job_shutdown"))

    async def hard_guard() -> None:
        await sleep_until_epoch(hard_deadline)
        stop_soon("hard_deadline")

    tasks.append(asyncio.create_task(hard_guard()))

    # ---- start media: avatar first (so audio routes to it), with fallback to voice
    if cfg["mode"] == "avatar":
        avatar_clock.start()  # vendor billing may start at session creation
    join_timeout = max(5.0, startup_s - 15.0)
    renderer, display, fallback_reason = await start_with_fallback(
        renderer, session, ctx.room, join_timeout_s=join_timeout
    )
    if fallback_reason:
        avatar_clock.stop()
        await _safe(api.event("fallback_to_voice", {"reason": fallback_reason}))

    await session.start(
        agent=InterviewAgent(instructions=policy["instructions"]),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            participant_identity=cfg["student_identity"],
            close_on_disconnect=True,
            text_input=False,
        ),
    )

    ready = await api.event("media_ready", {"display": display})
    if not ready.get("live"):
        await stop("settled_before_ready")
        return
    turns.practice_start_epoch = time.time()
    practice_ends_at = float(ready["practice_ends_at"])
    await ctx.room.local_participant.set_attributes(
        {
            "ni.display": display,
            "ni.practice_ends_at_ms": str(int(practice_ends_at * 1000)),
            "ni.fallback": fallback_reason or "",
        }
    )

    async def watchdog() -> None:
        await sleep_until_epoch(practice_ends_at)
        if closing.is_set():
            return
        await session.interrupt(force=True)
        handle = voice.speak_exact(session, policy["closing_line"])
        try:
            await asyncio.wait_for(
                handle.wait_for_playout(), timeout=max(3, int(cfg["closing_grace_s"]) - 5)
            )
        except Exception:
            pass
        await stop("deadline")

    async def heartbeat() -> None:
        while not closing.is_set():
            await asyncio.sleep(HEARTBEAT_S)
            try:
                hb = await api.event("heartbeat")
                if not hb.get("live"):
                    stop_soon("settled_elsewhere")  # student ended / reconciled
                    return
                await send_usage()
            except Exception:
                log.warning("heartbeat failed", exc_info=True)

    tasks += [asyncio.create_task(watchdog()), asyncio.create_task(heartbeat())]
    voice.speak_exact(session, policy["opening_line"])
    await teardown.wait()


async def _finish(api: InternalApi, reason: str, ctx: JobContext, agent_clock: WallClock):
    """Exit before any paid provider started: refund (media never ready) and close."""
    agent_clock.stop()
    await _safe(api.finalize(reason))
    await _safe(api.usage(usage_events([], {"livekit.agent_session_seconds": agent_clock.seconds})))
    ctx.delete_room()
    await api.aclose()


async def _safe(coro):
    try:
        return await coro
    except Exception:
        log.warning("non-fatal call failed", exc_info=True)
        return {}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cli.run_app(server)
