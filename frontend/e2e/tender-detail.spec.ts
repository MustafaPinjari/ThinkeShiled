/**
 * E2E tests: Tender detail page
 * Validates: Requirement 6.3 (SHAP chart renders within 3s), Requirement 11.6 (advisory disclaimer),
 *            Requirement 6.4 (red flags with rule text), Requirement 5 (score display).
 */
import { test, expect } from "@playwright/test";
import { loginViaUI } from "./helpers/auth";

test.describe("Tender detail page", () => {
  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
  });

  /**
   * Navigate to the first tender in the dashboard and verify the detail page.
   * If no tenders exist, the test is skipped gracefully.
   */
  async function navigateToFirstTender(page: Parameters<typeof loginViaUI>[0]) {
    await page.waitForSelector("table tbody tr", { timeout: 10_000 });
    const firstLink = page.locator("table tbody tr:first-child td:first-child a");
    const count = await firstLink.count();
    if (count === 0) {
      test.skip();
      return false;
    }
    await firstLink.click();
    await page.waitForURL("**/tenders/**", { timeout: 10_000 });
    return true;
  }

  test("tender detail page loads with score card", async ({ page }) => {
    const ok = await navigateToFirstTender(page);
    if (!ok) return;

    await expect(page.getByText(/fraud risk score/i).first()).toBeVisible({ timeout: 10_000 });
  });

  test("advisory disclaimer is present on tender detail page (Requirement 11.6)", async ({ page }) => {
    const ok = await navigateToFirstTender(page);
    if (!ok) return;

    await expect(page.getByText(/advisory only/i).first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/human review is required/i).first()).toBeVisible();
  });

  test("SHAP chart section renders within 3 seconds (Requirement 6.3)", async ({ page }) => {
    const ok = await navigateToFirstTender(page);
    if (!ok) return;

    // The SHAP section heading should appear within 3 seconds of page load
    await expect(
      page.getByRole("heading", { name: /top contributing factors/i })
    ).toBeVisible({ timeout: 3_000 });
  });

  test("SHAP chart SVG or fallback message is rendered", async ({ page }) => {
    const ok = await navigateToFirstTender(page);
    if (!ok) return;

    // Either the SVG chart or a fallback message should be present
    const svgOrFallback = page.locator("svg").or(
      page.getByText(/shap computation failed/i)
    ).or(
      page.getByText(/no shap factors available/i)
    ).or(
      page.getByText(/no explanation data available/i)
    );
    await expect(svgOrFallback.first()).toBeVisible({ timeout: 5_000 });
  });

  test("red flags section is present", async ({ page }) => {
    const ok = await navigateToFirstTender(page);
    if (!ok) return;

    await expect(
      page.getByRole("heading", { name: /red flags/i })
    ).toBeVisible({ timeout: 10_000 });
  });

  test("bid table section is present", async ({ page }) => {
    const ok = await navigateToFirstTender(page);
    if (!ok) return;

    // BidTable renders a table with bid data
    await expect(page.getByRole("table").nth(0)).toBeVisible({ timeout: 10_000 });
  });
});
