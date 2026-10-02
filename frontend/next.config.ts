import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Do not advertise the framework and its version in an `X-Powered-By` response header.
  poweredByHeader: false,
};

export default nextConfig;
