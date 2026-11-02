# Nepal interview practice — milestone one

An authenticated, time-limited mock US F-1 interview with a live avatar (Simli on
LiveKit), confirmed synthetic student facts, deterministic funding arithmetic,
interruption handling, voice fallback, atomic quotas and an evidence-linked scorecard.

**Status:** Everything except a live provider call has been built and tested (see
`docs/MILESTONE1_REPORT.md`). No live interview has been run yet, so latency and cost
are unmeasured. This is not production-ready.

```
apps/web/                    Next.js 16 student UI (login, confirm facts, interview, scorecard)
services/api/interview_api/  FastAPI session API: auth, quotas, tokens, settlement, grading, reconciler
services/agent/interview_agent/  LiveKit Agents worker: voice + avatar adapters, watchdog, teardown
packages/core/interview_core/    tracks, facts, funding maths, interview policy, scorecard, graders
config/prices.json           versioned price table (planning snapshot; OpenAI deliberately unpriced)
scripts/measurement_report.py    latency / interruption / reliability / cost from recorded sessions
scripts/provider_comparison.py   side-by-side provider results (LiveAvatar embed, Tavus, own pipeline)
config/providers.json        interview providers offered to students (see docs/PROVIDERS.md)
tests/                       pytest (Postgres-backed API tests, agent runtime, domain)
```

## How a session works

1. The student signs in (HttpOnly cookie) and confirms each proposed fact against its source. Only confirmed facts go into a versioned snapshot, and funding is computed from it with `Decimal`.
2. `POST /api/sessions` with an `Idempotency-Key`: locks the entitlement row, refuses a second live session (partial unique index), reserves the full drill length, creates the session with a hard deadline, then mints a 90-second, room-scoped, microphone-only LiveKit token that dispatches the agent with the session id.
3. The agent fetches its config from `/internal/...` (bearer service token), waits for the student, starts Simli (falling back to voice on any failure *before* the voice session starts, so only one audio stream exists), then reports `media_ready`. The student-facing clock starts there; startup is never charged.
4. A watchdog speaks the closing line at the server-set `practice_ends_at`; an independent guard fires at the hard deadline. Silence gets one gentle prompt, then ends as `no_input`. Over-long answers trigger a "please answer directly" prompt.
5. Every exit path (deadline, student left, End button, `pagehide` beacon, avatar lost, provider error, job shutdown) runs a single idempotent teardown: flush turns → settle → close avatar → close voice → delete room → usage → grade.
6. Settlement charges whole seconds from media-ready, capped at the reservation, once. Failed startup and short no-speech sessions are refunded; post-fallback seconds bill to the voice bucket.
7. The reconciler (`python -m interview_api.reconcile --loop`) settles sessions whose agent died, retries room deletion, deletes orphan rooms and grades anything left ungraded.
8. Feedback is generated from the transcript and passes strict validation (verbatim quotes, valid turn/timestamps, snapshot-only document refs, no approval/honesty/emotion claims) before it is shown. One repair attempt is allowed; otherwise it shows a recoverable failure.

## Run locally

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), Node 20.9+, Postgres 16.

```bash
uv sync                                   # pinned Python deps
cp .env.example .env                      # fill in keys (server-side only)
export PYTHONPATH=packages/core:services/api:services/agent
SEED_PASSWORD='choose-one' uv run python -m interview_api.seed
uv run uvicorn interview_api.app:create_app --factory --port 8000
uv run python -m interview_api.reconcile --loop
uv run python -m interview_agent.agent dev           # or: lk agent dev
cd apps/web && cp .env.example .env.local && npm ci && npm run dev
```

Open http://localhost:3000, sign in as `student@synthetic.test`, confirm the facts, start.
For UI work without LiveKit set `MEDIA_BACKEND=fake` (connection then fails and the
session is refunded, which also exercises the failure path).

## Tests

```bash
# Postgres reachable at TEST_DATABASE_URL (default: socket /var/tmp, port 5433, db ni_test)
uv run pytest -q
cd apps/web && npx eslint && npx tsc --noEmit && npm run build
```

## Before any paid use

Run `docs/RUNBOOK_first_live_interview.md`, then `scripts/measurement_report.py`. Fill
OpenAI prices from the current pricing page or an invoice. Set package allowances only
from measured p90 cost per session.
