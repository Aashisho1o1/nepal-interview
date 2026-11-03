# Nepal interview practice

Students from Nepal practise the **UK university pre-CAS credibility interview** with a
fictional AI interviewer, by **voice** or **video**, and get feedback built on their own
words and their confirmed documents. Practice only: not a government or university
service, and nothing here predicts a CAS or visa decision.

**Status:** early build for testing with 5–10 students. Voice runs on an ElevenLabs
agent; video on a HeyGen LiveAvatar embed. The phase plan is
`docs/ELEVENLABS_LIVEAVATAR_FOCUS.md`; how interviewers plug in is `docs/PROVIDERS.md`.

```
apps/web/                        Next.js 16 student UI: home, confirm facts, interview, feedback
services/api/interview_api/      FastAPI: auth, facts, credits, sessions, providers, feedback, reconciler
packages/core/interview_core/    domain: the track, facts, funding maths, agent variables, scorecard + graders
interviewer/                     the interviewer prompt (pasted into the ElevenLabs agent)
config/providers.json            interviewers offered to students   config/prices.json  vendor meters
scripts/provider_comparison.py   side-by-side results per interviewer from real sessions
tests/                           pytest, Postgres-backed
```

## How a session works

1. The student signs in (HttpOnly cookie) and confirms each proposed fact against its
   source. Only confirmed facts enter a versioned snapshot; funding is computed from it
   with `Decimal`, never by the interviewer.
2. `POST /api/sessions` with an `Idempotency-Key` reserves the full session length from
   the tier's credit bucket (one live session per student, enforced by the database) and
   asks the chosen provider for a launch: a per-session ElevenLabs token plus dynamic
   variables built from the confirmed facts, or the LiveAvatar embed URL.
3. The browser runs the call and reports the lifecycle: `media_ready` starts the
   server-owned clock, heartbeats keep the session live, and the End button, the
   deadline tick or the page-exit beacon end it.
4. Settlement runs once: whole seconds from media-ready, capped at the reservation.
   A session that never connected, or a short one with no student speech, is refunded.
5. The reconciler (`python -m interview_api.reconcile --loop`) settles sessions whose
   browser went quiet, asks vendors to stop, and grades transcripts that arrived late.
6. Feedback: transcript → rules grader → strict validation (verbatim quotes, snapshot-only
   references, no approval predictions, no honesty or emotion claims) → scorecard. Voice
   transcripts will arrive through the ElevenLabs post-call webhook (not wired yet); the
   static video embed sends none, so those sessions get a rating form only.

## Run locally

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), Node 20.9+, Postgres 14+.

```bash
uv sync
cp .env.example .env            # ELEVENLABS_AGENT_ID (+ API key), LIVEAVATAR_EMBED_URL
export PYTHONPATH=packages/core:services/api
SEED_PASSWORD='choose-one' uv run --env-file .env python -m interview_api.seed
uv run --env-file .env uvicorn interview_api.app:create_app --factory --port 8000
uv run --env-file .env python -m interview_api.reconcile --loop
cd apps/web && cp .env.example .env.local && npm ci && npm run dev
```

Open http://localhost:3000 and sign in as `student@synthetic.test`. The seeded student
is synthetic (Example University, GBP figures); confirm the facts, then practise.

Paste `interviewer/officer_miller_prompt.md` into the ElevenLabs agent; the app sends
the `{{variables}}` it references on every session.

## Tests

```bash
TEST_DATABASE_URL=postgresql://localhost/ni_test uv run pytest -q
cd apps/web && npx eslint && npx tsc --noEmit && npm run build
```

## Deploy on Railway (current)

`.railway/railway.ts` declares Postgres and three services in Singapore: `web` (the
only public one), a private `api` that `web` proxies `/api/*` to, and a `worker` running
the reconciler loop. Steps: `.railway/README.md`.

## Deploy on Vercel (alternative)


`vercel.json` deploys one project with two services on one domain: `web` (Next.js,
`apps/web`) for every page, and `api` (FastAPI, entry `asgi.py`) for `/api/*`. Neither
calls the other server-side; the browser calls `/api` on the same domain, so the login
cookie stays first-party. A cron job calls `/api/internal/reconcile` every minute in
place of the `--loop` process (Pro plan; it needs `CRON_SECRET`). The API is public at
`/api/*` for testing only; see `AGENTS.md` for making it private before real students.

1. Create Postgres (for example Neon from the Vercel Marketplace, Singapore region) and
   set the project's Function Region to match. The pooled connection string is fine.
2. Set the API variables from `.env.example` in the project, plus `CRON_SECRET`.
   `COOKIE_SECURE=true`, `ELEVENLABS_ALLOW_PUBLIC_AGENT=false`. Add a custom domain to
   `ALLOWED_ORIGINS`; the project's own `*.vercel.app` addresses are trusted
   automatically.
3. Deploy. The schema is applied on first start. Seed testers with
   `SEED_PASSWORD=... DATABASE_URL=... python -m interview_api.seed`.

## Before any paid use

Turn on authentication for the ElevenLabs agent and set `ELEVENLABS_API_KEY`; restrict
the LiveAvatar embed to your domain and cap its session length in the HeyGen dashboard.
Fill `config/prices.json` from invoices, then run `scripts/provider_comparison.py` on
real sessions before setting package sizes.
