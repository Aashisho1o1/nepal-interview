import { defineConfig } from "@playwright/test";

// Browser smoke test: starts the API and the built website (run `npm run build` first;
// its /api proxy targets http://localhost:8000 by default), then drives the site in
// Chromium. Locally, create the database once: createdb -h /var/tmp -p 5433 -U postgres ni_e2e The API gets a voice agent id but no vendor keys,
// so the voice card is offered and nothing ever calls a vendor.
export default defineConfig({
  testDir: "e2e",
  forbidOnly: !!process.env.CI,
  use: { baseURL: "http://localhost:3001" },
  webServer: [
    {
      command: "uv run uvicorn asgi:app --port 8000",
      cwd: "../..",
      url: "http://localhost:8000/healthz",
      env: {
        DATABASE_URL: process.env.E2E_DATABASE_URL ?? "postgresql://postgres@/ni_e2e?host=/var/tmp&port=5433",
        APPLY_SCHEMA_ON_START: "true",
        COOKIE_SECURE: "false",
        ALLOWED_ORIGINS: "http://localhost:3001",
        ELEVENLABS_ALLOW_PUBLIC_AGENT: "true",
        ELEVENLABS_AGENT_ID: "e2e-agent",
      },
    },
    {
      command: "npx next start -p 3001",
      url: "http://localhost:3001",
    },
  ],
});
