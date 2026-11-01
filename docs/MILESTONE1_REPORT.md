# Milestone one report

Date: 1 November 2026. Track built: **US F-1, three-minute pressure drill**. Data: synthetic only.

## Upstream inspection

| Repo | Commit | License | Notes |
|---|---|---|---|
| create-simli-app-livekit-agents | `e85f8ea` | MIT | livekit-agents/plugins **1.8.9**, Next 16.4.3. `/api/token` is open to anyone (README says so). Avatar caps 600 s / 300 s idle. Its `ABCRepro` fonts are Simli brand assets and were not copied. Simli plugin returns silently on API errors; the starter detects this via `session.output.audio is None`, and this build reuses that check |
| agent-starter-python | `469650c` | MIT | AGENTS.md: use uv, ruff, simulation scenarios, `lk agent debugger` |
| agent-starter-react | `9e1fc2f` | MIT | Next 15.5.27 and ~50 deps; used as reference only |

Verified against the installed 1.8.9 package: `RoomOptions(participant_identity, close_on_disconnect)`, `user_away_timeout`, `user_turn_limit`, `session.usage` (`session_usage_updated` supersedes `metrics_collected`), `ChatMessage.interrupted` and `metrics`, `AvatarSession.aclose()` removing the avatar participant, `RealtimeModel(max_session_duration=…)`, and token `RoomConfiguration` (agent dispatch metadata, `max_participants`).

## What was implemented

- **Auth and secrets.** Password login with scrypt hashes and server-side sessions in an HttpOnly, SameSite=Lax cookie, plus an Origin check. Provider keys exist only in the API and agent processes. The browser reaches `/api/*` through a Next rewrite; `/internal/*` requires a bearer service token and is never proxied.
- **Token issuance.** Tokens are issued only to authenticated students who have a confirmed snapshot and an available balance. Each is 90 s, scoped to one room and microphone-only, with max 3 participants. The agent is dispatched with the session id; the browser never chooses mode, limits or prompt.
- **Quotas.** The reservation runs under an entitlement row lock. A partial unique index enforces one live session per student. `Idempotency-Key` returns the same session on retries, and starts are rate-limited.
- **Settlement.** Settlement locks the row and is idempotent. Billing is in whole seconds from media-ready, capped at the reservation. Failed startup is a full refund; a session under 60 s with no student speech is refunded. After a fallback, voice seconds bill to the voice bucket and any shortfall is waived.
- **Usage ledger.** Writes are idempotent per `provider_event_id`. Cumulative meters (re-sent every heartbeat) can only increase. Cost comes from a versioned price table; unpriced meters stay `NULL`.
- **Teardown.** One ordered, idempotent teardown with per-step timeouts covers every exit: deadline, hard deadline, student left, End button, `pagehide` beacon, avatar lost, session error, job shutdown, and a session already settled elsewhere. Vendor-side caps back it up: Simli `maxSessionLength`, OpenAI `max_session_duration`, and LiveKit room `empty_timeout`/`departure_timeout`.
- **Reconciler.** Handles startup timeouts (refund), stale heartbeats (charges up to the last heartbeat), room-delete retries, orphan rooms and ungraded sessions.
- **Adapters.**
  - `VoiceEngine`: `OpenAIRealtimeVoice` (default) or `CascadeVoice` (LiveKit Inference STT/LLM/TTS).
  - `AvatarRenderer`: `SimliRenderer` or `PortraitRenderer`.
  - `InterviewPolicy`: `DefaultPolicy`.
  - `Grader`: `RulesGrader` (default, deterministic) or `OpenAIChatGrader`.
  - `MediaControl`: `LiveKitMedia` or `FakeMedia`.
- **Tracks.** US F-1, UK pre-CAS and UKVI are modelled separately. Pre-CAS must not require a CAS. Only US F-1 is enabled; the others are refused with a clear message.
- **Funding.** Decimal arithmetic over confirmed facts:
  - scholarships already deducted are not subtracted twice;
  - joint accounts are counted once;
  - foreign currency is converted only with a confirmed FX fact;
  - sponsor income is reported separately and never subtracted;
  - a fund available after the programme starts is flagged.
- **Policy.** The policy says plainly that the interviewer is fictional and not an officer. Facts are passed as a delimited data block with escaped brackets. Approval predictions, honesty or emotion inferences and invented circumstances are prohibited. Fabrication requests are refused. Figures come only from the backend summary.
- **Interruptions.** `resume_false_interruption=False` stops an interrupted reply from resuming on the avatar. Interrupted interviewer turns are stored with `canceled=true` and shown as interrupted. In avatar mode only the avatar publishes audio, and the browser plays one stream, preferring the avatar's.
- **Scorecard validation.** Strict schema (unknown keys rejected) and enum checks. Each quote must appear verbatim in the cited student turn, with timestamps inside that turn and the session. Document refs must come from the student's own snapshot. Forbidden-claim patterns are rejected. One repair attempt is allowed, then a recoverable failure is shown.
- **UI.** Mobile-first: no horizontal scroll at 390 px; light and dark mode. Every fact is shown with its source snippet. Avatar or voice is a choice, with the data-use note and the provider disclosure. The UI shows connecting, ready, listening, thinking, speaking, interrupted and reconnecting states and a server-time countdown. The fallback notice and avatar-lost recovery offer voice. The scorecard links each finding to its transcript turn.

## Tests actually run

| Command | Result |
|---|---|
| `pytest -q` (Postgres 16 local) | **54 passed** |
| Mutation: drop the one-live-session index | concurrency tests fail as expected |
| Mutation: drop `FOR UPDATE` in settlement | duplicate-settlement test fails as expected |
| `ruff check` / `ruff format` | clean |
| `eslint`, `tsc --noEmit`, `next build` | clean |
| Playwright, 390×844, fake media backend | wrong password rejected → 13 facts confirmed → funding shows USD 28,000 / gap 0 → start → connection fails → session settled `failed`, 0 s charged, redirected to scorecard page; no horizontal overflow |
| Simulated completed session via internal API, rendered scorecard (light and dark) | 4 evidence-linked findings (mismatched loan figure flagged for counsellor review, vague funding answer, very short answer, course strength); canceled turn shown as interrupted |

The pytest cases cover:
- unauthenticated or forged cookie gets no token, and internal endpoints reject a missing or wrong token;
- token claims are decoded and checked;
- no cross-student access (404s; per-student fact refs);
- 20 concurrent starts produce 1 session;
- 10 concurrent starts with the same key return the same session;
- five students starting in parallel do not interfere;
- insufficient balance is refused;
- 12 concurrent finalize/end calls charge once;
- failed startup restores the entitlement while startup provider cost is still recorded;
- no-speech refund;
- fallback billing split;
- the deadline caps the charge;
- the beacon settles and deletes the room;
- kill switch, disabled track and rate limit;
- the reconciler handles a startup timeout, a stale heartbeat, failed then retried room deletion, and an orphan room;
- cumulative usage only increases;
- funding edge cases, prompt injection in fact values, and 11 scorecard rejection cases;
- teardown runs once under 5 concurrent exits and continues after a step errors or times out;
- the turn recorder marks interrupted turns as canceled;
- latency and interruption meters, and the silence policy;
- avatar failure leaves exactly one audio route, checked on a real `AgentSession`.

## Not run, so not claimed

- **No live call.** There were no LiveKit, Simli or OpenAI keys in this environment, so the agent entrypoint has never joined a real room. Lip-sync, avatar audio cancellation on interruption (the framework sends `clear_buffer` to the avatar; not observed), first-word clipping and real teardown against vendors are all unverified.
- **No measured latency, interruption stop time, bandwidth or cost.** `config/prices.json` holds planning figures for LiveKit and Simli, and OpenAI is deliberately unpriced.
- No phones, Safari, Bluetooth or Nepal networks were tested.
- `OpenAIChatGrader` has never been called. `CascadeVoice` model ids come from the LiveKit starter and have not been benchmarked.

## Known gaps

1. **Mid-call avatar loss ends the session** (only used time is charged) and offers a new voice session. It does not switch the live session to voice. Startup fallback does keep the session.
2. The browser does not measure audible latency. Recorded latencies are agent-side state signals.
3. The login rate limiter lives in process memory. There is no password reset or real account creation; auth is meant to be replaced by Supabase or similar.
4. Document upload and extraction are not built. Facts are seeded as "proposed", and the confirm/correct/reject flow is real.
5. There is no counsellor role, consent records, retention jobs, payments or orders (deferred per the handoff).
6. The `no_input` ending cannot tell a broken microphone from silence beyond the browser's device-error message.
7. The rules grader is shallow: number matching, length and keyword checks. Counsellors need to calibrate it before students see it.
8. The policy prompt has not been tested with LiveKit `scenarios.yaml` simulations (AGENTS.md recommends this) because that needs LiveKit Cloud.
9. Transitive dependency licenses have not been audited.

## Next smallest milestone

**Run the live-interview runbook (`docs/RUNBOOK_first_live_interview.md`) on laptop Chrome and one Android phone, and fix only what breaks.** Concretely:

1. Add keys, run scenarios 1–7 five times each, and run `measurement_report.py`.
2. Fill the OpenAI prices and reconcile the ledger against the three vendor dashboards for the same window.
3. Add a `scenarios.yaml` with the scenarios that matter here: no approval prediction, refusing to invent a sponsor, asking for figures when the answer is vague, and the prompt-injection fact.

The deliverable is a one-page table of measured p50/p95 latency, interruption stop time, startup time, failure rate and p90 cost per three-minute drill in USD and NPR. That table, not the planning model, sets the first paid allowance.
