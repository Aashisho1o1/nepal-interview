"""Shared fixtures: a hermetic app per test (fresh schema, vendor env from constants,
never from the developer's environment), signed-in students, and the helpers every
session test needs."""

from __future__ import annotations

import os
import uuid

import httpx
import psycopg
import pytest

from interview_api.app import create_app
from interview_api.config import Settings
from interview_api.db import make_pool
from interview_api.seed import seed

TEST_DSN = os.getenv("TEST_DATABASE_URL", "postgresql://postgres@/ni_test?host=/var/tmp&port=5433")
ORIGIN = "http://test"

# The two providers students get, configured as a deployment would (minus real keys).
EMBED = (
    "https://embed.liveavatar.com/v1/f7caa47d-4036-4c85-9aad-f9e238025ad2?orientation=horizontal"
)
AGENT = "agent_test123"
HERO_ENV = {
    "LIVEAVATAR_EMBED_URL": EMBED,
    "ELEVENLABS_AGENT_ID": AGENT,
    "ELEVENLABS_ALLOW_PUBLIC_AGENT": "true",
}
VIDEO = "liveavatar_embed"
VOICE = "elevenlabs_voice"
TRACK = "uk_pre_cas"
FORMAT = "interview_5m"
VIDEO_SECONDS = VOICE_SECONDS = 300  # one five-minute format for both tiers


def settings(**kw) -> Settings:
    base = dict(
        database_url=TEST_DSN,
        cookie_secure=False,
        allowed_origins=(ORIGIN,),
        max_starts_per_10min=50,
    )
    base.update(kw)
    return Settings(**base)


def reset_db() -> None:
    with psycopg.connect(TEST_DSN, autocommit=True) as c:
        c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")


class Env:
    def __init__(self, app, pool, s):
        self.app, self.pool, self.s = app, pool, s

    @property
    def registry(self):
        return self.app.state.providers

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url=ORIGIN, headers={"origin": ORIGIN}
        )

    async def sql(self, q: str, params=()):
        async with self.pool.connection() as conn:
            cur = await conn.execute(q, params)
            try:
                return await cur.fetchall()
            except psycopg.ProgrammingError:
                return None


@pytest.fixture
async def make_env():
    created = []

    async def _make(*, provider_env: dict | None = None, provider_http=None, **kw) -> Env:
        reset_db()
        s = settings(**kw)
        pool = make_pool(TEST_DSN, max_size=30)
        app = create_app(
            s,
            pool=pool,
            provider_env=HERO_ENV if provider_env is None else provider_env,
            provider_http=provider_http,
        )
        cm = app.router.lifespan_context(app)
        await cm.__aenter__()
        created.append((cm, pool))
        return Env(app, pool, s)

    yield _make
    for cm, pool in created:
        await cm.__aexit__(None, None, None)
        await pool.close()


async def login_student(
    env: Env, email: str, name: str, password: str = "pw-for-tests-123", entitlements=None
) -> httpx.AsyncClient:
    await seed(env.pool, password, email=email, name=name, entitlements=entitlements)
    c = env.client()
    r = await c.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return c


async def confirm_all_and_snapshot(c: httpx.AsyncClient) -> dict:
    facts = (await c.get("/api/profile/facts")).json()
    for f in facts:
        r = await c.patch(f"/api/profile/facts/{f['ref']}", json={"status": "confirmed"})
        assert r.status_code == 200
    r = await c.post("/api/profile/snapshot")
    assert r.status_code == 200
    return r.json()


async def ready_student(env: Env, email="a@synthetic.test", name="Student A", **kw):
    c = await login_student(env, email, name, **kw)
    await confirm_all_and_snapshot(c)
    return c


def key() -> dict:
    return {"idempotency-key": uuid.uuid4().hex}


def body(provider_id: str = VIDEO, track: str = TRACK, format_id: str = FORMAT) -> dict:
    return {"track": track, "format_id": format_id, "provider_id": provider_id}


async def start(c, provider_id: str = VIDEO, headers=None, **kw):
    return await c.post("/api/sessions", json=body(provider_id, **kw), headers=headers or key())


async def media_ready(c, sid: str, payload: dict | None = None) -> dict:
    """What the browser reports once the vendor stream is up: starts the clock."""
    r = await c.post(
        f"/api/sessions/{sid}/client-events", json={"kind": "media_ready", "payload": payload or {}}
    )
    assert r.status_code == 200, r.text
    return r.json()


async def age_session(env: Env, sid, ready_ago_s: int, heartbeat_ago_s: int | None = None):
    """Simulate elapsed time by moving server timestamps into the past."""
    await env.sql(
        """UPDATE interview_sessions SET status='active',
             media_ready_at = now() - make_interval(secs => %s),
             practice_ends_at = now() - make_interval(secs => %s) + make_interval(secs => practice_seconds),
             last_heartbeat_at = now() - make_interval(secs => %s)
           WHERE id=%s""",
        (ready_ago_s, ready_ago_s, heartbeat_ago_s if heartbeat_ago_s is not None else 0, sid),
    )


async def balance(c, bucket="premium_seconds"):
    return (await c.get("/api/me")).json()["balances"][bucket]
