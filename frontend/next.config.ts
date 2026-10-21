import { withSentryConfig } from "@sentry/nextjs/config";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The production image runs `.next/standalone/server.js` (see Dockerfile);
  // `next dev` ignores this.
  output: "standalone",
};

// Sentry itself is set up in instrumentation.ts and instrumentation-client.ts
// (see config/sentry.ts). The build makes no calls to Sentry: no source map
// upload, no release creation, no build telemetry.
export default withSentryConfig(nextConfig, {
  sourcemaps: { disable: true },
  release: { create: false, finalize: false },
  telemetry: false,
  silent: true,
});
