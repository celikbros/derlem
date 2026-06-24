import { expect, type Page } from "@playwright/test";

const email = process.env.E2E_EMAIL;
const password = process.env.E2E_PASSWORD;
const token = process.env.E2E_TOKEN;

export const hasE2ESession = Boolean(token || (email && password));

export async function openAuthenticatedApp(page: Page) {
  if (token) {
    await page.context().addCookies([{
      name: "derlem_token",
      value: token,
      url: "http://127.0.0.1:3000",
      httpOnly: true,
      sameSite: "Lax",
    }]);
    await page.goto("/");
  } else {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Veri atölyesine giriş" })).toBeVisible();
    await page.getByLabel("E-posta").fill(email!);
    await page.getByLabel("Parola").fill(password!);
    await page.getByRole("button", { name: "Giriş yap" }).click();
  }
  await expect(page.getByRole("heading", { name: "Veri kaynakları" })).toBeVisible();
}
