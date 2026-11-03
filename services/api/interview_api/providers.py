"""Interview providers: one interface for every way a mock interview can be delivered.

Everything that differs between vendors lives here. Everything that must stay the
same across vendors (auth, quota reservation and settlement, the practice clock,
ending sessions, ratings, the scorecard) lives in app.py / quota.py and never
branches on a vendor name.

A provider answers three questions:
  * launch(ctx)   -> what the browser needs to show the interview (a "launch" dict
                     whose `kind` picks a frontend stage: "iframe" or "elevenlabs")
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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx

log = logging.getLogger("interview_api.providers")

DEFAULT_PROVIDERS_FILE = Path(__file__).resolve().parents[3] / "config" / "providers.json"
INTEGRATIONS = ("iframe_embed", "elevenlabs_agent")


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
    transport: str  # "iframe" | "elevenlabs"

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
        try:
            r = await self.http.get(
                f"{self.API}/convai/conversation/token",
                params=params,
                headers={"xi-api-key": self.api_key},
            )
        except httpx.HTTPError as e:
            raise ProviderError(f"elevenlabs unreachable: {e!r}") from e
        if r.status_code >= 400:
            raise ProviderError(f"elevenlabs {r.status_code}: {r.text[:300]}")
        token = r.json().get("token")
        if not token:
            raise ProviderError("elevenlabs returned no token")
        return {**out, "conversation_token": token}

    async def close(self, sess: dict[str, Any]) -> bool:
        return True  # ends when the browser disconnects; agent max duration is the backstop


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
