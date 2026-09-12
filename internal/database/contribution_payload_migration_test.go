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

const contributionPayloadMigration = "migrations/000028_contribution_payload.sql"

// TestContributionPayloadMigrationIsInChainAndAddsNoLedgerTrigger, 000028'in
// zincirde olduğunu ve katkı tablosuna satır-değişim tetikleyicisi eklemediğini
// dosya düzeyinde doğrular (payload ham kullanıcı içeriğidir, 000023).
func TestContributionPayloadMigrationIsInChainAndAddsNoLedgerTrigger(t *testing.T) {
	contents, err := migrationFiles.ReadFile(contributionPayloadMigration)
	if err != nil {
		t.Fatalf("read contribution payload migration: %v", err)
	}
	migration := string(contents)
	for _, required := range []string{
		"ALTER TABLE contributions DROP CONSTRAINT contributions_task_type_check",
		"'response_edit_pair'",
		"ADD COLUMN payload jsonb NOT NULL DEFAULT '{}'::jsonb",
		"contributions_payload_object",
		"contributions_model_origin_requires_model_id",
		"contributions_edit_pair_prompt",
	} {
		if !strings.Contains(migration, required) {
			t.Errorf("migration is missing %q", required)
		}
	}
	if strings.Contains(migration, "contributions_capture_row_change") ||
		strings.Contains(migration, "capture_row_change_event(") {
		t.Fatal("contributions must never get a generic row-change trigger")
	}
	if !slices.Contains(expectedMigrationVersions(t), "000028_contribution_payload.sql") {
		t.Fatal("migration list is missing 000028 contribution payload migration")
	}
}

// TestContributionPayloadConstraintsOnPostgres, migrate edilmiş gerçek şemada
// yeni tipin kabul edildiğini, kısıtların reddetmesi gerekeni reddettiğini ve ham
// içerikli bir düzeltme çiftinin satır-değişim defterine hiç olay üretmediğini
// doğrular.
func TestContributionPayloadConstraintsOnPostgres(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	t.Cleanup(cancel)
	// Yardımcı storage testine ait ama geneldir: tüm zinciri izole şemaya uygular.
	pool, schemaName := newStorageObjectsImmutabilityTestPool(t, ctx)

	var contributorID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO users(email, password_hash, display_name)
		VALUES ('payload-migration@example.test', 'test', 'Payload Test')
		RETURNING id::text
	`).Scan(&contributorID); err != nil {
		t.Fatalf("insert contributor: %v", err)
	}

	const rawMarker = "HAM-ICERIK-ISARETI-000028"
	var editPairID, origin string
	if err := pool.QueryRow(ctx, `
		INSERT INTO contributions(
			contributor_id, task_type, prompt, body, payload, terms_ack_version
		)
		VALUES (
			$1, 'response_edit_pair', 'Işık hızı nedir?',
			'Boşlukta yaklaşık 299.792 km/s''dir.',
			jsonb_build_object('original_response', $2::text), 'test-v1'
		)
		RETURNING id::text, data_origin
	`, contributorID, "Saniyede 300 km. "+rawMarker).Scan(&editPairID, &origin); err != nil {
		t.Fatalf("response_edit_pair with a prompt and an object payload must be accepted: %v", err)
	}
	if origin != "human" {
		t.Fatalf("data_origin default = %q, want human", origin)
	}

	// Mevcut iki kolonlu ekleme (varsayılanlarla) çalışmaya devam etmeli.
	if _, err := pool.Exec(ctx, `
		INSERT INTO contributions(contributor_id, task_type, body, terms_ack_version)
		VALUES ($1, 'free_text', 'Eski biçimde serbest metin.', 'test-v1')
	`, contributorID); err != nil {
		t.Fatalf("legacy two-column insert must keep working: %v", err)
	}

	rejected := map[string]string{
		"payload that is not an object": `
			INSERT INTO contributions(contributor_id, task_type, body, payload, terms_ack_version)
			VALUES ($1, 'free_text', 'metin', '[]'::jsonb, 'test-v1')`,
		"edit pair with an empty prompt": `
			INSERT INTO contributions(contributor_id, task_type, prompt, body, terms_ack_version)
			VALUES ($1, 'response_edit_pair', '   ', 'cevap', 'test-v1')`,
		"model origin without model_id": `
			INSERT INTO contributions(contributor_id, task_type, body, data_origin, terms_ack_version)
			VALUES ($1, 'free_text', 'metin', 'model', 'test-v1')`,
		"unknown data origin": `
			INSERT INTO contributions(contributor_id, task_type, body, data_origin, terms_ack_version)
			VALUES ($1, 'free_text', 'metin', 'robot', 'test-v1')`,
		"unknown task type": `
			INSERT INTO contributions(contributor_id, task_type, body, terms_ack_version)
			VALUES ($1, 'translation_pair', 'metin', 'test-v1')`,
	}
	for name, statement := range rejected {
		_, err := pool.Exec(ctx, statement, contributorID)
		var pgErr *pgconn.PgError
		if !errors.As(err, &pgErr) || pgErr.Code != "23514" {
			t.Errorf("%s: want check_violation (23514), got %v", name, err)
		}
	}

	if _, err := pool.Exec(ctx, `
		INSERT INTO contributions(
			contributor_id, task_type, body, data_origin, model_id, terms_ack_version
		)
		VALUES ($1, 'free_text', 'Model çıktısı, gözden geçirildi.', 'hybrid', 'model-x', 'test-v1')
	`, contributorID); err != nil {
		t.Fatalf("hybrid origin with model_id must be accepted: %v", err)
	}

	var contributionEvents int
	if err := pool.QueryRow(ctx, `
		SELECT count(*) FROM row_change_events
		WHERE table_schema = $1 AND table_name = 'contributions'
	`, schemaName).Scan(&contributionEvents); err != nil {
		t.Fatalf("count contribution ledger events: %v", err)
	}
	if contributionEvents != 0 {
		t.Fatalf("contributions produced %d generic ledger events; payload is raw user content", contributionEvents)
	}
	var leaked int
	if err := pool.QueryRow(ctx, `
		SELECT count(*) FROM row_change_events
		WHERE COALESCE(before_summary::text, '') LIKE '%' || $1 || '%'
		   OR COALESCE(after_summary::text, '') LIKE '%' || $1 || '%'
	`, rawMarker).Scan(&leaked); err != nil {
		t.Fatalf("search ledger for raw marker: %v", err)
	}
	if leaked != 0 {
		t.Fatalf("raw contribution content leaked into %d ledger events", leaked)
	}
}
