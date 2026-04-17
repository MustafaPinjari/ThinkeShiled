/**
 * E2E tests: Collusion graph page
 * Validates: Requirement 8.5 (interactive force-directed graph), Requirement 8.4 (collusion rings).
 */
import { test, expect } from "@playwright/test";
import { loginViaUI } from "./helpers/auth";

test.describe("Collusion graph page", () => {
  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
    await page.goto("/graph");
    await page.waitForURL("**/graph", { timeout: 10_000 });
  });

  test("graph page loads without errors", async ({ page }) => {
    // No error boundary or 500 page
    await expect(page.getByRole("heading", { name: /collusion/i }).or(
      page.getByText(/graph/i)
    ).first()).toBeVisible({ timeout: 10_000 });
  });

  test("graph canvas container is rendered", async ({ page }) => {
    // vis-network renders into a div container
    const canvas = page.locator("canvas").or(page.locator("[data-testid='graph-canvas']"));
    await expect(canvas.first()).toBeVisible({ timeout: 10_000 });
  });

  test("collusion ring panel is present", async ({ page }) => {
    // CollusionRingPanel renders a list of detected rings
    await expect(
      page.getByText(/collusion ring/i).or(page.getByText(/no rings detected/i)).first()
    ).toBeVisible({ timeout: 10_000 });
  });

  test("edge type filter controls are present", async ({ page }) => {
    // Edge type filter buttons/checkboxes
    await expect(
      page.getByText(/CO_BID/i).or(page.getByText(/co.bid/i)).first()
    ).toBeVisible({ timeout: 10_000 });
  });

  test("advisory disclaimer is not required on graph page (no score displayed)", async ({ page }) => {
    // Graph page does not display Fraud_Risk_Score directly, so disclaimer is optional
    // This test documents the expected behavior — no assertion needed
    // If a score IS shown, the disclaimer must be present
    const scoreText = page.getByText(/fraud risk score/i);
    const count = await scoreText.count();
    if (count > 0) {
      await expect(page.getByText(/advisory only/i).first()).toBeVisible();
    }
  });
});
