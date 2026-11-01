"""Framework-independent session runtime: turns, timing, silence, usage, teardown.

Nothing here imports LiveKit, so every rule is unit-tested with fakes
(tests/test_agent_runtime.py). agent.py wires these to LiveKit events.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("interview_agent.runtime")


# --------------------------------------------------------------------------- turns


@dataclass
class TurnRecorder:
    """Builds the transcript sent to the API. Times are ms since the practice clock
    started (media ready). Interrupted interviewer turns are kept and marked canceled,
    so feedback never treats words the student did not hear as spoken."""

    practice_start_epoch: float | None = None
    _seq: int = 0
    _pending: dict[str, dict] = field(default_factory=dict)
    _sent: dict[str, dict] = field(default_factory=dict)

    def _ms(self, epoch: float | None) -> int:
        if epoch is None or self.practice_start_epoch is None:
            return 0
        return max(0, int(round((epoch - self.practice_start_epoch) * 1000)))

    def add(
        self,
        *,
        item_id: str,
        role: str,
        text: str | None,
        interrupted: bool,
        created_at: float,
        metrics: dict[str, Any] | None = None,
    ) -> dict | None:
        if role not in ("user", "assistant") or not text or not text.strip():
            return None
        metrics = dict(metrics or {})
        start = metrics.get("started_speaking_at") or created_at
        end = metrics.get("stopped_speaking_at") or created_at
        if item_id in self._sent or item_id in self._pending:
            turn = (self._sent.get(item_id) or self._pending[item_id]).copy()
        else:
            self._seq += 1
            turn = {"turn_id": item_id, "sequence": self._seq}
        turn.update(
            speaker="student" if role == "user" else "interviewer",
            text=text.strip()[:8000],
            start_ms=self._ms(start),
            end_ms=max(self._ms(end), self._ms(start)),
            canceled=bool(interrupted) and role == "assistant",
            metrics={k: v for k, v in metrics.items() if isinstance(v, (int, float))},
        )
        self._pending[item_id] = turn
        return turn

    def take_pending(self) -> list[dict]:
        out = sorted(self._pending.values(), key=lambda t: t["sequence"])
        return out

    def mark_sent(self, turns: list[dict]) -> None:
        for t in turns:
            if self._pending.get(t["turn_id"]) is t:
                del self._pending[t["turn_id"]]
            self._sent[t["turn_id"]] = t

    @property
    def student_turns(self) -> int:
        all_turns = {**self._sent, **self._pending}
        return sum(1 for t in all_turns.values() if t["speaker"] == "student")


# --------------------------------------------------------------------------- timing


@dataclass
class TimingMeter:
    """Measures, from session state events:
    * response latency: student stops speaking -> interviewer state becomes speaking
    * interruption stop: student starts speaking while interviewer speaks ->
      interviewer leaves the speaking state.
    These are agent-side signals. Audible latency at the student's device also
    includes network and playout buffers; the browser reports its own measurement.
    """

    clock: Callable[[], float] = time.monotonic
    agent_state: str = "initializing"
    user_state: str = "listening"
    _user_stopped_at: float | None = None
    _interrupt_started_at: float | None = None
    response_latencies_ms: list[int] = field(default_factory=list)
    interruption_stop_ms: list[int] = field(default_factory=list)
    interruptions: int = 0

    def on_user_state(self, new: str) -> dict | None:
        now = self.clock()
        old, self.user_state = self.user_state, new
        if new == "speaking":
            self._user_stopped_at = None
            if self.agent_state == "speaking" and self._interrupt_started_at is None:
                self._interrupt_started_at = now
                self.interruptions += 1
        elif old == "speaking" and new == "listening":
            self._user_stopped_at = now
        return None

    def on_agent_state(self, new: str) -> dict | None:
        now = self.clock()
        old, self.agent_state = self.agent_state, new
        event = None
        if old == "speaking" and new != "speaking" and self._interrupt_started_at is not None:
            ms = round((now - self._interrupt_started_at) * 1000)
            self.interruption_stop_ms.append(ms)
            event = {"kind": "interruption", "payload": {"stop_signal_ms": ms}}
            self._interrupt_started_at = None
        if new == "speaking":
            self._interrupt_started_at = None
            if self._user_stopped_at is not None:
                ms = round((now - self._user_stopped_at) * 1000)
                self.response_latencies_ms.append(ms)
                event = {"kind": "latency", "payload": {"response_ms": ms}}
                self._user_stopped_at = None
        return event


def percentile(values: list[int | float], p: float) -> float | None:
    if not values:
        return None
    v = sorted(values)
    k = (len(v) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return float(v[lo] + (v[hi] - v[lo]) * (k - lo))


# --------------------------------------------------------------------------- silence


@dataclass
class SilencePolicy:
    """First silence: a gentle prompt. Silence again without the student speaking in
    between: end the session as no_input (refunded server-side if short). The framework
    marks the student 'away' after `away_timeout_s` of mutual silence, so a student who
    is thinking gets a prompt, not a disconnect."""

    prompts_before_end: int = 1
    _prompts: int = 0

    def on_user_state(self, new: str) -> str | None:
        if new == "speaking":
            self._prompts = 0
            return None
        if new == "away":
            if self._prompts < self.prompts_before_end:
                self._prompts += 1
                return "prompt"
            return "end"
        return None


# --------------------------------------------------------------------------- usage


def usage_events(model_usage: list[Any], wall_meters: dict[str, float]) -> list[dict]:
    """Converts the framework's cumulative per-model usage plus wall-clock meters into
    cumulative ledger events (safe to resend)."""
    events = []
    for u in model_usage:
        d = u.model_dump() if hasattr(u, "model_dump") else dict(u)
        provider, model = d.pop("provider", "unknown"), d.pop("model", "unknown")
        kind = d.pop("type", "usage")
        for k, v in d.items():
            if isinstance(v, (int, float)) and v:
                meter = f"{provider}.{model}.{k}"
                unit = (
                    "second"
                    if k.endswith("duration")
                    else (
                        "character"
                        if "characters" in k
                        else "request"
                        if "requests" in k
                        else "token"
                    )
                )
                events.append(
                    {
                        "provider_event_id": f"cum:{meter}",
                        "provider": provider,
                        "meter": meter,
                        "quantity": str(round(float(v), 6)),
                        "unit": unit,
                        "cumulative": True,
                        "_kind": kind,
                    }
                )
    for meter, secs in wall_meters.items():
        events.append(
            {
                "provider_event_id": f"cum:{meter}",
                "provider": meter.split(".")[0],
                "meter": meter,
                "quantity": f"{max(0.0, secs):.3f}",
                "unit": "second",
                "cumulative": True,
            }
        )
    for e in events:
        e.pop("_kind", None)
    return events


@dataclass
class WallClock:
    """Start/stop wall-clock meter for provider time we are billed on (avatar, agent)."""

    clock: Callable[[], float] = time.monotonic
    started: float | None = None
    stopped: float | None = None

    def start(self) -> None:
        if self.started is None:
            self.started = self.clock()

    def stop(self) -> None:
        if self.started is not None and self.stopped is None:
            self.stopped = self.clock()

    @property
    def seconds(self) -> float:
        if self.started is None:
            return 0.0
        return (self.stopped or self.clock()) - self.started


# --------------------------------------------------------------------------- teardown

Step = tuple[str, Callable[[], Awaitable[Any]], float]


class Teardown:
    """Runs the shutdown steps exactly once, in order, each with its own timeout, and
    keeps going when a step fails. Every exit path (deadline, student left, browser
    closed, provider failure, job shutdown) calls `run`; only the first call executes.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._done = asyncio.Event()
        self.reason: str | None = None
        self.results: list[tuple[str, str]] = []
        self.started = False

    @property
    def done(self) -> bool:
        return self._done.is_set()

    async def wait(self) -> None:
        await self._done.wait()

    async def run(self, reason: str, steps: list[Step]) -> bool:
        if self.started:
            await self._done.wait()
            return False
        async with self._lock:
            if self.started:
                return False
            self.started = True
            self.reason = reason
            for name, fn, timeout in steps:
                try:
                    await asyncio.wait_for(fn(), timeout=timeout)
                    self.results.append((name, "ok"))
                except TimeoutError:
                    self.results.append((name, "timeout"))
                    log.warning("teardown step %s timed out", name)
                except Exception as e:  # keep closing the rest
                    self.results.append((name, f"error: {e!r}"[:200]))
                    log.warning("teardown step %s failed", name, exc_info=True)
            self._done.set()
            return True


async def sleep_until_epoch(epoch: float, clock: Callable[[], float] = time.time) -> None:
    delay = epoch - clock()
    if delay > 0:
        await asyncio.sleep(delay)
