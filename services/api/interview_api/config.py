from __future__ import annotations

import os
from dataclasses import dataclass, field


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


@dataclass(frozen=True)
class Settings:
    database_url: str = field(
        default_factory=lambda: os.environ.get(
            "DATABASE_URL", "postgresql://localhost/nepal_interview"
        )
    )
    livekit_url: str = field(default_factory=lambda: os.getenv("LIVEKIT_URL", ""))
    livekit_api_key: str = field(default_factory=lambda: os.getenv("LIVEKIT_API_KEY", ""))
    livekit_api_secret: str = field(default_factory=lambda: os.getenv("LIVEKIT_API_SECRET", ""))
    agent_name: str = field(
        default_factory=lambda: os.getenv("LIVEKIT_AGENT_NAME", "nepal-interview-agent")
    )
    allowed_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip()
            for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
            if o.strip()
        )
    )
    cookie_secure: bool = field(default_factory=lambda: _bool("COOKIE_SECURE", True))
    login_ttl_hours: int = field(default_factory=lambda: _int("LOGIN_TTL_HOURS", 12))
    # Startup budget before the student clock starts. Avatar includes Simli join time.
    startup_budget_avatar_s: int = field(
        default_factory=lambda: _int("STARTUP_BUDGET_AVATAR_S", 45)
    )
    startup_budget_voice_s: int = field(default_factory=lambda: _int("STARTUP_BUDGET_VOICE_S", 25))
    closing_grace_s: int = field(default_factory=lambda: _int("CLOSING_GRACE_S", 15))
    teardown_grace_s: int = field(default_factory=lambda: _int("TEARDOWN_GRACE_S", 30))
    heartbeat_timeout_s: int = field(default_factory=lambda: _int("HEARTBEAT_TIMEOUT_S", 45))
    max_starts_per_10min: int = field(default_factory=lambda: _int("MAX_STARTS_PER_10MIN", 6))
    # Refund rule: a session with no student speech that ends within this window.
    no_input_refund_s: int = field(default_factory=lambda: _int("NO_INPUT_REFUND_S", 60))
    # Kill switches.
    avatar_enabled: bool = field(default_factory=lambda: _bool("AVATAR_ENABLED", True))
    sessions_enabled: bool = field(default_factory=lambda: _bool("SESSIONS_ENABLED", True))
    voice_engine: str = field(default_factory=lambda: os.getenv("VOICE_ENGINE", "openai_realtime"))
    grader: str = field(default_factory=lambda: os.getenv("GRADER", "rules"))
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    grader_model: str = field(default_factory=lambda: os.getenv("GRADER_MODEL", ""))
    price_table_path: str | None = field(default_factory=lambda: os.getenv("PRICE_TABLE_PATH"))
    # "livekit" in every real deployment; "fake" only for UI work without LiveKit.
    media_backend: str = field(default_factory=lambda: os.getenv("MEDIA_BACKEND", "livekit"))
    providers_file: str | None = field(default_factory=lambda: os.getenv("PROVIDERS_FILE"))
    # Browser-reported heartbeats (embeds/hosted vendors) get more slack than our agent:
    # mobile browsers throttle timers when the screen dims.
    client_heartbeat_timeout_s: int = field(
        default_factory=lambda: _int("CLIENT_HEARTBEAT_TIMEOUT_S", 90)
    )
    room_prefix: str = "ni-"


def get_settings() -> Settings:
    return Settings()
