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

  const releaseRow = page.getByRole("row").filter({ hasText: "Derlem Instruction Seed" });
  await expect(releaseRow).toBeVisible();
  await expect(releaseRow.getByText("2026.06.24-rc1 · Frozen", { exact: true })).toBeVisible();
  await releaseRow.getByRole("button", { name: /Derlem Instruction Seed/ }).click();

  const detail = page.locator(".release-detail");
  await expect(detail.getByRole("heading", { name: "Derlem Instruction Seed" })).toBeVisible();
  await expect(detail.getByText("Geçti", { exact: true })).toHaveCount(5);
  await expect(detail.getByText("Uygulanmaz", { exact: true })).toBeVisible();
  await expect(detail.getByRole("link", { name: "Manifest indir" })).toBeVisible();
  await expect(detail.getByTitle("Artifact indir")).toBeVisible();

  const screenshotDirectory = path.resolve("..", "var", "screenshots");
  await mkdir(screenshotDirectory, { recursive: true });
  await page.screenshot({
    path: path.join(screenshotDirectory, `releases-${testInfo.project.name}.png`),
    fullPage: true,
  });
});
