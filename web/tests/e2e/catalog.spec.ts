import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

import { hasE2ESession, openAuthenticatedApp } from "./session";

test.skip(!hasE2ESession, "E2E_TOKEN or email/password credentials are required");

test("login and inspect the source catalog", async ({ page }, testInfo) => {
  await openAuthenticatedApp(page);
  const screenshotDirectory = path.resolve("..", "var", "screenshots");
  await mkdir(screenshotDirectory, { recursive: true });
  await page.getByRole("button", { name: "Yeni kaynak" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading", { name: "Yeni kaynak" })).toBeVisible();
  await dialog.getByRole("button", { name: "Pencereyi kapat" }).click();
  await expect(dialog).not.toBeVisible();

  await page.getByRole("button", { name: "İşler" }).click();
  await expect(page.getByRole("heading", { name: "Arka plan işleri" })).toBeVisible();
  await page.screenshot({
    path: path.join(screenshotDirectory, `jobs-${testInfo.project.name}.png`),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Kaynaklar" }).click();
  await expect(page.getByRole("heading", { name: "Veri kaynakları" })).toBeVisible();
  const sampleSource = page.getByRole("button", { name: /Derlem Ornek Katki Verisi/ });
  if (await sampleSource.count() === 1) {
    await sampleSource.click();
    await expect(page.getByRole("heading", { name: "Derlem Ornek Katki Verisi" })).toBeVisible();
    await expect(page.getByText("basic-tr-v1")).toBeVisible();
  }

  await page.screenshot({
    path: path.join(screenshotDirectory, `catalog-${testInfo.project.name}.png`),
    fullPage: true,
  });
});
