from __future__ import annotations

from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

SCHEMA = (Path(__file__).parent / "schema.sql").read_text()

# Advisory-lock keys. Transaction-scoped locks only: they also work behind a
# transaction-mode connection pooler (for example Neon's pooled endpoint).
SCHEMA_LOCK = 7_301_001
RECONCILE_LOCK = 7_301_002


def make_pool(dsn: str, max_size: int = 20) -> AsyncConnectionPool:
    return AsyncConnectionPool(
        dsn,
        min_size=1,
        max_size=max_size,
        open=False,
        # No server-side prepared statements, so a transaction-mode pooler is safe.
        kwargs={"row_factory": dict_row, "autocommit": True, "prepare_threshold": None},
    )


async def apply_schema(pool: AsyncConnectionPool, *, lock_timeout_s: int = 0) -> None:
    """Idempotent. Serverless hosts start several instances at once; the lock makes
    them apply the schema one after another instead of racing on the DDL.

    The ALTER statements need an exclusive table lock. With `lock_timeout_s` set, a
    migration that cannot get it gives up (and can be re-run) instead of queueing and
    blocking every request behind it."""
    async with pool.connection() as conn, conn.transaction():
        if lock_timeout_s:  # set first, so waiting for the advisory lock times out too
            await conn.execute(f"SET LOCAL lock_timeout = '{int(lock_timeout_s)}s'")
        await conn.execute("SELECT pg_advisory_xact_lock(%s)", (SCHEMA_LOCK,))
        await conn.execute(SCHEMA)


async def audit(conn, actor: str, action: str, rtype: str, rid: str, detail: dict | None = None):
    from psycopg.types.json import Jsonb

    await conn.execute(
        "INSERT INTO audit_events (actor_id, action, resource_type, resource_id, detail) "
        "VALUES (%s,%s,%s,%s,%s)",
        (actor, action, rtype, rid, Jsonb(detail or {})),
    )
