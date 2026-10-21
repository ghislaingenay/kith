/**
 * Error and trace reporting to Sentry, shared by the browser
 * (`instrumentation-client.ts`) and the Node server (`instrumentation.ts`).
 * Mirrors the backend's `core/observability/config.py`.
 *
 * An empty DSN, or the default `local` environment, leaves Sentry off, so
 * development and the smoke test need no account. No Tenant data leaves: no
 * default PII, no request bodies, and `scrubEvent` and `scrubSpan` strip
 * cookies, auth headers, IP addresses and email addresses from whatever is
 * left.
 */
import type { Breadcrumb, BrowserOptions, Event } from "@sentry/nextjs";

import { env } from "@/config/env";

const LOCAL_ENVIRONMENT = "local";
const UNSAMPLED_PATHS = new Set(["/health"]);
const AUTH_HEADERS = new Set([
  "authorization",
  "proxy-authorization",
  "cookie",
  "set-cookie",
]);
// Also matches `%40`, the `@` of an email in a URL's query string.
const EMAIL_PATTERN = /[\w.+-]+(?:@|%40)[\w-]+(?:\.[\w-]+)+/gi;
const EMAIL_REPLACEMENT = "[email]";
// A span as `beforeSendSpan` receives it; @sentry/nextjs doesn't export the type.
export type StreamedSpanJSON = Parameters<
  NonNullable<BrowserOptions["beforeSendSpan"]>
>[0];
// Span attributes carry each header as `http.request.header.<name>` (or
// `http.response.header.<name>`).
const HEADER_ATTRIBUTE = /^http\.(?:request|response)\.header\.(.+)$/;

export type SentrySettings = Readonly<{
  dsn: string;
  environment: string;
  // The image's commit SHA, baked in by frontend/Dockerfile's `GIT_SHA`.
  release?: string;
  tracesSampleRate: number;
}>;

// The parts of Sentry's sampling context the sampler reads. Server spans
// carry the path in `normalizedRequest` or `url.path`; the name is the
// fallback ("GET /health").
type SamplingContext = Readonly<{
  name: string;
  attributes?: Record<string, unknown>;
  normalizedRequest?: { url?: string };
}>;

function requestPath(context: SamplingContext): string | undefined {
  const urlPath = context.attributes?.["url.path"];
  if (typeof urlPath === "string") return urlPath;
  if (context.normalizedRequest?.url) {
    return new URL(context.normalizedRequest.url, "http://localhost").pathname;
  }
  return context.name.split(" ").at(-1);
}

/** Sample every transaction at `rate`, except health checks, which the
 * container's health check hits often enough to drown out real traffic. */
export function tracesSampler(rate: number) {
  return (context: SamplingContext): number => {
    const path = requestPath(context);
    return path !== undefined && UNSAMPLED_PATHS.has(path) ? 0 : rate;
  };
}

const isAuthHeader = (name: string): boolean =>
  AUTH_HEADERS.has(name.toLowerCase());

function scrubEmails<T>(value: T): T {
  if (typeof value === "string") {
    return value.replace(EMAIL_PATTERN, EMAIL_REPLACEMENT) as T;
  }
  if (Array.isArray(value)) {
    return value.map(scrubEmails) as T;
  }
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, scrubEmails(item)]),
    ) as T;
  }
  return value;
}

/** `beforeSend`: drop request bodies, cookies, auth headers and the user's
 * IP address, and mask every email address left anywhere in the event. */
export function scrubEvent<T extends Event>(event: T): T {
  if (event.request) {
    delete event.request.data;
    delete event.request.cookies;
    if (event.request.headers) {
      event.request.headers = Object.fromEntries(
        Object.entries(event.request.headers).filter(
          ([name]) => !isAuthHeader(name),
        ),
      );
    }
  }
  if (event.user) {
    delete event.user.email;
    // The Node SDK sets it from the request even with `sendDefaultPii` off.
    delete event.user.ip_address;
  }
  // The SDK's own objects, possibly cyclic, which it strips before sending.
  const { sdkProcessingMetadata, ...sent } = event;
  return { ...scrubEmails(sent), sdkProcessingMetadata } as T;
}

/** `beforeBreadcrumb`: logs stay local, so console output is never attached. */
export function dropConsoleBreadcrumb(breadcrumb: Breadcrumb): Breadcrumb | null {
  return breadcrumb.category === "console" ? null : breadcrumb;
}

/** `beforeSendSpan`: traces are streamed as spans, which skip `beforeSend`.
 * Drop auth and cookie headers, and mask every email address (URLs and
 * error messages carry them). */
export function scrubSpan(span: StreamedSpanJSON): StreamedSpanJSON {
  const attributes = Object.fromEntries(
    Object.entries(span.attributes).filter(([key]) => {
      const header = HEADER_ATTRIBUTE.exec(key)?.[1];
      return header === undefined || !isAuthHeader(header);
    }),
  );
  return scrubEmails({ ...span, attributes });
}

const settingsFromEnv = (): SentrySettings => ({
  dsn: env.NEXT_PUBLIC_SENTRY_DSN,
  environment: env.NEXT_PUBLIC_SENTRY_ENVIRONMENT,
  release: env.NEXT_PUBLIC_SENTRY_RELEASE,
  tracesSampleRate: env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE,
});

/** `Sentry.init` options shared by the browser and the server, or
 * `undefined` to leave Sentry off (no DSN, or the local environment, so a
 * DSN copied into a dev `.env` stays silent). */
export function sentryOptions(settings: SentrySettings = settingsFromEnv()) {
  if (!settings.dsn || settings.environment === LOCAL_ENVIRONMENT) {
    return undefined;
  }
  return {
    dsn: settings.dsn,
    environment: settings.environment,
    release: settings.release,
    tracesSampler: tracesSampler(settings.tracesSampleRate),
    beforeSend: scrubEvent,
    beforeSendSpan: scrubSpan,
    beforeBreadcrumb: dropConsoleBreadcrumb,
    sendDefaultPii: false,
    enableLogs: false,
  };
}
