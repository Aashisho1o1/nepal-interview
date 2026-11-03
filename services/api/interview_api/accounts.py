"""Creating a student: open sign-up and the seed script share this.

Students can't add their own documents yet, so every new profile starts from the
example applicant's details (marked synthetic) with the student's own name. They
confirm each one before practising, exactly as they would real extracted facts.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from psycopg.types.json import Jsonb

from interview_core.synthetic import SYNTHETIC_FACTS

ENTITLEMENT_DAYS = 30


async def provision_student(
    conn, user_id, name: str, entitlements: dict[str, int], package: str
) -> str:
    """Profile, starting facts and practice time for `user_id`. Safe to re-run: existing
    facts and entitlements are left alone. Returns the profile id."""
    cur = await conn.execute(
        """INSERT INTO student_profiles (user_id, display_name, country_track, is_synthetic)
           VALUES (%s,%s,'uk_pre_cas',true)
           ON CONFLICT (user_id) DO UPDATE SET display_name=EXCLUDED.display_name RETURNING id""",
        (user_id, name),
    )
    sid = (await cur.fetchone())["id"]
    for ref, field, value, label, snippet in SYNTHETIC_FACTS:
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
