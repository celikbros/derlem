package repository_test

import (
	"sync"
	"testing"

	"github.com/celikbros/derlem/internal/domain"
	"github.com/celikbros/derlem/internal/repository"
)

func TestConcurrentReviewClaimsShareOnePinnedCampaign(t *testing.T) {
	ctx, pool, sourceID, reviewerIDs := setupDocumentClaimResumeFixture(t, 8, 2)
	documents := repository.NewDocuments(pool)

	type result struct {
		reviewerID string
		claim      domain.DocumentReviewClaim
		err        error
	}
	start := make(chan struct{})
	results := make(chan result, len(reviewerIDs))
	var workers sync.WaitGroup
	for _, reviewerID := range reviewerIDs {
		workers.Add(1)
		go func(reviewerID string) {
			defer workers.Done()
			<-start
			claim, err := documents.ClaimForReview(
				ctx, sourceID, reviewerID, 2, false,
			)
			results <- result{reviewerID: reviewerID, claim: claim, err: err}
		}(reviewerID)
	}
	close(start)
	workers.Wait()
	close(results)

	claims := make([]domain.DocumentReviewClaim, 0, len(reviewerIDs))
	claimsByReviewer := make(map[string]domain.DocumentReviewClaim, len(reviewerIDs))
	for result := range results {
		if result.err != nil {
			t.Fatalf("concurrent claim: %v", result.err)
		}
		if result.claim.ReviewCampaignID == "" {
			t.Fatal("claim did not expose its server-pinned campaign")
		}
		claims = append(claims, result.claim)
		claimsByReviewer[result.reviewerID] = result.claim
	}
	if len(claims) != 2 {
		t.Fatalf("claim count = %d, want 2", len(claims))
	}
	if claims[0].ReviewCampaignID != claims[1].ReviewCampaignID {
		t.Fatalf(
			"concurrent campaign IDs differ: %s vs %s",
			claims[0].ReviewCampaignID, claims[1].ReviewCampaignID,
		)
	}

	var campaignCount, openedAuditCount, claimedRowCount int
	if err := pool.QueryRow(ctx, `
		SELECT count(*)
		FROM review_campaigns
		WHERE source_id = $1::uuid AND sample_generation = 1
	`, sourceID).Scan(&campaignCount); err != nil {
		t.Fatalf("count campaigns: %v", err)
	}
	if campaignCount != 1 {
		t.Fatalf("campaign count = %d, want 1", campaignCount)
	}
	if err := pool.QueryRow(ctx, `
		SELECT count(*)
		FROM document_review_claims
		WHERE review_campaign_id = $1::uuid AND expires_at > now()
	`, claims[0].ReviewCampaignID).Scan(&claimedRowCount); err != nil {
		t.Fatalf("count campaign claims: %v", err)
	}
	if claimedRowCount != 4 {
		t.Fatalf("campaign claim rows = %d, want 4", claimedRowCount)
	}
	if err := pool.QueryRow(ctx, `
		SELECT count(*)
		FROM audit_events
		WHERE action = 'review_campaign.opened'
		  AND entity_id = $1::uuid
		  AND details->>'review_campaign_id' = $1::text
		  AND NOT (details ? 'canonical_bytes')
	`, claims[0].ReviewCampaignID).Scan(&openedAuditCount); err != nil {
		t.Fatalf("count campaign audit: %v", err)
	}
	if openedAuditCount != 1 {
		t.Fatalf("campaign open audits = %d, want 1", openedAuditCount)
	}

	bulkClaim := claimsByReviewer[reviewerIDs[1]]
	bulkItems := make([]domain.BulkReviewDocumentItem, 0, len(bulkClaim.Documents))
	for _, document := range bulkClaim.Documents {
		bulkItems = append(bulkItems, domain.BulkReviewDocumentItem{
			DocumentID: document.ID, DocumentVersion: document.CurrentVersion,
		})
	}
	bulkReason := "integration bulk rejection"
	bulkResult, err := documents.BulkReview(ctx, sourceID, domain.BulkReviewDocumentsInput{
		DocumentQualityScores: domain.DocumentQualityScores{
			QualityScore: 2, LanguageQualityScore: 2, CoherenceScore: 2,
			InformationDensityScore: 2, CleanlinessScore: 2,
		},
		Documents: bulkItems, Decision: "rejected", Reason: &bulkReason,
		ClaimToken: bulkClaim.ClaimToken,
	}, reviewerIDs[1], false)
	if err != nil {
		t.Fatalf("bulk review claimed documents: %v", err)
	}
	for _, review := range bulkResult.Reviews {
		if review.ReviewCampaignID == nil ||
			*review.ReviewCampaignID != bulkClaim.ReviewCampaignID {
			t.Fatalf("bulk review did not retain campaign: %+v", review)
		}
	}

	resumed, err := documents.ClaimForReview(
		ctx, sourceID, reviewerIDs[0], 1, false,
	)
	if err != nil {
		t.Fatalf("resume campaign claim: %v", err)
	}
	if !resumed.Resumed {
		t.Fatal("active campaign claim was not resumed")
	}
	if resumed.ReviewCampaignID != claims[0].ReviewCampaignID {
		t.Fatalf(
			"resumed campaign = %s, want %s",
			resumed.ReviewCampaignID, claims[0].ReviewCampaignID,
		)
	}

	reason := "integration rejection"
	reviewedDocument := resumed.Documents[0]
	_, _, review, err := documents.Review(ctx, reviewedDocument.ID, domain.ReviewDocumentInput{
		DocumentQualityScores: domain.DocumentQualityScores{
			QualityScore: 2, LanguageQualityScore: 2, CoherenceScore: 2,
			InformationDensityScore: 2, CleanlinessScore: 2,
		},
		Decision: "rejected", Reason: &reason,
		DocumentVersion: reviewedDocument.CurrentVersion,
		ClaimToken:      resumed.ClaimToken,
	}, reviewerIDs[0], false)
	if err != nil {
		t.Fatalf("review claimed document: %v", err)
	}
	if review.ReviewCampaignID == nil ||
		*review.ReviewCampaignID != resumed.ReviewCampaignID {
		t.Fatalf("review campaign = %v, want %s", review.ReviewCampaignID, resumed.ReviewCampaignID)
	}
	history, err := documents.ListReviews(ctx, reviewedDocument.ID)
	if err != nil {
		t.Fatalf("list review history: %v", err)
	}
	if len(history) != 1 || history[0].ReviewCampaignID == nil ||
		*history[0].ReviewCampaignID != resumed.ReviewCampaignID {
		t.Fatalf("history did not retain campaign identity: %+v", history)
	}
}

func TestLegacyNullCampaignClaimIsReleasedInsteadOfResumed(t *testing.T) {
	ctx, pool, sourceID, reviewerIDs := setupDocumentClaimResumeFixture(t, 4, 1)
	documents := repository.NewDocuments(pool)
	first, err := documents.ClaimForReview(
		ctx, sourceID, reviewerIDs[0], 2, false,
	)
	if err != nil {
		t.Fatalf("first claim: %v", err)
	}
	if _, err := pool.Exec(ctx, `
		ALTER TABLE document_review_claims
		DISABLE TRIGGER document_review_claims_validate_campaign
	`); err != nil {
		t.Fatalf("disable claim campaign trigger: %v", err)
	}
	if _, err := pool.Exec(ctx, `
		UPDATE document_review_claims
		SET review_campaign_id = NULL
		WHERE claim_token = $1::uuid
	`, first.ClaimToken); err != nil {
		t.Fatalf("simulate pre-registry claim: %v", err)
	}
	if _, err := pool.Exec(ctx, `
		ALTER TABLE document_review_claims
		ENABLE TRIGGER document_review_claims_validate_campaign
	`); err != nil {
		t.Fatalf("enable claim campaign trigger: %v", err)
	}

	replacement, err := documents.ClaimForReview(
		ctx, sourceID, reviewerIDs[0], 2, false,
	)
	if err != nil {
		t.Fatalf("replace pre-registry claim: %v", err)
	}
	if replacement.Resumed {
		t.Fatal("pre-registry NULL campaign claim was resumed")
	}
	if replacement.ClaimToken == first.ClaimToken {
		t.Fatal("pre-registry claim token was reused")
	}
	if replacement.ReviewCampaignID != first.ReviewCampaignID {
		t.Fatalf(
			"replacement campaign = %s, want existing %s",
			replacement.ReviewCampaignID, first.ReviewCampaignID,
		)
	}
}
