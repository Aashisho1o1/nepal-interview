// Railway project for the interview app: Postgres plus three services from this repo,
// all in Singapore. Apply with the Railway CLI (see .railway/README.md); Railway does
// not read this file on deploy. Secret values are never written here: they live in the
// project's shared variables (Project Settings > Shared Variables) and are referenced.
//
//   web     Next.js, the only public service. Proxies /api/* to `api` over the
//           private network, so the login cookie is first-party.
//   api     FastAPI session API. No public domain: reachable only from `web`.
//   worker  The reconciler loop: ends abandoned sessions, refunds, stops vendors.

import { defineRailway, github, group, postgres, project, service } from "railway/iac";

const REPO = "Aashisho1o1/nepal-interview";
const BRANCH = "main";
const REGION = "asia-southeast1-eqsg3a"; // Singapore, closest to students in Nepal
const API_PORT = "8000";

// Rebuild the Python services only when Python code or its config changes.
const PYTHON_PATHS = [
  "/asgi.py",
  "/pyproject.toml",
  "/uv.lock",
  "/config/**",
  "/packages/**",
  "/services/**",
];

export default defineRailway((ctx) => {
  const db = postgres("postgres", { region: REGION });

  // Server-side settings shared by the API and the worker. Everything sent to the
  // browser comes from the API's responses, never from these values directly.
  const server = {
    DATABASE_URL: db.env.DATABASE_URL,
    PYTHONPATH: "packages/core:services/api",
    COOKIE_SECURE: "true",
    GRADER: "rules",
    VIDEO_TIER_ENABLED: "true",
    VOICE_TIER_ENABLED: "true",
    ELEVENLABS_ALLOW_PUBLIC_AGENT: "false",
    // Shared variables, set once in the dashboard. A missing one turns that tier off.
    ELEVENLABS_AGENT_ID: ctx.shared.ELEVENLABS_AGENT_ID,
    ELEVENLABS_BRANCH_ID: ctx.shared.ELEVENLABS_BRANCH_ID,
    ELEVENLABS_API_KEY: ctx.shared.ELEVENLABS_API_KEY,
    LIVEAVATAR_EMBED_URL: ctx.shared.LIVEAVATAR_EMBED_URL,
    // Side-by-side video cards (docs/PROVIDERS.md). Missing = that card isn't offered.
    ELEVENLABS_VIDEO_AGENT_ID: ctx.shared.ELEVENLABS_VIDEO_AGENT_ID,
    LIVEAVATAR_API_KEY: ctx.shared.LIVEAVATAR_API_KEY,
    LIVEAVATAR_AVATAR_ID: ctx.shared.LIVEAVATAR_AVATAR_ID,
    LIVEAVATAR_ELEVENLABS_SECRET_ID: ctx.shared.LIVEAVATAR_ELEVENLABS_SECRET_ID,
    KEYFRAME_API_KEY: ctx.shared.KEYFRAME_API_KEY,
    KEYFRAME_PERSONA: ctx.shared.KEYFRAME_PERSONA,
    // Comma-separated provider ids to offer. Unset = every configured one.
    ENABLED_PROVIDERS: ctx.shared.ENABLED_PROVIDERS,
    // Founders' sign-in emails, comma-separated: they can open /team. Missing = nobody.
    TEAM_EMAILS: ctx.shared.TEAM_EMAILS,
  };

  const api = service("api", {
    source: github(REPO, { branch: BRANCH }),
    build: { builder: "RAILPACK", watchPatterns: PYTHON_PATHS },
    // IPv4: health checks and the private network of environments created after
    // 2025-10-16 use it. ("::" would be IPv6 only, because asyncio disables dual stack.)
    start: `uvicorn asgi:app --host 0.0.0.0 --port ${API_PORT}`,
    healthcheck: "/healthz",
    replicas: { [REGION]: 1 },
    env: {
      ...server,
      PORT: API_PORT,
      // No ALLOWED_ORIGINS needed: the API accepts requests whose Origin matches the
      // address the visitor opened, which the website's proxy reports.
    },
  });

  const worker = service("worker", {
    source: github(REPO, { branch: BRANCH }),
    build: { builder: "RAILPACK", watchPatterns: PYTHON_PATHS },
    start: "python -m interview_api.reconcile --loop",
    deploy: { restartPolicyType: "ALWAYS" },
    replicas: { [REGION]: 1 },
    env: server,
  });

  const web = service("web", {
    source: github(REPO, { branch: BRANCH, rootDirectory: "/apps/web" }),
    build: { builder: "RAILPACK", watchPatterns: ["/apps/web/**"] },
    healthcheck: "/",
    replicas: { [REGION]: 1 },
    env: {
      // Read when the site is built: Next.js bakes its /api proxy target in.
      SESSION_API_ORIGIN: `http://api.railway.internal:${API_PORT}`,
      EMBED_ORIGINS: "https://embed.liveavatar.com",
    },
  });

  return project("nepal-interview", {
    resources: [...group("Backend", [db, api, worker]), web],
  });
});
