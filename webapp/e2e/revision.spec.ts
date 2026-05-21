import { test, expect } from "@playwright/test";

/**
 * Revision E2E tests — S-35, 4.D.15
 *
 * Requires: `npm run dev` + backend running with a comprobante in "en_revision" state.
 * Set REVISION_ID env var to a known comprobante ID if available.
 */

async function loginAsAdmin(page: import("@playwright/test").Page) {
  await page.context().clearCookies();
  await page.goto("/login");
  await page.getByLabel(/correo|email/i).fill("admin@smartvoucher.com");
  await page.getByLabel(/contraseña|password/i).fill("admin123");
  await page.getByRole("button", { name: /iniciar sesión|login|ingresar/i }).click();
  await page.waitForURL("/", { timeout: 10_000 });
}

test.describe("Revision", () => {
  test("S-35: navigate to /revision/[id], click Aceptar, badge turns green (procesado)", async ({
    page,
  }) => {
    await loginAsAdmin(page);

    // Navigate to historial first to find an en_revision item
    await page.goto("/historial");
    await page.waitForLoadState("networkidle");

    // Look for an "en_revision" badge and click the corresponding "Ver" button
    const enRevisionBadge = page.getByText("en_revision").first();
    const isVisible = await enRevisionBadge.isVisible().catch(() => false);

    if (!isVisible) {
      // No en_revision items — skip gracefully
      test.skip();
      return;
    }

    // Click the "Ver" button in the same row
    const row = enRevisionBadge.locator("..").locator("..");
    await row.getByRole("button", { name: /ver/i }).click();

    // Should navigate to /revision/[id]
    await expect(page).toHaveURL(/\/revision\//);

    // Click Aceptar
    await page.getByRole("button", { name: /aceptar/i }).click();

    // Optimistic update: badge should change to "procesado"
    await expect(page.getByText("procesado")).toBeVisible({ timeout: 5_000 });
  });
});
