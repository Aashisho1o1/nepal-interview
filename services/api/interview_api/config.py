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
    allowed_origins: tuple[str, ...] = field(
        default_factory=lambda: (
            tuple(
                o.strip()
                for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
                if o.strip()
            )
            + _vercel_origins()
        )
    )
    cookie_secure: bool = field(default_factory=lambda: _bool("COOKIE_SECURE", True))
    login_ttl_hours: int = field(default_factory=lambda: _int("LOGIN_TTL_HOURS", 12))
    # Startup budget before the student clock starts (vendor connect + first tap).
    startup_budget_avatar_s: int = field(
        default_factory=lambda: _int("STARTUP_BUDGET_AVATAR_S", 45)
    )
    startup_budget_voice_s: int = field(default_factory=lambda: _int("STARTUP_BUDGET_VOICE_S", 25))
    closing_grace_s: int = field(default_factory=lambda: _int("CLOSING_GRACE_S", 15))
    teardown_grace_s: int = field(default_factory=lambda: _int("TEARDOWN_GRACE_S", 30))
    max_starts_per_10min: int = field(default_factory=lambda: _int("MAX_STARTS_PER_10MIN", 6))
    # Refund rule: a session with no student speech that ends within this window.
    no_input_refund_s: int = field(default_factory=lambda: _int("NO_INPUT_REFUND_S", 60))
    signup_enabled: bool = field(default_factory=lambda: _bool("SIGNUP_ENABLED", True))
    # Free plan (see plans.py): voice sessions every day, and one video session on each
    # of an account's first N days. 0 turns either off.
    free_voice_sessions_per_day: int = field(
        default_factory=lambda: _int("FREE_VOICE_SESSIONS_PER_DAY", 1)
    )
    free_video_days: int = field(default_factory=lambda: _int("FREE_VIDEO_DAYS", 3))
    # Kill switches, one per tier.
    video_tier_enabled: bool = field(default_factory=lambda: _bool("VIDEO_TIER_ENABLED", True))
    voice_tier_enabled: bool = field(default_factory=lambda: _bool("VOICE_TIER_ENABLED", True))
    grader: str = field(default_factory=lambda: os.getenv("GRADER", "rules"))
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    grader_model: str = field(default_factory=lambda: os.getenv("GRADER_MODEL", ""))
    price_table_path: str | None = field(default_factory=lambda: os.getenv("PRICE_TABLE_PATH"))
    providers_file: str | None = field(default_factory=lambda: os.getenv("PROVIDERS_FILE"))
    # Vercel Cron sends "Authorization: Bearer <CRON_SECRET>" to the reconcile route.
    # Unset means the route refuses every call.
    cron_secret: str = field(default_factory=lambda: os.getenv("CRON_SECRET", ""))
    # Browser heartbeats get generous slack: mobile browsers throttle timers when the
    # screen dims.
    client_heartbeat_timeout_s: int = field(
        default_factory=lambda: _int("CLIENT_HEARTBEAT_TIMEOUT_S", 90)
    )


def _vercel_origins() -> tuple[str, ...]:
    """This deployment's own addresses on Vercel (system variables, set by the
    platform). Trusting them lets preview and production URLs pass the origin check
    without listing each one in ALLOWED_ORIGINS. Custom domains still go there."""
    hosts = (
        os.getenv(k, "").strip()
        for k in ("VERCEL_URL", "VERCEL_BRANCH_URL", "VERCEL_PROJECT_PRODUCTION_URL")
    )
    return tuple(f"https://{h}" for h in hosts if h)


def get_settings() -> Settings:
    return Settings()
