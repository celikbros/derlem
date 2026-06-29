import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

import { hasE2ESession, openAuthenticatedApp } from "./session";

test.skip(!hasE2ESession, "E2E_TOKEN or email/password credentials are required");

test("inspect a frozen release and its downloadable artifacts", async ({ page }, testInfo) => {
  await openAuthenticatedApp(page);
  await page.getByRole("button", { name: "Sürümler" }).click();
  await expect(page.getByRole("heading", { name: "Sürümler" })).toBeVisible();

  await page.getByRole("button", { name: "Yeni release" }).click();
  const createDialog = page.getByRole("dialog");
  await expect(createDialog.getByRole("heading", { name: "Yeni release" })).toBeVisible();
  await expect(createDialog.getByText("Derlem Ornek Katki Verisi", { exact: true })).toBeVisible();
  await createDialog.getByRole("button", { name: "Pencereyi kapat" }).click();
  await expect(createDialog).not.toBeVisible();

  const releaseRow = page.getByRole("row").filter({ hasText: "2026.06.24-rc1" });
  await expect(releaseRow).toBeVisible();
  await expect(releaseRow.getByText("Derlem Instruction Seed", { exact: true })).toBeVisible();
  await expect(releaseRow.getByText("2026.06.24-rc1 · Frozen", { exact: true })).toBeVisible();
  await releaseRow.getByRole("button", { name: /Derlem Instruction Seed/ }).click();

  const detail = page.locator(".release-detail");
  await expect(detail.getByRole("heading", { name: "Derlem Instruction Seed" })).toBeVisible();
  await expect(detail.getByText("Geçti", { exact: true })).toHaveCount(5);
  await expect(detail.getByText("Uygulanmaz", { exact: true })).toBeVisible();
  await expect(detail.getByRole("link", { name: "Manifest indir" })).toBeVisible();
  await expect(detail.getByTitle("Artifact indir")).toBeVisible();

  const canonicalSmokeRow = page.getByRole("row").filter({ hasText: "Canonical Export Smoke" });
  if (await canonicalSmokeRow.count() === 1) {
    const smokeButton = canonicalSmokeRow.getByRole("button");
    await expect(smokeButton).toHaveCount(1);
    await smokeButton.click();
    await expect(detail.getByRole("heading", { name: "Canonical Export Smoke" })).toBeVisible();
    await expect(detail.getByText("~183 token", { exact: false })).toBeVisible();
  }

  const mixtureSmokeRow = page.getByRole("row").filter({ hasText: "Mixture Report Smoke" });
  if (await mixtureSmokeRow.count() === 1) {
    const mixtureButton = mixtureSmokeRow.getByRole("button");
    await expect(mixtureButton).toHaveCount(1);
    await mixtureButton.click();
    await expect(detail.getByRole("heading", { name: "Mixture Report Smoke" })).toBeVisible();
    await expect(detail.getByRole("heading", { name: "Veri karışımı" })).toBeVisible();
    await expect(detail.getByText("100% · 1", { exact: true })).toHaveCount(4);
  }

  const screenshotDirectory = path.resolve("..", "var", "screenshots");
  await mkdir(screenshotDirectory, { recursive: true });
  await page.screenshot({
    path: path.join(screenshotDirectory, `releases-${testInfo.project.name}.png`),
    fullPage: true,
  });
});
