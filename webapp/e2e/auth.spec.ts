import { test, expect } from "@playwright/test";

/**
 * Auth E2E tests — S-17, S-18, S-19, 4.D.15
 *
 * Requires: `npm run dev` + backend running
 */

test.describe("Auth flow", () => {
  test("S-17: unauthenticated user visiting / redirects to /login", async ({ page }) => {
    // Clear all cookies to ensure unauthenticated state
    await page.context().clearCookies();
    await page.goto("/");

    // Should be redirected to /login
    await expect(page).toHaveURL(/\/login/);
  });

  test("S-18: login form submits and redirects to dashboard on success", async ({ page }) => {
    await page.context().clearCookies();
    await page.goto("/login");

    // Fill in credentials
    await page.getByLabel(/correo|email/i).fill("admin@smartvoucher.com");
    await page.getByLabel(/contraseña|password/i).fill("admin123");
    await page.getByRole("button", { name: /iniciar sesión|login|ingresar/i }).click();

    // Should redirect to dashboard
    await expect(page).toHaveURL("/", { timeout: 10_000 });
    await expect(page.getByText("Dashboard")).toBeVisible();
  });

  test("S-19: login form shows error on wrong credentials", async ({ page }) => {
    await page.context().clearCookies();
    await page.goto("/login");

    await page.getByLabel(/correo|email/i).fill("wrong@example.com");
    await page.getByLabel(/contraseña|password/i).fill("wrongpassword");
    await page.getByRole("button", { name: /iniciar sesión|login|ingresar/i }).click();

    // Should show error, stay on /login
    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByRole("alert").or(page.getByText(/inválido|incorrecto|error/i))).toBeVisible({
      timeout: 5_000,
    });
  });
});
