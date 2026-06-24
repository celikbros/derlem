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

func (r *Sources) Review(
	ctx context.Context,
	sourceID string,
	input domain.ReviewInput,
	actorID string,
	allowSelfReview bool,
) (domain.Source, domain.Review, error) {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return domain.Source{}, domain.Review{}, err
	}
	defer tx.Rollback(ctx)

	source, err := scanSource(tx.QueryRow(ctx, "SELECT "+sourceColumns+" FROM sources WHERE id = $1 FOR UPDATE", sourceID))
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.Source{}, domain.Review{}, ErrNotFound
	}
	if err != nil {
		return domain.Source{}, domain.Review{}, err
	}
	if source.CreatedBy == actorID && !allowSelfReview {
		return domain.Source{}, domain.Review{}, ErrSelfReview
	}

	reason := trimReason(input.Reason)
	if (input.Decision == "rejected" || input.Decision == "sensitive_review") && reason == nil {
		return domain.Source{}, domain.Review{}, &GateError{Reasons: []string{"reason_required"}}
	}
	if input.Decision == "approved" {
		reasons := approvalGateReasons(source)
		if len(reasons) > 0 {
			return domain.Source{}, domain.Review{}, &GateError{Reasons: reasons}
		}
	}

	nextStatus := map[string]string{
		"approved":         "approved_source",
		"rejected":         "rejected",
		"sensitive_review": "quarantined",
	}[input.Decision]
	updated, err := scanSource(tx.QueryRow(ctx, `
		UPDATE sources
		SET approval_status = $1
		WHERE id = $2
		RETURNING `+sourceColumns,
		nextStatus, sourceID,
	))
	if err != nil {
		return domain.Source{}, domain.Review{}, fmt.Errorf("update review state: %w", err)
	}

	contextJSON, _ := json.Marshal(map[string]any{
		"rights_status":          source.RightsStatus,
		"pii_status":             source.PIIStatus,
		"duplicate_status":       source.DuplicateStatus,
		"duplicate_of_source_id": source.DuplicateOfSourceID,
		"risk_level":             source.RiskLevel,
		"object_sha256":          source.ObjectSHA256,
		"approval_before":        source.ApprovalStatus,
	})
	var review domain.Review
	if err := tx.QueryRow(ctx, `
		INSERT INTO reviews(source_id, reviewer_id, decision, reason, source_version, review_context)
		VALUES ($1, $2, $3, $4, $5, $6::jsonb)
		RETURNING id::text, source_id::text, reviewer_id::text, decision, reason,
			source_version, review_context, created_at
	`, sourceID, actorID, input.Decision, reason, source.Version, contextJSON).Scan(
		&review.ID, &review.SourceID, &review.ReviewerID, &review.Decision,
		&review.Reason, &review.SourceVersion, &review.Context, &review.CreatedAt,
	); err != nil {
		return domain.Source{}, domain.Review{}, fmt.Errorf("insert review: %w", err)
	}

	if _, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES (
			$1, 'source.reviewed', 'source', $2,
			jsonb_build_object(
				'review_id', $3::text, 'decision', $4::text,
				'source_version', $5::bigint, 'reason', $6::text
			)
		)
	`, actorID, sourceID, review.ID, input.Decision, source.Version, reason); err != nil {
		return domain.Source{}, domain.Review{}, fmt.Errorf("audit review: %w", err)
	}
	if err := tx.Commit(ctx); err != nil {
		return domain.Source{}, domain.Review{}, err
	}
	return updated, review, nil
}

func (r *Sources) ListReviews(ctx context.Context, sourceID string) ([]domain.Review, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT id::text, source_id::text, reviewer_id::text, decision, reason,
			source_version, review_context, created_at
		FROM reviews
		WHERE source_id = $1
		ORDER BY created_at DESC, id DESC
	`, sourceID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	reviews := []domain.Review{}
	for rows.Next() {
		var review domain.Review
		if err := rows.Scan(
			&review.ID, &review.SourceID, &review.ReviewerID, &review.Decision,
			&review.Reason, &review.SourceVersion, &review.Context, &review.CreatedAt,
		); err != nil {
			return nil, err
		}
		reviews = append(reviews, review)
	}
	return reviews, rows.Err()
}

func (r *Sources) ListPIIScans(ctx context.Context, sourceID string) ([]domain.PIIScan, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT id::text, source_id::text, object_sha256, scanner_version, status, findings, scanned_at
		FROM pii_scans
		WHERE source_id = $1
		ORDER BY scanned_at DESC, id DESC
	`, sourceID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	scans := []domain.PIIScan{}
	for rows.Next() {
		var scan domain.PIIScan
		if err := rows.Scan(
			&scan.ID, &scan.SourceID, &scan.ObjectSHA256, &scan.ScannerVersion,
			&scan.Status, &scan.Findings, &scan.ScannedAt,
		); err != nil {
			return nil, err
		}
		scans = append(scans, scan)
	}
	return scans, rows.Err()
}

func approvalGateReasons(source domain.Source) []string {
	reasons := []string{}
	if source.ObjectSHA256 == nil {
		reasons = append(reasons, "file_not_ingested")
	}
	if source.RightsStatus != "cleared" {
		reasons = append(reasons, "rights_not_cleared")
	}
	if source.LicenseEvidenceRef == nil {
		reasons = append(reasons, "license_evidence_missing")
	}
	if source.PIIStatus != "clear" {
		reasons = append(reasons, "pii_not_clear")
	}
	if source.DuplicateStatus != "unique" {
		reasons = append(reasons, "exact_duplicate_not_clear")
	}
	if source.ApprovalStatus == "approved_source" || source.ApprovalStatus == "release_candidate" {
		reasons = append(reasons, "already_approved")
	}
	return reasons
}

func trimReason(reason *string) *string {
	if reason == nil {
		return nil
	}
	trimmed := strings.TrimSpace(*reason)
	if trimmed == "" {
		return nil
	}
	return &trimmed
}
