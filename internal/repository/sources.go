package repository

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/celikbros/derlem/internal/domain"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Sources struct {
	pool *pgxpool.Pool
}

func (r *Sources) Update(ctx context.Context, id string, input domain.UpdateSourceInput, actorID string) (domain.Source, error) {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return domain.Source{}, err
	}
	defer tx.Rollback(ctx)

	before, err := scanSource(tx.QueryRow(ctx, "SELECT "+sourceColumns+" FROM sources WHERE id = $1 FOR UPDATE", id))
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.Source{}, ErrNotFound
	}
	if err != nil {
		return domain.Source{}, err
	}
	if before.Version != input.Version {
		return domain.Source{}, ErrConflict
	}

	updated, err := scanSource(tx.QueryRow(ctx, `
		UPDATE sources
		SET name = $1,
			source_type = $2,
			license = $3,
			rights_status = $4,
			language = $5,
			domain = $6,
			source_url = $7,
			license_evidence_ref = $8,
			lineage_ref = $9,
			approval_status = CASE
				WHEN approval_status IN ('approved_source', 'release_candidate') AND $4 <> 'cleared' THEN 'license_review'
				WHEN approval_status IN ('approved_source', 'release_candidate') THEN 'auto_checked'
				ELSE approval_status
			END
		WHERE id = $10 AND version = $11
		RETURNING `+sourceColumns,
		input.Name, input.SourceType, input.License, input.RightsStatus,
		input.Language, input.Domain, input.SourceURL, input.LicenseEvidenceRef,
		input.LineageRef, id, input.Version,
	))
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.Source{}, ErrConflict
	}
	if err != nil {
		return domain.Source{}, fmt.Errorf("update source: %w", err)
	}

	details, _ := json.Marshal(map[string]any{
		"before": map[string]any{
			"name": before.Name, "license": before.License, "rights_status": before.RightsStatus,
			"language": before.Language, "domain": before.Domain, "source_url": before.SourceURL,
			"license_evidence_ref": before.LicenseEvidenceRef, "lineage_ref": before.LineageRef,
		},
		"after": map[string]any{
			"name": updated.Name, "license": updated.License, "rights_status": updated.RightsStatus,
			"language": updated.Language, "domain": updated.Domain, "source_url": updated.SourceURL,
			"license_evidence_ref": updated.LicenseEvidenceRef, "lineage_ref": updated.LineageRef,
		},
		"source_version": updated.Version,
	})
	if _, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES ($1, 'source.metadata_updated', 'source', $2, $3::jsonb)
	`, actorID, id, details); err != nil {
		return domain.Source{}, fmt.Errorf("audit source update: %w", err)
	}
	if err := tx.Commit(ctx); err != nil {
		return domain.Source{}, err
	}
	return updated, nil
}

func NewSources(pool *pgxpool.Pool) *Sources {
	return &Sources{pool: pool}
}

func (r *Sources) Create(ctx context.Context, input domain.CreateSourceInput, actorID string) (domain.Source, error) {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return domain.Source{}, err
	}
	defer tx.Rollback(ctx)

	row := tx.QueryRow(ctx, `
		INSERT INTO sources(
			name, source_type, content_purpose, license, rights_status,
			language, domain, source_url, license_evidence_ref, lineage_ref, created_by
		)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
		RETURNING `+sourceColumns,
		input.Name, input.SourceType, input.ContentPurpose, input.License, input.RightsStatus,
		input.Language, input.Domain, input.SourceURL, input.LicenseEvidenceRef, input.LineageRef, actorID,
	)
	source, err := scanSource(row)
	if err != nil {
		return domain.Source{}, fmt.Errorf("insert source: %w", err)
	}

	details, _ := json.Marshal(map[string]any{
		"name":            source.Name,
		"content_purpose": source.ContentPurpose,
		"rights_status":   source.RightsStatus,
	})
	if _, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES ($1, 'source.created', 'source', $2, $3::jsonb)
	`, actorID, source.ID, details); err != nil {
		return domain.Source{}, fmt.Errorf("audit source creation: %w", err)
	}

	if err := tx.Commit(ctx); err != nil {
		return domain.Source{}, err
	}
	return source, nil
}

func (r *Sources) Get(ctx context.Context, id string) (domain.Source, error) {
	source, err := scanSource(r.pool.QueryRow(ctx,
		"SELECT "+sourceColumns+" FROM sources WHERE id = $1", id,
	))
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.Source{}, ErrNotFound
	}
	return source, err
}

func (r *Sources) List(ctx context.Context, limit int, beforeTime *time.Time, beforeID string) ([]domain.Source, error) {
	query := "SELECT " + sourceColumns + " FROM sources"
	args := []any{}
	if beforeTime != nil {
		query += " WHERE (created_at, id) < ($1, $2)"
		args = append(args, *beforeTime, beforeID)
	}
	query += fmt.Sprintf(" ORDER BY created_at DESC, id DESC LIMIT $%d", len(args)+1)
	args = append(args, limit)

	rows, err := r.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	sources := make([]domain.Source, 0, limit)
	for rows.Next() {
		source, err := scanSource(rows)
		if err != nil {
			return nil, err
		}
		sources = append(sources, source)
	}
	return sources, rows.Err()
}

func (r *Sources) QueueLocalIngest(ctx context.Context, sourceID, localPath, actorID string) (string, error) {
	return r.queueIngest(ctx, sourceID, "ingest_local_file", map[string]any{
		"source_id":  sourceID,
		"local_path": localPath,
	}, actorID, map[string]any{"mode": "server_path"})
}

func (r *Sources) QueueStagedIngest(
	ctx context.Context,
	sourceID, stagedPath, originalFilename string,
	byteSize int64,
	actorID string,
) (string, error) {
	return r.queueIngest(ctx, sourceID, "ingest_staged_file", map[string]any{
		"source_id":         sourceID,
		"staged_path":       stagedPath,
		"original_filename": originalFilename,
		"uploaded_bytes":    byteSize,
	}, actorID, map[string]any{
		"mode": "browser_upload", "original_filename": originalFilename, "uploaded_bytes": byteSize,
	})
}

func (r *Sources) queueIngest(
	ctx context.Context,
	sourceID, jobType string,
	payload map[string]any,
	actorID string,
	auditDetails map[string]any,
) (string, error) {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return "", err
	}
	defer tx.Rollback(ctx)

	var objectSHA256 *string
	if err := tx.QueryRow(ctx, "SELECT object_sha256 FROM sources WHERE id = $1 FOR UPDATE", sourceID).Scan(&objectSHA256); errors.Is(err, pgx.ErrNoRows) {
		return "", ErrNotFound
	} else if err != nil {
		return "", err
	}
	if objectSHA256 != nil {
		return "", ErrConflict
	}
	var active bool
	if err := tx.QueryRow(ctx, `
		SELECT EXISTS (
			SELECT 1 FROM background_jobs
			WHERE payload->>'source_id' = $1
			  AND job_type IN ('ingest_local_file', 'ingest_staged_file', 'distill_source')
			  AND status IN ('queued', 'running')
		)
	`, sourceID).Scan(&active); err != nil {
		return "", err
	}
	if active {
		return "", ErrConflict
	}

	payloadJSON, _ := json.Marshal(payload)
	var jobID string
	if err := tx.QueryRow(ctx, `
		INSERT INTO background_jobs(job_type, payload, created_by)
		VALUES ($1, $2::jsonb, $3)
		RETURNING id::text
	`, jobType, payloadJSON, actorID).Scan(&jobID); err != nil {
		return "", fmt.Errorf("queue ingest job: %w", err)
	}
	auditDetails["job_id"] = jobID
	auditDetails["job_type"] = jobType
	auditJSON, _ := json.Marshal(auditDetails)
	if _, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES ($1, 'source.ingest_queued', 'source', $2, $3::jsonb)
	`, actorID, sourceID, auditJSON); err != nil {
		return "", fmt.Errorf("audit ingest job: %w", err)
	}
	if err := tx.Commit(ctx); err != nil {
		return "", err
	}
	return jobID, nil
}

const sourceColumns = `
	id::text, name, source_type, content_purpose, license, rights_status,
	language, domain, source_url, license_evidence_ref, lineage_ref,
	declared_sha256, declared_byte_size, declared_line_count, source_metadata,
	object_sha256, byte_size, line_count, document_count,
	document_sampling_status, document_sample_generation, document_sampling_method,
	sampled_document_count, reviewed_document_count,
	approved_document_count, flagged_document_count, detected_encoding,
	pii_status, duplicate_status, duplicate_of_source_id::text,
	normalized_dedup_status, normalized_duplicate_count, normalized_duplicate_source_count,
	risk_level, approval_status, version, created_by::text,
	created_at, updated_at`

type scanner interface {
	Scan(...any) error
}

func scanSource(row scanner) (domain.Source, error) {
	var source domain.Source
	err := row.Scan(
		&source.ID, &source.Name, &source.SourceType, &source.ContentPurpose,
		&source.License, &source.RightsStatus, &source.Language, &source.Domain,
		&source.SourceURL, &source.LicenseEvidenceRef, &source.LineageRef,
		&source.DeclaredSHA256, &source.DeclaredByteSize, &source.DeclaredLineCount, &source.SourceMetadata,
		&source.ObjectSHA256, &source.ByteSize, &source.LineCount, &source.DocumentCount,
		&source.DocumentSamplingStatus, &source.DocumentSampleGeneration,
		&source.DocumentSamplingMethod, &source.SampledDocumentCount,
		&source.ReviewedDocumentCount, &source.ApprovedDocumentCount, &source.FlaggedDocumentCount,
		&source.DetectedEncoding,
		&source.PIIStatus, &source.DuplicateStatus,
		&source.DuplicateOfSourceID,
		&source.NormalizedDedupStatus, &source.NormalizedDuplicateCount,
		&source.NormalizedDuplicateSourceCount,
		&source.RiskLevel,
		&source.ApprovalStatus, &source.Version, &source.CreatedBy,
		&source.CreatedAt, &source.UpdatedAt,
	)
	return source, err
}

// DistillationInput carries the generation configuration for a distill job.
// The API key itself is never accepted here — only the name of the worker
// environment variable that holds it.
type DistillationInput struct {
	Provider       string   `json:"provider"`
	Model          string   `json:"model"`
	APIKeyEnv      string   `json:"api_key_env"`
	SystemPrompt   string   `json:"system_prompt"`
	PromptTemplate string   `json:"prompt_template"`
	Topics         []string `json:"topics"`
	Count          int      `json:"count"`
	MaxTokens      int      `json:"max_tokens"`
	Temperature    float64  `json:"temperature"`
	SourceName     string   `json:"source_name"`
}

// QueueDistillation queues a distill_source job for a registered source that
// has no object yet, mirroring the ingest-queue guards.
func (r *Sources) QueueDistillation(ctx context.Context, sourceID string, input DistillationInput, actorID string) (string, error) {
	payload := map[string]any{
		"source_id":       sourceID,
		"provider":        input.Provider,
		"model":           input.Model,
		"api_key_env":     input.APIKeyEnv,
		"system_prompt":   input.SystemPrompt,
		"prompt_template": input.PromptTemplate,
		"topics":          input.Topics,
		"count":           input.Count,
		"max_tokens":      input.MaxTokens,
		"temperature":     input.Temperature,
		"source_name":     input.SourceName,
	}
	return r.queueIngest(ctx, sourceID, "distill_source", payload, actorID, map[string]any{
		"mode": "distillation", "provider": input.Provider, "model": input.Model,
	})
}
