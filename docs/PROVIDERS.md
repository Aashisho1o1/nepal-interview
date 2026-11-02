# Interview providers: plug in, switch, compare

Every way of delivering a mock interview is a **provider**. Students see neutral labels
("Video interviewer A/B/C", "Voice only") so they rate the experience, not the brand.
Quotas, the practice clock, ending sessions, ratings and the scorecard are shared; only
the provider differs.

```
config/providers.json        which providers exist, labels, order, iframe permissions
services/api/.../providers.py one class per integration type (LiveKit agent, iframe embed, Tavus)
apps/web/components/stages/   one component per launch kind ("livekit", "iframe")
scripts/provider_comparison.py side-by-side results from real sessions + ratings
```

## Add your LiveAvatar embed (5 minutes)

1. Put the URL from your embed code in the API environment (server side, never in the web app):
   ```
   LIVEAVATAR_EMBED_URL=https://embed.liveavatar.com/v1/<your-embed-id>?orientation=horizontal
   ```
2. Restart the API. "Video interviewer A" now appears on the interview page. Students
   sign in, pick it, and the embed opens inside our page.
3. In the LiveAvatar dashboard, before sharing with students:
   - **Paste the interviewer instructions** into the embed's persona/context. Use
     `STABLE_POLICY` from `packages/core/interview_core/policy.py` plus a UK pre-CAS
     scenario. The embed can't see each student's confirmed facts, so it can only run a
     generic interview.
   - **Restrict allowed domains** to your site if the dashboard offers it. The embed ID
     is visible in the page, and anyone with it can spend your credits.
   - **Set the session length cap** to about 5 minutes. Our page removes the iframe at
     the deadline, but only the vendor's cap can stop a student who tampers with the page.
4. On phones, also try `orientation=vertical` in the URL to see whether it fits better.

## What each integration type gives you

| | Static embed (LiveAvatar) | Tavus conversation | Own pipeline (LiveKit + Simli/voice) |
|---|---|---|---|
| Setup | Paste URL | API key + face ID (+ optional PAL ID) | LiveKit, OpenAI, Simli keys + agent worker |
| Knows this student's facts | No (dashboard persona only) | Yes (sent per session) | Yes |
| Transcript → scorecard | No (rating only) | Yes (webhook) | Yes |
| Server can stop it | No (browser removes the iframe; vendor cap is the backstop) | Yes | Yes |
| Practice clock starts | First click into the interviewer window (or 20 s after load) | Same | When our agent reports media ready |
| Turn latency measured | No; students rate "reply speed" | No; rating | Yes, by our agent |

The Tavus adapter follows Tavus's current API (`face_id`/`pal_id`, checked 2 Nov 2026)
but has only run against a mock. Enable it with `TAVUS_API_KEY`, `TAVUS_FACE_ID`,
optional `TAVUS_PAL_ID`, and for transcripts `PUBLIC_BASE_URL` + `TAVUS_WEBHOOK_SECRET`.

## Switch or add a provider

- **Turn providers on/off or reorder:** edit `config/providers.json` (`enabled`, order),
  or set `ENABLED_PROVIDERS=liveavatar_embed,livekit_voice` for a quick test.
- **Another vendor with an embed or room URL** (D-ID, Anam share link, a second LiveAvatar
  persona): copy the `liveavatar_embed` entry with a new `id`, `url_env` and
  `allowed_hosts`. No code changes. Add its origin to `EMBED_ORIGINS` for the web app,
  otherwise the browser blocks its microphone.
- **A vendor that needs per-session API calls:** copy `TavusConversationProvider` (about
  60 lines). Mark it `stateful = True` and the API guarantees one vendor conversation per
  session, even if a student double-clicks.
- **A LiveKit avatar plugin** (HeyGen LiveAvatar via LiveKit, Anam, bitHuman, Tavus via
  LiveKit): add a small renderer to `AVATAR_RENDERERS` in
  `services/agent/interview_agent/adapters.py` and a providers.json entry with
  `"integration": "livekit_agent", "avatar": "<name>"`.
- **A vendor with its own JS SDK** (e.g. ElevenLabs Agents): one new stage component and
  one new launch `kind`. This is the only case that touches the web app.

## Compare them

```
DATABASE_URL=... python scripts/provider_comparison.py --since 2026-11-03
```

For each provider it shows: start success, failed starts, drops, time until the student
can talk, our measured reply latency (own pipeline only), average realism rating,
"reply speed felt OK", audio/video OK, "would use again", billed minutes, our cost, end
reasons, vendor events seen, and student comments. Vendors that bill you directly must
be reconciled from their dashboards.

## Things that will bite if forgotten

- `EMBED_ORIGINS` (web) must include every iframe vendor's origin. Missing it means the
  embed loads but cannot hear the student.
- Students must allow the microphone for the vendor's iframe. The browser asks
  separately for the embedded site.
- A static embed only knows what its dashboard persona knows. For document-grounded
  interviews, use a per-session API (Tavus, or LiveAvatar's API in "Full" mode) or our
  own pipeline.
