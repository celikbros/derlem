import { expect, test } from "@playwright/test";
import path from "node:path";

const email = process.env.E2E_EMAIL;
const password = process.env.E2E_PASSWORD;
const mutating = process.env.E2E_MUTATING === "1";

test.skip(!email || !password || !mutating, "Mutating upload smoke is opt-in");

test("create a source and stream a browser upload", async ({ page }, testInfo) => {
  test.setTimeout(60_000);
  test.skip(testInfo.project.name !== "desktop", "One mutation is sufficient");
  const sourceName = `Browser Upload Smoke ${Date.now()}`;

  await page.goto("/");
  await page.getByLabel("E-posta").fill(email!);
  await page.getByLabel("Parola").fill(password!);
  await page.getByRole("button", { name: "Giriş yap" }).click();
  await expect(page.getByRole("heading", { name: "Veri kaynakları" })).toBeVisible();

  await page.getByRole("button", { name: "Yeni kaynak" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Kaynak adı", { exact: true }).fill(sourceName);
  await dialog.getByLabel("Kaynak tipi", { exact: true }).fill("jsonl");
  await dialog.locator('select[name="content_purpose"]').selectOption({ label: "Instruction" });
  await dialog.getByLabel("Lisans", { exact: true }).fill("internal-test");
  await dialog.locator('select[name="rights_status"]').selectOption({ label: "Temizlendi" });
  await dialog.getByLabel("Dil", { exact: true }).fill("tr");
  await dialog.getByLabel("Alan", { exact: true }).fill("e2e");
  await dialog.getByLabel("Lisans kanıtı", { exact: true }).fill("e2e/browser-upload");
  await dialog.getByLabel("Köken bilgisi", { exact: true }).fill("browser-upload-smoke");
  await dialog.getByRole("button", { name: "Kaynağı kaydet" }).click();

  await expect(page.getByRole("heading", { name: sourceName })).toBeVisible();
  await page.getByLabel("Dosya").setInputFiles(path.resolve("..", "data_samples", "example_contributions.jsonl"));
  await page.getByRole("button", { name: "Dosyayı yükle" }).click();
  await expect(page.getByRole("status")).toContainText("Dosya yüklendi ve kuyruğa alındı");
  await expect(page.getByText("clear / low", { exact: true })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("basic-tr-v1")).toBeVisible({ timeout: 30_000 });
});
