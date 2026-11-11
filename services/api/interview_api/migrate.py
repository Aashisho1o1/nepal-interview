"""Apply schema.sql once per deploy, before the new API starts.

    python -m interview_api.migrate

Run it as a release step with a database role that may change tables, set
APPLY_SCHEMA_ON_START=false on the API, and the API itself then needs no such rights.
"""

from __future__ import annotations

import asyncio

from .config import get_settings
from .db import apply_schema, make_pool


async def _main() -> None:
    pool = make_pool(get_settings().database_url, max_size=1)
    await pool.open()
    try:
        await apply_schema(pool, lock_timeout_s=5)
    finally:
        await pool.close()
    print("Schema is up to date.")


if __name__ == "__main__":
    asyncio.run(_main())
