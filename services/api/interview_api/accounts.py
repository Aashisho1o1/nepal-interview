"""Creating a student: open sign-up and the seed script share this.

A new account starts with only its name. Students add the rest on the "About you"
page, or practise without it. The demo account (seed script) also gets the example
applicant's facts, so its form starts filled in.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from psycopg.types.json import Jsonb

from interview_core.synthetic import SYNTHETIC_FACTS

ENTITLEMENT_DAYS = 30


async def provision_student(
    conn,
    user_id,
    name: str,
    entitlements: dict[str, int],
    package: str,
    *,
    example_facts: bool = False,
) -> str:
    """Profile, starting facts and practice time for `user_id`. Safe to re-run: existing
    facts and entitlements are left alone. Returns the profile id."""
    cur = await conn.execute(
        """INSERT INTO student_profiles (user_id, display_name, country_track, is_synthetic)
           VALUES (%s,%s,'uk_pre_cas',%s)
           ON CONFLICT (user_id) DO UPDATE SET display_name=EXCLUDED.display_name RETURNING id""",
        (user_id, name, example_facts),
    )
    sid = (await cur.fetchone())["id"]
    for ref, field, value, label, snippet in SYNTHETIC_FACTS if example_facts else ():
        if field == "student.full_name":
            value, label, snippet = name, "Your account", f"Name: {name}"
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
        expires = datetime.now(UTC) + timedelta(days=ENTITLEMENT_DAYS)
        for bucket, secs in entitlements.items():
            if secs > 0:
                await conn.execute(
                    """INSERT INTO entitlements (student_id, bucket, package_version,
                         granted_seconds, expires_at) VALUES (%s,%s,%s,%s,%s)""",
                    (sid, bucket, package, secs, expires),
                )
    return str(sid)


# ---------------------------------------------------------------- admin command


async def set_role(conn, email: str, role: str) -> bool:
    """Returns False when no account has that email."""
    cur = await conn.execute(
        "UPDATE users SET role=%s WHERE email=%s RETURNING id", (role, email.strip().lower())
    )
    return await cur.fetchone() is not None


async def _cli(email: str, role: str) -> None:
    from .config import get_settings
    from .db import make_pool

    pool = make_pool(get_settings().database_url, max_size=1)
    await pool.open()
    try:
        async with pool.connection() as conn:
            found = await set_role(conn, email, role)
    finally:
        await pool.close()
    print(f"{email} is now {role}." if found else "No account with that email. Sign up first.")


if __name__ == "__main__":
    import argparse
    import asyncio

    ap = argparse.ArgumentParser(
        prog="python -m interview_api.accounts",
        description="Give or remove team access (/team: every session and transcript).",
    )
    ap.add_argument("action", choices=["grant-team", "revoke-team"])
    ap.add_argument("email", help="the account's sign-in email")
    a = ap.parse_args()
    asyncio.run(_cli(a.email, "admin" if a.action == "grant-team" else "student"))
