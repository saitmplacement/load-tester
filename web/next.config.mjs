/** @type {import('next').NextConfig} */
const API_BASE = process.env.API_BASE || "http://localhost:8000";

const nextConfig = {
  reactStrictMode: true,
  // Proxy API calls to the FastAPI backend so the browser talks same-origin
  // (no CORS) in both dev and production.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${API_BASE}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
