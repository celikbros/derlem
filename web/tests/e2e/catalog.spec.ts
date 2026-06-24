import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const email = process.env.E2E_EMAIL;
const password = process.env.E2E_PASSWORD;

test.skip(!email || !password, "E2E_EMAIL and E2E_PASSWORD are required");

test("login and inspect the source catalog", async ({ page }, testInfo) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Veri atölyesine giriş" })).toBeVisible();
  await page.getByLabel("E-posta").fill(email!);
  await page.getByLabel("Parola").fill(password!);
  await page.getByRole("button", { name: "Giriş yap" }).click();

  await expect(page.getByRole("heading", { name: "Veri kaynakları" })).toBeVisible();
  await page.getByRole("button", { name: "Yeni kaynak" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading", { name: "Yeni kaynak" })).toBeVisible();
  await dialog.getByRole("button", { name: "Pencereyi kapat" }).click();
  await expect(dialog).not.toBeVisible();

  await page.getByRole("button", { name: "İşler" }).click();
  await expect(page.getByRole("heading", { name: "Arka plan işleri" })).toBeVisible();
  await page.getByRole("button", { name: "Kaynaklar" }).click();
  await expect(page.getByRole("heading", { name: "Veri kaynakları" })).toBeVisible();
  const sampleSource = page.getByRole("button", { name: /Derlem Ornek Katki Verisi/ });
  if (await sampleSource.count() === 1) {
    await sampleSource.click();
    await expect(page.getByRole("heading", { name: "Derlem Ornek Katki Verisi" })).toBeVisible();
    await expect(page.getByText("basic-tr-v1")).toBeVisible();
  }

  const screenshotDirectory = path.resolve("..", "var", "screenshots");
  await mkdir(screenshotDirectory, { recursive: true });
  await page.screenshot({
    path: path.join(screenshotDirectory, `catalog-${testInfo.project.name}.png`),
    fullPage: true,
  });
});
