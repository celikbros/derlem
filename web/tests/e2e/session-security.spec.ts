import { expect, test, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";

const testPassword = "DerlemTest123!";

async function loginAs(page: Page, email: string) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Veri atölyesine giriş" })).toBeVisible();
  await page.getByLabel("E-posta").fill(email);
  await page.getByLabel("Parola").fill(testPassword);
  await page.getByRole("button", { name: "Giriş yap" }).click();
}

test("logout revokes the server session", async ({ context, page }) => {
  await loginAs(page, "manager@derlem.local");
  await expect(page.getByRole("heading", { name: "Veri kaynakları" })).toBeVisible();

  const tokenCookie = (await context.cookies()).find((cookie) => cookie.name === "derlem_token");
  expect(tokenCookie).toBeDefined();
  await expect((await page.request.get("/api/session/me")).status()).toBe(200);
  await expect((await page.request.post("/api/session/logout")).status()).toBe(200);

  await context.addCookies([tokenCookie!]);
  await expect((await page.request.get("/api/session/me")).status()).toBe(401);
});

test("logout-all revokes another active session", async ({ browser }) => {
  const firstContext = await browser.newContext();
  const secondContext = await browser.newContext();
  try {
    const firstPage = await firstContext.newPage();
    const secondPage = await secondContext.newPage();
    await loginAs(firstPage, "editor@derlem.local");
    await loginAs(secondPage, "editor@derlem.local");
    await expect(firstPage.getByRole("heading", { name: "Veri kaynakları" })).toBeVisible();
    await expect(secondPage.getByRole("heading", { name: "Veri kaynakları" })).toBeVisible();

    await expect((await firstPage.request.post("/api/session/logout-all")).status()).toBe(200);
    await expect((await secondPage.request.get("/api/session/me")).status()).toBe(401);
  } finally {
    await firstContext.close();
    await secondContext.close();
  }
});

test("repeated bad credentials are rate limited", async ({ request }) => {
  const runID = randomUUID().replaceAll("-", "");
  const email = `rate-limit-${runID}@derlem.invalid`;
  const ip = `2001:db8:${runID.slice(0, 4)}:${runID.slice(4, 8)}::1`;
  let rateLimitedResponse;
  for (let attempt = 0; attempt < 10; attempt += 1) {
    const response = await request.post("/api/session/login", {
      data: { email, password: "wrong-password" },
      headers: { "x-real-ip": ip },
    });
    if (response.status() === 429) {
      rateLimitedResponse = response;
      break;
    }
    expect(response.status()).toBe(401);
  }
  expect(rateLimitedResponse).toBeDefined();
  expect(Number(rateLimitedResponse!.headers()["retry-after"])).toBeGreaterThan(0);
});
