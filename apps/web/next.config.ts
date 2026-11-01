import type { NextConfig } from "next";

// The browser only ever talks to this origin. /api/* is proxied to the session API so
// the HttpOnly session cookie is first-party. /internal/* is never proxied.
const API_ORIGIN = process.env.SESSION_API_ORIGIN || "http://localhost:8000";

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
          { key: "Permissions-Policy", value: "camera=(), microphone=(self), geolocation=()" },
          { key: "Referrer-Policy", value: "same-origin" },
          { key: "X-Content-Type-Options", value: "nosniff" },
        ],
      },
    ];
  },
};

export default nextConfig;
