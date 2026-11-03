# Notes for coding agents

## Hosting

The app is launched on Railway (`.railway/railway.ts`, steps in `.railway/README.md`).
There the API is already private: only the website is public, and it proxies `/api/*`
to the API over Railway's private network. Never give the `api` or `worker` service a
public domain.

## Open TODO if Vercel is used again: make the API private (owner decision, 2026-11-02)

The `api` service in `vercel.json` is public at `/api/*` on purpose, for quick testing.
Before real students use a Vercel deployment, make it internal:

- Remove the `/api/(.*)` rewrite to `api` from `vercel.json`, so the service gets no
  public traffic.
- Give the `web` service a binding to `api`
  (`{ "type": "service", "service": "api", "format": "url", "env": "API_URL" }`) and
  forward `/api/*` through a Next.js route handler that calls `process.env.API_URL`.
  Bindings resolve at runtime in functions only, not in `next.config.ts` rewrites or
  middleware.
- The cron job then needs its own way in: point it at a website route that forwards to
  the API with `CRON_SECRET`, or move the reconciler to a Vercel Daemon.
- Keep the login cookie first-party and the origin check (`ALLOWED_ORIGINS`) working.

Ask the owner before doing this; it is not yet scheduled.

## Future work (owner decision, 2026-11-02)

- **Email verification before the free plan.** Sign-up is open with no email check, so
  one person can make several accounts and use each one's free daily voice session and
  first-three-days video sessions. Before promoting the site publicly, verify the email
  (a one-time link) before granting free time. Grants live in
  `services/api/interview_api/plans.py`; the per-network sign-up limit in `app.py`
  only slows this down.
- **Payments.** The free plan and shared promo codes (`plans.py`) are the only ways to
  get practice time; paid packages are not built.
- **Rate limits are per process.** Sign-up and wrong-code limits live in memory; with
  more than one API instance they need a shared store.
