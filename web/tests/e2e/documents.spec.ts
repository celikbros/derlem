import { expect, test } from "@playwright/test";

import { hasE2ESession, openAuthenticatedApp } from "./session";

test.skip(!hasE2ESession, "E2E_TOKEN or email/password credentials are required");

test("inspect sampled document content", async ({ page }) => {
  await openAuthenticatedApp(page);

  const source = page.getByRole("button", { name: /Derlem Ornek Katki Verisi/ });
  await expect(source).toBeVisible();
  await source.click();
  await expect(page.getByRole("heading", { name: "Belge örnekleri" })).toBeVisible();

  const firstDocument = page.getByRole("button", { name: /^#1 / });
  await expect(firstDocument).toBeVisible();
  await firstDocument.click();

  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading", { name: "Belge örneği" })).toBeVisible();
  await expect(dialog.getByLabel("İçerik")).not.toHaveValue("");
  await expect(dialog.getByRole("button", { name: "Yeni sürümü kaydet" })).toBeVisible();
  await dialog.getByRole("button", { name: "Pencereyi kapat" }).click();
  await expect(dialog).not.toBeVisible();
});
