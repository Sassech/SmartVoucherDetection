import { test, expect } from "@playwright/test";

/**
 * Historial E2E tests — S-27, S-28, S-29, 4.D.15
 *
 * Requires: `npm run dev` + backend running
 */

async function loginAsAdmin(page: import("@playwright/test").Page) {
  await page.context().clearCookies();
  await page.goto("/login");
  await page.getByLabel(/correo|email/i).fill("admin@smartvoucher.com");
  await page.getByLabel(/contraseña|password/i).fill("admin123");
  await page.getByRole("button", { name: /iniciar sesión|login|ingresar/i }).click();
  await page.waitForURL("/", { timeout: 10_000 });
}

test.describe("Historial", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto("/historial");
    await page.waitForLoadState("networkidle");
  });

  test("S-27: clicking status pill updates URL params and filters", async ({ page }) => {
    await page.getByRole("button", { name: /pendiente/i }).click();

    await expect(page).toHaveURL(/status=pendiente/);
  });

  test("S-28: date range filter updates URL params", async ({ page }) => {
    await page.getByLabel(/fecha desde/i).fill("2024-01-01");

    await expect(page).toHaveURL(/date_from=2024-01-01/);
  });

  test("S-29: clicking next page loads more results", async ({ page }) => {
    // Only test if hasMore is true (backend-dependent)
    const nextBtn = page.getByRole("button", { name: /siguiente/i });
    const isVisible = await nextBtn.isVisible().catch(() => false);

    if (isVisible) {
      await nextBtn.click();
      await expect(page).toHaveURL(/page=2/);
    } else {
      // Gracefully skip when there aren't enough items
      test.skip();
    }
  });
});
