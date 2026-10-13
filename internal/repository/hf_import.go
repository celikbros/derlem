package repository

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/celikbros/derlem/internal/domain"
)

// QueueHFImport, HF alimi icin kaynagi olusturur ve import_hf_dataset isini ayni
// transaction'da kuyruga alir (TASK-032). Ayni uyarlayici yolu icin aktif bir alim
// isi varsa ErrConflict doner: iki is ayni veriyi iki kez indirmesin.
func (r *Sources) QueueHFImport(
	ctx context.Context,
	input domain.CreateSourceInput,
	adapterPath string,
	lineageNote *string,
	actorID string,
) (domain.Source, string, error) {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return domain.Source{}, "", err
	}
	defer tx.Rollback(ctx)

	// Ayni uyarlayici icin eszamanli iki istek ayni anda bos kume gormesin.
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtextextended('derlem.import_hf_dataset:' || $1, 0))`, adapterPath); err != nil {
		return domain.Source{}, "", fmt.Errorf("lock hf import: %w", err)
	}
	var active bool
	if err := tx.QueryRow(ctx, `
		SELECT EXISTS (
			SELECT 1 FROM background_jobs
			WHERE job_type = 'import_hf_dataset'
			  AND payload->>'adapter_path' = $1
			  AND status IN ('queued', 'running')
		)
	`, adapterPath).Scan(&active); err != nil {
		return domain.Source{}, "", err
	}
	if active {
		return domain.Source{}, "", ErrConflict
	}

	source, err := scanSource(tx.QueryRow(ctx, `
		INSERT INTO sources(
			name, source_type, content_purpose, license, rights_status,
			language, domain, source_url, license_evidence_ref, lineage_ref, created_by
		)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
		RETURNING `+sourceColumns,
		input.Name, input.SourceType, input.ContentPurpose, input.License, input.RightsStatus,
		input.Language, input.Domain, input.SourceURL, input.LicenseEvidenceRef, input.LineageRef, actorID,
	))
	if err != nil {
		return domain.Source{}, "", fmt.Errorf("insert hf source: %w", err)
	}
	createdDetails, _ := json.Marshal(map[string]any{
		"name":            source.Name,
		"source_type":     source.SourceType,
		"content_purpose": source.ContentPurpose,
		"rights_status":   source.RightsStatus,
		"data_origin":     source.DataOrigin,
	})
	if _, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES ($1, 'source.created', 'source', $2, $3::jsonb)
	`, actorID, source.ID, createdDetails); err != nil {
		return domain.Source{}, "", fmt.Errorf("audit hf source creation: %w", err)
	}

	payload := map[string]any{"source_id": source.ID, "adapter_path": adapterPath}
	if lineageNote != nil {
		payload["lineage_note"] = *lineageNote
	}
	payloadJSON, _ := json.Marshal(payload)
	var jobID string
	if err := tx.QueryRow(ctx, `
		INSERT INTO background_jobs(job_type, payload, created_by)
		VALUES ('import_hf_dataset', $1::jsonb, $2)
		RETURNING id::text
	`, payloadJSON, actorID).Scan(&jobID); err != nil {
		return domain.Source{}, "", fmt.Errorf("queue hf import job: %w", err)
	}
	queuedDetails, _ := json.Marshal(map[string]any{
		"mode": "hf_dataset", "job_id": jobID, "job_type": "import_hf_dataset", "adapter_path": adapterPath,
	})
	if _, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES ($1, 'source.ingest_queued', 'source', $2, $3::jsonb)
	`, actorID, source.ID, queuedDetails); err != nil {
		return domain.Source{}, "", fmt.Errorf("audit hf import job: %w", err)
	}
	if err := tx.Commit(ctx); err != nil {
		return domain.Source{}, "", err
	}
	return source, jobID, nil
}
