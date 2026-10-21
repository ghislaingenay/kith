import { afterEach, describe, expect, it, vi } from "vitest";

async function loadEnv() {
  vi.resetModules();
  return (await import("./env")).env;
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("env's Ask flags", () => {
  it("shows sources and citation markers by default", async () => {
    vi.stubEnv("NEXT_PUBLIC_ASK_SHOW_SOURCES", undefined);
    vi.stubEnv("NEXT_PUBLIC_ASK_CITATION_MARKERS", undefined);
    const env = await loadEnv();
    expect(env.NEXT_PUBLIC_ASK_SHOW_SOURCES).toBe(true);
    expect(env.NEXT_PUBLIC_ASK_CITATION_MARKERS).toBe(true);
  });

  it("turns each off with false", async () => {
    vi.stubEnv("NEXT_PUBLIC_ASK_SHOW_SOURCES", "false");
    vi.stubEnv("NEXT_PUBLIC_ASK_CITATION_MARKERS", "false");
    const env = await loadEnv();
    expect(env.NEXT_PUBLIC_ASK_SHOW_SOURCES).toBe(false);
    expect(env.NEXT_PUBLIC_ASK_CITATION_MARKERS).toBe(false);
  });

  it("rejects a value that is not true or false", async () => {
    vi.stubEnv("NEXT_PUBLIC_ASK_SHOW_SOURCES", "no");
    await expect(loadEnv()).rejects.toThrow();
  });
});

describe("env's Sentry settings", () => {
  const names = [
    "NEXT_PUBLIC_SENTRY_DSN",
    "NEXT_PUBLIC_SENTRY_ENVIRONMENT",
    "NEXT_PUBLIC_SENTRY_RELEASE",
    "NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE",
  ];

  it("is off in the local environment, tracing 10 %, by default", async () => {
    names.forEach((name) => vi.stubEnv(name, undefined));
    const env = await loadEnv();
    expect(env.NEXT_PUBLIC_SENTRY_DSN).toBe("");
    expect(env.NEXT_PUBLIC_SENTRY_ENVIRONMENT).toBe("local");
    expect(env.NEXT_PUBLIC_SENTRY_RELEASE).toBeUndefined();
    expect(env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE).toBe(0.1);
  });

  // An unset GitHub variable reaches the image build as an empty string.
  it("treats empty values as unset", async () => {
    names.forEach((name) => vi.stubEnv(name, ""));
    const env = await loadEnv();
    expect(env.NEXT_PUBLIC_SENTRY_DSN).toBe("");
    expect(env.NEXT_PUBLIC_SENTRY_ENVIRONMENT).toBe("local");
    expect(env.NEXT_PUBLIC_SENTRY_RELEASE).toBeUndefined();
    expect(env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE).toBe(0.1);
  });

  it("reads each value", async () => {
    vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", "https://key@o1.ingest.sentry.io/1");
    vi.stubEnv("NEXT_PUBLIC_SENTRY_ENVIRONMENT", "production");
    vi.stubEnv("NEXT_PUBLIC_SENTRY_RELEASE", "abc123");
    vi.stubEnv("NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE", "0.5");
    const env = await loadEnv();
    expect(env.NEXT_PUBLIC_SENTRY_DSN).toBe("https://key@o1.ingest.sentry.io/1");
    expect(env.NEXT_PUBLIC_SENTRY_ENVIRONMENT).toBe("production");
    expect(env.NEXT_PUBLIC_SENTRY_RELEASE).toBe("abc123");
    expect(env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE).toBe(0.5);
  });

  it("rejects a sample rate outside 0 to 1", async () => {
    vi.stubEnv("NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE", "2");
    await expect(loadEnv()).rejects.toThrow();
  });
});
