import type { NextConfig } from "next";

// The browser only ever talks to this origin. /api/* is proxied to the session API so
// the HttpOnly session cookie is first-party. /internal/* is never proxied.
const API_ORIGIN = process.env.SESSION_API_ORIGIN || "http://localhost:8000";

// Vendor iframes that may use the microphone (and camera, for vendors whose rooms ask
// for it). Without listing them here, Permissions-Policy blocks the mic inside the
// iframe even when the iframe has allow="microphone": the embed would load but never
// hear the student. Keep in sync with allowed_hosts in config/providers.json.
const EMBED_ORIGINS = (process.env.EMBED_ORIGINS || "https://embed.liveavatar.com https://tavus.daily.co")
  .split(/[\s,]+/)
  .filter((o) => /^https?:\/\/[a-z0-9.-]+(:\d+)?$/i.test(o));
const quoted = EMBED_ORIGINS.map((o) => `"${o}"`).join(" ");

const permissionsPolicy = [
  `microphone=(self ${quoted})`,
  `autoplay=(self ${quoted})`,
  `fullscreen=(self ${quoted})`,
  `camera=(${quoted})`, // our own pages never use the camera
  "geolocation=()",
].join(", ");

const nextConfig: NextConfig = {
  devIndicators: { position: "bottom-right" },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Permissions-Policy", value: permissionsPolicy },
          { key: "Referrer-Policy", value: "same-origin" },
          { key: "X-Content-Type-Options", value: "nosniff" },
        ],
      },
    ];
  },
};

export default nextConfig;
