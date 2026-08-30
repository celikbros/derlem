import { expect, test } from "@playwright/test";

import type {
  Document,
  DocumentReview,
  DocumentReviewReversal,
  Source,
  User,
} from "../../lib/types";

const now = "2026-08-22T09:00:00.000Z";
const sourceID = "22222222-2222-4222-8222-222222222222";
const documentID = "44444444-4444-4444-8444-444444444444";
const campaignID = "77777777-7777-4777-8777-777777777777";

const reviewer: User = {
  id: "11111111-1111-4111-8111-111111111111",
  email: "moderator@derlem.local",
  roles: ["moderator"],
};

test("keeps every decision while reject, reverse, approve, reverse, and reject run again", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "The state transition only needs one browser project");

  let source: Source = {
    id: sourceID,
    name: "Disposable review state machine source",
    source_type: "jsonl",
    content_purpose: "pretrain",
    license: "internal-test",
    rights_status: "cleared",
    language: "tr",
    domain: "e2e",
    license_evidence_ref: "e2e/mock-only",
    lineage_ref: "mock-only",
    data_profile_key: "legacy-auto",
    data_profile_version: "1",
    profile_config_artifact_kind: "profile_config",
    profile_config_sha256: "c".repeat(64),
    profile_assignment_reason: "test fixture",
    profile_assigned_at: now,
    data_origin: "human",
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
    created_by: "33333333-3333-4333-8333-333333333333",
    created_at: now,
    updated_at: now,
  };
  let document: Document = {
    id: documentID,
    source_id: sourceID,
    source_ordinal: 1,
    current_object_sha256: "b".repeat(64),
    text_preview: "Kabul state machine belgesi",
    byte_size: 76,
    char_count: 76,
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
  const reviews: DocumentReview[] = [];
  let claimSequence = 0;
  let activeClaimToken: string | null = null;
  let eventSequence = 0;

  const nextTimestamp = () => {
    eventSequence += 1;
    return new Date(Date.parse(now) + eventSequence * 1_000).toISOString();
  };
  const syncSourceCounters = () => {
    const effective = reviews.find((review) => !review.reversal);
    source = {
      ...source,
      reviewed_document_count: effective ? 1 : 0,
      approved_document_count: effective?.decision === "approved" ? 1 : 0,
      flagged_document_count: effective && effective.decision !== "approved" ? 1 : 0,
      version: source.version + 1,
      updated_at: nextTimestamp(),
    };
  };
  const effectiveReviews = () => reviews.filter((review) => !review.reversal);
  const qualitySummary = () => {
    const effective = effectiveReviews();
    const average = (field: keyof Pick<DocumentReview,
      "quality_score" | "language_quality_score" | "coherence_score" |
      "information_density_score" | "cleanliness_score"
    >) => effective.length === 0
      ? undefined
      : effective.reduce((total, review) => total + Number(review[field] ?? 0), 0) / effective.length;
    return {
      source_id: sourceID,
      rubric_version: "multidimensional-v1",
      review_count: effective.length,
      document_count: effective.length === 0 ? 0 : 1,
      legacy_review_count: 0,
      average_quality_score: average("quality_score"),
      average_language_quality_score: average("language_quality_score"),
      average_coherence_score: average("coherence_score"),
      average_information_density_score: average("information_density_score"),
      average_cleanliness_score: average("cleanliness_score"),
    };
  };

  await page.addInitScript((reviewerID) => {
    window.localStorage.setItem(`derlem-welcome-dismissed-${reviewerID}`, "1");
  }, reviewer.id);
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const { pathname } = new URL(request.url());
    const json = (body: unknown, status = 200) => route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(body),
    });

    if (pathname === "/api/session/me") return json(reviewer);
    if (pathname === "/api/sources") return json({ items: [source] });
    if (pathname === `/api/sources/${sourceID}/reviews`) return json({ items: [] });
    if (pathname === `/api/sources/${sourceID}/pii-scans`) return json({ items: [] });
    if (pathname === `/api/sources/${sourceID}/documents`) return json({ items: [document] });
    if (pathname === `/api/sources/${sourceID}/document-sample-generations`) {
      return json({ items: [] });
    }
    if (pathname === `/api/sources/${sourceID}/document-quality-summary`) {
      return json(qualitySummary());
    }
    if (pathname === `/api/sources/${sourceID}/document-review-history`) {
      return json({ items: reviews.length === 0 ? [] : [{ document, reviews }] });
    }
    if (pathname === `/api/sources/${sourceID}/documents/claims` && request.method() === "POST") {
      if (document.status !== "sampled" && document.status !== "edited") {
        return json({
          claim_token: "00000000-0000-4000-8000-000000000000",
          review_campaign_id: campaignID,
          expires_at: "2026-08-22T09:15:00.000Z",
          documents: [],
          resumed: false,
        });
      }
      claimSequence += 1;
      activeClaimToken = `00000000-0000-4000-8000-${String(claimSequence).padStart(12, "0")}`;
      return json({
        claim_token: activeClaimToken,
        review_campaign_id: campaignID,
        expires_at: "2026-08-22T09:15:00.000Z",
        documents: [document],
        resumed: false,
      }, 201);
    }
    if (pathname === `/api/documents/${documentID}`) {
      return json({
        document,
        content: "Bu yalnız bellek içinde kullanılan, gerçek veriye dokunmayan kabul testi belgesidir.",
      });
    }
    if (pathname === `/api/documents/${documentID}/reviews` && request.method() === "GET") {
      return json({ items: reviews });
    }
    if (pathname === `/api/documents/${documentID}/reviews` && request.method() === "POST") {
      const input = request.postDataJSON() as {
        claim_token: string;
        decision: DocumentReview["decision"];
        reason?: string;
        quality_score: number;
        language_quality_score: number;
        coherence_score: number;
        information_density_score: number;
        cleanliness_score: number;
        document_version: number;
      };
      if (input.claim_token !== activeClaimToken || effectiveReviews().length !== 0) {
        return json({ error: { code: "invalid_mock_transition", message: "Geçersiz mock karar geçişi." } }, 409);
      }
      const review: DocumentReview = {
        id: `review-${reviews.length + 1}`,
        document_id: documentID,
        reviewer_id: reviewer.id,
        review_campaign_id: campaignID,
        decision: input.decision,
        reason: input.reason,
        rubric_version: "multidimensional-v1",
        quality_score: input.quality_score,
        language_quality_score: input.language_quality_score,
        coherence_score: input.coherence_score,
        information_density_score: input.information_density_score,
        cleanliness_score: input.cleanliness_score,
        document_version: input.document_version,
        object_sha256: document.current_object_sha256,
        context: { previous_status: document.status },
        created_at: nextTimestamp(),
      };
      reviews.unshift(review);
      document = {
        ...document,
        status: input.decision === "approved"
          ? "approved"
          : input.decision === "rejected" ? "rejected" : "sensitive_review",
        updated_at: nextTimestamp(),
      };
      activeClaimToken = null;
      syncSourceCounters();
      return json({ source, document, review }, 201);
    }

    const reversalMatch = pathname.match(/^\/api\/document-reviews\/([^/]+)\/reversal$/u);
    if (reversalMatch && request.method() === "POST") {
      const review = reviews.find((item) => item.id === reversalMatch[1]);
      if (!review) {
        return json({ error: { code: "not_found", message: "Mock karar bulunamadı." } }, 404);
      }
      if (review.reversal) {
        return json({
          source,
          document,
          review,
          reversal: review.reversal,
          already_reversed: true,
        });
      }
      if (effectiveReviews().length !== 1 || effectiveReviews()[0].id !== review.id) {
        return json({ error: { code: "conflict", message: "Mock karar artık etkin değil." } }, 409);
      }
      const input = request.postDataJSON() as { reason: string };
      const reversal: DocumentReviewReversal = {
        id: `reversal-${reviews.filter((item) => item.reversal).length + 1}`,
        review_id: review.id,
        reversed_by: reviewer.id,
        reason: input.reason,
        restored_document_status: "sampled",
        created_at: nextTimestamp(),
      };
      review.reversal = reversal;
      document = { ...document, status: "sampled", updated_at: nextTimestamp() };
      syncSourceCounters();
      return json({
        source,
        document,
        review,
        reversal,
        already_reversed: false,
      }, 201);
    }

    return json({ error: { code: "not_mocked", message: pathname } }, 404);
  });

  let reversalPromptCount = 0;
  page.on("dialog", async (dialog) => {
    if (dialog.type() === "prompt") {
      reversalPromptCount += 1;
      await dialog.accept(reversalPromptCount === 1
        ? "Birinci karar düzeltmesi"
        : "İkinci karar düzeltmesi");
      return;
    }
    await dialog.accept();
  });

  await page.goto("/");
  await page.getByRole("button", { name: /Disposable review state machine source/ }).click();

  const workspace = page.getByRole("complementary", { name: "Belge inceleme çalışma alanı" });
  const history = workspace.getByTestId("document-review-history");
  const claim = workspace.getByRole("button", { name: "Paketi al ve incelemeye başla" });

  await claim.click();
  let dialog = page.getByRole("dialog", { name: "Belge örneği" });
  await dialog.getByRole("button", { name: "Anlamsız / yetersiz içerik" }).click();
  await dialog.getByLabel("Karar gerekçesi").fill("İlk ret kararı");
  await dialog.getByRole("button", { name: "Reddet", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await expect(history.getByRole("button", { name: "Reddedildi 1" })).toBeVisible();

  await history.getByRole("button", { name: /Kabul state machine belgesi/ }).click();
  dialog = page.getByRole("dialog", { name: "Belge örneği" });
  await dialog.getByRole("button", { name: "Kararı geri al" }).click();
  await expect(dialog.getByText("Geri alındı", { exact: true })).toHaveCount(1);
  await dialog.getByRole("button", { name: "Pencereyi kapat" }).click();
  await expect(history.getByRole("button", { name: "Geri alındı 1" })).toBeVisible();

  await claim.click();
  dialog = page.getByRole("dialog", { name: "Belge örneği" });
  for (const label of ["Genel", "Dil", "Tutarlılık", "Bilgi", "Temizlik"]) {
    await dialog.getByLabel(`${label} kalite puanı`).fill("4");
  }
  await dialog.getByRole("button", { name: "Onayla", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await expect(history.getByRole("button", { name: "Onaylı 1" })).toBeVisible();

  await history.getByRole("button", { name: /Kabul state machine belgesi/ }).click();
  dialog = page.getByRole("dialog", { name: "Belge örneği" });
  await dialog.getByRole("button", { name: "Kararı geri al" }).click();
  await expect(dialog.getByText("Geri alındı", { exact: true })).toHaveCount(2);
  await dialog.getByRole("button", { name: "Pencereyi kapat" }).click();
  await expect(history.getByRole("button", { name: "Geri alındı 1" })).toBeVisible();

  await claim.click();
  dialog = page.getByRole("dialog", { name: "Belge örneği" });
  await dialog.getByRole("button", { name: "Aşırı tekrar / hashtag" }).click();
  await dialog.getByLabel("Karar gerekçesi").fill("Son ret kararı");
  await dialog.getByRole("button", { name: "Reddet", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await expect(history.getByRole("button", { name: "Reddedildi 1" })).toBeVisible();

  await history.getByRole("button", { name: /Kabul state machine belgesi/ }).click();
  dialog = page.getByRole("dialog", { name: "Belge örneği" });
  const visibleHistory = dialog.locator(".document-review-history > div");
  await expect(visibleHistory).toHaveCount(3);
  await expect(dialog.getByText("Geri alındı", { exact: true })).toHaveCount(2);
  await expect(dialog.getByText("İlk ret kararı", { exact: true })).toBeVisible();
  await expect(dialog.getByText("Geri alma gerekçesi: Birinci karar düzeltmesi", { exact: true })).toBeVisible();
  await expect(dialog.getByText("Geri alma gerekçesi: İkinci karar düzeltmesi", { exact: true })).toBeVisible();
  await expect(dialog.getByText("Son ret kararı", { exact: true })).toBeVisible();

  expect(reviews).toHaveLength(3);
  expect(reviews.filter((review) => review.reversal)).toHaveLength(2);
  expect(effectiveReviews()).toHaveLength(1);
  expect(effectiveReviews()[0].decision).toBe("rejected");
  expect(document.status).toBe("rejected");
});
