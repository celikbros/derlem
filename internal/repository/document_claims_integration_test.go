package repository_test

import (
	"context"
	"errors"
	"fmt"
	"os"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/celikbros/derlem/internal/database"
	"github.com/celikbros/derlem/internal/domain"
	"github.com/celikbros/derlem/internal/repository"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

func TestDocumentReviewClaimsDistributeWithoutCollisions(t *testing.T) {
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

	schemaName := fmt.Sprintf("derlem_claim_test_%d", time.Now().UnixNano())
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
	config.MaxConns = 64
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
		VALUES ('creator@example.test', 'test', 'Creator')
		RETURNING id::text
	`).Scan(&creatorID); err != nil {
		t.Fatalf("insert creator: %v", err)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
		VALUES (repeat('a', 64), 'objects/test', 4, 'text/plain')
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
			'Claim test', 'jsonl', 'pretrain', 'test', 'cleared',
			'tr', 'test', 'integration-test', repeat('a', 64), $1,
			'sampled', 200, 1, 'risk-stratified-v1'
		)
		RETURNING id::text
	`, creatorID).Scan(&sourceID); err != nil {
		t.Fatalf("insert source: %v", err)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO documents(
			source_id, source_ordinal, current_object_sha256, text_preview,
			byte_size, char_count, risk_score, sample_generation
		)
		SELECT $1, ordinal, repeat('a', 64), 'test document', 4, 4,
			(ordinal % 11)::smallint, 1
		FROM generate_series(1, 200) AS ordinal
	`, sourceID); err != nil {
		t.Fatalf("insert documents: %v", err)
	}

	rows, err := pool.Query(ctx, `
		INSERT INTO users(email, password_hash, display_name)
		SELECT 'reviewer-' || ordinal || '@example.test', 'test', 'Reviewer ' || ordinal
		FROM generate_series(1, 1000) AS ordinal
		RETURNING id::text
	`)
	if err != nil {
		t.Fatalf("insert reviewers: %v", err)
	}
	reviewerIDs := make([]string, 0, 1000)
	for rows.Next() {
		var reviewerID string
		if err := rows.Scan(&reviewerID); err != nil {
			t.Fatalf("scan reviewer: %v", err)
		}
		reviewerIDs = append(reviewerIDs, reviewerID)
	}
	rows.Close()
	if len(reviewerIDs) != 1000 {
		t.Fatalf("reviewer count = %d, want 1000", len(reviewerIDs))
	}

	documents := repository.NewDocuments(pool)
	type claimResult struct {
		reviewerID string
		claim      domain.DocumentReviewClaim
		err        error
	}
	results := make(chan claimResult, len(reviewerIDs))
	var wait sync.WaitGroup
	for _, reviewerID := range reviewerIDs {
		wait.Add(1)
		go func(reviewerID string) {
			defer wait.Done()
			claim, err := documents.ClaimForReview(ctx, sourceID, reviewerID, 1, false)
			results <- claimResult{reviewerID: reviewerID, claim: claim, err: err}
		}(reviewerID)
	}
	wait.Wait()
	close(results)

	claimedIDs := make(map[string]claimResult, 200)
	for result := range results {
		if result.err != nil {
			t.Fatalf("concurrent claim: %v", result.err)
		}
		if len(result.claim.Documents) == 0 {
			continue
		}
		if len(result.claim.Documents) != 1 {
			t.Fatalf("claim size = %d, want 1", len(result.claim.Documents))
		}
		documentID := result.claim.Documents[0].ID
		if previous, exists := claimedIDs[documentID]; exists {
			t.Fatalf("document %s claimed by both %s and %s", documentID, previous.reviewerID, result.reviewerID)
		}
		claimedIDs[documentID] = result
	}
	if len(claimedIDs) != 200 {
		t.Fatalf("unique claimed document count = %d, want 200", len(claimedIDs))
	}

	var owner claimResult
	for _, result := range claimedIDs {
		owner = result
		break
	}
	document := owner.claim.Documents[0]
	wrongReviewer := reviewerIDs[0]
	if wrongReviewer == owner.reviewerID {
		wrongReviewer = reviewerIDs[1]
	}
	input := domain.ReviewDocumentInput{
		DocumentQualityScores: domain.DocumentQualityScores{
			QualityScore: 5, LanguageQualityScore: 5, CoherenceScore: 5,
			InformationDensityScore: 5, CleanlinessScore: 5,
		},
		Decision: "approved", DocumentVersion: document.CurrentVersion,
		ClaimToken: owner.claim.ClaimToken,
	}
	if _, _, _, err := documents.Review(ctx, document.ID, input, wrongReviewer, false); !errors.Is(err, repository.ErrClaimLost) {
		t.Fatalf("review with another user's token error = %v, want ErrClaimLost", err)
	}
	if _, _, _, err := documents.Review(ctx, document.ID, input, owner.reviewerID, false); err != nil {
		t.Fatalf("review by claim owner: %v", err)
	}
	var remainingClaimCount, leakedTokenCount int
	if err := pool.QueryRow(ctx,
		"SELECT count(*) FROM document_review_claims WHERE document_id = $1",
		document.ID,
	).Scan(&remainingClaimCount); err != nil {
		t.Fatalf("count consumed claim: %v", err)
	}
	if remainingClaimCount != 0 {
		t.Fatalf("claim remained after review: count=%d", remainingClaimCount)
	}
	if err := pool.QueryRow(ctx, `
		SELECT count(*) FROM audit_events WHERE details::text LIKE '%' || $1 || '%'
	`, owner.claim.ClaimToken).Scan(&leakedTokenCount); err != nil {
		t.Fatalf("scan audit token leakage: %v", err)
	}
	if leakedTokenCount != 0 {
		t.Fatalf("claim token leaked into audit details")
	}
}
