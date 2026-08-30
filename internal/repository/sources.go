package repository

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"path/filepath"
	"strconv"
	"strings"
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
	if input.DerivedFromSourceID != nil {
		var parentID string
		err := tx.QueryRow(ctx, `
			SELECT id::text
			FROM sources
			WHERE id = $1
			FOR KEY SHARE
		`, *input.DerivedFromSourceID).Scan(&parentID)
		if errors.Is(err, pgx.ErrNoRows) {
			return domain.Source{}, ErrNotFound
		}
		if err != nil {
			return domain.Source{}, fmt.Errorf("validate derived source parent: %w", err)
		}
	}

	row := tx.QueryRow(ctx, `
		INSERT INTO sources(
			name, source_type, content_purpose, license, rights_status,
			language, domain, source_url, license_evidence_ref, lineage_ref,
			derived_from_source_id, created_by
		)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
		RETURNING `+sourceColumns,
		input.Name, input.SourceType, input.ContentPurpose, input.License, input.RightsStatus,
		input.Language, input.Domain, input.SourceURL, input.LicenseEvidenceRef, input.LineageRef,
		input.DerivedFromSourceID, actorID,
	)
	source, err := scanSource(row)
	if err != nil {
		return domain.Source{}, fmt.Errorf("insert source: %w", err)
	}

	details, _ := json.Marshal(map[string]any{
		"name":                         source.Name,
		"content_purpose":              source.ContentPurpose,
		"rights_status":                source.RightsStatus,
		"derived_from_source_id":       source.DerivedFromSourceID,
		"data_profile_key":             source.DataProfileKey,
		"data_profile_version":         source.DataProfileVersion,
		"profile_config_artifact_kind": source.ProfileConfigArtifactKind,
		"profile_config_sha256":        source.ProfileConfigSHA256,
		"profile_assignment_reason":    source.ProfileAssignmentReason,
		"profile_assigned_at":          source.ProfileAssignedAt,
		"data_origin":                  source.DataOrigin,
		"production_run_id":            source.ProductionRunID,
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
		"source_id":         sourceID,
		"local_path":        localPath,
		"original_filename": filepath.Base(localPath),
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

	var objectSHA256, productionRunID *string
	var dataOrigin string
	if err := tx.QueryRow(ctx, `
		SELECT object_sha256, data_origin, production_run_id::text
		FROM sources
		WHERE id = $1
		FOR UPDATE
	`, sourceID).Scan(
		&objectSHA256, &dataOrigin, &productionRunID,
	); errors.Is(err, pgx.ErrNoRows) {
		return "", ErrNotFound
	} else if err != nil {
		return "", err
	}
	if objectSHA256 != nil {
		return "", ErrConflict
	}
	// A production run is immutable provenance, not a label that a later
	// browser/server upload may inherit. Model/hybrid sources are populated only
	// by the worker's run-bound distillation handoff. This also leaves a source
	// whose distillation failed terminally fail-closed instead of allowing an
	// unrelated file to masquerade as that run's output.
	if productionRunID != nil || dataOrigin == "model" || dataOrigin == "hybrid" {
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
	derived_from_source_id::text,
	data_profile_key, data_profile_version,
	profile_config_artifact_kind, profile_config_sha256,
	profile_assignment_reason, profile_assigned_at, data_origin,
	production_run_id::text,
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
		&source.DerivedFromSourceID,
		&source.DataProfileKey, &source.DataProfileVersion,
		&source.ProfileConfigArtifactKind, &source.ProfileConfigSHA256,
		&source.ProfileAssignmentReason, &source.ProfileAssignedAt, &source.DataOrigin,
		&source.ProductionRunID,
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

// DistillationInput carries the non-secret generation configuration for a
// distill job. Provider credentials are selected from the worker-owned
// provider registry and are never part of the API or job contract.
type DistillationInput struct {
	Provider       string   `json:"provider"`
	Model          string   `json:"model"`
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
	if input.MaxTokens <= 0 {
		input.MaxTokens = 2000
	}
	if input.Temperature <= 0 {
		input.Temperature = 1
	}
	if input.Topics == nil {
		input.Topics = []string{}
	}
	configSHA256, err := distillationConfigSHA256(input)
	if err != nil {
		return "", fmt.Errorf("hash distillation configuration: %w", err)
	}
	implementationDigest := distillationImplementationDigest()

	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return "", err
	}
	defer tx.Rollback(ctx)

	var objectSHA256, productionRunID *string
	var dataOrigin string
	if err := tx.QueryRow(ctx, `
		SELECT object_sha256, data_origin, production_run_id::text
		FROM sources
		WHERE id = $1
		FOR UPDATE
	`, sourceID).Scan(
		&objectSHA256, &dataOrigin, &productionRunID,
	); errors.Is(err, pgx.ErrNoRows) {
		return "", ErrNotFound
	} else if err != nil {
		return "", err
	}
	if objectSHA256 != nil || dataOrigin != "unknown" || productionRunID != nil {
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

	var runID string
	if err := tx.QueryRow(ctx, `
		INSERT INTO production_runs(
			run_kind, origin_kind, implementation_key,
			implementation_digest, config_sha256, created_by
		)
		VALUES ('model_generation', 'model', $1, $2, $3, $4)
		RETURNING id::text
	`, distillationImplementationKey, implementationDigest,
		configSHA256, actorID).Scan(&runID); err != nil {
		return "", fmt.Errorf("record distillation production run: %w", err)
	}

	command, err := tx.Exec(ctx, `
		UPDATE sources
		SET data_origin = 'model', production_run_id = $2
		WHERE id = $1
		  AND object_sha256 IS NULL
		  AND data_origin = 'unknown'
		  AND production_run_id IS NULL
	`, sourceID, runID)
	if err != nil {
		return "", fmt.Errorf("finalize distillation source provenance: %w", err)
	}
	if command.RowsAffected() != 1 {
		return "", ErrConflict
	}

	payloadJSON, err := json.Marshal(distillationJobPayload(sourceID, runID, input))
	if err != nil {
		return "", fmt.Errorf("marshal distillation job: %w", err)
	}
	var jobID string
	if err := tx.QueryRow(ctx, `
		INSERT INTO background_jobs(job_type, payload, created_by)
		VALUES ('distill_source', $1::jsonb, $2)
		RETURNING id::text
	`, payloadJSON, actorID).Scan(&jobID); err != nil {
		return "", fmt.Errorf("queue distillation job: %w", err)
	}

	if _, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES (
			$1, 'source.distillation_queued', 'source', $2,
			jsonb_build_object(
				'job_id', $3::text,
				'production_run_id', $4::text,
				'config_sha256', $5::text,
				'implementation_digest', $6::text
			)
		)
	`, actorID, sourceID, jobID, runID, configSHA256,
		implementationDigest); err != nil {
		return "", fmt.Errorf("audit distillation job: %w", err)
	}

	if err := tx.Commit(ctx); err != nil {
		return "", err
	}
	return jobID, nil
}

const distillationImplementationKey = "derlem.worker.distill_source.v1"

const distillationImplementationContract = "derlem.worker.distill_source.v1\nprovider-registry-http-json\njsonl-output"

type distillationRunConfig struct {
	SchemaVersion  string   `json:"schema_version"`
	Provider       string   `json:"provider"`
	Model          string   `json:"model"`
	SystemPrompt   string   `json:"system_prompt"`
	PromptTemplate string   `json:"prompt_template"`
	Topics         []string `json:"topics"`
	Count          int      `json:"count"`
	MaxTokens      int      `json:"max_tokens"`
	Temperature    string   `json:"temperature"`
	SourceName     string   `json:"source_name"`
}

func distillationConfigSHA256(input DistillationInput) (string, error) {
	config := distillationRunConfig{
		SchemaVersion: "derlem.distillation-config.v1",
		Provider:      input.Provider, Model: input.Model,
		SystemPrompt: input.SystemPrompt, PromptTemplate: input.PromptTemplate,
		Topics: input.Topics, Count: input.Count, MaxTokens: input.MaxTokens,
		Temperature: strconv.FormatFloat(input.Temperature, 'g', -1, 64),
		SourceName:  input.SourceName,
	}
	var canonical strings.Builder
	encoder := json.NewEncoder(&canonical)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(config); err != nil {
		return "", err
	}
	canonicalBytes := []byte(strings.TrimSuffix(canonical.String(), "\n"))
	digest := sha256.Sum256(canonicalBytes)
	return fmt.Sprintf("%x", digest), nil
}

func distillationImplementationDigest() string {
	digest := sha256.Sum256([]byte(distillationImplementationContract))
	return fmt.Sprintf("%x", digest)
}

func distillationJobPayload(sourceID, productionRunID string, input DistillationInput) map[string]any {
	return map[string]any{
		"source_id":         sourceID,
		"production_run_id": productionRunID,
		"provider":          input.Provider,
		"model":             input.Model,
		"system_prompt":     input.SystemPrompt,
		"prompt_template":   input.PromptTemplate,
		"topics":            input.Topics,
		"count":             input.Count,
		"max_tokens":        input.MaxTokens,
		"temperature":       input.Temperature,
		"source_name":       input.SourceName,
	}
}
