import { expect, test } from "@playwright/test";

import type { Document, DocumentReviewClaim, Release, Source, User } from "../../lib/types";

const now = "2026-08-22T09:30:00Z";
const user: User = {
  id: "11111111-1111-4111-8111-111111111111",
  email: "admin@derlem.local",
  roles: ["admin"],
};
const productionRunID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const reviewCampaignID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const configSHA = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
const contractSHA = "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef";
const implementationSHA = "fedcba0987654321fedcba0987654321fedcba0987654321fedcba0987654321";

const source: Source = {
  id: "22222222-2222-4222-8222-222222222222",
  name: "Profile evidence E2E source",
  source_type: "jsonl",
  content_purpose: "pretrain",
  license: "test",
  rights_status: "cleared",
  language: "tr",
  domain: "test",
  license_evidence_ref: "test-evidence",
  lineage_ref: "e2e",
  data_profile_key: "translation",
  data_profile_version: "1",
  profile_config_artifact_kind: "profile_config",
  profile_config_sha256: configSHA,
  profile_assignment_reason: "declared_at_ingest",
  profile_assigned_at: now,
  data_origin: "model",
  production_run_id: productionRunID,
  source_metadata: {},
  object_sha256: "a".repeat(64),
  byte_size: 128,
  line_count: 1,
  document_count: 1,
  document_sampling_status: "sampled",
  document_sample_generation: 1,
  document_sampling_method: "risk-stratified-sha256-v1",
  sampled_document_count: 1,
  reviewed_document_count: 0,
  approved_document_count: 0,
  flagged_document_count: 0,
  pii_status: "clear",
  duplicate_status: "unique",
  normalized_dedup_status: "unique",
  normalized_duplicate_count: 0,
  normalized_duplicate_source_count: 0,
  risk_level: "low",
  approval_status: "sampled_for_review",
  version: 1,
  created_by: user.id,
  created_at: now,
  updated_at: now,
};

const document: Document = {
  id: "33333333-3333-4333-8333-333333333333",
  source_id: source.id,
  source_ordinal: 1,
  current_object_sha256: "b".repeat(64),
  text_preview: "Profil kampanyası örneği",
  byte_size: 32,
  char_count: 30,
  status: "sampled",
  current_version: 1,
  sampling_method: "risk-stratified-sha256-v1",
  risk_score: 1,
  risk_reasons: [],
  is_active: true,
  sample_generation: 1,
  created_at: now,
  updated_at: now,
};

const claim: DocumentReviewClaim = {
  claim_token: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
  review_campaign_id: reviewCampaignID,
  expires_at: "2026-08-22T09:45:00Z",
  documents: [document],
  resumed: false,
};

function release(overrides: Partial<Release>): Release {
  return {
    id: "44444444-4444-4444-8444-444444444444",
    name: "Present contract release",
    version: "v1",
    content_purpose: "pretrain",
    status: "frozen",
    manifest_object_sha256: "c".repeat(64),
    manifest_sha256: "d".repeat(64),
    contract_snapshot_status: "present",
    contract_snapshot_artifact_kind: "release_contract_snapshot",
    contract_snapshot_sha256: contractSHA,
    implementation_bundle_sha256: implementationSHA,
    gate_results: {},
    created_by: user.id,
    frozen_by: user.id,
    created_at: now,
    frozen_at: now,
    sources: [],
    exports: [],
    ...overrides,
  };
}

test("source profile evidence stays full in source detail and compact in review mode", async ({ page }, testInfo) => {
  await page.addInitScript((userID) => {
    window.localStorage.setItem(`derlem-welcome-dismissed-${userID}`, "1");
  }, user.id);
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const { pathname } = new URL(request.url());
    const json = (body: unknown, status = 200) => route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
    if (pathname === "/api/session/me") return json(user);
    if (pathname === "/api/sources") return json({ items: [source] });
    if (pathname === "/api/jobs") return json({ items: [] });
    if (pathname === `/api/sources/${source.id}/reviews`) return json({ items: [] });
    if (pathname === `/api/sources/${source.id}/pii-scans`) return json({ items: [] });
    if (pathname === `/api/sources/${source.id}/documents`) return json({ items: [document] });
    if (pathname === `/api/sources/${source.id}/document-sample-generations`) return json({ items: [] });
    if (pathname === `/api/sources/${source.id}/document-quality-summary`) {
      return json({ source_id: source.id, rubric_version: "multidimensional-v1", review_count: 0, document_count: 0, legacy_review_count: 0 });
    }
    if (pathname === `/api/sources/${source.id}/document-review-history`) return json({ items: [] });
    if (pathname === `/api/sources/${source.id}/documents/claims` && request.method() === "POST") return json(claim);
    if (pathname === `/api/documents/${document.id}`) return json({ document, content: "Profil kampanyası tam metni." });
    if (pathname === `/api/documents/${document.id}/reviews`) return json({ items: [] });
    if (pathname === `/api/document-review-claims/${claim.claim_token}` && request.method() === "DELETE") return json({ released: 1 });
    return json({ error: { code: "not_mocked", message: pathname } }, 404);
  });

  await page.goto("/");
  await page.getByRole("button", { name: /Profile evidence E2E source/ }).click();

  const normalCard = page.getByTestId("source-profile-evidence");
  await expect(normalCard).toBeVisible();
  await expect(normalCard.getByRole("heading", { name: "Profil ve kanıt" })).toBeVisible();
  await expect(normalCard.getByText("translation · sürüm 1", { exact: true })).toBeVisible();
  await expect(normalCard.getByText("Alım sırasında atandı", { exact: true })).toBeVisible();
  await expect(normalCard.getByText("Model üretimi", { exact: true })).toBeVisible();
  await expect(normalCard.getByText("aaaaaaaa…aaaaaa", { exact: true })).toBeVisible();
  await expect(normalCard.getByLabel(`Profil yapılandırma SHA256: ${configSHA}`)).toHaveText("0123456789ab…89abcdef");
  await normalCard.getByRole("button", { name: "Profil yapılandırma SHA256 değerini kopyala" }).click();
  await expect(normalCard.getByRole("button", { name: "Profil yapılandırma SHA256 kopyalandı" })).toBeVisible();
  await normalCard.locator("summary").click();
  await expect(normalCard.getByText("declared_at_ingest", { exact: true })).toBeVisible();
  await expect(normalCard.getByText(productionRunID, { exact: true })).toBeVisible();
  await expect(normalCard.getByText("İnceleme kampanyası kimliği", { exact: true })).toHaveCount(0);

  await page.getByRole("button", { name: "İnceleme" }).click();
  await page.getByRole("button", { name: /Profile evidence E2E source/ }).click();
  const reviewCard = page.getByRole("complementary", { name: "Belge inceleme çalışma alanı" }).getByTestId("source-profile-evidence");
  await expect(reviewCard).toBeVisible();
  await expect(reviewCard).not.toHaveAttribute("open", "");
  await expect(reviewCard.getByRole("heading", { name: "Profil ve kanıt" })).toBeVisible();
  await expect(reviewCard.getByText("translation · sürüm 1", { exact: true })).toBeVisible();
  await expect(reviewCard.getByText("Model üretimi", { exact: true })).toBeHidden();
  if (testInfo.project.name === "desktop") {
    const compactBounds = await reviewCard.boundingBox();
    expect(compactBounds).not.toBeNull();
    expect(compactBounds!.height).toBeLessThanOrEqual(55);
  }
  await page.getByRole("button", { name: "Paketi al ve incelemeye başla" }).click();
  const documentDialog = page.getByRole("dialog", { name: "Belge örneği" });
  await expect(documentDialog).toBeVisible();
  await documentDialog.getByRole("button", { name: "Kapat", exact: true }).click();
  await expect(reviewCard.getByText(reviewCampaignID, { exact: true })).toBeHidden();
  await reviewCard.locator("summary").click();
  await expect(reviewCard.getByText("İnceleme kampanyası kimliği", { exact: true })).toBeVisible();
  await expect(reviewCard.getByText(reviewCampaignID, { exact: true })).toBeVisible();
});

test("release evidence distinguishes present, pre-registry, and pending without inventing hashes", async ({ page }) => {
  const releases = [
    release({}),
    release({
      id: "55555555-5555-4555-8555-555555555555",
      name: "Pre-registry release",
      version: "legacy",
      contract_snapshot_status: "absent_pre_registry",
      contract_snapshot_artifact_kind: undefined,
      contract_snapshot_sha256: undefined,
      implementation_bundle_sha256: undefined,
    }),
    release({
      id: "66666666-6666-4666-8666-666666666666",
      name: "Pending contract release",
      version: "draft",
      status: "draft",
      manifest_object_sha256: undefined,
      manifest_sha256: undefined,
      contract_snapshot_status: "pending",
      contract_snapshot_artifact_kind: undefined,
      contract_snapshot_sha256: undefined,
      implementation_bundle_sha256: undefined,
      frozen_by: undefined,
      frozen_at: undefined,
    }),
  ];
  await page.addInitScript((userID) => {
    window.localStorage.setItem(`derlem-welcome-dismissed-${userID}`, "1");
  }, user.id);
  await page.route("**/api/**", async (route) => {
    const { pathname } = new URL(route.request().url());
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (pathname === "/api/session/me") return json(user);
    if (pathname === "/api/sources") return json({ items: [] });
    if (pathname === "/api/releases") return json({ items: releases });
    return json({ error: { code: "not_mocked", message: pathname } }, 404);
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Sürümler" }).click();
  const card = page.getByTestId("release-profile-evidence");

  await expect(card.getByText("Hazır", { exact: true })).toBeVisible();
  await expect(card.getByText("present", { exact: true })).toBeVisible();
  await expect(card.getByLabel(`Sözleşme SHA256: ${contractSHA}`)).toHaveText("1234567890ab…90abcdef");
  await expect(card.getByLabel(`Uygulama paketi SHA256: ${implementationSHA}`)).toHaveText("fedcba098765…87654321");
  await card.getByRole("button", { name: "Sözleşme SHA256 değerini kopyala" }).click();
  await expect(card.getByRole("button", { name: "Sözleşme SHA256 kopyalandı" })).toBeVisible();

  await page.getByRole("button", { name: /Pre-registry release/ }).click();
  await expect(card.getByText("Profil kayıt sistemi öncesi", { exact: true })).toBeVisible();
  await expect(card.getByText("absent_pre_registry", { exact: true })).toBeVisible();
  await expect(card.getByRole("button", { name: /SHA256 değerini kopyala/ })).toHaveCount(0);
  await expect(card.getByLabel(/SHA256:/)).toHaveCount(0);

  await page.getByRole("button", { name: /Pending contract release/ }).click();
  await expect(card.getByText("Bekliyor", { exact: true })).toBeVisible();
  await expect(card.getByText("pending", { exact: true })).toBeVisible();
  await expect(card.getByRole("button", { name: /SHA256 değerini kopyala/ })).toHaveCount(0);
  await expect(card.getByLabel(/SHA256:/)).toHaveCount(0);
});
