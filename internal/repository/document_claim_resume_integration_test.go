package repository_test

import (
	"context"
	"fmt"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/celikbros/derlem/internal/database"
	"github.com/celikbros/derlem/internal/domain"
	"github.com/celikbros/derlem/internal/repository"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

func TestDocumentReviewClaimResumesAndConsolidatesActivePackages(t *testing.T) {
	ctx, pool, sourceID, reviewerIDs := setupDocumentClaimResumeFixture(t, 8, 2)
	documents := repository.NewDocuments(pool)
	reviewerID := reviewerIDs[0]

	first, err := documents.ClaimForReview(ctx, sourceID, reviewerID, 3, false)
	if err != nil {
		t.Fatalf("first claim: %v", err)
	}
	if first.Resumed {
		t.Fatal("first claim unexpectedly marked resumed")
	}
	assertResumeClaimOrdinals(t, first, []int64{2, 3, 5})

	resumed, err := documents.ClaimForReview(ctx, sourceID, reviewerID, 1, false)
	if err != nil {
		t.Fatalf("resume claim: %v", err)
	}
	if !resumed.Resumed {
		t.Fatal("second claim was not marked resumed")
	}
	if resumed.ClaimToken != first.ClaimToken {
		t.Fatalf("resumed token = %s, want %s", resumed.ClaimToken, first.ClaimToken)
	}
	assertResumeClaimOrdinals(t, resumed, []int64{2, 3, 5})
	if resumed.ExpiresAt.Before(first.ExpiresAt) {
		t.Fatalf("resumed expiry %s is before first expiry %s", resumed.ExpiresAt, first.ExpiresAt)
	}

	const newerToken = "00000000-0000-4000-8000-000000000001"
	if _, err := pool.Exec(ctx, `
		UPDATE document_review_claims
		SET claimed_at = now() - interval '2 minutes',
			expires_at = now() + interval '10 minutes'
		WHERE reviewer_id = $1::uuid AND claim_token = $2::uuid
	`, reviewerID, first.ClaimToken); err != nil {
		t.Fatalf("age original package: %v", err)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO document_review_claims(
			document_id, reviewer_id, claim_token, document_version,
			claimed_at, expires_at, review_campaign_id
		)
		SELECT id, $2::uuid, $3::uuid, current_version,
			now() - interval '1 minute', now() + interval '10 minutes', $4::uuid
		FROM documents
		WHERE source_id = $1::uuid AND source_ordinal IN (6, 7)
	`, sourceID, reviewerID, newerToken, first.ReviewCampaignID); err != nil {
		t.Fatalf("insert duplicate active package: %v", err)
	}

	consolidated, err := documents.ClaimForReview(ctx, sourceID, reviewerID, 3, false)
	if err != nil {
		t.Fatalf("resume newest package: %v", err)
	}
	if !consolidated.Resumed {
		t.Fatal("consolidated package was not marked resumed")
	}
	if consolidated.ClaimToken != newerToken {
		t.Fatalf("consolidated token = %s, want newest %s", consolidated.ClaimToken, newerToken)
	}
	assertResumeClaimOrdinals(t, consolidated, []int64{6, 7})

	var activeCount, tokenCount, releasedCount int
	if err := pool.QueryRow(ctx, `
		SELECT count(*), count(DISTINCT claim.claim_token)
		FROM document_review_claims AS claim
		JOIN documents AS document ON document.id = claim.document_id
		WHERE document.source_id = $1::uuid
		  AND claim.reviewer_id = $2::uuid
		  AND claim.expires_at > now()
	`, sourceID, reviewerID).Scan(&activeCount, &tokenCount); err != nil {
		t.Fatalf("count consolidated claims: %v", err)
	}
	if activeCount != 2 || tokenCount != 1 {
		t.Fatalf("active claims = %d across %d tokens, want 2 across 1", activeCount, tokenCount)
	}
	if err := pool.QueryRow(ctx, `
		SELECT (details->>'released_duplicate_claim_count')::int
		FROM audit_events
		WHERE actor_id = $1::uuid
		  AND entity_id = $2::uuid
		  AND action = 'documents.review_claim_resumed'
		ORDER BY created_at DESC
		LIMIT 1
	`, reviewerID, sourceID).Scan(&releasedCount); err != nil {
		t.Fatalf("read resume audit: %v", err)
	}
	if releasedCount != 3 {
		t.Fatalf("released duplicate claim count = %d, want 3", releasedCount)
	}

	var leakedTokenCount int
	if err := pool.QueryRow(ctx, `
		SELECT count(*)
		FROM audit_events
		WHERE action IN ('documents.review_claimed', 'documents.review_claim_resumed')
		  AND details::text LIKE '%' || $1 || '%'
	`, newerToken).Scan(&leakedTokenCount); err != nil {
		t.Fatalf("scan audit token leakage: %v", err)
	}
	if leakedTokenCount != 0 {
		t.Fatalf("claim token leaked into audit details")
	}

	nextReviewerClaim, err := documents.ClaimForReview(ctx, sourceID, reviewerIDs[1], 3, false)
	if err != nil {
		t.Fatalf("claim released documents as another reviewer: %v", err)
	}
	assertResumeClaimOrdinals(t, nextReviewerClaim, []int64{2, 3, 5})
}

func TestConcurrentAcquireBySameReviewerReturnsOnePackage(t *testing.T) {
	ctx, pool, sourceID, reviewerIDs := setupDocumentClaimResumeFixture(t, 8, 1)
	documents := repository.NewDocuments(pool)

	start := make(chan struct{})
	results := make(chan documentClaimResumeResult, 2)
	for range 2 {
		go func() {
			<-start
			claim, err := documents.ClaimForReview(ctx, sourceID, reviewerIDs[0], 4, false)
			results <- documentClaimResumeResult{claim: claim, err: err}
		}()
	}
	close(start)
	first := <-results
	second := <-results
	for index, result := range []documentClaimResumeResult{first, second} {
		if result.err != nil {
			t.Fatalf("concurrent acquire %d: %v", index+1, result.err)
		}
	}
	if first.claim.ClaimToken != second.claim.ClaimToken {
		t.Fatalf("concurrent tokens differ: %s vs %s", first.claim.ClaimToken, second.claim.ClaimToken)
	}
	if first.claim.Resumed == second.claim.Resumed {
		t.Fatalf("resumed flags = %t and %t, want one new and one resumed", first.claim.Resumed, second.claim.Resumed)
	}
	assertResumeClaimOrdinals(t, first.claim, []int64{2, 3, 5, 6})
	assertResumeClaimOrdinals(t, second.claim, []int64{2, 3, 5, 6})

	var activeCount, tokenCount, claimedAuditCount, resumedAuditCount int
	if err := pool.QueryRow(ctx, `
		SELECT count(*), count(DISTINCT claim_token)
		FROM document_review_claims
		WHERE reviewer_id = $1::uuid AND expires_at > now()
	`, reviewerIDs[0]).Scan(&activeCount, &tokenCount); err != nil {
		t.Fatalf("count concurrent claims: %v", err)
	}
	if activeCount != 4 || tokenCount != 1 {
		t.Fatalf("active claims = %d across %d tokens, want 4 across 1", activeCount, tokenCount)
	}
	if err := pool.QueryRow(ctx, `
		SELECT
			count(*) FILTER (WHERE action = 'documents.review_claimed'),
			count(*) FILTER (WHERE action = 'documents.review_claim_resumed')
		FROM audit_events
		WHERE actor_id = $1::uuid AND entity_id = $2::uuid
	`, reviewerIDs[0], sourceID).Scan(&claimedAuditCount, &resumedAuditCount); err != nil {
		t.Fatalf("count concurrent claim audits: %v", err)
	}
	if claimedAuditCount != 1 || resumedAuditCount != 1 {
		t.Fatalf("claim audits = claimed:%d resumed:%d, want 1 and 1", claimedAuditCount, resumedAuditCount)
	}
}

type documentClaimResumeResult struct {
	claim domain.DocumentReviewClaim
	err   error
}

func assertResumeClaimOrdinals(t *testing.T, claim domain.DocumentReviewClaim, want []int64) {
	t.Helper()
	got := make([]int64, 0, len(claim.Documents))
	for _, document := range claim.Documents {
		got = append(got, document.SourceOrdinal)
	}
	if fmt.Sprint(got) != fmt.Sprint(want) {
		t.Fatalf("claim ordinals = %v, want %v", got, want)
	}
}

func setupDocumentClaimResumeFixture(
	t *testing.T,
	documentCount, reviewerCount int,
) (context.Context, *pgxpool.Pool, string, []string) {
	t.Helper()
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

	schemaName := fmt.Sprintf("derlem_claim_resume_test_%d", time.Now().UnixNano())
	schemaIdentifier := pgx.Identifier{schemaName}.Sanitize()
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

	var creatorID, sourceID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO users(email, password_hash, display_name)
		VALUES ('resume-creator@example.test', 'test', 'Resume Creator')
		RETURNING id::text
	`).Scan(&creatorID); err != nil {
		t.Fatalf("insert creator: %v", err)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
		VALUES (repeat('b', 64), 'objects/claim-resume-test', 4, 'text/plain')
	`); err != nil {
		t.Fatalf("insert object: %v", err)
	}
	if err := pool.QueryRow(ctx, `
		INSERT INTO sources(
			name, source_type, content_purpose, license, rights_status,
			language, domain, lineage_ref, object_sha256, created_by,
			document_sampling_status, sampled_document_count,
			document_sample_generation, document_sampling_method
		)
		VALUES (
			'Claim resume test', 'jsonl', 'pretrain', 'test', 'cleared',
			'tr', 'test', 'claim-resume-integration-test', repeat('b', 64), $1,
			'sampled', $2, 1, 'risk-stratified-v1'
		)
		RETURNING id::text
	`, creatorID, documentCount).Scan(&sourceID); err != nil {
		t.Fatalf("insert source: %v", err)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO document_sample_generations(
			source_id, generation, source_sha256, sampling_method, status, sample_count
		)
		VALUES ($1, 1, repeat('b', 64), 'risk-stratified-v1', 'active', $2)
	`, sourceID, documentCount); err != nil {
		t.Fatalf("insert sample generation: %v", err)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO documents(
			source_id, source_ordinal, current_object_sha256, text_preview,
			byte_size, char_count, risk_score, sample_generation
		)
		SELECT $1, ordinal, repeat('b', 64), 'claim resume test document', 4, 4,
			(CASE ordinal
				WHEN 1 THEN 5 WHEN 2 THEN 9 WHEN 3 THEN 9 WHEN 4 THEN 2
				WHEN 5 THEN 8 WHEN 6 THEN 7 WHEN 7 THEN 1 ELSE 0
			END)::smallint,
			1
		FROM generate_series(1, $2) AS ordinal
	`, sourceID, documentCount); err != nil {
		t.Fatalf("insert documents: %v", err)
	}
	insertActiveDocumentSampleMemberships(t, ctx, pool, sourceID)

	rows, err := pool.Query(ctx, `
		INSERT INTO users(email, password_hash, display_name)
		SELECT 'resume-reviewer-' || ordinal || '@example.test', 'test', 'Resume Reviewer ' || ordinal
		FROM generate_series(1, $1) AS ordinal
		RETURNING id::text
	`, reviewerCount)
	if err != nil {
		t.Fatalf("insert reviewers: %v", err)
	}
	reviewerIDs := make([]string, 0, reviewerCount)
	for rows.Next() {
		var reviewerID string
		if err := rows.Scan(&reviewerID); err != nil {
			rows.Close()
			t.Fatalf("scan reviewer: %v", err)
		}
		reviewerIDs = append(reviewerIDs, reviewerID)
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		t.Fatalf("read reviewers: %v", err)
	}
	rows.Close()
	if len(reviewerIDs) != reviewerCount {
		t.Fatalf("reviewer count = %d, want %d", len(reviewerIDs), reviewerCount)
	}
	return ctx, pool, sourceID, reviewerIDs
}

func insertActiveDocumentSampleMemberships(
	t *testing.T,
	ctx context.Context,
	pool *pgxpool.Pool,
	sourceID string,
) {
	t.Helper()
	if _, err := pool.Exec(ctx, `
		INSERT INTO document_sample_memberships(
			source_id, generation, document_id, source_ordinal,
			object_sha256, risk_score, risk_reasons
		)
		SELECT document.source_id, document.sample_generation, document.id,
			document.source_ordinal, document.current_object_sha256,
			document.risk_score, document.risk_reasons
		FROM documents AS document
		WHERE document.source_id = $1::uuid AND document.is_active
		ORDER BY document.source_ordinal, document.id
	`, sourceID); err != nil {
		t.Fatalf("insert immutable sample memberships: %v", err)
	}
}
