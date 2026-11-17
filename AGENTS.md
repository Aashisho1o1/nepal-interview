# Notes for coding agents

## Hosting

The app is launched on Railway (`.railway/railway.ts`, steps in `.railway/README.md`).
There the API is already private: only the website is public, and it proxies `/api/*`
to the API over Railway's private network. Never give the `api` or `worker` service a
public domain. Never run `railway config apply` until a plan shows 0 to destroy: as of
2026-11-06 it would delete the production database (`.railway/README.md`).

## Future work (owner decision, 2026-11-02)

- **Email verification before the free plan.** Sign-up is open with no email check, so
  one person can make several accounts and use each one's free daily sessions. Before promoting the site publicly, verify the email
  (a one-time link) before granting free time. Grants live in
  `services/api/interview_api/plans.py`; the per-network sign-up limit in `app.py`
  only slows this down.
- **Payments.** The free plan and shared promo codes (`plans.py`) are the only ways to
  get practice time; paid packages are not built.
- **Rate limits are per process.** Sign-up, login, wrong-code and details-save limits
  live in memory; with more than one API instance they need a shared store.
