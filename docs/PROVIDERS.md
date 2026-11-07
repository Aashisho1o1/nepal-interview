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

## Side-by-side video cards

**Video A** is HeyGen LiveAvatar in LITE mode (1 credit a minute). **Video B** is Keyframe.
Both are only the face: the voice and the logic come from one ElevenLabs agent. A card
stays hidden, for everyone, until all its settings exist, so add vendor keys whenever you
buy the plan.

| | Video A (HeyGen LITE) | Video B (Keyframe) |
|---|---|---|
| Student details | Not sent: its token request goes through HeyGen, so the agent asks instead | Browser sends them to ElevenLabs only |
| Student's voice | Reaches HeyGen, which runs the bridge to ElevenLabs | Reaches ElevenLabs only |
| Agent's voice | Reaches HeyGen | Reaches Keyframe |
| Server can stop a call | Yes, with a hard time limit | No; the agent's max duration is the backstop |

Anything said aloud reaches the avatar vendor with that audio, so an agent that speaks a
student's name or figures sends them too.

Setup, once:

1. **ElevenLabs:** duplicate the interviewer agent, so voice calls aren't touched. On the
   copy set audio **output and input to PCM 24000 Hz** and max conversation duration to
   **180 s**. Its id is `ELEVENLABS_VIDEO_AGENT_ID`. A paid plan is required.
2. **HeyGen:** at app.liveavatar.com get an API key (`LIVEAVATAR_API_KEY`) and an avatar id
   (`LIVEAVATAR_AVATAR_ID`). Make a new ElevenLabs key just for HeyGen, with an expiry and
   only `convai_read`, `user_read`, `voices_read`. Register it, in your own terminal:
   ```
   curl -X POST https://api.liveavatar.com/v1/secrets -H "X-API-KEY: $LIVEAVATAR_API_KEY" \
     -H "Content-Type: application/json" -d '{"secret_type": "ELEVENLABS_API_KEY",
     "secret_value": "<that key>", "secret_name": "interviewer"}'
   ```
   `data.id` in the reply is `LIVEAVATAR_ELEVENLABS_SECRET_ID`.
3. **Keyframe:** at platform.keyframelabs.com get an API key (`KEYFRAME_API_KEY`) and pick a
   stock avatar for `KEYFRAME_PERSONA` (for example `public:cosmo_persona-1.5-live`).
   Video B also uses the existing `ELEVENLABS_API_KEY`.
4. **Railway, in the dashboard:** add those under Project Settings > Shared Variables, share
   each with both `api` and `worker`, then deploy the staged changes. The worker needs them
   too, or it can't stop abandoned calls. **Do not run `railway config apply`** (see
   `.railway/README.md`).

Things to check in the first real calls, which no automated test can: closing the tab
mid-call (does Keyframe stop using minutes?), a phone on mobile data, iPhone sound (tap the
video if it's silent), and an agent hang-up (the browser console shows the stop event).

**Choosing:** in `config/providers.json` set `"enabled": false` on the losers, and set the
winner's `"label"` to `"Video interviewer"`. `scripts/provider_comparison.py` shows results
by card. The current embed is listed at 2 credits a minute, so turn it off first if credits
run short.

## Switch or add a provider

- **Turn providers on/off or reorder:** edit `config/providers.json` (`enabled`, order),
  or set `ENABLED_PROVIDERS=voice` for a quick test. `VIDEO_TIER_ENABLED` and
  `VOICE_TIER_ENABLED` pause a whole tier without a config change.
- **Another vendor with an embed URL:** copy the `liveavatar_embed` entry with a new
  `id`, `url_env` and `allowed_hosts`. No code changes. Add its origin to `IFRAME_ORIGINS`
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

- `IFRAME_ORIGINS` (web) must include every iframe vendor's origin.
- Students must allow the microphone for the vendor's iframe; the browser asks
  separately for the embedded site.
- The ElevenLabs prompt only uses a dynamic variable if it references `{{that_variable}}`.
  `tests/test_core_domain.py` checks the prompt file against the variables we send.
