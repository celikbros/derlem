import { expect, test, type Page } from "@playwright/test";

const testPassword = "DerlemTest123!";

async function loginAs(page: Page, email: string) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Veri atölyesine giriş" })).toBeVisible();
  await page.getByLabel("E-posta").fill(email);
  await page.getByLabel("Parola").fill(testPassword);
  await page.getByRole("button", { name: "Giriş yap" }).click();
}

test("consumer sees frozen releases but no operational workspaces", async ({ page }) => {
  await loginAs(page, "consumer@derlem.local");

  await expect(page.getByRole("heading", { name: "Sürümler" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sürümler", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Kaynaklar" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "İnceleme" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Benzerlik" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "İşler" })).toHaveCount(0);

  await expect((await page.request.get("/api/releases")).status()).toBe(200);
  await expect((await page.request.get("/api/sources")).status()).toBe(403);
  await expect((await page.request.get("/api/jobs")).status()).toBe(403);
  await expect((await page.request.get("/api/similarity-calibrations")).status()).toBe(403);
});

test("contributor receives no operational data before contribution workspace", async ({ page }) => {
  await loginAs(page, "contributor@derlem.local");

  await expect(page.getByRole("heading", { name: "Çalışma alanı" })).toBeVisible();
  await expect(page.getByText("Bu rol için etkin bir çalışma alanı bulunmuyor.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Kaynaklar" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Sürümler" })).toHaveCount(0);

  await expect((await page.request.get("/api/sources")).status()).toBe(403);
  await expect((await page.request.get("/api/releases")).status()).toBe(403);
  await expect((await page.request.get("/api/jobs")).status()).toBe(403);
  await expect((await page.request.get("/api/similarity-calibrations")).status()).toBe(403);
});
