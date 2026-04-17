import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright E2E configuration for TenderShield frontend.
 * Tests run against the Next.js dev server (started externally).
 * Set BASE_URL env var to override (default: http://localhost:3000).
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  timeout: 30_000,

  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    // Credentials stored in env vars for CI
    storageState: process.env.STORAGE_STATE ?? undefined,
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
