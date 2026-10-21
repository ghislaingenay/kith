import type { ErrorEvent } from "@sentry/nextjs";
import { describe, expect, it } from "vitest";

import {
  scrubEvent,
  scrubSpan,
  sentryOptions,
  type StreamedSpanJSON,
  tracesSampler,
} from "./sentry";

const settings = {
  dsn: "https://key@o1.ingest.sentry.io/1",
  environment: "production",
  release: "abc123",
  tracesSampleRate: 0.1,
};

describe("sentryOptions", () => {
  it("is off without a DSN", () => {
    expect(sentryOptions({ ...settings, dsn: "" })).toBeUndefined();
  });

  it("is off in the local environment, even with a DSN", () => {
    expect(sentryOptions({ ...settings, environment: "local" })).toBeUndefined();
  });

  it("tags events with the release and environment, and sends no PII", () => {
    expect(sentryOptions(settings)).toMatchObject({
      dsn: settings.dsn,
      environment: "production",
      release: "abc123",
      sendDefaultPii: false,
    });
  });

  // Logs stay local, as in the backend.
  it("drops console breadcrumbs, keeping the rest", () => {
    const { beforeBreadcrumb } = sentryOptions(settings)!;
    expect(beforeBreadcrumb({ category: "console", message: "hi" })).toBeNull();
    expect(beforeBreadcrumb({ category: "navigation" })).toEqual({
      category: "navigation",
    });
  });
});

describe("tracesSampler", () => {
  const sample = tracesSampler(0.25);

  it("never samples a health check", () => {
    expect(sample({ name: "GET /health", attributes: {} })).toBe(0);
    expect(
      sample({ name: "GET", attributes: { "url.path": "/health" } }),
    ).toBe(0);
    expect(
      sample({
        name: "GET",
        attributes: {},
        normalizedRequest: { url: "http://localhost:3000/health" },
      }),
    ).toBe(0);
  });

  it("samples everything else at the configured rate", () => {
    expect(sample({ name: "GET /sign-in", attributes: {} })).toBe(0.25);
    expect(sample({ name: "/w/[slug]", attributes: {} })).toBe(0.25);
    expect(sample({ name: "GET /healthy", attributes: {} })).toBe(0.25);
  });
});

describe("scrubEvent", () => {
  function sampleEvent(): ErrorEvent {
    return {
      type: undefined,
      message: "Sign-in failed for ada@example.com",
      user: { id: "u1", email: "ada@example.com", ip_address: "203.0.113.7" },
      request: {
        url: "https://app.example.com/sign-in?email=ada%40example.com&next=ada@example.com",
        data: '{"email":"ada@example.com"}',
        cookies: { kith_session: "secret" },
        headers: {
          Authorization: "Bearer secret",
          Cookie: "kith_session=secret",
          "Set-Cookie": "kith_session=secret",
          "User-Agent": "Firefox",
        },
      },
      breadcrumbs: [{ message: "console: ada@example.com signed in" }],
    };
  }

  it("removes the request body and cookies", () => {
    const event = scrubEvent(sampleEvent());
    expect(event.request).not.toHaveProperty("data");
    expect(event.request).not.toHaveProperty("cookies");
  });

  it("removes auth and cookie headers, keeping the rest", () => {
    const event = scrubEvent(sampleEvent());
    expect(event.request?.headers).toEqual({ "User-Agent": "Firefox" });
  });

  it("removes the user's IP address", () => {
    const event = scrubEvent(sampleEvent());
    expect(event.user).not.toHaveProperty("ip_address");
  });

  // The SDK's own objects, possibly cyclic, which it strips before sending.
  it("leaves the SDK's processing metadata alone", () => {
    const metadata: Record<string, unknown> = { note: "ada@example.com" };
    metadata.self = metadata;
    const event = scrubEvent({ ...sampleEvent(), sdkProcessingMetadata: metadata });
    expect(event.sdkProcessingMetadata).toBe(metadata);
  });

  it("masks every email address left in the event", () => {
    const event = scrubEvent(sampleEvent());
    expect(JSON.stringify(event)).not.toMatch(/ada(@|%40)example\.com/);
    expect(event.user).toEqual({ id: "u1" });
    expect(event.message).toBe("Sign-in failed for [email]");
  });
});

describe("scrubSpan", () => {
  // Shaped like a span the Node server streams for `POST /boom?email=…`.
  function sampleSpan(): StreamedSpanJSON {
    return {
      trace_id: "t1",
      span_id: "s1",
      name: "POST /boom",
      start_timestamp: 1,
      status: "error",
      is_segment: true,
      attributes: {
        "sentry.status.message": "boom for ada@example.com",
        "url.full": "http://localhost:3000/boom?email=ada@example.com",
        "http.request.header.authorization": "Bearer secret",
        "http.request.header.cookie": ["kith_session=[Filtered]"],
        "http.response.header.set-cookie": ["kith_session=secret"],
        "http.request.header.user-agent": "curl",
      },
    };
  }

  it("removes auth and cookie headers, keeping the rest", () => {
    const span = scrubSpan(sampleSpan());
    expect(Object.keys(span.attributes)).not.toContain(
      "http.request.header.authorization",
    );
    expect(Object.keys(span.attributes)).not.toContain(
      "http.request.header.cookie",
    );
    expect(Object.keys(span.attributes)).not.toContain(
      "http.response.header.set-cookie",
    );
    expect(span.attributes["http.request.header.user-agent"]).toBe("curl");
  });

  it("masks every email address", () => {
    const span = scrubSpan(sampleSpan());
    expect(JSON.stringify(span)).not.toContain("ada@example.com");
    expect(span.attributes["sentry.status.message"]).toBe("boom for [email]");
  });
});
