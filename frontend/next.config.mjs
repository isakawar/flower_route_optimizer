/** @type {import('next').NextConfig} */
const nextConfig = {
  // Produces a minimal self-contained build used by the Docker runner stage
  output: "standalone",

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
