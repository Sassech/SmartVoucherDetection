import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright E2E configuration — 4.D.15
 *
 * NOTE: E2E tests require:
 *   1. `npm run dev` (Next.js dev server on port 3000)
 *   2. Backend running on port 8000
 *
 * Run: npx playwright test
 */

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: "html",
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "npm run dev",
    port: 3000,
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
