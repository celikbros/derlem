import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

import { hasE2ESession, openAuthenticatedApp } from "./session";

test.skip(!hasE2ESession, "E2E_TOKEN or email/password credentials are required");

test("inspect calibrated similarity pairs", async ({ page }, testInfo) => {
  const consoleErrors: string[] = [];
  await openAuthenticatedApp(page);
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await page.getByRole("button", { name: "Benzerlik", exact: true }).click();

  await expect(page.getByRole("heading", { name: "Benzerlik incelemesi" })).toBeVisible();
  await expect(page.getByLabel("Kalibrasyon")).not.toHaveValue("");
  await expect(page.getByTestId("similarity-pair-1")).toBeVisible();
  await expect(page.locator(".similarity-detail-header h2")).toContainText("Hamming");
  await expect(page.getByText("Belge A", { exact: true })).toBeVisible();
  await expect(page.getByText("Belge B", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Kararı kaydet" }).or(page.locator(".similarity-own-review")),
  ).toBeVisible();

  const screenshotDirectory = path.resolve("..", "var", "screenshots");
  await mkdir(screenshotDirectory, { recursive: true });
  await page.screenshot({
    path: path.join(screenshotDirectory, `similarity-review-${testInfo.project.name}.png`),
    fullPage: true,
  });

  const hasHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(hasHorizontalOverflow).toBe(false);
  expect(consoleErrors).toEqual([]);
});
