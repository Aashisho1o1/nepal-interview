"""Seed one synthetic student. Facts start as 'proposed' so the confirmation flow is real.

SEED_PASSWORD=... python -m interview_api.seed
"""

from __future__ import annotations

import asyncio
import os
import secrets

from interview_core.synthetic import (
    SYNTHETIC_ENTITLEMENTS,
    SYNTHETIC_STUDENT_EMAIL,
    SYNTHETIC_STUDENT_NAME,
)

from .accounts import provision_student
from .auth import hash_password
from .config import get_settings
from .db import apply_schema, make_pool


async def seed(
    pool,
    password: str,
    email: str = SYNTHETIC_STUDENT_EMAIL,
    name: str = SYNTHETIC_STUDENT_NAME,
    entitlements: dict | None = None,
) -> str:
    async with pool.connection() as conn, conn.transaction():
        cur = await conn.execute(
            """INSERT INTO users (email, password_hash) VALUES (%s,%s)
               ON CONFLICT (email) DO UPDATE SET password_hash=EXCLUDED.password_hash RETURNING id""",
            (email, hash_password(password)),
        )
        uid = (await cur.fetchone())["id"]
        return await provision_student(
            conn, uid, name, entitlements or SYNTHETIC_ENTITLEMENTS, "synthetic-test-v1"
        )


async def _main() -> None:
    s = get_settings()
    pw = os.getenv("SEED_PASSWORD") or secrets.token_urlsafe(12)
    pool = make_pool(s.database_url, max_size=2)
    await pool.open()
    await apply_schema(pool)
    sid = await seed(pool, pw)
    await pool.close()
    print(f"Seeded synthetic student {SYNTHETIC_STUDENT_EMAIL} (profile {sid}).")
    if not os.getenv("SEED_PASSWORD"):
        print(f"Generated password: {pw}")


if __name__ == "__main__":
    asyncio.run(_main())
