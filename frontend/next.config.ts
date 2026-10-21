import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The production image runs `.next/standalone/server.js` (see Dockerfile);
  // `next dev` ignores this.
  output: "standalone",
};

export default nextConfig;
