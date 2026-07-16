package repository

import (
	"context"
	"crypto/rand"
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"strings"
	"time"

	"github.com/celikbros/derlem/internal/domain"
	"github.com/celikbros/derlem/internal/storage"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

const documentReviewClaimLease = 15 * time.Minute

var uuidPattern = regexp.MustCompile(`(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`)

type Documents struct {
	pool *pgxpool.Pool
}

func NewDocuments(pool *pgxpool.Pool) *Documents {
	return &Documents{pool: pool}
}

func (r *Documents) ListBySource(ctx context.Context, sourceID string, limit int) ([]domain.Document, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT `+documentColumns+`
		FROM documents
		WHERE source_id = $1 AND is_active
		ORDER BY source_ordinal ASC
		LIMIT $2
	`, sourceID, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	documents := make([]domain.Document, 0, limit)
	for rows.Next() {
		document, err := scanDocument(rows)
		if err != nil {
			return nil, err
		}
		documents = append(documents, document)
	}
	return documents, rows.Err()
}

func (r *Documents) ListSampleGenerations(ctx context.Context, sourceID string) ([]domain.DocumentSampleGeneration, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT source_id::text, generation, source_sha256, sampling_method,
			status, sample_count, job_id::text, created_at
		FROM document_sample_generations
		WHERE source_id = $1
		ORDER BY generation DESC
	`, sourceID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	generations := []domain.DocumentSampleGeneration{}
	for rows.Next() {
		var generation domain.DocumentSampleGeneration
		if err := rows.Scan(
			&generation.SourceID, &generation.Generation, &generation.SourceSHA256,
			&generation.SamplingMethod, &generation.Status, &generation.SampleCount,
			&generation.JobID, &generation.CreatedAt,
		); err != nil {
			return nil, err
		}
		generations = append(generations, generation)
	}
	return generations, rows.Err()
}

func (r *Documents) QueueResample(ctx context.Context, sourceID, actorID string) (string, error) {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return "", err
	}
	defer tx.Rollback(ctx)

	var objectSHA256 *string
	var samplingStatus, samplingMethod, approvalStatus string
	var generation, reviewedCount int64
	if err := tx.QueryRow(ctx, `
		SELECT object_sha256, document_sampling_status, document_sample_generation,
			document_sampling_method, reviewed_document_count, approval_status
		FROM sources
		WHERE id = $1
		FOR UPDATE
	`, sourceID).Scan(
		&objectSHA256, &samplingStatus, &generation, &samplingMethod,
		&reviewedCount, &approvalStatus,
	); errors.Is(err, pgx.ErrNoRows) {
		return "", ErrNotFound
	} else if err != nil {
		return "", err
	}

	reasons := []string{}
	if objectSHA256 == nil || samplingStatus != "sampled" {
		reasons = append(reasons, "source_not_sampled")
	}
	sourceReviewStarted := reviewedCount > 0 || approvalStatus == "approved_source" ||
		approvalStatus == "release_candidate" || approvalStatus == "rejected" ||
		approvalStatus == "quarantined"

	var activeCount, unsafeCount, documentReviewCount, sourceReviewCount int64
	if err := tx.QueryRow(ctx, `
		SELECT
			count(*) FILTER (WHERE document.is_active),
			count(*) FILTER (WHERE document.is_active AND (
				document.current_version <> 1 OR document.status <> 'sampled'
			)),
			(SELECT count(*)
			 FROM document_reviews AS review
			 JOIN documents AS reviewed_document ON reviewed_document.id = review.document_id
			 WHERE reviewed_document.source_id = $1),
			(SELECT count(*) FROM reviews AS review WHERE review.source_id = $1)
		FROM documents AS document
		WHERE document.source_id = $1
	`, sourceID).Scan(
		&activeCount, &unsafeCount, &documentReviewCount, &sourceReviewCount,
	); err != nil {
		return "", err
	}
	if sourceReviewStarted || sourceReviewCount > 0 {
		reasons = append(reasons, "source_review_already_started")
	}
	if activeCount == 0 {
		reasons = append(reasons, "active_sample_missing")
	}
	if unsafeCount > 0 {
		reasons = append(reasons, "sample_documents_changed")
	}
	if documentReviewCount > 0 {
		reasons = append(reasons, "sample_reviews_exist")
	}
	var activeClaimCount int64
	if err := tx.QueryRow(ctx, `
		SELECT count(*)
		FROM document_review_claims AS claim
		JOIN documents AS document ON document.id = claim.document_id
		WHERE document.source_id = $1 AND claim.expires_at > now()
	`, sourceID).Scan(&activeClaimCount); err != nil {
		return "", err
	}
	if activeClaimCount > 0 {
		reasons = append(reasons, "sample_review_claims_active")
	}
	if len(reasons) > 0 {
		return "", &GateError{Reasons: reasons}
	}

	var jobID string
	err = tx.QueryRow(ctx, `
		INSERT INTO background_jobs(job_type, priority, payload, created_by)
		VALUES (
			'resample_documents', 55,
			jsonb_build_object(
				'source_id', $1::text,
				'object_sha256', $2::text,
				'previous_generation', $3::bigint,
				'previous_sampling_method', $4::text,
				'requested_by', $5::text
			),
			$5::uuid
		)
		ON CONFLICT DO NOTHING
		RETURNING id::text
	`, sourceID, *objectSHA256, generation, samplingMethod, actorID).Scan(&jobID)
	if errors.Is(err, pgx.ErrNoRows) {
		return "", ErrConflict
	}
	if err != nil {
		return "", err
	}

	updated, err := tx.Exec(ctx, `
		UPDATE sources
		SET document_sampling_status = 'resampling'
		WHERE id = $1 AND document_sampling_status = 'sampled'
	`, sourceID)
	if err != nil {
		return "", err
	}
	if updated.RowsAffected() != 1 {
		return "", ErrConflict
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES (
			$1, 'source.document_resample_queued', 'source', $2,
			jsonb_build_object(
				'job_id', $3::text, 'object_sha256', $4::text,
				'previous_generation', $5::bigint,
				'previous_sampling_method', $6::text,
				'active_sample_count', $7::bigint
			)
		)
	`, actorID, sourceID, jobID, *objectSHA256, generation, samplingMethod, activeCount); err != nil {
		return "", fmt.Errorf("audit document resample queue: %w", err)
	}
	if err := tx.Commit(ctx); err != nil {
		return "", err
	}
	return jobID, nil
}

func (r *Documents) Get(ctx context.Context, id string) (domain.Document, error) {
	document, err := scanDocument(r.pool.QueryRow(ctx,
		"SELECT "+documentColumns+" FROM documents WHERE id = $1", id,
	))
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.Document{}, ErrNotFound
	}
	return document, err
}

func (r *Documents) ClaimForReview(
	ctx context.Context,
	sourceID, actorID string,
	limit int,
	allowSelfReview bool,
) (domain.DocumentReviewClaim, error) {
	if limit < 1 || limit > 200 {
		return domain.DocumentReviewClaim{}, &GateError{Reasons: []string{"invalid_claim_limit"}}
	}
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return domain.DocumentReviewClaim{}, err
	}
	defer tx.Rollback(ctx)

	var sourceCreator, samplingStatus string
	if err := tx.QueryRow(ctx,
		"SELECT created_by::text, document_sampling_status FROM sources WHERE id = $1 FOR SHARE", sourceID,
	).Scan(&sourceCreator, &samplingStatus); errors.Is(err, pgx.ErrNoRows) {
		return domain.DocumentReviewClaim{}, ErrNotFound
	} else if err != nil {
		return domain.DocumentReviewClaim{}, err
	}
	if sourceCreator == actorID && !allowSelfReview {
		return domain.DocumentReviewClaim{}, ErrSelfReview
	}
	if samplingStatus != "sampled" {
		return domain.DocumentReviewClaim{}, &GateError{Reasons: []string{"source_not_sampled"}}
	}

	claimToken, err := newUUID()
	if err != nil {
		return domain.DocumentReviewClaim{}, fmt.Errorf("generate document review claim token: %w", err)
	}
	var expiresAt time.Time
	if err := tx.QueryRow(ctx, `
		SELECT now() + make_interval(secs => $1)
	`, int(documentReviewClaimLease.Seconds())).Scan(&expiresAt); err != nil {
		return domain.DocumentReviewClaim{}, err
	}
	rows, err := tx.Query(ctx, `
		WITH candidates AS (
			SELECT document.id
			FROM documents AS document
			LEFT JOIN document_review_claims AS active_claim
			  ON active_claim.document_id = document.id
			 AND active_claim.expires_at > now()
			WHERE document.source_id = $1
			  AND document.is_active
			  AND document.status IN ('sampled', 'edited')
			  AND active_claim.document_id IS NULL
			ORDER BY document.risk_score DESC, document.source_ordinal ASC
			FOR UPDATE OF document SKIP LOCKED
			LIMIT $4
		)
		INSERT INTO document_review_claims(
			document_id, reviewer_id, claim_token, document_version, claimed_at, expires_at
		)
		SELECT document.id, $2::uuid, $3::uuid, document.current_version, now(), $5
		FROM candidates
		JOIN documents AS document ON document.id = candidates.id
		ON CONFLICT (document_id) DO UPDATE
		SET reviewer_id = EXCLUDED.reviewer_id,
			claim_token = EXCLUDED.claim_token,
			document_version = EXCLUDED.document_version,
			claimed_at = EXCLUDED.claimed_at,
			expires_at = EXCLUDED.expires_at
		WHERE document_review_claims.expires_at <= now()
		RETURNING document_id::text
	`, sourceID, actorID, claimToken, limit, expiresAt)
	if err != nil {
		return domain.DocumentReviewClaim{}, err
	}
	documentIDs := make([]string, 0, limit)
	for rows.Next() {
		var documentID string
		if err := rows.Scan(&documentID); err != nil {
			rows.Close()
			return domain.DocumentReviewClaim{}, err
		}
		documentIDs = append(documentIDs, documentID)
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		return domain.DocumentReviewClaim{}, err
	}
	rows.Close()

	documents := make([]domain.Document, 0, len(documentIDs))
	if len(documentIDs) > 0 {
		rows, err = tx.Query(ctx, `
			SELECT `+documentColumns+`
			FROM documents
			WHERE id = ANY($1::uuid[])
			ORDER BY risk_score DESC, source_ordinal ASC
		`, documentIDs)
		if err != nil {
			return domain.DocumentReviewClaim{}, err
		}
		for rows.Next() {
			document, err := scanDocument(rows)
			if err != nil {
				rows.Close()
				return domain.DocumentReviewClaim{}, err
			}
			documents = append(documents, document)
		}
		if err := rows.Err(); err != nil {
			rows.Close()
			return domain.DocumentReviewClaim{}, err
		}
		rows.Close()

		details, _ := json.Marshal(map[string]any{
			"document_count": len(documents),
			"expires_at":     expiresAt,
		})
		if _, err := tx.Exec(ctx, `
			INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
			VALUES ($1, 'documents.review_claimed', 'source', $2, $3::jsonb)
		`, actorID, sourceID, details); err != nil {
			return domain.DocumentReviewClaim{}, fmt.Errorf("audit document review claim: %w", err)
		}
	}

	if err := tx.Commit(ctx); err != nil {
		return domain.DocumentReviewClaim{}, err
	}
	return domain.DocumentReviewClaim{
		ClaimToken: claimToken,
		ExpiresAt:  expiresAt,
		Documents:  documents,
	}, nil
}

func (r *Documents) RenewReviewClaim(
	ctx context.Context,
	claimToken, actorID string,
) (domain.DocumentReviewClaimRenewal, error) {
	claimToken = strings.TrimSpace(claimToken)
	if !uuidPattern.MatchString(claimToken) {
		return domain.DocumentReviewClaimRenewal{}, ErrClaimLost
	}
	rows, err := r.pool.Query(ctx, `
		UPDATE document_review_claims AS claim
		SET expires_at = now() + make_interval(secs => $3)
		FROM documents AS document
		WHERE claim.claim_token = $1::uuid
		  AND claim.reviewer_id = $2::uuid
		  AND claim.expires_at > now()
		  AND document.id = claim.document_id
		  AND document.is_active
		  AND document.status IN ('sampled', 'edited')
		  AND document.current_version = claim.document_version
		RETURNING claim.expires_at
	`, claimToken, actorID, int(documentReviewClaimLease.Seconds()))
	if err != nil {
		return domain.DocumentReviewClaimRenewal{}, err
	}
	defer rows.Close()
	var count int64
	var expiresAt time.Time
	for rows.Next() {
		if err := rows.Scan(&expiresAt); err != nil {
			return domain.DocumentReviewClaimRenewal{}, err
		}
		count++
	}
	if err := rows.Err(); err != nil {
		return domain.DocumentReviewClaimRenewal{}, err
	}
	if count == 0 {
		return domain.DocumentReviewClaimRenewal{}, ErrClaimLost
	}
	return domain.DocumentReviewClaimRenewal{ExpiresAt: expiresAt, DocumentCount: count}, nil
}

func (r *Documents) ReleaseReviewClaim(ctx context.Context, claimToken, actorID string) error {
	claimToken = strings.TrimSpace(claimToken)
	if !uuidPattern.MatchString(claimToken) {
		return ErrClaimLost
	}
	_, err := r.pool.Exec(ctx, `
		DELETE FROM document_review_claims
		WHERE claim_token = $1::uuid AND reviewer_id = $2::uuid
	`, claimToken, actorID)
	return err
}

func (r *Documents) UpdateContent(
	ctx context.Context,
	id string,
	expectedVersion int64,
	object storage.Object,
	textPreview string,
	charCount int64,
	reason *string,
	actorID string,
) (domain.Document, error) {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return domain.Document{}, err
	}
	defer tx.Rollback(ctx)

	before, err := scanDocument(tx.QueryRow(ctx,
		"SELECT "+documentColumns+" FROM documents WHERE id = $1 FOR UPDATE", id,
	))
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.Document{}, ErrNotFound
	}
	if err != nil {
		return domain.Document{}, err
	}
	if !before.IsActive {
		return domain.Document{}, ErrConflict
	}
	if before.CurrentVersion != expectedVersion {
		return domain.Document{}, ErrConflict
	}

	if _, err := tx.Exec(ctx, `
		INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
		VALUES ($1, $2, $3, 'text/plain; charset=utf-8')
		ON CONFLICT (sha256) DO NOTHING
	`, object.SHA256, object.StorageKey, object.ByteSize); err != nil {
		return domain.Document{}, fmt.Errorf("register document object: %w", err)
	}

	nextVersion := before.CurrentVersion + 1
	updated, err := scanDocument(tx.QueryRow(ctx, `
		UPDATE documents
		SET current_object_sha256 = $1,
			text_preview = $2,
			byte_size = $3,
			char_count = $4,
			status = 'edited',
			current_version = $5,
			risk_score = 0,
			risk_reasons = '{}'::text[]
		WHERE id = $6 AND current_version = $7
		RETURNING `+documentColumns,
		object.SHA256, textPreview, object.ByteSize, charCount, nextVersion, id, expectedVersion,
	))
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.Document{}, ErrConflict
	}
	if err != nil {
		return domain.Document{}, fmt.Errorf("update document: %w", err)
	}

	reason = trimReason(reason)
	if _, err := tx.Exec(ctx, `
		INSERT INTO document_versions(
			document_id, version, object_sha256, byte_size, char_count,
			actor_type, created_by, reason
		)
		VALUES ($1, $2, $3, $4, $5, 'human', $6, $7)
	`, id, nextVersion, object.SHA256, object.ByteSize, charCount, actorID, reason); err != nil {
		return domain.Document{}, fmt.Errorf("insert document version: %w", err)
	}

	details, _ := json.Marshal(map[string]any{
		"source_id":     before.SourceID,
		"from_version":  before.CurrentVersion,
		"to_version":    nextVersion,
		"before_sha256": before.CurrentObjectSHA256,
		"after_sha256":  object.SHA256,
		"reason":        reason,
	})
	if _, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES ($1, 'document.edited', 'document', $2, $3::jsonb)
	`, actorID, id, details); err != nil {
		return domain.Document{}, fmt.Errorf("audit document edit: %w", err)
	}
	if err := refreshSourceDocumentReviewCounts(ctx, tx, before.SourceID, true); err != nil {
		return domain.Document{}, err
	}

	if err := tx.Commit(ctx); err != nil {
		return domain.Document{}, err
	}
	return updated, nil
}

func (r *Documents) Review(
	ctx context.Context,
	id string,
	input domain.ReviewDocumentInput,
	actorID string,
	allowSelfReview bool,
) (domain.Source, domain.Document, domain.DocumentReview, error) {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return domain.Source{}, domain.Document{}, domain.DocumentReview{}, err
	}
	defer tx.Rollback(ctx)

	document, err := scanDocument(tx.QueryRow(ctx,
		"SELECT "+documentColumns+" FROM documents WHERE id = $1 FOR UPDATE", id,
	))
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.Source{}, domain.Document{}, domain.DocumentReview{}, ErrNotFound
	}
	if err != nil {
		return domain.Source{}, domain.Document{}, domain.DocumentReview{}, err
	}
	if !document.IsActive {
		return domain.Source{}, domain.Document{}, domain.DocumentReview{}, ErrConflict
	}
	if document.Status != "sampled" && document.Status != "edited" {
		return domain.Source{}, domain.Document{}, domain.DocumentReview{}, ErrConflict
	}
	if document.CurrentVersion != input.DocumentVersion {
		return domain.Source{}, domain.Document{}, domain.DocumentReview{}, ErrConflict
	}

	var sourceCreator string
	if err := tx.QueryRow(ctx, "SELECT created_by::text FROM sources WHERE id = $1", document.SourceID).Scan(&sourceCreator); err != nil {
		return domain.Source{}, domain.Document{}, domain.DocumentReview{}, err
	}
	if sourceCreator == actorID && !allowSelfReview {
		return domain.Source{}, domain.Document{}, domain.DocumentReview{}, ErrSelfReview
	}
	if err := validateReviewClaim(ctx, tx, document, input.ClaimToken, actorID); err != nil {
		return domain.Source{}, domain.Document{}, domain.DocumentReview{}, err
	}

	nextStatus, reason, err := normalizeDocumentReview(
		input.Decision, input.Reason, input.DocumentQualityScores,
	)
	if err != nil {
		return domain.Source{}, domain.Document{}, domain.DocumentReview{}, err
	}
	updated, review, err := reviewDocumentTx(ctx, tx, document, input, nextStatus, reason, actorID)
	if err != nil {
		return domain.Source{}, domain.Document{}, domain.DocumentReview{}, err
	}

	if err := refreshSourceDocumentReviewCounts(ctx, tx, document.SourceID, true); err != nil {
		return domain.Source{}, domain.Document{}, domain.DocumentReview{}, err
	}
	source, err := scanSource(tx.QueryRow(ctx,
		"SELECT "+sourceColumns+" FROM sources WHERE id = $1", document.SourceID,
	))
	if err != nil {
		return domain.Source{}, domain.Document{}, domain.DocumentReview{}, err
	}

	if err := tx.Commit(ctx); err != nil {
		return domain.Source{}, domain.Document{}, domain.DocumentReview{}, err
	}
	return source, updated, review, nil
}

func (r *Documents) BulkReview(
	ctx context.Context,
	sourceID string,
	input domain.BulkReviewDocumentsInput,
	actorID string,
	allowSelfReview bool,
) (domain.BulkDocumentReviewResult, error) {
	if len(input.Documents) == 0 || len(input.Documents) > 200 {
		return domain.BulkDocumentReviewResult{}, &GateError{Reasons: []string{"invalid_document_count"}}
	}
	input.ClaimToken = strings.TrimSpace(input.ClaimToken)
	if !uuidPattern.MatchString(input.ClaimToken) {
		return domain.BulkDocumentReviewResult{}, ErrClaimLost
	}
	nextStatus, reason, err := normalizeDocumentReview(
		input.Decision, input.Reason, input.DocumentQualityScores,
	)
	if err != nil {
		return domain.BulkDocumentReviewResult{}, err
	}

	versions := make(map[string]int64, len(input.Documents))
	documentIDs := make([]string, 0, len(input.Documents))
	for _, item := range input.Documents {
		id := strings.TrimSpace(item.DocumentID)
		if id == "" || item.DocumentVersion <= 0 {
			return domain.BulkDocumentReviewResult{}, &GateError{Reasons: []string{"invalid_document_reference"}}
		}
		if _, exists := versions[id]; exists {
			return domain.BulkDocumentReviewResult{}, &GateError{Reasons: []string{"duplicate_document_reference"}}
		}
		versions[id] = item.DocumentVersion
		documentIDs = append(documentIDs, id)
	}

	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return domain.BulkDocumentReviewResult{}, err
	}
	defer tx.Rollback(ctx)

	var sourceCreator string
	if err := tx.QueryRow(ctx,
		"SELECT created_by::text FROM sources WHERE id = $1", sourceID,
	).Scan(&sourceCreator); errors.Is(err, pgx.ErrNoRows) {
		return domain.BulkDocumentReviewResult{}, ErrNotFound
	} else if err != nil {
		return domain.BulkDocumentReviewResult{}, err
	}
	if sourceCreator == actorID && !allowSelfReview {
		return domain.BulkDocumentReviewResult{}, ErrSelfReview
	}

	rows, err := tx.Query(ctx, `
		SELECT `+documentColumns+`
		FROM documents
		WHERE source_id = $1 AND is_active AND id = ANY($2::uuid[])
		ORDER BY source_ordinal
		FOR UPDATE
	`, sourceID, documentIDs)
	if err != nil {
		return domain.BulkDocumentReviewResult{}, err
	}
	documents := make([]domain.Document, 0, len(documentIDs))
	for rows.Next() {
		document, err := scanDocument(rows)
		if err != nil {
			rows.Close()
			return domain.BulkDocumentReviewResult{}, err
		}
		documents = append(documents, document)
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		return domain.BulkDocumentReviewResult{}, err
	}
	rows.Close()
	if len(documents) != len(documentIDs) {
		return domain.BulkDocumentReviewResult{}, ErrNotFound
	}
	claimRows, err := tx.Query(ctx, `
		SELECT claim.document_id
		FROM document_review_claims AS claim
		JOIN documents AS document ON document.id = claim.document_id
		WHERE claim.document_id = ANY($1::uuid[])
		  AND claim.reviewer_id = $2::uuid
		  AND claim.claim_token = $3::uuid
		  AND claim.expires_at > now()
		  AND claim.document_version = document.current_version
		ORDER BY claim.document_id
		FOR UPDATE OF claim
	`, documentIDs, actorID, input.ClaimToken)
	if err != nil {
		return domain.BulkDocumentReviewResult{}, err
	}
	claimedCount := 0
	for claimRows.Next() {
		claimedCount++
	}
	if err := claimRows.Err(); err != nil {
		claimRows.Close()
		return domain.BulkDocumentReviewResult{}, err
	}
	claimRows.Close()
	if claimedCount != len(documentIDs) {
		return domain.BulkDocumentReviewResult{}, ErrClaimLost
	}
	var lockedSourceID string
	if err := tx.QueryRow(ctx,
		"SELECT id::text FROM sources WHERE id = $1 FOR UPDATE", sourceID,
	).Scan(&lockedSourceID); err != nil {
		return domain.BulkDocumentReviewResult{}, err
	}

	updatedDocuments := make([]domain.Document, 0, len(documents))
	reviews := make([]domain.DocumentReview, 0, len(documents))
	for _, document := range documents {
		if document.CurrentVersion != versions[document.ID] {
			return domain.BulkDocumentReviewResult{}, ErrConflict
		}
		if document.Status != "sampled" && document.Status != "edited" {
			return domain.BulkDocumentReviewResult{}, &GateError{Reasons: []string{"document_not_pending"}}
		}
		reviewInput := domain.ReviewDocumentInput{
			DocumentQualityScores: input.DocumentQualityScores,
			Decision:              input.Decision,
			Reason:                reason,
			DocumentVersion:       document.CurrentVersion,
			ClaimToken:            input.ClaimToken,
		}
		updated, review, err := reviewDocumentTx(
			ctx, tx, document, reviewInput, nextStatus, reason, actorID,
		)
		if err != nil {
			return domain.BulkDocumentReviewResult{}, err
		}
		updatedDocuments = append(updatedDocuments, updated)
		reviews = append(reviews, review)
	}

	if err := refreshSourceDocumentReviewCounts(ctx, tx, sourceID, true); err != nil {
		return domain.BulkDocumentReviewResult{}, err
	}
	source, err := scanSource(tx.QueryRow(ctx,
		"SELECT "+sourceColumns+" FROM sources WHERE id = $1", sourceID,
	))
	if err != nil {
		return domain.BulkDocumentReviewResult{}, err
	}
	bulkAuditDetails, _ := json.Marshal(map[string]any{
		"decision":                  input.Decision,
		"rubric_version":            domain.MultidimensionalQualityRubric,
		"quality_score":             input.QualityScore,
		"language_quality_score":    input.LanguageQualityScore,
		"coherence_score":           input.CoherenceScore,
		"information_density_score": input.InformationDensityScore,
		"cleanliness_score":         input.CleanlinessScore,
		"document_count":            len(updatedDocuments),
		"document_ids":              documentIDs,
		"reason":                    reason,
	})
	if _, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES ($1, 'documents.bulk_reviewed', 'source', $2, $3::jsonb)
	`, actorID, sourceID, bulkAuditDetails); err != nil {
		return domain.BulkDocumentReviewResult{}, fmt.Errorf("audit bulk document review: %w", err)
	}

	if err := tx.Commit(ctx); err != nil {
		return domain.BulkDocumentReviewResult{}, err
	}
	return domain.BulkDocumentReviewResult{
		Source: source, Documents: updatedDocuments, Reviews: reviews,
	}, nil
}

func validateReviewClaim(
	ctx context.Context,
	tx pgx.Tx,
	document domain.Document,
	claimToken, actorID string,
) error {
	claimToken = strings.TrimSpace(claimToken)
	if !uuidPattern.MatchString(claimToken) {
		return ErrClaimLost
	}
	var valid bool
	if err := tx.QueryRow(ctx, `
		SELECT true
		FROM document_review_claims
		WHERE document_id = $1::uuid
		  AND reviewer_id = $2::uuid
		  AND claim_token = $3::uuid
		  AND document_version = $4
		  AND expires_at > now()
		FOR UPDATE
	`, document.ID, actorID, claimToken, document.CurrentVersion).Scan(&valid); errors.Is(err, pgx.ErrNoRows) {
		return ErrClaimLost
	} else if err != nil {
		return err
	}
	if !valid {
		return ErrClaimLost
	}
	return nil
}

func newUUID() (string, error) {
	value := make([]byte, 16)
	if _, err := rand.Read(value); err != nil {
		return "", err
	}
	value[6] = (value[6] & 0x0f) | 0x40
	value[8] = (value[8] & 0x3f) | 0x80
	return fmt.Sprintf(
		"%08x-%04x-%04x-%04x-%012x",
		value[0:4], value[4:6], value[6:8], value[8:10], value[10:16],
	), nil
}

func normalizeDocumentReview(
	decision string,
	inputReason *string,
	scores domain.DocumentQualityScores,
) (string, *string, error) {
	reason := trimReason(inputReason)
	invalidScores := []string{}
	for _, score := range []struct {
		value  int16
		reason string
	}{
		{scores.QualityScore, "quality_score_required"},
		{scores.LanguageQualityScore, "language_quality_score_required"},
		{scores.CoherenceScore, "coherence_score_required"},
		{scores.InformationDensityScore, "information_density_score_required"},
		{scores.CleanlinessScore, "cleanliness_score_required"},
	} {
		if score.value < 1 || score.value > 5 {
			invalidScores = append(invalidScores, score.reason)
		}
	}
	if len(invalidScores) > 0 {
		return "", nil, &GateError{Reasons: invalidScores}
	}
	if decision != "approved" && reason == nil {
		return "", nil, &GateError{Reasons: []string{"reason_required"}}
	}
	nextStatus, valid := map[string]string{
		"approved":         "approved",
		"rejected":         "rejected",
		"sensitive_review": "sensitive_review",
	}[decision]
	if !valid {
		return "", nil, &GateError{Reasons: []string{"invalid_decision"}}
	}
	return nextStatus, reason, nil
}

func reviewDocumentTx(
	ctx context.Context,
	tx pgx.Tx,
	document domain.Document,
	input domain.ReviewDocumentInput,
	nextStatus string,
	reason *string,
	actorID string,
) (domain.Document, domain.DocumentReview, error) {
	var alreadyReviewed bool
	if err := tx.QueryRow(ctx, `
		SELECT EXISTS (
			SELECT 1 FROM document_reviews
			WHERE document_id = $1 AND document_version = $2 AND reviewer_id = $3
		)
	`, document.ID, input.DocumentVersion, actorID).Scan(&alreadyReviewed); err != nil {
		return domain.Document{}, domain.DocumentReview{}, err
	}
	if alreadyReviewed {
		return domain.Document{}, domain.DocumentReview{}, ErrConflict
	}

	updated, err := scanDocument(tx.QueryRow(ctx, `
		UPDATE documents
		SET status = $1
		WHERE id = $2 AND current_version = $3
		RETURNING `+documentColumns,
		nextStatus, document.ID, input.DocumentVersion,
	))
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.Document{}, domain.DocumentReview{}, ErrConflict
	}
	if err != nil {
		return domain.Document{}, domain.DocumentReview{}, err
	}

	contextJSON, _ := json.Marshal(map[string]any{
		"source_id":         document.SourceID,
		"previous_status":   document.Status,
		"sampling_method":   document.SamplingMethod,
		"sample_generation": document.SampleGeneration,
		"risk_score":        document.RiskScore,
		"risk_reasons":      document.RiskReasons,
	})
	var review domain.DocumentReview
	if err := tx.QueryRow(ctx, `
		INSERT INTO document_reviews(
			document_id, reviewer_id, decision, reason, rubric_version,
			quality_score, language_quality_score, coherence_score,
			information_density_score, cleanliness_score,
			document_version, object_sha256, review_context
		)
		VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, $12, $13::jsonb
		)
		RETURNING id::text, document_id::text, reviewer_id::text, decision, reason,
			rubric_version, quality_score, language_quality_score, coherence_score,
			information_density_score, cleanliness_score,
			document_version, object_sha256, review_context, created_at
	`, document.ID, actorID, input.Decision, reason,
		domain.MultidimensionalQualityRubric, input.QualityScore,
		input.LanguageQualityScore, input.CoherenceScore,
		input.InformationDensityScore, input.CleanlinessScore,
		input.DocumentVersion, document.CurrentObjectSHA256, contextJSON,
	).Scan(
		&review.ID, &review.DocumentID, &review.ReviewerID, &review.Decision,
		&review.Reason, &review.RubricVersion, &review.QualityScore,
		&review.LanguageQualityScore, &review.CoherenceScore,
		&review.InformationDensityScore, &review.CleanlinessScore,
		&review.DocumentVersion, &review.ObjectSHA256, &review.Context, &review.CreatedAt,
	); err != nil {
		return domain.Document{}, domain.DocumentReview{}, fmt.Errorf("insert document review: %w", err)
	}

	reviewAuditDetails, _ := json.Marshal(map[string]any{
		"review_id":                 review.ID,
		"decision":                  input.Decision,
		"rubric_version":            domain.MultidimensionalQualityRubric,
		"quality_score":             input.QualityScore,
		"language_quality_score":    input.LanguageQualityScore,
		"coherence_score":           input.CoherenceScore,
		"information_density_score": input.InformationDensityScore,
		"cleanliness_score":         input.CleanlinessScore,
		"document_version":          input.DocumentVersion,
		"object_sha256":             document.CurrentObjectSHA256,
		"sample_generation":         document.SampleGeneration,
		"reason":                    reason,
	})
	if _, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES ($1, 'document.reviewed', 'document', $2, $3::jsonb)
	`, actorID, document.ID, reviewAuditDetails); err != nil {
		return domain.Document{}, domain.DocumentReview{}, fmt.Errorf("audit document review: %w", err)
	}
	return updated, review, nil
}

func (r *Documents) ListReviews(ctx context.Context, documentID string) ([]domain.DocumentReview, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT id::text, document_id::text, reviewer_id::text, decision, reason,
			rubric_version, quality_score, language_quality_score, coherence_score,
			information_density_score, cleanliness_score,
			document_version, object_sha256, review_context, created_at
		FROM document_reviews
		WHERE document_id = $1
		ORDER BY created_at DESC, id DESC
	`, documentID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	reviews := []domain.DocumentReview{}
	for rows.Next() {
		var review domain.DocumentReview
		if err := rows.Scan(
			&review.ID, &review.DocumentID, &review.ReviewerID, &review.Decision,
			&review.Reason, &review.RubricVersion, &review.QualityScore,
			&review.LanguageQualityScore, &review.CoherenceScore,
			&review.InformationDensityScore, &review.CleanlinessScore,
			&review.DocumentVersion, &review.ObjectSHA256, &review.Context, &review.CreatedAt,
		); err != nil {
			return nil, err
		}
		reviews = append(reviews, review)
	}
	return reviews, rows.Err()
}

func (r *Documents) QualitySummary(ctx context.Context, sourceID string) (domain.DocumentQualitySummary, error) {
	var summary domain.DocumentQualitySummary
	err := r.pool.QueryRow(ctx, `
		SELECT
			$1::text,
			$2::text,
			count(review.id) FILTER (
				WHERE review.rubric_version = $2
			)::bigint,
			count(DISTINCT review.document_id) FILTER (
				WHERE review.rubric_version = $2
			)::bigint,
			count(review.id) FILTER (
				WHERE review.rubric_version = 'overall-v1'
			)::bigint,
			avg(review.quality_score) FILTER (
				WHERE review.rubric_version = $2
			)::float8,
			avg(review.language_quality_score) FILTER (
				WHERE review.rubric_version = $2
			)::float8,
			avg(review.coherence_score) FILTER (
				WHERE review.rubric_version = $2
			)::float8,
			avg(review.information_density_score) FILTER (
				WHERE review.rubric_version = $2
			)::float8,
			avg(review.cleanliness_score) FILTER (
				WHERE review.rubric_version = $2
			)::float8
		FROM documents AS document
		LEFT JOIN document_reviews AS review
		  ON review.document_id = document.id
		 AND review.document_version = document.current_version
		 AND review.object_sha256 = document.current_object_sha256
		WHERE document.source_id = $1::uuid AND document.is_active
	`, sourceID, domain.MultidimensionalQualityRubric).Scan(
		&summary.SourceID, &summary.RubricVersion,
		&summary.ReviewCount, &summary.DocumentCount, &summary.LegacyReviewCount,
		&summary.AverageQualityScore, &summary.AverageLanguageQualityScore,
		&summary.AverageCoherenceScore, &summary.AverageInformationDensityScore,
		&summary.AverageCleanlinessScore,
	)
	return summary, err
}

func refreshSourceDocumentReviewCounts(ctx context.Context, tx pgx.Tx, sourceID string, demote bool) error {
	_, err := tx.Exec(ctx, `
		UPDATE sources
		SET reviewed_document_count = (
				SELECT count(*) FROM documents
				WHERE source_id = $1 AND is_active
				  AND status IN ('approved', 'rejected', 'sensitive_review')
			),
			approved_document_count = (
				SELECT count(*) FROM documents
				WHERE source_id = $1 AND is_active AND status = 'approved'
			),
			flagged_document_count = (
				SELECT count(*) FROM documents
				WHERE source_id = $1 AND is_active
				  AND status IN ('rejected', 'sensitive_review')
			),
			approval_status = CASE
				WHEN $2 AND approval_status IN ('approved_source', 'release_candidate')
					THEN 'sampled_for_review'
				ELSE approval_status
			END
		WHERE id = $1
	`, sourceID, demote)
	if err != nil {
		return fmt.Errorf("refresh source document review counts: %w", err)
	}
	return nil
}

const documentColumns = `
	id::text, source_id::text, source_ordinal, external_id,
	current_object_sha256, text_preview, byte_size, char_count,
	status, current_version, sampling_method, risk_score, risk_reasons,
	is_active, sample_generation,
	created_at, updated_at`

func scanDocument(row scanner) (domain.Document, error) {
	var document domain.Document
	err := row.Scan(
		&document.ID, &document.SourceID, &document.SourceOrdinal, &document.ExternalID,
		&document.CurrentObjectSHA256, &document.TextPreview, &document.ByteSize,
		&document.CharCount, &document.Status, &document.CurrentVersion,
		&document.SamplingMethod, &document.RiskScore, &document.RiskReasons,
		&document.IsActive, &document.SampleGeneration,
		&document.CreatedAt, &document.UpdatedAt,
	)
	return document, err
}

func DocumentPreview(content string) string {
	preview := strings.Join(strings.Fields(content), " ")
	if len([]rune(preview)) <= 240 {
		return preview
	}
	return string([]rune(preview)[:240]) + "…"
}
