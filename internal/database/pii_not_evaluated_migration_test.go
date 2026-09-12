package database

import (
	"context"
	"errors"
	"slices"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgconn"
)

const piiNotEvaluatedMigration = "migrations/000027_pii_not_evaluated.sql"

// TestPIINotEvaluatedMigrationIsInChain, 000027'nin zincirde olduğunu ve iki
// CHECK kısıtını da yeniden tanımladığını dosya düzeyinde doğrular.
func TestPIINotEvaluatedMigrationIsInChain(t *testing.T) {
	contents, err := migrationFiles.ReadFile(piiNotEvaluatedMigration)
	if err != nil {
		t.Fatalf("read pii not_evaluated migration: %v", err)
	}
	migration := string(contents)
	for _, required := range []string{
		"ALTER TABLE sources DROP CONSTRAINT sources_pii_status_check",
		"ALTER TABLE sources ADD CONSTRAINT sources_pii_status_check",
		"ALTER TABLE pii_scans DROP CONSTRAINT pii_scans_status_check",
		"ALTER TABLE pii_scans ADD CONSTRAINT pii_scans_status_check",
	} {
		if !strings.Contains(migration, required) {
			t.Errorf("migration is missing %q", required)
		}
	}
	if !slices.Contains(expectedMigrationVersions(t), "000027_pii_not_evaluated.sql") {
		t.Fatal("migration list is missing 000027 pii not_evaluated migration")
	}
}

// TestPIINotEvaluatedIsAcceptedAndJunkStillRejectedOnPostgres, migrate edilmiş
// gerçek şemada iki kısıtın not_evaluated'ı kabul ettiğini ve CHECK'in
// gevşemediğini (uydurma değer hâlâ reddedilir) doğrular. Worker bu değeri
// yazar; migration eksik olsaydı üretimde UPDATE check_violation ile düşerdi.
func TestPIINotEvaluatedIsAcceptedAndJunkStillRejectedOnPostgres(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	t.Cleanup(cancel)
	// Yardımcı storage testine ait ama geneldir: tüm zinciri izole şemaya uygular.
	pool, _ := newStorageObjectsImmutabilityTestPool(t, ctx)

	for table, constraint := range map[string]string{
		"sources":   "sources_pii_status_check",
		"pii_scans": "pii_scans_status_check",
	} {
		var definition string
		if err := pool.QueryRow(ctx, `
			SELECT pg_get_constraintdef(oid) FROM pg_constraint
			WHERE conrelid = $1::regclass AND conname = $2
		`, table, constraint).Scan(&definition); err != nil {
			t.Fatalf("read %s: %v", constraint, err)
		}
		if !strings.Contains(definition, "not_evaluated") {
			t.Fatalf("%s does not allow not_evaluated: %s", constraint, definition)
		}
	}

	var userID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO users(email, password_hash, display_name)
		VALUES ('pii-not-evaluated@example.test', 'test', 'PII Test')
		RETURNING id::text
	`).Scan(&userID); err != nil {
		t.Fatalf("insert user: %v", err)
	}
	// Katkı demetinin (repository.Contributions.Bundle) çalışan kaynak eklemesiyle
	// aynı kolonlar; dil bilerek Türkçe dışı.
	var sourceID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO sources(
			name, source_type, content_purpose, license, rights_status,
			language, domain, license_evidence_ref, lineage_ref, created_by
		)
		VALUES (
			'pii-not-evaluated', 'community_contribution', 'pretrain',
			'topluluk-katkisi-ic-sozlesme-v1', 'cleared', 'ku', 'genel',
			'tests/license.txt', 'pii-not-evaluated-test', $1
		)
		RETURNING id::text
	`, userID).Scan(&sourceID); err != nil {
		t.Fatalf("insert source: %v", err)
	}

	if _, err := pool.Exec(ctx, `
		UPDATE sources SET pii_status = 'not_evaluated' WHERE id = $1
	`, sourceID); err != nil {
		t.Fatalf("not_evaluated must be accepted: %v", err)
	}
	_, err := pool.Exec(ctx, `
		UPDATE sources SET pii_status = 'evaluated_somehow' WHERE id = $1
	`, sourceID)
	var pgErr *pgconn.PgError
	if !errors.As(err, &pgErr) || pgErr.Code != "23514" {
		t.Fatalf("unknown pii_status must still violate the CHECK, got: %v", err)
	}
}
