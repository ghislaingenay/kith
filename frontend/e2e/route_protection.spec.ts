import { expect, test } from "@playwright/test";

test("bounces an unauthenticated visitor away from a protected route", async ({ page }) => {
  await page.goto("/onboarding");

  await expect(page).toHaveURL(/\/sign-in$/);
});
