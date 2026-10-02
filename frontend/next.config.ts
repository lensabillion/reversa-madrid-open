import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${process.env.INFLUENCE_API_URL ?? "http://127.0.0.1:8000"}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
