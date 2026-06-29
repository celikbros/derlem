package repository

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/celikbros/derlem/internal/domain"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Releases struct {
	pool *pgxpool.Pool
}

type ReleaseArtifact struct {
	SHA256    string
	Name      string
	MediaType string
	ByteSize  int64
}

func NewReleases(pool *pgxpool.Pool) *Releases {
	return &Releases{pool: pool}
}

func (r *Releases) Create(ctx context.Context, input domain.CreateReleaseInput, actorID string) (domain.Release, error) {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return domain.Release{}, err
	}
	defer tx.Rollback(ctx)

	release, err := scanRelease(tx.QueryRow(ctx, `
		INSERT INTO releases(name, version, content_purpose, created_by)
		VALUES ($1, $2, $3, $4)
		RETURNING `+releaseColumns,
		input.Name, input.Version, input.ContentPurpose, actorID,
	))
	if isUniqueViolation(err) {
		return domain.Release{}, ErrConflict
	}
	if err != nil {
		return domain.Release{}, fmt.Errorf("insert release: %w", err)
	}

	rows, err := tx.Query(ctx, `
		SELECT source.id::text, source.object_sha256, source.version, source.name,
			source.source_type, source.license, source.rights_status, source.language,
			source.domain, source.lineage_ref, source.byte_size, source.line_count,
			object.media_type, source.content_purpose, source.approval_status
		FROM sources AS source
		JOIN storage_objects AS object ON object.sha256 = source.object_sha256
		WHERE source.id = ANY($1::uuid[])
		ORDER BY source.id
		FOR UPDATE OF source
	`, input.SourceIDs)
	if err != nil {
		return domain.Release{}, err
	}
	defer rows.Close()

	sources := make([]domain.ReleaseSource, 0, len(input.SourceIDs))
	for rows.Next() {
		var source domain.ReleaseSource
		var purpose, approvalStatus string
		if err := rows.Scan(
			&source.SourceID, &source.SourceSHA256, &source.SourceVersion, &source.SourceName,
			&source.SourceType, &source.License, &source.RightsStatus, &source.Language,
			&source.Domain, &source.LineageRef, &source.ByteSize, &source.LineCount,
			&source.MediaType, &purpose, &approvalStatus,
		); err != nil {
			return domain.Release{}, err
		}
		if purpose != input.ContentPurpose || approvalStatus != "approved_source" || source.RightsStatus != "cleared" {
			return domain.Release{}, &GateError{Reasons: []string{"source_not_release_eligible"}}
		}
		sources = append(sources, source)
	}
	if err := rows.Err(); err != nil {
		return domain.Release{}, err
	}
	if len(sources) != len(input.SourceIDs) {
		return domain.Release{}, &GateError{Reasons: []string{"source_not_found_or_not_ingested"}}
	}

	for index := range sources {
		source := &sources[index]
		if err := tx.QueryRow(ctx, `
			INSERT INTO release_sources(
				release_id, source_id, source_sha256, source_version, source_name,
				source_type, license, rights_status, language, domain, lineage_ref,
				byte_size, line_count
			)
			VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
			RETURNING added_at
		`, release.ID, source.SourceID, source.SourceSHA256, source.SourceVersion,
			source.SourceName, source.SourceType, source.License, source.RightsStatus,
			source.Language, source.Domain, source.LineageRef, source.ByteSize, source.LineCount,
		).Scan(&source.AddedAt); err != nil {
			return domain.Release{}, fmt.Errorf("insert release source: %w", err)
		}
	}

	if _, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES (
			$1, 'release.created', 'release', $2,
			jsonb_build_object(
				'name', $3::text, 'version', $4::text,
				'content_purpose', $5::text, 'source_ids', to_jsonb($6::text[])
			)
		)
	`, actorID, release.ID, release.Name, release.Version, release.ContentPurpose, input.SourceIDs); err != nil {
		return domain.Release{}, fmt.Errorf("audit release creation: %w", err)
	}

	if err := tx.Commit(ctx); err != nil {
		return domain.Release{}, err
	}
	release.Sources = sources
	release.Exports = []domain.ReleaseExport{}
	return release, nil
}

func (r *Releases) List(ctx context.Context, limit int) ([]domain.Release, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT `+releaseColumns+`
		FROM releases
		ORDER BY created_at DESC, id DESC
		LIMIT $1
	`, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	releases := []domain.Release{}
	for rows.Next() {
		release, err := scanRelease(rows)
		if err != nil {
			return nil, err
		}
		releases = append(releases, release)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	for index := range releases {
		releases[index].Sources, err = listReleaseSources(ctx, r.pool, releases[index].ID)
		if err != nil {
			return nil, err
		}
		releases[index].Exports, err = listReleaseExports(ctx, r.pool, releases[index].ID)
		if err != nil {
			return nil, err
		}
	}
	return releases, nil
}

func (r *Releases) Get(ctx context.Context, id string) (domain.Release, error) {
	release, err := scanRelease(r.pool.QueryRow(ctx,
		"SELECT "+releaseColumns+" FROM releases WHERE id = $1", id,
	))
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.Release{}, ErrNotFound
	}
	if err != nil {
		return domain.Release{}, err
	}
	release.Sources, err = listReleaseSources(ctx, r.pool, release.ID)
	if err != nil {
		return domain.Release{}, err
	}
	release.Exports, err = listReleaseExports(ctx, r.pool, release.ID)
	return release, err
}

func (r *Releases) QueueExport(ctx context.Context, releaseID, exportFormat, actorID string) (domain.ReleaseExport, string, error) {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return domain.ReleaseExport{}, "", err
	}
	defer tx.Rollback(ctx)

	var releaseStatus string
	if err := tx.QueryRow(ctx, "SELECT status FROM releases WHERE id = $1 FOR SHARE", releaseID).Scan(&releaseStatus); errors.Is(err, pgx.ErrNoRows) {
		return domain.ReleaseExport{}, "", ErrNotFound
	} else if err != nil {
		return domain.ReleaseExport{}, "", err
	}
	if releaseStatus != "frozen" {
		return domain.ReleaseExport{}, "", &GateError{Reasons: []string{"release_not_frozen"}}
	}

	export, err := scanReleaseExport(tx.QueryRow(ctx, `
		SELECT `+releaseExportColumns+`
		FROM release_exports
		WHERE release_id = $1 AND format = $2
		FOR UPDATE
	`, releaseID, exportFormat))
	if errors.Is(err, pgx.ErrNoRows) {
		export, err = scanReleaseExport(tx.QueryRow(ctx, `
			INSERT INTO release_exports(release_id, format, created_by)
			VALUES ($1, $2, $3)
			RETURNING `+releaseExportColumns,
			releaseID, exportFormat, actorID,
		))
	} else if err == nil && export.Status == "failed" {
		export, err = scanReleaseExport(tx.QueryRow(ctx, `
			UPDATE release_exports
			SET status = 'queued', last_error = NULL, created_by = $3,
				created_at = now(), completed_at = NULL
			WHERE id = $1 AND release_id = $2
			RETURNING `+releaseExportColumns,
			export.ID, releaseID, actorID,
		))
	} else if err == nil {
		return domain.ReleaseExport{}, "", ErrConflict
	}
	if err != nil {
		return domain.ReleaseExport{}, "", fmt.Errorf("queue release export record: %w", err)
	}

	var jobID string
	err = tx.QueryRow(ctx, `
		INSERT INTO background_jobs(job_type, priority, payload, created_by)
		VALUES (
			'export_release', 60,
			jsonb_build_object(
				'release_id', $1::text, 'export_id', $2::text,
				'format', $3::text, 'requested_by', $4::text
			),
			$4::uuid
		)
		ON CONFLICT DO NOTHING
		RETURNING id::text
	`, releaseID, export.ID, exportFormat, actorID).Scan(&jobID)
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.ReleaseExport{}, "", ErrConflict
	}
	if err != nil {
		return domain.ReleaseExport{}, "", err
	}

	if _, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES (
			$1, 'release.export_queued', 'release', $2,
			jsonb_build_object('export_id', $3::text, 'format', $4::text, 'job_id', $5::text)
		)
	`, actorID, releaseID, export.ID, exportFormat, jobID); err != nil {
		return domain.ReleaseExport{}, "", fmt.Errorf("audit release export queue: %w", err)
	}
	if err := tx.Commit(ctx); err != nil {
		return domain.ReleaseExport{}, "", err
	}
	return export, jobID, nil
}

func (r *Releases) QueueFreeze(ctx context.Context, id, actorID string) (string, error) {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return "", err
	}
	defer tx.Rollback(ctx)

	var status string
	if err := tx.QueryRow(ctx, "SELECT status FROM releases WHERE id = $1 FOR UPDATE", id).Scan(&status); errors.Is(err, pgx.ErrNoRows) {
		return "", ErrNotFound
	} else if err != nil {
		return "", err
	}
	if status != "draft" {
		return "", ErrConflict
	}

	var sourceCount, invalidCount int
	if err := tx.QueryRow(ctx, `
		SELECT count(*), count(*) FILTER (WHERE
			source.object_sha256 IS DISTINCT FROM release_source.source_sha256 OR
			source.version <> release_source.source_version OR
			source.approval_status <> 'approved_source' OR
			source.rights_status <> 'cleared' OR
			source.license_evidence_ref IS NULL OR
			source.pii_status <> 'clear' OR
			source.duplicate_status <> 'unique' OR
			source.normalized_dedup_status <> 'unique' OR
			source.document_sampling_status <> 'sampled' OR
			source.sampled_document_count <= 0 OR
			source.reviewed_document_count <> source.sampled_document_count OR
			source.approved_document_count <> source.sampled_document_count OR
			source.flagged_document_count > 0
		)
		FROM release_sources AS release_source
		JOIN sources AS source ON source.id = release_source.source_id
		WHERE release_source.release_id = $1
	`, id).Scan(&sourceCount, &invalidCount); err != nil {
		return "", err
	}
	if sourceCount == 0 || invalidCount > 0 {
		return "", &GateError{Reasons: []string{"release_sources_changed_or_ineligible"}}
	}

	var jobID string
	err = tx.QueryRow(ctx, `
		INSERT INTO background_jobs(job_type, priority, payload, created_by)
		VALUES (
			'freeze_release', 50,
			jsonb_build_object('release_id', $1::text, 'requested_by', $2::text),
			$2::uuid
		)
		ON CONFLICT DO NOTHING
		RETURNING id::text
	`, id, actorID).Scan(&jobID)
	if errors.Is(err, pgx.ErrNoRows) {
		return "", ErrConflict
	}
	if err != nil {
		return "", err
	}

	if _, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES ($1, 'release.freeze_queued', 'release', $2, jsonb_build_object('job_id', $3::text))
	`, actorID, id, jobID); err != nil {
		return "", fmt.Errorf("audit release freeze queue: %w", err)
	}
	if err := tx.Commit(ctx); err != nil {
		return "", err
	}
	return jobID, nil
}

func (r *Releases) ManifestObject(ctx context.Context, id string) (ReleaseArtifact, error) {
	var artifact ReleaseArtifact
	err := r.pool.QueryRow(ctx, `
		SELECT release.manifest_object_sha256, release.name || '-' || release.version || '-manifest.json',
			object.media_type, object.byte_size
		FROM releases AS release
		JOIN storage_objects AS object ON object.sha256 = release.manifest_object_sha256
		WHERE release.id = $1 AND release.status = 'frozen'
	`, id).Scan(&artifact.SHA256, &artifact.Name, &artifact.MediaType, &artifact.ByteSize)
	if errors.Is(err, pgx.ErrNoRows) {
		return ReleaseArtifact{}, ErrNotFound
	}
	return artifact, err
}

func (r *Releases) SourceArtifact(ctx context.Context, releaseID, sourceID string) (ReleaseArtifact, error) {
	var artifact ReleaseArtifact
	err := r.pool.QueryRow(ctx, `
		SELECT release_source.source_sha256,
			release_source.source_name || '-' || release_source.source_id::text || '.' || release_source.source_type,
			COALESCE(object.media_type, 'application/octet-stream'), object.byte_size
		FROM release_sources AS release_source
		JOIN releases AS release ON release.id = release_source.release_id
		JOIN storage_objects AS object ON object.sha256 = release_source.source_sha256
		WHERE release_source.release_id = $1 AND release_source.source_id = $2
			AND release.status = 'frozen'
	`, releaseID, sourceID).Scan(&artifact.SHA256, &artifact.Name, &artifact.MediaType, &artifact.ByteSize)
	if errors.Is(err, pgx.ErrNoRows) {
		return ReleaseArtifact{}, ErrNotFound
	}
	return artifact, err
}

func (r *Releases) ExportArtifact(ctx context.Context, releaseID, exportFormat string, manifest bool) (ReleaseArtifact, error) {
	digestColumn := "export.object_sha256"
	nameSuffix := "." + exportFormat
	if manifest {
		digestColumn = "export.manifest_object_sha256"
		nameSuffix = "-" + exportFormat + "-manifest.json"
	}
	var artifact ReleaseArtifact
	err := r.pool.QueryRow(ctx, `
		SELECT `+digestColumn+`, release.name || '-' || release.version || $3::text,
			object.media_type, object.byte_size
		FROM release_exports AS export
		JOIN releases AS release ON release.id = export.release_id
		JOIN storage_objects AS object ON object.sha256 = `+digestColumn+`
		WHERE export.release_id = $1 AND export.format = $2
			AND export.status = 'ready' AND release.status = 'frozen'
	`, releaseID, exportFormat, nameSuffix).Scan(
		&artifact.SHA256, &artifact.Name, &artifact.MediaType, &artifact.ByteSize,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return ReleaseArtifact{}, ErrNotFound
	}
	return artifact, err
}

const releaseColumns = `
	id::text, name, version, content_purpose, status,
	manifest_object_sha256, manifest_sha256, gate_results,
	created_by::text, frozen_by::text, created_at, frozen_at`

func scanRelease(row scanner) (domain.Release, error) {
	var release domain.Release
	err := row.Scan(
		&release.ID, &release.Name, &release.Version, &release.ContentPurpose,
		&release.Status, &release.ManifestObjectSHA256, &release.ManifestSHA256,
		&release.GateResults, &release.CreatedBy, &release.FrozenBy,
		&release.CreatedAt, &release.FrozenAt,
	)
	return release, err
}

type releaseSourceQueryer interface {
	Query(context.Context, string, ...any) (pgx.Rows, error)
}

func listReleaseSources(ctx context.Context, queryer releaseSourceQueryer, releaseID string) ([]domain.ReleaseSource, error) {
	rows, err := queryer.Query(ctx, `
		SELECT release_source.source_id::text, release_source.source_sha256,
			release_source.source_version, release_source.source_name,
			release_source.source_type, release_source.license,
			release_source.rights_status, release_source.language,
			release_source.domain, release_source.lineage_ref,
			release_source.byte_size, release_source.line_count,
			object.media_type, release_source.added_at
		FROM release_sources AS release_source
		JOIN storage_objects AS object ON object.sha256 = release_source.source_sha256
		WHERE release_source.release_id = $1
		ORDER BY release_source.source_id
	`, releaseID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	sources := []domain.ReleaseSource{}
	for rows.Next() {
		var source domain.ReleaseSource
		if err := rows.Scan(
			&source.SourceID, &source.SourceSHA256, &source.SourceVersion,
			&source.SourceName, &source.SourceType, &source.License,
			&source.RightsStatus, &source.Language, &source.Domain,
			&source.LineageRef, &source.ByteSize, &source.LineCount,
			&source.MediaType, &source.AddedAt,
		); err != nil {
			return nil, err
		}
		sources = append(sources, source)
	}
	return sources, rows.Err()
}

const releaseExportColumns = `
	id::text, release_id::text, format, status, object_sha256,
	manifest_object_sha256, record_count, byte_size,
	estimated_token_count, token_estimate_lower_bound,
	token_estimate_upper_bound, token_estimate_method, record_type_counts,
	last_error,
	created_by::text, created_at, completed_at`

func scanReleaseExport(row scanner) (domain.ReleaseExport, error) {
	var export domain.ReleaseExport
	err := row.Scan(
		&export.ID, &export.ReleaseID, &export.Format, &export.Status,
		&export.ObjectSHA256, &export.ManifestObjectSHA256, &export.RecordCount,
		&export.ByteSize, &export.EstimatedTokenCount, &export.TokenEstimateLower,
		&export.TokenEstimateUpper, &export.TokenEstimateMethod, &export.RecordTypeCounts,
		&export.LastError, &export.CreatedBy,
		&export.CreatedAt, &export.CompletedAt,
	)
	return export, err
}

func listReleaseExports(ctx context.Context, queryer releaseSourceQueryer, releaseID string) ([]domain.ReleaseExport, error) {
	rows, err := queryer.Query(ctx, `
		SELECT `+releaseExportColumns+`
		FROM release_exports
		WHERE release_id = $1
		ORDER BY format
	`, releaseID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	exports := []domain.ReleaseExport{}
	for rows.Next() {
		export, err := scanReleaseExport(rows)
		if err != nil {
			return nil, err
		}
		exports = append(exports, export)
	}
	return exports, rows.Err()
}

func isUniqueViolation(err error) bool {
	var postgresError *pgconn.PgError
	return errors.As(err, &postgresError) && postgresError.Code == "23505"
}

func NormalizeReleaseInput(input *domain.CreateReleaseInput) {
	input.Name = strings.TrimSpace(input.Name)
	input.Version = strings.TrimSpace(input.Version)
	input.ContentPurpose = strings.TrimSpace(input.ContentPurpose)
	seen := make(map[string]struct{}, len(input.SourceIDs))
	unique := make([]string, 0, len(input.SourceIDs))
	for _, sourceID := range input.SourceIDs {
		sourceID = strings.TrimSpace(sourceID)
		if sourceID == "" {
			continue
		}
		if _, exists := seen[sourceID]; exists {
			continue
		}
		seen[sourceID] = struct{}{}
		unique = append(unique, sourceID)
	}
	input.SourceIDs = unique
}

func ReleaseInputGateReasons(input domain.CreateReleaseInput) []string {
	reasons := []string{}
	if input.Name == "" || len(input.Name) > 120 {
		reasons = append(reasons, "invalid_name")
	}
	if input.Version == "" || len(input.Version) > 80 {
		reasons = append(reasons, "invalid_version")
	}
	if _, valid := domain.ContentPurposes[input.ContentPurpose]; !valid {
		reasons = append(reasons, "invalid_content_purpose")
	}
	if len(input.SourceIDs) == 0 || len(input.SourceIDs) > 10000 {
		reasons = append(reasons, "invalid_source_count")
	}
	return reasons
}
