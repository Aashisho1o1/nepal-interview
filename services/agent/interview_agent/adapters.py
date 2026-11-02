"""Voice engine and avatar renderer adapters.

The interview policy decides what is said; a VoiceEngine turns that into speech
and hears the student; an AvatarRenderer only animates the voice it is given. Each
can be replaced without touching the others.

Trinity2Config is adapted from simliai/create-simli-app-livekit-agents (MIT,
commit e85f8ea6c6e11f4175e318ff4e849e82dc9f3749); see THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any, Protocol

from livekit import rtc
from livekit.agents import AgentSession
from livekit.plugins import openai, simli

log = logging.getLogger("interview_agent.adapters")


# --------------------------------------------------------------------------- voice


class VoiceEngine(Protocol):
    name: str

    def session_kwargs(self, *, max_session_s: float) -> dict[str, Any]: ...

    def speak_exact(self, session: AgentSession, text: str):
        """Speak fixed text (opening, closing). Returns a SpeechHandle."""
        ...


class OpenAIRealtimeVoice:
    """Speech-to-speech. One provider hears and speaks; no separate STT/TTS."""

    name = "openai_realtime"

    def __init__(self, model: str | None = None, voice: str | None = None):
        self.model = model or os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime")
        self.voice = voice or os.getenv("OPENAI_REALTIME_VOICE", "marin")

    def session_kwargs(self, *, max_session_s: float) -> dict[str, Any]:
        return {
            "llm": openai.realtime.RealtimeModel(
                model=self.model,
                voice=self.voice,
                # Provider-side cap so a stuck worker cannot keep the model session open.
                max_session_duration=max_session_s,
            )
        }

    def speak_exact(self, session: AgentSession, text: str):
        # A realtime model has no TTS to `say` through; instruct it to read the line.
        return session.generate_reply(
            instructions=f"Say exactly the following and nothing else: {text}"
        )


class CascadeVoice:
    """STT + text model + TTS through LiveKit Inference. Benchmark candidate for the
    basic tier; model ids are configuration, not product decisions."""

    name = "cascade"

    def __init__(self) -> None:
        self.stt = os.getenv("CASCADE_STT", "assemblyai/universal-3-6-pro")
        self.llm = os.getenv("CASCADE_LLM", "google/gemma-4-31b-it")
        self.tts = os.getenv("CASCADE_TTS", "fishaudio/s2.1-pro")

    def session_kwargs(self, *, max_session_s: float) -> dict[str, Any]:
        return {"stt": self.stt, "llm": self.llm, "tts": self.tts}

    def speak_exact(self, session: AgentSession, text: str):
        return session.say(text)


def make_voice(name: str) -> VoiceEngine:
    if name == "cascade":
        return CascadeVoice()
    return OpenAIRealtimeVoice()


# --------------------------------------------------------------------------- avatar


@dataclass
class Trinity2Config(simli.SimliConfig):
    """SimliConfig plus Trinity-2 framing; sends the plain face id. From the Simli
    starter. Portrait framing suits phones."""

    streaming_width: int = 768
    streaming_height: int = 768
    avatar_position_x: float = 0.5
    avatar_position_y: float = 1.0
    camera: dict[str, float] | None = None
    background_id: str | None = None
    foreground_id: str | None = None

    def create_json(self) -> dict[str, Any]:
        body = super().create_json()
        body["faceId"] = self.face_id
        for name in (
            "streaming_width",
            "streaming_height",
            "avatar_position_x",
            "avatar_position_y",
            "camera",
            "background_id",
            "foreground_id",
        ):
            if (value := getattr(self, name)) is not None:
                body[name] = value
        return body


class AvatarRenderer(Protocol):
    name: str
    identity: str | None

    async def start(
        self, session: AgentSession, room: rtc.Room, *, join_timeout_s: float
    ) -> tuple[bool, str]: ...

    async def aclose(self) -> None: ...


class PortraitRenderer:
    """No rendered face; the browser shows a still portrait and voice plays directly."""

    name = "portrait"
    identity = None

    async def start(self, session, room, *, join_timeout_s):
        return True, "portrait"

    async def aclose(self) -> None:
        return None


class SimliRenderer:
    name = "simli"

    def __init__(self, *, max_session_s: int, max_idle_s: int):
        self.cfg = Trinity2Config(
            api_key=os.environ["SIMLI_API_KEY"],
            face_id=os.environ["SIMLI_FACE_ID"],  # a licensed fictional face; no default
            # Simli-side caps: even if this worker dies, the vendor session ends.
            max_session_length=max_session_s,
            max_idle_time=max_idle_s,
        )
        self._avatar: simli.AvatarSession | None = None
        self.identity: str | None = None

    async def start(self, session, room, *, join_timeout_s):
        self._avatar = simli.AvatarSession(simli_config=self.cfg)
        self.identity = self._avatar.avatar_identity
        await self._avatar.start(session, room=room)
        # The plugin logs and returns (without raising) on Simli API errors; it only
        # routes audio to the avatar on success.
        if session.output.audio is None:
            return False, "simli_start_failed"
        try:
            await self._avatar.wait_for_join(timeout=join_timeout_s)
        except TimeoutError:
            return False, "simli_join_timeout"
        return True, "avatar"

    async def aclose(self) -> None:
        if self._avatar is not None:
            await self._avatar.aclose()  # removes the avatar participant from the room


# Avatar renderers our own agent can drive, by the name in config/providers.json
# ("avatar": "simli"). Add LiveKit avatar plugins (liveavatar, tavus, anam, bithuman)
# here as small AvatarRenderer classes; the API side needs only a providers.json entry.
AVATAR_RENDERERS = {"simli": SimliRenderer}


def make_avatar(name: str | None, *, max_session_s: int, max_idle_s: int) -> AvatarRenderer:
    if not name:
        return PortraitRenderer()
    try:
        cls = AVATAR_RENDERERS[name]
    except KeyError as e:
        raise ValueError(f"unknown avatar renderer {name!r}") from e
    return cls(max_session_s=max_session_s, max_idle_s=max_idle_s)


async def start_with_fallback(
    renderer: AvatarRenderer, session: AgentSession, room: rtc.Room, *, join_timeout_s: float
) -> tuple[AvatarRenderer, str, str | None]:
    """Try the avatar before the voice session starts. On any failure close it, clear
    the audio route so the voice publishes directly, and continue in portrait mode.
    Returns (renderer in use, display, fallback reason)."""
    if isinstance(renderer, PortraitRenderer):
        return renderer, "portrait", None
    try:
        ok, why = await renderer.start(session, room, join_timeout_s=join_timeout_s)
    except Exception as e:  # missing key, network, plugin error
        ok, why = False, f"avatar_error:{type(e).__name__}"
    if ok:
        return renderer, "avatar", None
    try:
        await asyncio.wait_for(renderer.aclose(), timeout=5)
    except Exception:
        log.warning("closing failed avatar raised", exc_info=True)
    # Exactly one audio stream: drop the avatar route so RoomIO publishes agent audio.
    session.output.audio = None
    return PortraitRenderer(), "portrait", why
