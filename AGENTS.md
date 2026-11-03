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
