# Runbook: first live interview and measurement

Goal: prove one reliable interview end to end and record actual latency, interruption,
provider usage and cost. Do this before you set any paid allowance.

## Setup (about 30 minutes)

1. LiveKit Cloud project (URL, key, secret). Simli API key and a **licensed fictional** face id. OpenAI key with realtime access.
2. Fill `.env` (root) and `apps/web/.env.local`. Use a long random `INTERNAL_API_TOKEN`.
3. Start Postgres, seed, then run API, reconciler, agent and web (see README).
4. Fill the OpenAI rows in `config/prices.json` from the current pricing page and record the date. Leave a row `null` rather than guess.

## Script: run each at least 5 times per device

| # | Scenario | What to check |
|---|---|---|
| 1 | Avatar mode, answer every question, let the deadline end it | Face speaks with synced lips; one voice only (no echo/double audio); closing line plays; scorecard appears; `charged_premium_seconds` ≈ 180 |
| 2 | Interrupt the interviewer mid-sentence three times | Old voice **and** mouth stop; they never resume; transcript shows the turn as interrupted |
| 3 | Stay silent | One gentle prompt, then the session ends as `no_input`; refunded if under 60 s |
| 4 | Close the tab mid-session | Session settles as `student_ended`; room disappears in LiveKit dashboard within seconds; Simli dashboard shows the session ended |
| 5 | Kill the agent process mid-session (`Ctrl-C` twice) | Reconciler settles it as `reconciled_stale`, charging only until the last heartbeat; room deleted |
| 6 | Set `SIMLI_FACE_ID` to an invalid id | Session continues in voice with the fallback notice; avatar seconds = 0; voice seconds bill to the voice bucket |
| 7 | Double-click Start / open two tabs | Exactly one session; second tab is told a session is already live |
| 8 | Voice mode | Portrait only; lower data |
| 9 | Android Chrome, iOS Safari, laptop Chrome, Bluetooth earphones, speakerphone | Mic permission flow, echo, autoplay, background tab |
| 10 | Throttled network (Chrome devtools "Fast 3G") and a real Nepal connection if possible | Reconnecting state, startup time, video quality |

## Record

```bash
DATABASE_URL=... uv run python scripts/measurement_report.py --since 2026-11-01 --fx 160
```

Also capture, per run: device, browser, network, region of LiveKit project, repo commit,
and anything that looked wrong (lip-sync drift, clipped first words, double audio).
Compare usage with the LiveKit, Simli and OpenAI dashboards for the same window; a
mismatch means a meter is missing or wrong.

## Pass bar for "one reliable interview"

All of scenarios 1–7 pass on at least laptop Chrome and one phone, no session leaves a
room or vendor session open past the teardown grace, and every scorecard quote is
something the student actually said.
