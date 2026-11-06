"""Interview providers: one interface for every way a mock interview can be delivered.

Everything that differs between vendors lives here. Everything that must stay the
same across vendors (auth, quota reservation and settlement, the practice clock,
ending sessions, ratings, the scorecard) lives in app.py / quota.py and never
branches on a vendor name.

A provider answers three questions:
  * launch(ctx)   -> what the browser needs to show the interview (a "launch" dict
                     whose `kind` picks a frontend stage in components/stages)
  * close(sess)   -> best-effort stop of anything still running at the vendor
  * stateful      -> does launching create something at the vendor that must be
                     created exactly once per session?

The browser reports the lifecycle (media ready, heartbeats) for every provider; the
server enforces the deadline and settles credits.

Adding a vendor = add a class (or reuse IframeEmbedProvider) + an entry in
config/providers.json. Nothing else changes.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Awaitable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx

from interview_core.dynamic_vars import build_dynamic_variables

log = logging.getLogger("interview_api.providers")

DEFAULT_PROVIDERS_FILE = Path(__file__).resolve().parents[3] / "config" / "providers.json"
INTEGRATIONS = ("iframe_embed", "elevenlabs_agent", "liveavatar_lite", "keyframe_persona")


class ProviderError(Exception):
    """A vendor call failed. The session is refunded and the student sees a retry."""


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    label: str
    vendor: str
    integration: str
    modality: str  # "avatar" (premium bucket) | "voice" (basic bucket)
    data_note: str = ""
    capabilities: dict[str, bool] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    def public(self) -> dict[str, Any]:
        """What the student's browser may see. Vendor names are hidden so test
        participants rate the experience, not the brand."""
        return {
            "id": self.id,
            "label": self.label,
            "modality": self.modality,
            "data_note": self.data_note,
            "capabilities": self.capabilities,
        }


@dataclass(frozen=True)
class LaunchContext:
    session_id: str
    student_id: str
    student_name: str
    practice_seconds: int
    max_vendor_seconds: int  # vendor-side hard cap: startup + practice + closing grace
    # Short plain-text values for hosted agents that template their own prompt
    # (ElevenLabs {{variables}}). Built from confirmed facts only.
    dynamic_variables: dict[str, str] = field(default_factory=dict)


class InterviewProvider(Protocol):
    spec: ProviderSpec
    stateful: bool
    transport: str  # same as the launch kind

    async def launch(self, ctx: LaunchContext) -> dict[str, Any]: ...

    async def close(self, sess: dict[str, Any]) -> bool: ...

    def session_providers(self) -> dict[str, Any]:
        """Stored on the session row for reporting."""
        ...


def _checked_url(url: str, allowed_hosts: list[str]) -> str:
    parts = urlsplit(url)
    local_dev = parts.hostname in ("localhost", "127.0.0.1")
    if parts.scheme != "https" and not (local_dev and parts.scheme == "http"):
        raise ValueError(f"embed URL must be https: {url!r}")
    if parts.hostname not in allowed_hosts:
        raise ValueError(f"embed host {parts.hostname!r} is not in allowed_hosts {allowed_hosts}")
    return url


def _origin(url: str) -> str:
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}"


async def _vendor_json(vendor: str, request: Awaitable[httpx.Response]) -> dict[str, Any]:
    """A vendor's JSON reply. Anything else is a ProviderError (refund and retry), never a
    raw 500."""
    try:
        r = await request
        if r.status_code >= 400:
            raise ProviderError(f"{vendor} {r.status_code}: {r.text[:300]}")
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        raise ProviderError(f"{vendor} unreachable or bad reply: {e!r}") from e
    if not isinstance(data, dict):
        raise ProviderError(f"{vendor} returned unexpected JSON")
    return data


def _blank_variables(ctx: LaunchContext) -> dict[str, str]:
    """The same prompt as voice, with nothing about the student: the agent asks instead
    ("not provided" means ask). For a path where the variables would pass through the
    avatar vendor."""
    return build_dynamic_variables(
        session_id=ctx.session_id,
        student_name="",
        facts={},
        funding=None,
        practice_seconds=ctx.practice_seconds,
    )


# --------------------------------------------------------------------------- iframe


class IframeEmbedProvider:
    """A vendor's ready-made embed (e.g. a LiveAvatar embed URL). Fastest to test.

    Limits, by design of static embeds: the persona and its knowledge are configured
    in the vendor dashboard, so it cannot see this student's confirmed facts; the
    vendor does not send us transcripts; and we cannot stop the vendor stream from
    the server (the browser unmounts the iframe at the deadline, and the vendor's own
    session cap is the backstop). Anyone holding the embed URL can use it, so it is
    only returned to signed-in students with a reserved session.
    """

    stateful = False
    transport = "iframe"

    def __init__(self, spec: ProviderSpec, url: str):
        self.spec = spec
        self.url = _checked_url(url, spec.raw.get("allowed_hosts", []))

    def session_providers(self) -> dict[str, Any]:
        return {
            "provider_id": self.spec.id,
            "integration": self.spec.integration,
            "transport": self.transport,
            "vendor": self.spec.vendor,
        }

    async def launch(self, ctx: LaunchContext) -> dict[str, Any]:
        r = self.spec.raw
        return {
            "kind": "iframe",
            "url": self.url,
            "origin": _origin(self.url),
            "allow": r.get("allow", "microphone; autoplay"),
            "aspect_ratio": r.get("aspect_ratio", "16 / 9"),
            "clock_start": r.get("clock_start", "on_interaction"),
            "clock_fallback_ms": int(r.get("clock_fallback_ms", 20000)),
            "title": "Practice interviewer",
        }

    async def close(self, sess: dict[str, Any]) -> bool:
        return True  # nothing server-side to stop for a static embed


# --------------------------------------------------------------------------- ElevenLabs


class ElevenLabsAgentProvider:
    """An ElevenLabs agent (prompt, voice and turn-taking configured in their dashboard)
    that the browser talks to directly with the ElevenLabs SDK.

    Private agent (ELEVENLABS_API_KEY set): we mint a short-lived WebRTC conversation
    token per session; the browser never sees our key. Public agent without a key: the
    browser gets only the agent id, which anyone could also use, so this is allowed
    only when ELEVENLABS_ALLOW_PUBLIC_AGENT=true (local testing).

    Nothing can be stopped from our server: the call ends when the browser
    disconnects, and the agent's own max-duration setting is the backstop.
    """

    stateful = False
    transport = "elevenlabs"
    API = "https://api.elevenlabs.io/v1"

    def __init__(
        self,
        spec: ProviderSpec,
        *,
        agent_id: str,
        api_key: str | None,
        branch_id: str | None = None,
        http: httpx.AsyncClient | None = None,
    ):
        self.spec, self.agent_id, self.api_key, self.branch_id = spec, agent_id, api_key, branch_id
        self.http = http or httpx.AsyncClient(timeout=15)

    def session_providers(self) -> dict[str, Any]:
        return {
            "provider_id": self.spec.id,
            "integration": self.spec.integration,
            "transport": self.transport,
            "vendor": "elevenlabs",
            "agent_access": "token" if self.api_key else "public",
        }

    async def launch(self, ctx: LaunchContext) -> dict[str, Any]:
        out: dict[str, Any] = {
            "kind": "elevenlabs",
            "connection_type": "webrtc",
            "dynamic_variables": ctx.dynamic_variables,
        }
        if not self.api_key:
            return {**out, "agent_id": self.agent_id}
        params = {"agent_id": self.agent_id}
        if self.branch_id:
            params["branch_id"] = self.branch_id
        reply = await _vendor_json(
            "elevenlabs",
            self.http.get(
                f"{self.API}/convai/conversation/token",
                params=params,
                headers={"xi-api-key": self.api_key},
            ),
        )
        token = reply.get("token")
        if not token:
            raise ProviderError("elevenlabs returned no token")
        return {**out, "conversation_token": token}

    async def close(self, sess: dict[str, Any]) -> bool:
        return True  # ends when the browser disconnects; agent max duration is the backstop


# --------------------------------------------------------------------------- video agents


class LiveAvatarLiteProvider:
    """LiveAvatar in LITE ("avatar only") mode: it draws the face, and our ElevenLabs agent
    listens, thinks and talks through LiveAvatar's connector. We mint a session token per
    session; the browser SDK starts the session with it. The server can stop it, and
    max_session_duration caps it at the vendor. The token request goes through LiveAvatar,
    so it carries no student details."""

    stateful = True
    transport = "liveavatar"
    API = "https://api.liveavatar.com/v1"

    def __init__(
        self,
        spec: ProviderSpec,
        *,
        api_key: str,
        avatar_id: str,
        secret_id: str,
        agent_id: str,
        sandbox: bool = False,
        http: httpx.AsyncClient | None = None,
    ):
        self.spec, self.api_key, self.avatar_id = spec, api_key, avatar_id
        self.secret_id, self.agent_id, self.sandbox = secret_id, agent_id, sandbox
        self.http = http or httpx.AsyncClient(timeout=15)

    def session_providers(self) -> dict[str, Any]:
        return {
            "provider_id": self.spec.id,
            "integration": self.spec.integration,
            "transport": self.transport,
            "vendor": self.spec.vendor,
        }

    async def launch(self, ctx: LaunchContext) -> dict[str, Any]:
        reply = await _vendor_json(
            "liveavatar",
            self.http.post(
                f"{self.API}/sessions/token",
                headers={"X-API-KEY": self.api_key},
                json={
                    "mode": "LITE",
                    "avatar_id": self.avatar_id,
                    "is_sandbox": self.sandbox,
                    # Sandbox refuses anything over 60 s.
                    "max_session_duration": 60 if self.sandbox else ctx.max_vendor_seconds,
                    "video_settings": {"quality": "medium", "encoding": "H264"},
                    "elevenlabs_agent_config": {
                        "secret_id": self.secret_id,
                        "agent_id": self.agent_id,
                        "dynamic_variables": _blank_variables(ctx),
                    },
                },
            ),
        )
        data = reply.get("data") or {}
        if not data.get("session_token") or not data.get("session_id"):
            raise ProviderError("liveavatar returned no session token")
        return {
            "kind": "liveavatar",
            "session_token": data["session_token"],
            "vendor_ref": data["session_id"],
        }

    async def close(self, sess: dict[str, Any]) -> bool:
        if not sess.get("vendor_ref"):
            return True  # nothing was ever created at the vendor
        try:
            r = await self.http.post(
                f"{self.API}/sessions/stop",
                headers={"X-API-KEY": self.api_key},
                json={"session_id": sess["vendor_ref"], "reason": "USER_CLOSED"},
                timeout=5,
            )
        except httpx.HTTPError as e:
            log.warning("liveavatar stop failed: %r", e)
            return False
        # The browser SDK stops the session too, and the reply to a second stop isn't
        # documented. Other 4xx can't be fixed by retrying, so they count as closed.
        return r.status_code < 500 and r.status_code not in (401, 403, 408, 429)


class KeyframeProvider:
    """A Keyframe avatar driven by our ElevenLabs agent. The browser talks to ElevenLabs
    over a signed URL, sending the student's voice and details there only, and passes the
    agent's audio to Keyframe to animate. Both keys stay here. Keyframe documents no server
    stop or per-session cap: the browser disconnecting ends it, and the video agent's max
    duration is the backstop."""

    stateful = True
    transport = "keyframe"
    API = "https://api.keyframelabs.com/v1"
    ELEVENLABS_API = "https://api.elevenlabs.io/v1"

    def __init__(
        self,
        spec: ProviderSpec,
        *,
        api_key: str,
        persona: str,
        agent_id: str,
        elevenlabs_key: str,
        http: httpx.AsyncClient | None = None,
    ):
        self.spec, self.api_key, self.persona = spec, api_key, persona
        self.agent_id, self.elevenlabs_key = agent_id, elevenlabs_key
        self.http = http or httpx.AsyncClient(timeout=15)

    def session_providers(self) -> dict[str, Any]:
        return {
            "provider_id": self.spec.id,
            "integration": self.spec.integration,
            "transport": self.transport,
            "vendor": self.spec.vendor,
        }

    async def launch(self, ctx: LaunchContext) -> dict[str, Any]:
        signed = await _vendor_json(
            "elevenlabs",
            self.http.get(
                f"{self.ELEVENLABS_API}/convai/conversation/get-signed-url",
                params={"agent_id": self.agent_id},
                headers={"xi-api-key": self.elevenlabs_key},
            ),
        )
        session = await _vendor_json(
            "keyframe",
            self.http.post(
                f"{self.API}/sessions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"persona_slug": self.persona},
            ),
        )
        try:
            details = {k: session[k] for k in ("server_url", "participant_token", "agent_identity")}
            voice_agent = {
                "type": "elevenlabs",
                "agent_id": self.agent_id,
                "signed_url": signed["signed_url"],
            }
        except KeyError as e:
            raise ProviderError(f"keyframe launch reply is missing {e}") from e
        return {
            "kind": "keyframe",
            "session_details": details,
            "voice_agent": voice_agent,
            "dynamic_variables": ctx.dynamic_variables,
        }

    async def close(self, sess: dict[str, Any]) -> bool:
        return True  # nothing to call; see the class comment


# --------------------------------------------------------------------------- registry


@dataclass
class ProviderRegistry:
    providers: dict[str, InterviewProvider]
    order: list[str]
    disabled: dict[str, str]  # id -> reason, for operators

    def get(self, provider_id: str) -> InterviewProvider:
        return self.providers[provider_id]

    def enabled(self) -> list[InterviewProvider]:
        return [self.providers[i] for i in self.order if i in self.providers]

    def frame_origins(self) -> list[str]:
        """Origins the web app must allow microphone/autoplay for (Permissions-Policy)."""
        out = []
        for p in self.enabled():
            if p.transport == "iframe":
                for h in p.spec.raw.get("allowed_hosts", []):
                    out.append(f"https://{h}")
        return sorted(set(out))


def load_registry(
    settings: Any,
    *,
    env: dict[str, str] | None = None,
    path: str | Path | None = None,
    http: httpx.AsyncClient | None = None,
) -> ProviderRegistry:
    env = dict(os.environ if env is None else env)
    data = json.loads(Path(path or settings.providers_file or DEFAULT_PROVIDERS_FILE).read_text())
    only = {x.strip() for x in env.get("ENABLED_PROVIDERS", "").split(",") if x.strip()}
    providers: dict[str, InterviewProvider] = {}
    order: list[str] = []
    disabled: dict[str, str] = {}
    for raw in data["providers"]:
        pid = raw["id"]
        if raw.get("integration") not in INTEGRATIONS:
            disabled[pid] = f"unknown integration {raw.get('integration')!r}"
            continue
        if raw.get("modality") not in ("avatar", "voice"):
            disabled[pid] = "modality must be avatar or voice"
            continue
        if not raw.get("enabled", False) or (only and pid not in only):
            disabled[pid] = "disabled in config"
            continue
        missing = [k for k in raw.get("requires_env", []) if not env.get(k)]
        if raw.get("url_env") and not env.get(raw["url_env"]):
            missing.append(raw["url_env"])
        if missing:
            disabled[pid] = f"missing env: {', '.join(missing)}"
            continue
        spec = ProviderSpec(
            id=pid,
            label=raw["label"],
            vendor=raw.get("vendor", ""),
            integration=raw["integration"],
            modality=raw["modality"],
            data_note=raw.get("data_note", ""),
            capabilities=dict(raw.get("capabilities", {})),
            raw=raw,
        )
        try:
            if raw["integration"] == "iframe_embed":
                prov: InterviewProvider = IframeEmbedProvider(spec, env[raw["url_env"]])
            elif raw["integration"] == "liveavatar_lite":
                prov = LiveAvatarLiteProvider(
                    spec,
                    api_key=env["LIVEAVATAR_API_KEY"],
                    avatar_id=env["LIVEAVATAR_AVATAR_ID"],
                    secret_id=env["LIVEAVATAR_ELEVENLABS_SECRET_ID"],
                    agent_id=env["ELEVENLABS_VIDEO_AGENT_ID"],
                    sandbox=env.get("LIVEAVATAR_SANDBOX", "").lower() in ("1", "true"),
                    http=http,
                )
            elif raw["integration"] == "keyframe_persona":
                prov = KeyframeProvider(
                    spec,
                    api_key=env["KEYFRAME_API_KEY"],
                    persona=env["KEYFRAME_PERSONA"],
                    agent_id=env["ELEVENLABS_VIDEO_AGENT_ID"],
                    elevenlabs_key=env["ELEVENLABS_API_KEY"],
                    http=http,
                )
            else:  # elevenlabs_agent
                key = env.get("ELEVENLABS_API_KEY") or None
                public_ok = env.get("ELEVENLABS_ALLOW_PUBLIC_AGENT", "").lower() in ("1", "true")
                if not key and not public_ok:
                    disabled[pid] = (
                        "missing env: ELEVENLABS_API_KEY "
                        "(or ELEVENLABS_ALLOW_PUBLIC_AGENT=true for a public test agent)"
                    )
                    continue
                prov = ElevenLabsAgentProvider(
                    spec,
                    agent_id=env["ELEVENLABS_AGENT_ID"],
                    api_key=key,
                    branch_id=env.get("ELEVENLABS_BRANCH_ID") or None,
                    http=http,
                )
        except ValueError as e:
            disabled[pid] = str(e)
            continue
        providers[pid] = prov
        order.append(pid)
    # Warnings, not info: hosts print them with no logging setup, so a missing setting
    # shows in the deploy logs instead of only as "No interviewer is available".
    for pid, why in disabled.items():
        log.warning("provider %s not offered: %s", pid, why)
    if not providers:
        log.warning("no interviewer is configured: students will see none")
    return ProviderRegistry(providers, order, disabled)
