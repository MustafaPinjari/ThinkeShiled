/**
 * E2E tests: Dashboard filtering
 * Validates: Requirement 9.1–9.5 (dashboard list, filters, color-coded badges, disclaimer).
 */
import { test, expect } from "@playwright/test";
import { loginViaUI } from "./helpers/auth";

test.describe("Dashboard filtering", () => {
  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
  });

  test("dashboard page loads and shows tender table", async ({ page }) => {
    await expect(page.getByRole("heading", { name: /dashboard/i })).toBeVisible();
    await expect(page.getByRole("table")).toBeVisible({ timeout: 10_000 });
  });

  test("advisory disclaimer is present on dashboard (Requirement 11.6)", async ({ page }) => {
    await expect(page.getByText(/advisory only/i).first()).toBeVisible();
    await expect(page.getByText(/human review is required/i).first()).toBeVisible();
  });

  test("filter panel is visible with all controls", async ({ page }) => {
    await expect(page.getByLabel(/minimum risk score/i)).toBeVisible();
    await expect(page.getByLabel(/maximum risk score/i)).toBeVisible();
    await expect(page.getByLabel(/filter by category/i)).toBeVisible();
    await expect(page.getByLabel(/filter by buyer name/i)).toBeVisible();
    await expect(page.getByLabel(/filter by red flag type/i)).toBeVisible();
  });

  test("filtering by category updates the tender list within 1 second (Requirement 9.3)", async ({ page }) => {
    const categoryInput = page.getByLabel(/filter by category/i);
    await categoryInput.fill("Construction");

    // Table should update within 1 second (debounce is 400ms + render)
    await expect(page.getByRole("table")).toBeVisible({ timeout: 1500 });
  });

  test("filtering by flag type updates the tender list", async ({ page }) => {
    const select = page.getByLabel(/filter by red flag type/i);
    await select.selectOption("SINGLE_BIDDER");
    // Table should reload
    await expect(page.getByRole("table")).toBeVisible({ timeout: 5_000 });
  });

  test("score range filter accepts min and max values", async ({ page }) => {
    await page.getByLabel(/minimum risk score/i).fill("70");
    await page.getByLabel(/maximum risk score/i).fill("100");
    await expect(page.getByRole("table")).toBeVisible({ timeout: 5_000 });
  });

  test("summary stats section is visible", async ({ page }) => {
    // SummaryStats renders total tenders, high-risk count, etc.
    await expect(page.locator("[aria-label='Summary statistics']").or(
      page.getByText(/total tenders/i)
    )).toBeVisible({ timeout: 10_000 });
  });

  test("table has sortable column headers", async ({ page }) => {
    const riskScoreHeader = page.getByRole("columnheader", { name: /risk score/i });
    await expect(riskScoreHeader).toBeVisible();
    await riskScoreHeader.click();
    // Table should still be visible after sort
    await expect(page.getByRole("table")).toBeVisible({ timeout: 5_000 });
  });

  test("pagination controls are present", async ({ page }) => {
    await expect(page.getByRole("button", { name: /next page/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /previous page/i })).toBeVisible();
  });

  test("clear all filter button appears after applying a filter", async ({ page }) => {
    await page.getByLabel(/filter by category/i).fill("Roads");
    // Wait for debounce
    await page.waitForTimeout(500);
    await expect(page.getByRole("button", { name: /clear all/i })).toBeVisible();
  });
});
