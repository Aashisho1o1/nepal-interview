"""Domain logic shared by the session API: tracks, confirmed facts, funding
arithmetic, the per-session variables sent to the hosted interviewer, and the
scorecard contract with its graders. Nothing here talks to a vendor."""

# Stored on every session so feedback can be read against the prompt that ran.
# Bump when interviewer/officer_miller_prompt.md changes in substance.
POLICY_VERSION = "officer-miller-2026-11-02.2"
RUBRIC_VERSION = "rubric-2026-11-01.1"
SCORECARD_SCHEMA_VERSION = "1.0"
