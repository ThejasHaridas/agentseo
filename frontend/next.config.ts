import type { NextConfig } from "next";

const API = process.env.AGENTRANK_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  devIndicators: false,
  // The dashboard talks to the FastAPI backend through same-origin paths, so no CORS setup is needed.
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API}/:path*` },
      { source: "/storage/:path*", destination: `${API}/storage/:path*` },
    ];
  },
};

export default nextConfig;
