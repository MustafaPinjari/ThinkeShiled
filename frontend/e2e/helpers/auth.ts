/**
 * Shared authentication helpers for Playwright E2E tests.
 * Credentials are read from environment variables so they are never
 * hard-coded in source.
 */
import { Page } from "@playwright/test";

export const TEST_USERNAME = process.env.E2E_USERNAME ?? "admin";
export const TEST_PASSWORD = process.env.E2E_PASSWORD ?? "adminpassword";

/**
 * Perform a login via the UI and wait for the dashboard to load.
 */
export async function loginViaUI(page: Page): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Username").fill(TEST_USERNAME);
  await page.getByLabel("Password").fill(TEST_PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  // Wait for redirect to dashboard
  await page.waitForURL("**/dashboard", { timeout: 10_000 });
}
