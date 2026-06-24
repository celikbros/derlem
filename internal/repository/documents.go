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

	if err := tx.Commit(ctx); err != nil {
		return domain.Document{}, err
	}
	return updated, nil
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
