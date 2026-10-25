import { expect, test } from "@playwright/test";

import { findMagicLinkFor } from "./mailpit";

test("sign-in -> onboarding -> landing for a brand-new user", async ({ page }) => {
  const email = `e2e-${Date.now()}@example.com`;

  await page.goto("/sign-in");
  await page.getByLabel("Work email").fill(email);
  await page.getByRole("button", { name: /send magic link/i }).click();
  await expect(page.getByRole("status")).toContainText("Check your email");

  const magicLink = await findMagicLinkFor(email);
  await page.goto(magicLink);

  // A brand-new identity has no Tenant Membership yet, so /verify lands here.
  await expect(page).toHaveURL(/\/onboarding$/);
  await expect(
    page.getByRole("heading", { name: "Name your workspace" }),
  ).toBeVisible();

  const workspaceNameInput = page.getByLabel("Workspace name");
  await expect(workspaceNameInput).not.toHaveValue("");
  const workspaceName = await workspaceNameInput.inputValue();

  await page.getByRole("button", { name: /create workspace/i }).click();

  await expect(page).toHaveURL(/\/w\/[^/]+$/);
  // The dashboard sets the workspace name as its wordmark.
  await expect(
    page.getByRole("heading", { level: 1, name: workspaceName }),
  ).toBeVisible();
});
