package repository

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	"github.com/celikbros/derlem/internal/domain"
	"github.com/celikbros/derlem/internal/storage"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

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
		WHERE source_id = $1
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

func (r *Documents) Get(ctx context.Context, id string) (domain.Document, error) {
	document, err := scanDocument(r.pool.QueryRow(ctx,
		"SELECT "+documentColumns+" FROM documents WHERE id = $1", id,
	))
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.Document{}, ErrNotFound
	}
	return document, err
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
			current_version = $5
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

	nextStatus, reason, err := normalizeDocumentReview(input.Decision, input.Reason, input.QualityScore)
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
	nextStatus, reason, err := normalizeDocumentReview(input.Decision, input.Reason, input.QualityScore)
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
		WHERE source_id = $1 AND id = ANY($2::uuid[])
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
			Decision: input.Decision, Reason: reason, QualityScore: input.QualityScore,
			DocumentVersion: document.CurrentVersion,
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
	if _, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES (
			$1, 'documents.bulk_reviewed', 'source', $2,
			jsonb_build_object(
				'decision', $3::text, 'quality_score', $4::smallint,
				'document_count', $5::integer, 'document_ids', to_jsonb($6::text[]),
				'reason', $7::text
			)
		)
	`, actorID, sourceID, input.Decision, input.QualityScore,
		len(updatedDocuments), documentIDs, reason); err != nil {
		return domain.BulkDocumentReviewResult{}, fmt.Errorf("audit bulk document review: %w", err)
	}

	if err := tx.Commit(ctx); err != nil {
		return domain.BulkDocumentReviewResult{}, err
	}
	return domain.BulkDocumentReviewResult{
		Source: source, Documents: updatedDocuments, Reviews: reviews,
	}, nil
}

func normalizeDocumentReview(decision string, inputReason *string, qualityScore int16) (string, *string, error) {
	reason := trimReason(inputReason)
	if qualityScore < 1 || qualityScore > 5 {
		return "", nil, &GateError{Reasons: []string{"quality_score_required"}}
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
		"source_id":       document.SourceID,
		"previous_status": document.Status,
		"sampling_method": document.SamplingMethod,
	})
	var review domain.DocumentReview
	if err := tx.QueryRow(ctx, `
		INSERT INTO document_reviews(
			document_id, reviewer_id, decision, reason, quality_score,
			document_version, object_sha256, review_context
		)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
		RETURNING id::text, document_id::text, reviewer_id::text, decision, reason,
			quality_score, document_version, object_sha256, review_context, created_at
	`, document.ID, actorID, input.Decision, reason, input.QualityScore,
		input.DocumentVersion, document.CurrentObjectSHA256, contextJSON,
	).Scan(
		&review.ID, &review.DocumentID, &review.ReviewerID, &review.Decision,
		&review.Reason, &review.QualityScore, &review.DocumentVersion,
		&review.ObjectSHA256, &review.Context, &review.CreatedAt,
	); err != nil {
		return domain.Document{}, domain.DocumentReview{}, fmt.Errorf("insert document review: %w", err)
	}

	if _, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES (
			$1, 'document.reviewed', 'document', $2,
			jsonb_build_object(
				'review_id', $3::text, 'decision', $4::text,
				'quality_score', $5::smallint, 'document_version', $6::bigint,
				'object_sha256', $7::text, 'reason', $8::text
			)
		)
	`, actorID, document.ID, review.ID, input.Decision, input.QualityScore,
		input.DocumentVersion, document.CurrentObjectSHA256, reason); err != nil {
		return domain.Document{}, domain.DocumentReview{}, fmt.Errorf("audit document review: %w", err)
	}
	return updated, review, nil
}

func (r *Documents) ListReviews(ctx context.Context, documentID string) ([]domain.DocumentReview, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT id::text, document_id::text, reviewer_id::text, decision, reason,
			quality_score, document_version, object_sha256, review_context, created_at
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
			&review.Reason, &review.QualityScore, &review.DocumentVersion,
			&review.ObjectSHA256, &review.Context, &review.CreatedAt,
		); err != nil {
			return nil, err
		}
		reviews = append(reviews, review)
	}
	return reviews, rows.Err()
}

func refreshSourceDocumentReviewCounts(ctx context.Context, tx pgx.Tx, sourceID string, demote bool) error {
	_, err := tx.Exec(ctx, `
		UPDATE sources
		SET reviewed_document_count = (
				SELECT count(*) FROM documents
				WHERE source_id = $1 AND status IN ('approved', 'rejected', 'sensitive_review')
			),
			approved_document_count = (
				SELECT count(*) FROM documents
				WHERE source_id = $1 AND status = 'approved'
			),
			flagged_document_count = (
				SELECT count(*) FROM documents
				WHERE source_id = $1 AND status IN ('rejected', 'sensitive_review')
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
	status, current_version, sampling_method, created_at, updated_at`

func scanDocument(row scanner) (domain.Document, error) {
	var document domain.Document
	err := row.Scan(
		&document.ID, &document.SourceID, &document.SourceOrdinal, &document.ExternalID,
		&document.CurrentObjectSHA256, &document.TextPreview, &document.ByteSize,
		&document.CharCount, &document.Status, &document.CurrentVersion,
		&document.SamplingMethod, &document.CreatedAt, &document.UpdatedAt,
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
