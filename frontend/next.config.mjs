/** @type {import('next').NextConfig} */
const nextConfig = {
  // Produces a minimal self-contained build used by the Docker runner stage
  output: "standalone",

  // Optimization can take 30-90 s (geocoding + OSRM + OR-Tools).
  // Default rewrite proxy timeout is 30 s — raise it to 2 minutes.
  experimental: {
    proxyTimeout: 120_000,
  },

  async rewrites() {
    // In Docker the backend is reached via the compose service name.
    // Locally it stays on localhost:8000.
    const backendUrl =
      process.env.BACKEND_URL ?? "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
