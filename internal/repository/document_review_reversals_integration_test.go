package repository_test

import (
	"context"
	"errors"
	"fmt"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/celikbros/derlem/internal/database"
	"github.com/celikbros/derlem/internal/domain"
	"github.com/celikbros/derlem/internal/repository"
	"github.com/celikbros/derlem/internal/storage"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

func TestDocumentReviewReversalIsAppendOnlyIdempotentAndRestoresCounts(t *testing.T) {
	databaseURL := strings.TrimSpace(os.Getenv("DERLEM_TEST_DATABASE_URL"))
	if databaseURL == "" {
		t.Skip("DERLEM_TEST_DATABASE_URL is not set")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	t.Cleanup(cancel)
	adminPool, err := pgxpool.New(ctx, databaseURL)
	if err != nil {
		t.Fatalf("open admin pool: %v", err)
	}
	t.Cleanup(adminPool.Close)

	schemaName := fmt.Sprintf("derlem_review_reversal_test_%d", time.Now().UnixNano())
	schemaIdentifier := pgx.Identifier{schemaName}.Sanitize()
	// pgcrypto'yu izole semadan ONCE ve public'te olustur. Izole semanin icinde
	// olusursa (migration 000001 search_path'e kurar) test bitiminde
	// DROP SCHEMA ... CASCADE eklentiyi de siler; paralel kosan diger paketlerin
	// migration'lari o anda 000023/000024'un pgcrypto kontrolunde fail-loud duser.
	if _, err := adminPool.Exec(ctx, "CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public"); err != nil {
		t.Fatalf("ensure pgcrypto: %v", err)
	}

	if _, err := adminPool.Exec(ctx, "CREATE SCHEMA "+schemaIdentifier); err != nil {
		t.Fatalf("create test schema: %v", err)
	}
	t.Cleanup(func() {
		cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cleanupCancel()
		if _, err := adminPool.Exec(cleanupCtx, "DROP SCHEMA "+schemaIdentifier+" CASCADE"); err != nil {
			t.Errorf("drop test schema: %v", err)
		}
	})

	config, err := pgxpool.ParseConfig(databaseURL)
	if err != nil {
		t.Fatalf("parse test database URL: %v", err)
	}
	config.ConnConfig.RuntimeParams["search_path"] = schemaName
	config.MaxConns = 8
	config.MinConns = 0
	pool, err := pgxpool.NewWithConfig(ctx, config)
	if err != nil {
		t.Fatalf("open isolated pool: %v", err)
	}
	t.Cleanup(pool.Close)
	if err := database.Migrate(ctx, pool); err != nil {
		t.Fatalf("migrate isolated schema: %v", err)
	}

	var creatorID, reviewerID, adminID, sourceID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO users(email, password_hash, display_name)
		VALUES ('creator-reversal@example.test', 'test', 'Creator')
		RETURNING id::text
	`).Scan(&creatorID); err != nil {
		t.Fatalf("insert creator: %v", err)
	}
	if err := pool.QueryRow(ctx, `
		INSERT INTO users(email, password_hash, display_name)
		VALUES ('reviewer-reversal@example.test', 'test', 'Reviewer')
		RETURNING id::text
	`).Scan(&reviewerID); err != nil {
		t.Fatalf("insert reviewer: %v", err)
	}
	if err := pool.QueryRow(ctx, `
		INSERT INTO users(email, password_hash, display_name)
		VALUES ('admin-reversal@example.test', 'test', 'Admin')
		RETURNING id::text
	`).Scan(&adminID); err != nil {
		t.Fatalf("insert admin: %v", err)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
		VALUES (repeat('a', 64), 'objects/reversal-a', 4, 'text/plain')
	`); err != nil {
		t.Fatalf("insert object: %v", err)
	}
	if err := pool.QueryRow(ctx, `
		INSERT INTO sources(
			name, source_type, content_purpose, license, rights_status,
			language, domain, lineage_ref, object_sha256, created_by,
			document_sampling_status, sampled_document_count,
			document_sample_generation, document_sampling_method,
			approval_status
		)
		VALUES (
			'Reversal test', 'jsonl', 'pretrain', 'test', 'cleared',
			'tr', 'test', 'integration-test', repeat('a', 64), $1,
			'sampled', 4, 1, 'risk-stratified-v1', 'sampled_for_review'
		)
		RETURNING id::text
	`, creatorID).Scan(&sourceID); err != nil {
		t.Fatalf("insert source: %v", err)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO document_sample_generations(
			source_id, generation, source_sha256, sampling_method, status, sample_count
		)
		VALUES ($1, 1, repeat('a', 64), 'risk-stratified-v1', 'active', 4)
	`, sourceID); err != nil {
		t.Fatalf("insert sample generation: %v", err)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO documents(
			source_id, source_ordinal, current_object_sha256, text_preview,
			byte_size, char_count, risk_score, sample_generation
		)
		SELECT $1, ordinal, repeat('a', 64), 'test document', 4, 4, 0, 1
		FROM generate_series(1, 4) AS ordinal
	`, sourceID); err != nil {
		t.Fatalf("insert documents: %v", err)
	}
	insertActiveDocumentSampleMemberships(t, ctx, pool, sourceID)

	documents := repository.NewDocuments(pool)
	claim, err := documents.ClaimForReview(ctx, sourceID, reviewerID, 4, false)
	if err != nil {
		t.Fatalf("claim documents: %v", err)
	}
	if len(claim.Documents) != 4 {
		t.Fatalf("claim document count = %d, want 4", len(claim.Documents))
	}
	byOrdinal := make(map[int64]domain.Document, 4)
	for _, document := range claim.Documents {
		byOrdinal[document.SourceOrdinal] = document
	}

	approvedInput := domain.ReviewDocumentInput{
		DocumentQualityScores: domain.DocumentQualityScores{
			QualityScore: 5, LanguageQualityScore: 5, CoherenceScore: 5,
			InformationDensityScore: 5, CleanlinessScore: 5,
		},
		Decision: "approved", DocumentVersion: 1, ClaimToken: claim.ClaimToken,
	}
	_, _, firstReview, err := documents.Review(ctx, byOrdinal[1].ID, approvedInput, reviewerID, false)
	if err != nil {
		t.Fatalf("review first document: %v", err)
	}
	_, _, secondReview, err := documents.Review(ctx, byOrdinal[2].ID, approvedInput, reviewerID, false)
	if err != nil {
		t.Fatalf("review second document: %v", err)
	}
	rejectionReason := "spam"
	rejectedInput := approvedInput
	rejectedInput.Decision = "rejected"
	rejectedInput.Reason = &rejectionReason
	_, _, thirdReview, err := documents.Review(ctx, byOrdinal[3].ID, rejectedInput, reviewerID, false)
	if err != nil {
		t.Fatalf("review third document: %v", err)
	}
	assertSourceReviewCounts(t, ctx, pool, sourceID, 3, 2, 1, "sampled_for_review")
	assertActiveReviewCount(t, ctx, pool, 3)
	assertClaimPreserved(t, ctx, pool, byOrdinal[4].ID, claim.ClaimToken, reviewerID)

	reversalInput := domain.ReverseDocumentReviewInput{Reason: "accidental approval"}
	type reversalCallResult struct {
		reviewID string
		result   domain.ReverseDocumentReviewResult
		err      error
	}
	reversalResults := make(chan reversalCallResult, 2)
	for _, reviewID := range []string{firstReview.ID, secondReview.ID} {
		go func(reviewID string) {
			result, err := documents.ReverseReview(ctx, reviewID, reversalInput, reviewerID, false)
			reversalResults <- reversalCallResult{reviewID: reviewID, result: result, err: err}
		}(reviewID)
	}
	var firstResult, secondResult domain.ReverseDocumentReviewResult
	for range 2 {
		call := <-reversalResults
		if call.err != nil {
			t.Fatalf("reverse review %s: %v", call.reviewID, call.err)
		}
		switch call.reviewID {
		case firstReview.ID:
			firstResult = call.result
		case secondReview.ID:
			secondResult = call.result
		default:
			t.Fatalf("unexpected reversed review %s", call.reviewID)
		}
	}
	if firstResult.AlreadyReversed || firstResult.Document.Status != "sampled" {
		t.Fatalf("unexpected first reversal result: %#v", firstResult)
	}
	if secondResult.AlreadyReversed || secondResult.Document.Status != "sampled" {
		t.Fatalf("unexpected second reversal result: %#v", secondResult)
	}
	assertSourceReviewCounts(t, ctx, pool, sourceID, 1, 0, 1, "sampled_for_review")
	assertActiveReviewCount(t, ctx, pool, 1)
	assertClaimPreserved(t, ctx, pool, byOrdinal[4].ID, claim.ClaimToken, reviewerID)

	idempotent, err := documents.ReverseReview(
		ctx, firstReview.ID,
		domain.ReverseDocumentReviewInput{Reason: "a later duplicate request"},
		reviewerID, false,
	)
	if err != nil {
		t.Fatalf("repeat first reversal: %v", err)
	}
	if !idempotent.AlreadyReversed || idempotent.Reversal.ID != firstResult.Reversal.ID ||
		idempotent.Reversal.Reason != reversalInput.Reason {
		t.Fatalf("repeat was not idempotent: %#v", idempotent)
	}
	assertReversalAndAuditCounts(t, ctx, pool, 2, 2)
	assertSourceReviewCounts(t, ctx, pool, sourceID, 1, 0, 1, "sampled_for_review")

	if _, err := documents.ReverseReview(ctx, thirdReview.ID, reversalInput, adminID, false); !errors.Is(err, repository.ErrForbidden) {
		t.Fatalf("reverse another review without admin permission error = %v, want ErrForbidden", err)
	}
	if _, err := documents.ReverseReview(ctx, thirdReview.ID, reversalInput, adminID, true); err != nil {
		t.Fatalf("admin reverse third review: %v", err)
	}
	assertReversalAndAuditCounts(t, ctx, pool, 3, 3)
	assertActiveReviewCount(t, ctx, pool, 0)
	assertClaimPreserved(t, ctx, pool, byOrdinal[4].ID, claim.ClaimToken, reviewerID)
	if err := documents.ReleaseReviewClaim(ctx, claim.ClaimToken, reviewerID); err != nil {
		t.Fatalf("release remaining package before claiming restored document: %v", err)
	}

	reviewAgainClaim, err := documents.ClaimForReview(ctx, sourceID, reviewerID, 1, false)
	if err != nil {
		t.Fatalf("claim restored document: %v", err)
	}
	if len(reviewAgainClaim.Documents) != 1 || reviewAgainClaim.Documents[0].ID != byOrdinal[1].ID {
		t.Fatalf("restored document was not claimable again: %#v", reviewAgainClaim.Documents)
	}
	rejectedInput.ClaimToken = reviewAgainClaim.ClaimToken
	_, _, replacementReview, err := documents.Review(ctx, byOrdinal[1].ID, rejectedInput, reviewerID, false)
	if err != nil {
		t.Fatalf("review restored version again: %v", err)
	}
	assertSourceReviewCounts(t, ctx, pool, sourceID, 1, 0, 1, "sampled_for_review")
	assertActiveReviewCount(t, ctx, pool, 1)

	history, err := documents.ListReviews(ctx, byOrdinal[1].ID)
	if err != nil {
		t.Fatalf("list review history: %v", err)
	}
	if len(history) != 2 || history[0].Reversal != nil || history[1].Reversal == nil {
		t.Fatalf("review history does not distinguish effective and reversed records: %#v", history)
	}
	reviewerHistory, err := documents.ListReviewHistory(ctx, sourceID, reviewerID)
	if err != nil {
		t.Fatalf("list reviewer-scoped history: %v", err)
	}
	if len(reviewerHistory) != 3 {
		t.Fatalf("reviewer history item count = %d, want 3: %#v", len(reviewerHistory), reviewerHistory)
	}
	historyByDocument := make(map[string]domain.DocumentReviewHistoryItem, len(reviewerHistory))
	for _, item := range reviewerHistory {
		historyByDocument[item.Document.ID] = item
		for _, review := range item.Reviews {
			if review.ReviewerID != reviewerID {
				t.Fatalf("reviewer history leaked review from %s: %#v", review.ReviewerID, review)
			}
		}
	}
	firstHistory := historyByDocument[byOrdinal[1].ID]
	if len(firstHistory.Reviews) != 2 ||
		firstHistory.Reviews[0].ID != replacementReview.ID ||
		firstHistory.Reviews[0].Decision != "rejected" ||
		firstHistory.Reviews[0].Reversal != nil ||
		firstHistory.Reviews[1].ID != firstReview.ID ||
		firstHistory.Reviews[1].Reversal == nil {
		t.Fatalf("first document history chain = %#v", firstHistory.Reviews)
	}
	for _, ordinal := range []int64{2, 3} {
		item := historyByDocument[byOrdinal[ordinal].ID]
		if len(item.Reviews) != 1 || item.Reviews[0].Reversal == nil {
			t.Fatalf("reversed document %d missing from reviewer history: %#v", ordinal, item)
		}
	}
	adminHistory, err := documents.ListReviewHistory(ctx, sourceID, adminID)
	if err != nil {
		t.Fatalf("list admin reviewer history: %v", err)
	}
	if len(adminHistory) != 0 {
		t.Fatalf("reversing another review must not make it the admin's authored review: %#v", adminHistory)
	}
	summary, err := documents.QualitySummary(ctx, sourceID)
	if err != nil {
		t.Fatalf("quality summary: %v", err)
	}
	if summary.ReviewCount != 1 || summary.DocumentCount != 1 {
		t.Fatalf("quality summary counted reversed reviews: %#v", summary)
	}

	editReason := "conflict test"
	if _, err := documents.UpdateContent(
		ctx, byOrdinal[1].ID, 1,
		storage.Object{SHA256: strings.Repeat("b", 64), StorageKey: "objects/reversal-b", ByteSize: 5},
		"edited", 5, &editReason, adminID,
	); err != nil {
		t.Fatalf("edit reviewed document: %v", err)
	}
	if _, err := documents.ReverseReview(ctx, replacementReview.ID, reversalInput, reviewerID, false); !errors.Is(err, repository.ErrConflict) {
		t.Fatalf("reverse stale review error = %v, want ErrConflict", err)
	}

	if _, err := pool.Exec(ctx, `
		UPDATE document_review_reversals SET reason = 'tampered' WHERE id = $1
	`, firstResult.Reversal.ID); err == nil {
		t.Fatal("append-only reversal record accepted UPDATE")
	}
	if _, err := pool.Exec(ctx, `
		DELETE FROM document_review_reversals WHERE id = $1
	`, firstResult.Reversal.ID); err == nil {
		t.Fatal("append-only reversal record accepted DELETE")
	}
}

func assertSourceReviewCounts(
	t *testing.T,
	ctx context.Context,
	pool *pgxpool.Pool,
	sourceID string,
	wantReviewed, wantApproved, wantFlagged int64,
	wantStatus string,
) {
	t.Helper()
	var reviewed, approved, flagged int64
	var status string
	if err := pool.QueryRow(ctx, `
		SELECT reviewed_document_count, approved_document_count,
			flagged_document_count, approval_status
		FROM sources WHERE id = $1
	`, sourceID).Scan(&reviewed, &approved, &flagged, &status); err != nil {
		t.Fatalf("read source counters: %v", err)
	}
	if reviewed != wantReviewed || approved != wantApproved || flagged != wantFlagged || status != wantStatus {
		t.Fatalf(
			"source counters/status = %d/%d/%d %s, want %d/%d/%d %s",
			reviewed, approved, flagged, status,
			wantReviewed, wantApproved, wantFlagged, wantStatus,
		)
	}
}

func assertClaimPreserved(
	t *testing.T,
	ctx context.Context,
	pool *pgxpool.Pool,
	documentID, wantToken, wantReviewer string,
) {
	t.Helper()
	var token, reviewer string
	if err := pool.QueryRow(ctx, `
		SELECT claim_token::text, reviewer_id::text
		FROM document_review_claims WHERE document_id = $1
	`, documentID).Scan(&token, &reviewer); err != nil {
		t.Fatalf("read preserved claim: %v", err)
	}
	if token != wantToken || reviewer != wantReviewer {
		t.Fatalf("claim changed: token=%s reviewer=%s", token, reviewer)
	}
}

func assertReversalAndAuditCounts(
	t *testing.T,
	ctx context.Context,
	pool *pgxpool.Pool,
	wantReversals, wantAudits int,
) {
	t.Helper()
	var reversals, audits int
	if err := pool.QueryRow(ctx, "SELECT count(*) FROM document_review_reversals").Scan(&reversals); err != nil {
		t.Fatalf("count reversals: %v", err)
	}
	if err := pool.QueryRow(ctx, `
		SELECT count(*) FROM audit_events WHERE action = 'document.review_reversed'
	`).Scan(&audits); err != nil {
		t.Fatalf("count reversal audits: %v", err)
	}
	if reversals != wantReversals || audits != wantAudits {
		t.Fatalf("reversal/audit counts = %d/%d, want %d/%d", reversals, audits, wantReversals, wantAudits)
	}
}

func assertActiveReviewCount(t *testing.T, ctx context.Context, pool *pgxpool.Pool, want int) {
	t.Helper()
	var got int
	if err := pool.QueryRow(ctx, "SELECT count(*) FROM active_document_reviews").Scan(&got); err != nil {
		t.Fatalf("count active reviews: %v", err)
	}
	if got != want {
		t.Fatalf("active review count = %d, want %d", got, want)
	}
}
