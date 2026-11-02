from __future__ import annotations

import os

import httpx
import psycopg
import pytest

from interview_api.app import create_app
from interview_api.config import Settings
from interview_api.db import make_pool
from interview_api.media import FakeMedia
from interview_api.seed import seed

TEST_DSN = os.getenv("TEST_DATABASE_URL", "postgresql://postgres@/ni_test?host=/var/tmp&port=5433")
ORIGIN = "http://test"
ITOK = "internal-test-token"


def settings(**kw) -> Settings:
    base = dict(
        database_url=TEST_DSN,
        cookie_secure=False,
        internal_api_token=ITOK,
        allowed_origins=(ORIGIN,),
        max_starts_per_10min=50,
    )
    base.update(kw)
    return Settings(**base)


def reset_db() -> None:
    with psycopg.connect(TEST_DSN, autocommit=True) as c:
        c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")


class Env:
    def __init__(self, app, pool, media, s):
        self.app, self.pool, self.media, self.s = app, pool, media, s

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url=ORIGIN, headers={"origin": ORIGIN}
        )

    def internal(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url=ORIGIN,
            headers={"authorization": f"Bearer {ITOK}"},
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
        media = FakeMedia()
        pool = make_pool(TEST_DSN, max_size=30)
        # Hermetic: never read provider URLs/keys from the developer's environment.
        app = create_app(
            s,
            media=media,
            pool=pool,
            provider_env=provider_env or {},
            provider_http=provider_http,
        )
        cm = app.router.lifespan_context(app)
        await cm.__aenter__()
        created.append((cm, pool))
        return Env(app, pool, media, s)

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
