# Interview providers: plug in, switch, compare

Every way of delivering a mock interview is a **provider**. Students see neutral labels
("Video interviewer", "Voice only") so they rate the experience, not the brand. Credits,
the practice clock, ending sessions, ratings and the scorecard are shared; only the
provider differs.

```
config/providers.json          which providers exist, labels, order, iframe permissions
services/api/.../providers.py  one class per integration type (iframe embed, ElevenLabs agent)
apps/web/components/stages/    one component per launch kind ("iframe", "elevenlabs")
scripts/provider_comparison.py side-by-side results from real sessions + ratings
```

## The two providers in use

| | Voice: ElevenLabs agent | Video: LiveAvatar static embed |
|---|---|---|
| Setup | `ELEVENLABS_AGENT_ID`; `ELEVENLABS_API_KEY` for a private agent (per-session tokens) | `LIVEAVATAR_EMBED_URL` from the embed code |
| Knows this student's facts | Yes: dynamic variables from confirmed facts, prompt in `interviewer/officer_miller_prompt.md` | No: only the dashboard persona |
| Transcript → scorecard | Via the post-call webhook (not wired yet) | No (rating only) |
| Server can stop it | No: ends when the browser disconnects; agent max duration is the backstop | No: the browser removes the iframe; set the vendor's session cap |
| Practice clock starts | When the SDK connects | First click into the embed (or 20 s after load) |

A public ElevenLabs agent (no API key) is allowed only with
`ELEVENLABS_ALLOW_PUBLIC_AGENT=true`, for local testing: anyone with the agent id can
spend your minutes. Likewise anyone holding the embed URL can spend LiveAvatar credits,
so restrict the embed to your domain in the HeyGen dashboard.

The target for the video tier is LiveAvatar's session-token flow driven by the same
ElevenLabs agent (facts and transcripts included); see
`docs/ELEVENLABS_LIVEAVATAR_FOCUS.md` §6.

## Switch or add a provider

- **Turn providers on/off or reorder:** edit `config/providers.json` (`enabled`, order),
  or set `ENABLED_PROVIDERS=elevenlabs_voice` for a quick test. `VIDEO_TIER_ENABLED` and
  `VOICE_TIER_ENABLED` pause a whole tier without a config change.
- **Another vendor with an embed URL:** copy the `liveavatar_embed` entry with a new
  `id`, `url_env` and `allowed_hosts`. No code changes. Add its origin to `EMBED_ORIGINS`
  in the web app, otherwise the browser blocks its microphone.
- **A vendor that needs per-session API calls:** add a class in `providers.py` with
  `launch()` and `close()`; mark it `stateful = True` and the API guarantees one vendor
  conversation per session, even if a student double-clicks.
- **A vendor with its own JS SDK:** one new stage component and one new launch `kind`.
  This is the only case that touches the web app.

## Compare them

```
DATABASE_URL=... python scripts/provider_comparison.py --since 2026-11-03
```

Per provider: start success, failed starts, drops, time until the student can talk,
average realism rating, "reply speed felt OK", audio/video OK, "would use again", billed
minutes, our cost, end reasons and student comments. Vendors that bill you directly must
be reconciled from their dashboards.

## Things that bite if forgotten

- `EMBED_ORIGINS` (web) must include every iframe vendor's origin.
- Students must allow the microphone for the vendor's iframe; the browser asks
  separately for the embedded site.
- The ElevenLabs prompt only uses a dynamic variable if it references `{{that_variable}}`.
  `tests/test_core_domain.py` checks the prompt file against the variables we send.
