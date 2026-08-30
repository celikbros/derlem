import { expect, test } from "@playwright/test";

import type { Document, DocumentReview, Source, User } from "../../lib/types";

const now = "2026-08-21T12:00:00Z";
const reviewer: User = {
  id: "11111111-1111-4111-8111-111111111111",
  email: "moderator@derlem.local",
  roles: ["moderator"],
};
const source: Source = {
  id: "22222222-2222-4222-8222-222222222222",
  name: "Reviewer history E2E source",
  source_type: "jsonl",
  content_purpose: "pretrain",
  license: "test",
  rights_status: "cleared",
  language: "tr",
  domain: "test",
  license_evidence_ref: "test-evidence",
  lineage_ref: "e2e",
  data_profile_key: "legacy-auto",
  data_profile_version: "1",
  profile_config_artifact_kind: "profile_config",
  profile_config_sha256: "c".repeat(64),
  profile_assignment_reason: "backfilled",
  profile_assigned_at: now,
  data_origin: "unknown",
  source_metadata: {},
  object_sha256: "a".repeat(64),
  byte_size: 128,
  line_count: 2,
  document_count: 2,
  document_sampling_status: "sampled",
  document_sample_generation: 1,
  document_sampling_method: "risk-stratified-sha256-v1",
  sampled_document_count: 2,
  reviewed_document_count: 1,
  approved_document_count: 1,
  flagged_document_count: 0,
  pii_status: "clear",
  duplicate_status: "unique",
  normalized_dedup_status: "unique",
  normalized_duplicate_count: 0,
  normalized_duplicate_source_count: 0,
  risk_level: "low",
  approval_status: "sampled_for_review",
  version: 3,
  created_by: "33333333-3333-4333-8333-333333333333",
  created_at: now,
  updated_at: now,
};
const pendingDocument: Document = {
  id: "44444444-4444-4444-8444-444444444444",
  source_id: source.id,
  source_ordinal: 8,
  current_object_sha256: "b".repeat(64),
  text_preview: "Yeni pakete girecek riskli örnek",
  byte_size: 64,
  char_count: 64,
  status: "sampled",
  current_version: 1,
  sampling_method: "risk-stratified-sha256-v1",
  risk_score: 8,
  risk_reasons: ["long_text"],
  is_active: true,
  sample_generation: 1,
  created_at: now,
  updated_at: now,
};
const reviewedDocument: Document = {
  ...pendingDocument,
  id: "55555555-5555-4555-8555-555555555555",
  source_ordinal: 21,
  text_preview: "Daha önce onayladığım örnek",
  status: "approved",
  risk_score: 0,
  risk_reasons: [],
};
const review: DocumentReview = {
  id: "66666666-6666-4666-8666-666666666666",
  document_id: reviewedDocument.id,
  reviewer_id: reviewer.id,
  decision: "approved",
  rubric_version: "multidimensional-v1",
  quality_score: 4,
  language_quality_score: 4,
  coherence_score: 4,
  information_density_score: 4,
  cleanliness_score: 4,
  document_version: 1,
  object_sha256: reviewedDocument.current_object_sha256,
  context: {},
  created_at: now,
};

test("review workspace separates a new package from the reviewer's append-only history", async ({ page }) => {
  await page.addInitScript((reviewerID) => {
    window.localStorage.setItem(`derlem-welcome-dismissed-${reviewerID}`, "1");
  }, reviewer.id);
  await page.route("**/api/**", async (route) => {
    const { pathname } = new URL(route.request().url());
    const json = (body: unknown, status = 200) => route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
    if (pathname === "/api/session/me") return json(reviewer);
    if (pathname === "/api/sources") return json({ items: [source] });
    if (pathname === `/api/sources/${source.id}/reviews`) return json({ items: [] });
    if (pathname === `/api/sources/${source.id}/pii-scans`) return json({ items: [] });
    if (pathname === `/api/sources/${source.id}/documents`) {
      return json({ items: [pendingDocument, reviewedDocument] });
    }
    if (pathname === `/api/sources/${source.id}/document-sample-generations`) {
      return json({ items: [] });
    }
    if (pathname === `/api/sources/${source.id}/document-quality-summary`) {
      return json({
        source_id: source.id,
        rubric_version: "multidimensional-v1",
        review_count: 1,
        document_count: 1,
        legacy_review_count: 0,
      });
    }
    if (pathname === `/api/sources/${source.id}/document-review-history`) {
      return json({ items: [{ document: reviewedDocument, reviews: [review] }] });
    }
    if (pathname === `/api/documents/${reviewedDocument.id}`) {
      return json({ document: reviewedDocument, content: "Tam metin." });
    }
    if (pathname === `/api/documents/${reviewedDocument.id}/reviews`) {
      return json({ items: [review] });
    }
    return json({ error: { code: "not_mocked", message: pathname } }, 404);
  });

  await page.goto("/");
  const sourceButton = page.getByRole("button", { name: /Reviewer history E2E source/ });
  await expect(sourceButton).toBeVisible();
  await sourceButton.click();

  const workspace = page.getByRole("complementary", { name: "Belge inceleme çalışma alanı" });
  await expect(workspace.getByRole("heading", { name: "Yeni inceleme paketi" })).toBeVisible();
  await expect(workspace.getByText("Risk puanı yüksek olan önce gelir")).toBeVisible();

  const history = workspace.getByTestId("document-review-history");
  await expect(history.getByRole("heading", { name: "İncelediklerim" })).toBeVisible();
  await expect(history.getByRole("button", { name: "Tümü 1" })).toBeVisible();
  await expect(history.getByRole("button", { name: "Onaylı 1" })).toBeVisible();
  await expect(history.getByRole("button", { name: "Reddedildi 0" })).toBeVisible();
  await expect(history.getByRole("button", { name: "Hassas 0" })).toBeVisible();
  await expect(history.getByRole("button", { name: "Geri alındı 0" })).toBeVisible();

  await history.getByRole("button", { name: /Daha önce onayladığım örnek/ }).click();
  const dialog = page.getByRole("dialog", { name: "Belge örneği" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Kararı geri al" })).toBeVisible();
});
