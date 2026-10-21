// Runs in the browser before the app hydrates (Next's
// `instrumentation-client` convention); see config/sentry.ts.
import * as Sentry from "@sentry/nextjs";

import { sentryOptions } from "@/config/sentry";

const options = sentryOptions();
if (options) {
  Sentry.init(options);
}

// Names a trace after the page navigated to; a no-op while Sentry is off.
export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
