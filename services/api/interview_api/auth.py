"""Password login with server-side sessions in an HttpOnly cookie.

Milestone one keeps auth self-contained so it can be tested end to end. The
`current_student` dependency is the seam where Supabase Auth (or another provider)
plugs in later: it only needs to resolve a request to a user id.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request

COOKIE = "ni_session"
_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
    except ValueError:
        return False
    dk = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), **_SCRYPT)
    return hmac.compare_digest(dk.hex(), digest)


def token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def create_login(conn, user_id, ttl_hours: int) -> tuple[str, datetime]:
    raw = secrets.token_urlsafe(32)
    exp = datetime.now(UTC) + timedelta(hours=ttl_hours)
    await conn.execute(
        "INSERT INTO auth_sessions (token_hash, user_id, expires_at) VALUES (%s,%s,%s)",
        (token_hash(raw), user_id, exp),
    )
    return raw, exp


class LoginLimiter:
    """Per-process failed-login limiter. A shared store is needed with >1 API process."""

    def __init__(self, max_failures: int = 8, window_s: int = 600):
        self.max, self.window = max_failures, window_s
        self.failures: dict[str, list[float]] = defaultdict(list)

    def blocked(self, key: str) -> bool:
        now = time.monotonic()
        self.failures[key] = [t for t in self.failures[key] if now - t < self.window]
        return len(self.failures[key]) >= self.max

    def fail(self, key: str) -> None:
        self.failures[key].append(time.monotonic())


def check_origin(request: Request, allowed: tuple[str, ...]) -> None:
    """Reject state-changing browser requests from other origins (CSRF defence in depth
    alongside SameSite=Lax)."""
    origin = request.headers.get("origin")
    if origin is not None and origin not in allowed:
        raise HTTPException(403, "origin not allowed")


async def current_student(request: Request) -> dict:
    raw = request.cookies.get(COOKIE)
    if not raw:
        raise HTTPException(401, "not signed in")
    pool = request.app.state.pool
    async with pool.connection() as conn:
        cur = await conn.execute(
            """SELECT u.id AS user_id, u.email, u.role, p.id AS student_id, p.display_name,
                      p.is_synthetic
               FROM auth_sessions s JOIN users u ON u.id = s.user_id
               LEFT JOIN student_profiles p ON p.user_id = u.id
               WHERE s.token_hash = %s AND s.revoked_at IS NULL AND s.expires_at > now()""",
            (token_hash(raw),),
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(401, "session expired")
    if row["student_id"] is None:
        raise HTTPException(403, "no student profile")
    return row


def require_internal(request: Request) -> None:
    expected = request.app.state.settings.internal_api_token
    got = request.headers.get("authorization", "")
    if not expected or not hmac.compare_digest(got, f"Bearer {expected}"):
        raise HTTPException(401, "internal token required")
