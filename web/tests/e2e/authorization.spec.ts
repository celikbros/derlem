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

test("contributor is limited to the contribution workspace", async ({ page }) => {
  await loginAs(page, "contributor@derlem.local");

  await expect(page.getByRole("heading", { name: "Katkılar" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Katkılar", exact: true })).toBeVisible();
  await expect(page.getByRole("form", { name: "Yeni katkı" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Kaynaklar" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Sürümler" })).toHaveCount(0);

  await expect((await page.request.get("/api/contributions/mine")).status()).toBe(200);
  await expect((await page.request.get("/api/sources")).status()).toBe(403);
  await expect((await page.request.get("/api/releases")).status()).toBe(403);
  await expect((await page.request.get("/api/jobs")).status()).toBe(403);
  await expect((await page.request.get("/api/similarity-calibrations")).status()).toBe(403);
});

test("moderator gets a focused review workspace without the restricted job feed", async ({ page }, testInfo) => {
  const jobRequests: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/api/jobs") {
      jobRequests.push(request.url());
    }
  });

  await loginAs(page, "moderator@derlem.local");

  const source = page.getByRole("button", {
    name: /gardash_faz2_tr_dedup_20260621_clean_candidate_20260625/,
  });
  await expect(source).toBeVisible();
  await source.click();

  const workspace = page.getByRole("complementary", { name: "Belge inceleme çalışma alanı" });
  const claimButton = workspace.getByRole("button", { name: "Paketi al ve incelemeye başla" });
  await expect(workspace).toBeVisible();
  await expect(workspace.getByText("Burada yalnız üç şey yapacaksınız")).toBeVisible();
  await expect(workspace.getByRole("heading", { name: "Yeni inceleme paketi" })).toBeVisible();
  await expect(workspace.getByText("Nereden başlar?")).toBeVisible();
  await expect(claimButton).toBeVisible();
  const profileEvidence = workspace.getByTestId("source-profile-evidence");
  await expect(profileEvidence.getByRole("heading", { name: "Profil ve kanıt" })).toBeVisible();
  await expect(profileEvidence.getByText("legacy-auto · sürüm 1", { exact: true })).toBeVisible();
  const ownHistory = workspace.getByTestId("document-review-history");
  await expect(ownHistory.getByRole("heading", { name: "İncelediklerim" })).toBeVisible();
  await expect(ownHistory.getByText("Burada yalnız sizin bu kaynak için verdiğiniz kararlar")).toBeVisible();
  await expect(ownHistory.getByRole("button", { name: /^Tümü \d+$/ })).toBeVisible();
  await expect(ownHistory.getByRole("button", { name: /^Onaylı \d+$/ })).toBeVisible();
  await expect(ownHistory.getByRole("button", { name: /^Reddedildi \d+$/ })).toBeVisible();
  await expect(ownHistory.getByRole("button", { name: /^Hassas \d+$/ })).toBeVisible();
  await expect(ownHistory.getByRole("button", { name: /^Geri alındı \d+$/ })).toBeVisible();
  await expect(workspace.locator(":scope > dl")).toBeHidden();
  await expect(workspace.getByText(/\d+ bekleyen örnek/)).toBeVisible();
  await expect(source).not.toBeVisible();
  await expect(page.getByText("Bu işlem için yetkiniz bulunmuyor.")).toHaveCount(0);
  expect(jobRequests).toEqual([]);
  if (testInfo.project.name === "desktop") {
    const viewport = page.viewportSize();
    const bounds = await workspace.boundingBox();
    const claimBounds = await claimButton.boundingBox();
    expect(viewport).not.toBeNull();
    expect(bounds).not.toBeNull();
    expect(claimBounds).not.toBeNull();
    expect(bounds!.width).toBeGreaterThan(viewport!.width * 0.7);
    expect(claimBounds!.y - bounds!.y).toBeLessThan(520);
    expect(claimBounds!.y + claimBounds!.height).toBeLessThanOrEqual(viewport!.height);
  }
});
