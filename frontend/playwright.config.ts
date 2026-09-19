import { defineConfig, devices } from "@playwright/test";

/** Runs against the compose stack (infra/docker-compose.yml), never a dev
 * server Playwright manages itself — the flow under test spans the
 * frontend, the API, and Mailpit for magic-link delivery, so it needs the
 * real stack, not an isolated Next.js server. */
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:3000";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: "html",
  use: {
    baseURL,
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
