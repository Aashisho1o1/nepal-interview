"""Seed one synthetic student. Facts start as 'proposed' so the confirmation flow is real.

SEED_PASSWORD=... python -m interview_api.seed
"""

from __future__ import annotations

import asyncio
import os
import secrets
from datetime import UTC, datetime, timedelta

from psycopg.types.json import Jsonb

from interview_core.synthetic import (
    SYNTHETIC_ENTITLEMENTS,
    SYNTHETIC_FACTS,
    SYNTHETIC_STUDENT_EMAIL,
    SYNTHETIC_STUDENT_NAME,
)

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
    ents = entitlements or SYNTHETIC_ENTITLEMENTS
    async with pool.connection() as conn, conn.transaction():
        cur = await conn.execute(
            """INSERT INTO users (email, password_hash) VALUES (%s,%s)
               ON CONFLICT (email) DO UPDATE SET password_hash=EXCLUDED.password_hash RETURNING id""",
            (email, hash_password(password)),
        )
        uid = (await cur.fetchone())["id"]
        cur = await conn.execute(
            """INSERT INTO student_profiles (user_id, display_name, country_track, is_synthetic)
               VALUES (%s,%s,'us_f1',true)
               ON CONFLICT (user_id) DO UPDATE SET display_name=EXCLUDED.display_name RETURNING id""",
            (uid, name),
        )
        sid = (await cur.fetchone())["id"]
        for ref, field, value, label, snippet in SYNTHETIC_FACTS:
            await conn.execute(
                """INSERT INTO extracted_facts (student_id, ref, field_name, value_json,
                     source_label, source_snippet) VALUES (%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (student_id, ref) DO NOTHING""",
                (sid, ref, field, Jsonb(value), label, snippet),
            )
        cur = await conn.execute(
            "SELECT count(*)::int AS n FROM entitlements WHERE student_id=%s", (sid,)
        )
        if (await cur.fetchone())["n"] == 0:
            for bucket, secs in ents.items():
                await conn.execute(
                    """INSERT INTO entitlements (student_id, bucket, package_version,
                         granted_seconds, expires_at) VALUES (%s,%s,'synthetic-test-v1',%s,%s)""",
                    (sid, bucket, secs, datetime.now(UTC) + timedelta(days=30)),
                )
    return str(sid)


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
