"""Domain logic shared by the session API and the interview agent.

Nothing in this package talks to a network provider. Voice, avatar, grading and
media transport sit behind adapters in their own modules so they can be swapped
and tested without live keys.
"""

POLICY_VERSION = "policy-2026-11-01.1"
RUBRIC_VERSION = "rubric-2026-11-01.1"
SCORECARD_SCHEMA_VERSION = "1.0"
