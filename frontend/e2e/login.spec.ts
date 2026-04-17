/**
 * E2E tests: Login flow
 * Validates: Requirement 1 (JWT authentication), Requirement 11.6 (advisory disclaimer on login page).
 */
import { test, expect } from "@playwright/test";
import { TEST_USERNAME, TEST_PASSWORD } from "./helpers/auth";

test.describe("Login flow", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/login");
  });

  test("renders login form with username and password fields", async ({ page }) => {
    await expect(page.getByLabel("Username")).toBeVisible();
    await expect(page.getByLabel("Password")).toBeVisible();
    await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();
  });

  test("shows TenderShield branding", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "TenderShield" })).toBeVisible();
  });

  test("advisory disclaimer is present on login page (Requirement 11.6)", async ({ page }) => {
    await expect(page.getByText(/advisory only/i)).toBeVisible();
    await expect(page.getByText(/human review is required/i)).toBeVisible();
  });

  test("sign-in button is disabled when fields are empty", async ({ page }) => {
    await expect(page.getByRole("button", { name: /sign in/i })).toBeDisabled();
  });

  test("sign-in button enables when both fields are filled", async ({ page }) => {
    await page.getByLabel("Username").fill("user");
    await page.getByLabel("Password").fill("pass");
    await expect(page.getByRole("button", { name: /sign in/i })).toBeEnabled();
  });

  test("shows error message on invalid credentials", async ({ page }) => {
    await page.getByLabel("Username").fill("wronguser");
    await page.getByLabel("Password").fill("wrongpass");
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page.getByRole("alert")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole("alert")).toContainText(/invalid username or password/i);
  });

  test("successful login redirects to dashboard", async ({ page }) => {
    await page.getByLabel("Username").fill(TEST_USERNAME);
    await page.getByLabel("Password").fill(TEST_PASSWORD);
    await page.getByRole("button", { name: /sign in/i }).click();
    await page.waitForURL("**/dashboard", { timeout: 15_000 });
    await expect(page).toHaveURL(/\/dashboard/);
  });

  test("already-authenticated user is redirected to dashboard", async ({ page }) => {
    // Login first
    await page.getByLabel("Username").fill(TEST_USERNAME);
    await page.getByLabel("Password").fill(TEST_PASSWORD);
    await page.getByRole("button", { name: /sign in/i }).click();
    await page.waitForURL("**/dashboard", { timeout: 15_000 });

    // Navigate back to /login — should redirect to dashboard
    await page.goto("/login");
    await page.waitForURL("**/dashboard", { timeout: 10_000 });
    await expect(page).toHaveURL(/\/dashboard/);
  });
});
