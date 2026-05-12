import { test, expect } from "@playwright/test";

/**
 * Dashboard E2E tests — S-23, S-25, 4.D.15
 *
 * Requires: `npm run dev` + backend running with valid credentials
 */

// Helper to log in before dashboard tests
async function loginAsAdmin(page: import("@playwright/test").Page) {
  await page.context().clearCookies();
  await page.goto("/login");
  await page.getByLabel(/correo|email/i).fill("admin@smartvoucher.com");
  await page.getByLabel(/contraseña|password/i).fill("admin123");
  await page.getByRole("button", { name: /iniciar sesión|login|ingresar/i }).click();
  await page.waitForURL("/", { timeout: 10_000 });
}

test.describe("Dashboard", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test("S-23: after login, dashboard shows 4 KPI cards", async ({ page }) => {
    await expect(page.getByText("Total Comprobantes")).toBeVisible();
    await expect(page.getByText("Pendientes")).toBeVisible();
    await expect(page.getByText("Procesados Hoy")).toBeVisible();
    await expect(page.getByText("Duplicados Detectados")).toBeVisible();
  });

  test("S-25: dashboard shows recent activity table", async ({ page }) => {
    await expect(page.getByText("Actividad Reciente")).toBeVisible();
  });
});
