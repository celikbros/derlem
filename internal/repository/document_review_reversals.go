package repository

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	"github.com/celikbros/derlem/internal/domain"
	"github.com/jackc/pgx/v5"
)

// ReverseReview appends a compensating record for a mistaken document review.
// The original review is intentionally left untouched.
func (r *Documents) ReverseReview(
	ctx context.Context,
	reviewID string,
	input domain.ReverseDocumentReviewInput,
	actorID string,
	allowAnyReviewer bool,
) (domain.ReverseDocumentReviewResult, error) {
	reason := strings.TrimSpace(input.Reason)
	if reason == "" {
		return domain.ReverseDocumentReviewResult{}, &GateError{Reasons: []string{"reason_required"}}
	}

	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return domain.ReverseDocumentReviewResult{}, err
	}
	defer tx.Rollback(ctx)

	// Release evidence validation takes locks in source -> document -> active
	// review order. Resolve identifiers without locking, then acquire the same
	// hierarchy and revalidate every relationship under lock. The preliminary
	// lookup is only routing information; it is never used as authoritative
	// review state.
	var sourceID, documentID string
	if err := tx.QueryRow(ctx, `
		SELECT document.source_id::text, review.document_id::text
		FROM document_reviews AS review
		JOIN documents AS document ON document.id = review.document_id
		WHERE review.id = $1
	`, reviewID).Scan(&sourceID, &documentID); errors.Is(err, pgx.ErrNoRows) {
		return domain.ReverseDocumentReviewResult{}, ErrNotFound
	} else if err != nil {
		return domain.ReverseDocumentReviewResult{}, err
	}

	var lockedSourceID string
	if err := tx.QueryRow(ctx, `
		SELECT id::text FROM sources WHERE id = $1 FOR UPDATE
	`, sourceID).Scan(&lockedSourceID); errors.Is(err, pgx.ErrNoRows) {
		return domain.ReverseDocumentReviewResult{}, ErrConflict
	} else if err != nil {
		return domain.ReverseDocumentReviewResult{}, err
	}

	document, err := scanDocument(tx.QueryRow(ctx,
		"SELECT "+documentColumns+" FROM documents WHERE id = $1 AND source_id = $2 FOR UPDATE",
		documentID, sourceID,
	))
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.ReverseDocumentReviewResult{}, ErrConflict
	}
	if err != nil {
		return domain.ReverseDocumentReviewResult{}, err
	}

	// Absence is valid for an idempotent request whose review was already
	// reversed. When present, lock the projection before its immutable review
	// row because release validation follows this same order.
	var activeReviewID string
	if err := tx.QueryRow(ctx, `
		SELECT review_id::text
		FROM active_document_reviews
		WHERE review_id = $1
		FOR UPDATE
	`, reviewID).Scan(&activeReviewID); err != nil && !errors.Is(err, pgx.ErrNoRows) {
		return domain.ReverseDocumentReviewResult{}, err
	}

	review, err := scanDocumentReview(tx.QueryRow(ctx, `
		SELECT `+documentReviewColumns+`
		FROM document_reviews
		WHERE id = $1
		FOR UPDATE
	`, reviewID))
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.ReverseDocumentReviewResult{}, ErrNotFound
	}
	if err != nil {
		return domain.ReverseDocumentReviewResult{}, err
	}
	if review.DocumentID != document.ID {
		return domain.ReverseDocumentReviewResult{}, ErrConflict
	}
	if review.ReviewerID != actorID && !allowAnyReviewer {
		return domain.ReverseDocumentReviewResult{}, ErrForbidden
	}

	if reversal, found, err := findDocumentReviewReversal(ctx, tx, review.ID); err != nil {
		return domain.ReverseDocumentReviewResult{}, err
	} else if found {
		review.Reversal = &reversal
		source, err := scanSource(tx.QueryRow(ctx,
			"SELECT "+sourceColumns+" FROM sources WHERE id = $1",
			document.SourceID,
		))
		if err != nil {
			return domain.ReverseDocumentReviewResult{}, err
		}
		if err := tx.Commit(ctx); err != nil {
			return domain.ReverseDocumentReviewResult{}, err
		}
		return domain.ReverseDocumentReviewResult{
			Source: source, Document: document, Review: review, Reversal: reversal,
			AlreadyReversed: true,
		}, nil
	}

	restoredStatus, ok := previousReviewDocumentStatus(review.Context)
	if !ok || !document.IsActive || document.CurrentVersion != review.DocumentVersion ||
		document.CurrentObjectSHA256 != review.ObjectSHA256 ||
		document.Status != reviewedDocumentStatus(review.Decision) {
		return domain.ReverseDocumentReviewResult{}, ErrConflict
	}

	var anotherEffectiveReview bool
	if err := tx.QueryRow(ctx, `
		SELECT EXISTS (
			SELECT 1
			FROM document_reviews AS other_review
			LEFT JOIN document_review_reversals AS reversal
			  ON reversal.review_id = other_review.id
			WHERE other_review.document_id = $1
			  AND other_review.document_version = $2
			  AND other_review.object_sha256 = $3
			  AND other_review.id <> $4
			  AND reversal.review_id IS NULL
		)
	`, review.DocumentID, review.DocumentVersion, review.ObjectSHA256, review.ID).Scan(&anotherEffectiveReview); err != nil {
		return domain.ReverseDocumentReviewResult{}, err
	}
	if anotherEffectiveReview {
		return domain.ReverseDocumentReviewResult{}, ErrConflict
	}
	updated, err := scanDocument(tx.QueryRow(ctx, `
		UPDATE documents
		SET status = $1
		WHERE id = $2
		  AND is_active
		  AND current_version = $3
		  AND current_object_sha256 = $4
		  AND status = $5
		RETURNING `+documentColumns,
		restoredStatus, review.DocumentID, review.DocumentVersion,
		review.ObjectSHA256, reviewedDocumentStatus(review.Decision),
	))
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.ReverseDocumentReviewResult{}, ErrConflict
	}
	if err != nil {
		return domain.ReverseDocumentReviewResult{}, err
	}

	var reversal domain.DocumentReviewReversal
	if err := tx.QueryRow(ctx, `
		INSERT INTO document_review_reversals(
			review_id, reversed_by, reason, restored_document_status
		)
		VALUES ($1, $2, $3, $4)
		RETURNING id::text, review_id::text, reversed_by::text, reason,
			restored_document_status, created_at
	`, review.ID, actorID, reason, restoredStatus).Scan(
		&reversal.ID, &reversal.ReviewID, &reversal.ReversedBy,
		&reversal.Reason, &reversal.RestoredDocumentStatus, &reversal.CreatedAt,
	); err != nil {
		return domain.ReverseDocumentReviewResult{}, fmt.Errorf("insert document review reversal: %w", err)
	}
	review.Reversal = &reversal

	if err := refreshSourceDocumentReviewCounts(ctx, tx, document.SourceID, true); err != nil {
		return domain.ReverseDocumentReviewResult{}, err
	}
	source, err := scanSource(tx.QueryRow(ctx,
		"SELECT "+sourceColumns+" FROM sources WHERE id = $1",
		document.SourceID,
	))
	if err != nil {
		return domain.ReverseDocumentReviewResult{}, err
	}

	auditDetails, _ := json.Marshal(map[string]any{
		"review_id":                review.ID,
		"reversal_id":              reversal.ID,
		"original_reviewer_id":     review.ReviewerID,
		"original_decision":        review.Decision,
		"document_version":         review.DocumentVersion,
		"object_sha256":            review.ObjectSHA256,
		"review_campaign_id":       review.ReviewCampaignID,
		"restored_document_status": restoredStatus,
		"reason":                   reason,
		"performed_by_admin":       allowAnyReviewer && review.ReviewerID != actorID,
	})
	if _, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES ($1, 'document.review_reversed', 'document', $2, $3::jsonb)
	`, actorID, document.ID, auditDetails); err != nil {
		return domain.ReverseDocumentReviewResult{}, fmt.Errorf("audit document review reversal: %w", err)
	}

	if err := tx.Commit(ctx); err != nil {
		return domain.ReverseDocumentReviewResult{}, err
	}
	return domain.ReverseDocumentReviewResult{
		Source: source, Document: updated, Review: review, Reversal: reversal,
	}, nil
}

func findDocumentReviewReversal(
	ctx context.Context,
	tx pgx.Tx,
	reviewID string,
) (domain.DocumentReviewReversal, bool, error) {
	var reversal domain.DocumentReviewReversal
	err := tx.QueryRow(ctx, `
		SELECT id::text, review_id::text, reversed_by::text, reason,
			restored_document_status, created_at
		FROM document_review_reversals
		WHERE review_id = $1
	`, reviewID).Scan(
		&reversal.ID, &reversal.ReviewID, &reversal.ReversedBy,
		&reversal.Reason, &reversal.RestoredDocumentStatus, &reversal.CreatedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.DocumentReviewReversal{}, false, nil
	}
	return reversal, err == nil, err
}

func previousReviewDocumentStatus(contextJSON json.RawMessage) (string, bool) {
	var reviewContext struct {
		PreviousStatus string `json:"previous_status"`
	}
	if err := json.Unmarshal(contextJSON, &reviewContext); err != nil {
		return "", false
	}
	if reviewContext.PreviousStatus != "sampled" && reviewContext.PreviousStatus != "edited" {
		return "", false
	}
	return reviewContext.PreviousStatus, true
}

func reviewedDocumentStatus(decision string) string {
	return map[string]string{
		"approved":         "approved",
		"rejected":         "rejected",
		"sensitive_review": "sensitive_review",
	}[decision]
}

const documentReviewColumns = `
	id::text, document_id::text, reviewer_id::text, review_campaign_id::text,
	decision, reason,
	rubric_version, quality_score, language_quality_score, coherence_score,
	information_density_score, cleanliness_score,
	document_version, object_sha256, review_context, created_at`

func scanDocumentReview(row scanner) (domain.DocumentReview, error) {
	var review domain.DocumentReview
	err := row.Scan(
		&review.ID, &review.DocumentID, &review.ReviewerID, &review.ReviewCampaignID,
		&review.Decision,
		&review.Reason, &review.RubricVersion, &review.QualityScore,
		&review.LanguageQualityScore, &review.CoherenceScore,
		&review.InformationDensityScore, &review.CleanlinessScore,
		&review.DocumentVersion, &review.ObjectSHA256, &review.Context, &review.CreatedAt,
	)
	return review, err
}
