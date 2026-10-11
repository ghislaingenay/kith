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
