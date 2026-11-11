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
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

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


# Checked when no account matches, so a sign-in takes the same time either way.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


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


class RateLimiter:
    """Per-process sliding-window counter (failed logins, sign-ups). A shared store is
    needed with more than one API process."""

    MAX_KEYS = 50_000

    def __init__(self, max_hits: int, window_s: int):
        self.max, self.window = max_hits, window_s
        self.hits: dict[str, list[float]] = {}

    def blocked(self, key: str) -> bool:
        # Reading never stores a key, and keys with no recent hits are dropped, so
        # callers cannot grow the table by probing with made-up keys.
        now = time.monotonic()
        live = [t for t in self.hits.get(key, ()) if now - t < self.window]
        if live:
            self.hits[key] = live
        else:
            self.hits.pop(key, None)
        return len(live) >= self.max

    def hit(self, key: str) -> None:
        if len(self.hits) >= self.MAX_KEYS:  # bounded memory; fails open
            self.hits.clear()
        self.hits.setdefault(key, []).append(time.monotonic())


def client_ip(request: Request) -> str:
    """The host platform's edge (Railway, Vercel) sets X-Real-IP; the website's proxy
    passes it through. Locally there is none."""
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "")


def check_origin(request: Request, allowed: tuple[str, ...]) -> None:
    """Reject state-changing browser requests from other sites (CSRF defence in depth
    alongside SameSite=Lax).

    Same-origin requests pass without configuration: the browser's Origin must name the
    host the browser actually requested. The website's proxy (and Vercel's edge) put that
    host in X-Forwarded-Host, overwriting anything a client sent. ALLOWED_ORIGINS adds
    extra origins on top."""
    origin = request.headers.get("origin")
    if origin is None or origin in allowed:
        return
    requested = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    requested = requested.split(",")[0].strip().lower()
    if requested and urlsplit(origin).netloc.lower() == requested:
        return
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
