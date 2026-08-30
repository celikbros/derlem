import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

import { hasE2ESession, openAuthenticatedApp } from "./session";

test.skip(!hasE2ESession, "E2E_TOKEN or email/password credentials are required");

test("inspect sampled document content and quality review", async ({ page }, testInfo) => {
  await openAuthenticatedApp(page);

  const source = page.getByRole("button", { name: /Derlem Ornek Katki Verisi/ });
  await expect(source).toBeVisible();
  await source.click();
  await expect(page.getByRole("heading", { name: "Belge örnekleri" })).toBeVisible();

  await page.getByRole("button", { name: /^Onaylı / }).click();
  const firstDocument = page.getByRole("button", { name: /^#1 / });
  await expect(firstDocument).toBeVisible();
  await firstDocument.click();

  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading", { name: "Belge örneği" })).toBeVisible();
  await expect(dialog.getByLabel("Okuma görünümü")).toBeVisible();
  await expect(dialog.getByLabel("Ham içerik")).not.toHaveValue("");
  await expect(dialog.getByRole("button", { name: "Yeni sürümü kaydet" })).toBeVisible();
  await expect(dialog.getByRole("heading", { name: "Belge moderasyonu" })).toBeVisible();
  for (const label of ["Genel", "Dil", "Tutarlılık", "Bilgi", "Temizlik"]) {
    await expect(dialog.getByLabel(`${label} kalite puanı`)).toHaveValue("");
  }
  await expect(dialog.getByText("approved", { exact: true })).toBeVisible();
  await expect(dialog.getByText("Genel 5/5", { exact: true })).toBeVisible();
  await expect(dialog.getByText("Eski tek puanlı rubric", { exact: true })).toBeVisible();

  const screenshotDirectory = path.resolve("..", "var", "screenshots");
  await mkdir(screenshotDirectory, { recursive: true });
  await page.screenshot({
    path: path.join(screenshotDirectory, `document-review-${testInfo.project.name}.png`),
    fullPage: true,
  });

  await dialog.getByRole("button", { name: "Pencereyi kapat" }).click();
  await expect(dialog).not.toBeVisible();
});
