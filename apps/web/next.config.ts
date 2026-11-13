import type { NextConfig } from "next";

// The browser only ever talks to this origin, so the HttpOnly session cookie is
// first-party. On Vercel, the project's routing sends /api/* to the API service before
// a request reaches Next.js (see vercel.json). Locally, `next dev` proxies it here.
const API_ORIGIN = process.env.SESSION_API_ORIGIN || "http://localhost:8000";
const ON_VERCEL = Boolean(process.env.VERCEL);

// Vendor iframes that may use the microphone (and camera, for vendors whose rooms ask
// for it). Without listing them here, Permissions-Policy blocks the mic inside the
// iframe even when the iframe has allow="microphone": the embed would load but never
// hear the student. Keep in sync with allowed_hosts in config/providers.json.
// Empty by default, because this header goes to every visitor and would name the vendor.
// Set it only when an iframe interviewer is offered.
const EMBED_ORIGINS = (process.env.IFRAME_ORIGINS || "")
  .split(/[\s,]+/)
  .filter((o) => /^https?:\/\/[a-z0-9.-]+(:\d+)?$/i.test(o));
const quoted = EMBED_ORIGINS.map((o) => `"${o}"`).join(" ");
const allowed = ["self", ...EMBED_ORIGINS.map((o) => `"${o}"`)].join(" ");

const permissionsPolicy = [
  `microphone=(${allowed})`,
  `autoplay=(${allowed})`,
  `fullscreen=(${allowed})`,
  `camera=(${quoted})`, // our own pages never use the camera
  "geolocation=()",
].join(", ");

// Enforced: nothing may frame the site (clickjacking), and forms and <base> stay here.
const csp = "frame-ancestors 'none'; base-uri 'self'; form-action 'self'";
// Report-only until real calls confirm the vendor hosts: violations show in the browser
// console and block nothing. Tighten it, then move it into `csp`.
const cspReportOnly = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "media-src 'self' blob:",
  "connect-src 'self' https: wss:",
  `frame-src ${EMBED_ORIGINS.join(" ") || "'none'"}`,
].join("; ");

const nextConfig: NextConfig = {
  devIndicators: { position: "bottom-right" },
  async rewrites() {
    return ON_VERCEL ? [] : [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
  async headers() {
    return [
      // Demo files are versioned by name (-v1, -v2), so browsers can keep them.
      { source: "/demo/:file", headers: [{ key: "Cache-Control", value: "public, max-age=31536000, immutable" }] },
      {
        source: "/:path*",
        headers: [
          { key: "Permissions-Policy", value: permissionsPolicy },
          { key: "Referrer-Policy", value: "same-origin" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          // Ignored by browsers over plain http, so local development is unaffected.
          { key: "Strict-Transport-Security", value: "max-age=63072000" },
          { key: "Content-Security-Policy", value: csp },
          { key: "Content-Security-Policy-Report-Only", value: cspReportOnly },
        ],
      },
    ];
  },
};

export default nextConfig;
