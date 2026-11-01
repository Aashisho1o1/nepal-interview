from __future__ import annotations

from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

SCHEMA = (Path(__file__).parent / "schema.sql").read_text()


def make_pool(dsn: str, max_size: int = 20) -> AsyncConnectionPool:
    return AsyncConnectionPool(
        dsn,
        min_size=1,
        max_size=max_size,
        open=False,
        kwargs={"row_factory": dict_row, "autocommit": True},
    )


async def apply_schema(pool: AsyncConnectionPool) -> None:
    async with pool.connection() as conn:
        await conn.execute(SCHEMA)


async def audit(conn, actor: str, action: str, rtype: str, rid: str, detail: dict | None = None):
    from psycopg.types.json import Jsonb

    await conn.execute(
        "INSERT INTO audit_events (actor_id, action, resource_type, resource_id, detail) "
        "VALUES (%s,%s,%s,%s,%s)",
        (actor, action, rtype, rid, Jsonb(detail or {})),
    )
