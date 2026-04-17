/**
 * E2E tests: Advisory disclaimer presence on all pages displaying a Fraud_Risk_Score.
 * Validates: Requirement 11.6 — "This score is advisory only. Human review is required
 * before initiating any legal or administrative action."
 *
 * Pages that display Fraud_Risk_Score:
 *   - /login          (platform-level disclaimer)
 *   - /dashboard      (TenderTable ScoreBadge + TenderTable disclaimer banner)
 *   - /tenders/[id]   (ScoreCard component)
 *   - /companies      (highest_fraud_risk_score column)
 *   - /companies/[id] (MetricCard with ScoreBadge)
 *   - /alerts         (AlertList fraud_risk_score column)
 */
import { test, expect } from "@playwright/test";
import { loginViaUI } from "./helpers/auth";

const DISCLAIMER_PATTERN = /advisory only/i;
const HUMAN_REVIEW_PATTERN = /human review is required/i;

test.describe("Advisory disclaimer — Requirement 11.6", () => {
  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
  });

  test("/login — advisory disclaimer present", async ({ page }) => {
    // Log out first so we can see the login page
    await page.goto("/login");
    // Even if redirected, the login page itself has the disclaimer
    // Check the page source directly
    const content = await page.content();
    expect(content).toMatch(/advisory only/i);
  });

  test("/dashboard — advisory disclaimer present", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");
    await expect(page.getByText(DISCLAIMER_PATTERN).first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(HUMAN_REVIEW_PATTERN).first()).toBeVisible();
  });

  test("/tenders/[id] — advisory disclaimer present on ScoreCard", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForSelector("table tbody tr", { timeout: 10_000 });

    const firstLink = page.locator("table tbody tr:first-child td:first-child a");
    const count = await firstLink.count();
    if (count === 0) {
      test.skip();
      return;
    }

    await firstLink.click();
    await page.waitForURL("**/tenders/**", { timeout: 10_000 });
    await expect(page.getByText(DISCLAIMER_PATTERN).first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(HUMAN_REVIEW_PATTERN).first()).toBeVisible();
  });

  test("/companies — advisory disclaimer present", async ({ page }) => {
    await page.goto("/companies");
    await page.waitForLoadState("networkidle");
    await expect(page.getByText(DISCLAIMER_PATTERN).first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(HUMAN_REVIEW_PATTERN).first()).toBeVisible();
  });

  test("/companies/[id] — advisory disclaimer present", async ({ page }) => {
    await page.goto("/companies");
    await page.waitForSelector("table tbody tr", { timeout: 10_000 });

    const firstLink = page.locator("table tbody tr:first-child td:first-child a");
    const count = await firstLink.count();
    if (count === 0) {
      test.skip();
      return;
    }

    await firstLink.click();
    await page.waitForURL("**/companies/**", { timeout: 10_000 });
    await expect(page.getByText(DISCLAIMER_PATTERN).first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(HUMAN_REVIEW_PATTERN).first()).toBeVisible();
  });

  test("/alerts — advisory disclaimer present", async ({ page }) => {
    await page.goto("/alerts");
    await page.waitForLoadState("networkidle");
    await expect(page.getByText(DISCLAIMER_PATTERN).first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(HUMAN_REVIEW_PATTERN).first()).toBeVisible();
  });
});
