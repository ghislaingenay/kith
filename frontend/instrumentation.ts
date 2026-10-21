// Runs once when the Next.js server starts (Next's `instrumentation`
// convention); see config/sentry.ts. Proxy runs on Node.js in Next 16, so no
// edge runtime needs Sentry.
import * as Sentry from "@sentry/nextjs";

import { sentryOptions } from "@/config/sentry";

export function register(): void {
  const options = sentryOptions();
  if (process.env.NEXT_RUNTIME !== "nodejs" || !options) {
    return;
  }
  Sentry.init({
    ...options,
    includeLocalVariables: false,
    // Incoming request bodies are never read, so none can reach an event.
    integrations: [Sentry.httpIntegration({ maxRequestBodySize: "none" })],
  });
}

// Reports errors thrown in Server Components, Route Handlers and Proxy; a
// no-op while Sentry is off.
export const onRequestError = Sentry.captureRequestError;
