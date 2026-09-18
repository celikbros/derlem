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

const sourceLineageInputsMigration = "migrations/000029_source_lineage_inputs.sql"

// 000029 çoklu girdi soyunu ekler. Bilgi kaydıdır: satır-değişim defterine
// girmez; kendine referans veritabanında reddedilir.
func TestSourceLineageInputsMigrationIsInChainWithoutLedgerTrigger(t *testing.T) {
	contents, err := migrationFiles.ReadFile(sourceLineageInputsMigration)
	if err != nil {
		t.Fatalf("read migration: %v", err)
	}
	migration := string(contents)
	for _, required := range []string{
		"CREATE TABLE source_lineage_inputs",
		"REFERENCES sources(id) ON DELETE CASCADE",
		"REFERENCES sources(id) ON DELETE RESTRICT",
		"source_lineage_inputs_not_self",
	} {
		if !strings.Contains(migration, required) {
			t.Errorf("migration is missing %q", required)
		}
	}
	if strings.Contains(migration, "capture_row_change_event(") {
		t.Fatal("lineage inputs are bookkeeping, not a ledgered row")
	}
	if !slices.Contains(expectedMigrationVersions(t), "000029_source_lineage_inputs.sql") {
		t.Fatal("migration list is missing 000029")
	}
}

func TestSourceLineageInputsConstraintsOnPostgres(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	t.Cleanup(cancel)
	pool, _ := newStorageObjectsImmutabilityTestPool(t, ctx)

	var userID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO users(email, password_hash, display_name)
		VALUES ('lineage-migration@example.test', 'test', 'Lineage Test')
		RETURNING id::text
	`).Scan(&userID); err != nil {
		t.Fatalf("insert user: %v", err)
	}
	newSource := func(name string) string {
		var id string
		if err := pool.QueryRow(ctx, `
			INSERT INTO sources(name, source_type, content_purpose, license, language, domain, lineage_ref, created_by)
			VALUES ($1, 'jsonl', 'pretrain', 'unknown', 'tr', 'test', 'test', $2)
			RETURNING id::text
		`, name, userID).Scan(&id); err != nil {
			t.Fatalf("insert source %s: %v", name, err)
		}
		return id
	}
	parent := newSource("parent")
	input := newSource("input")

	if _, err := pool.Exec(ctx, `INSERT INTO source_lineage_inputs(source_id, input_source_id) VALUES ($1, $2)`, parent, input); err != nil {
		t.Fatalf("insert lineage input: %v", err)
	}
	var pgErr *pgconn.PgError
	_, err := pool.Exec(ctx, `INSERT INTO source_lineage_inputs(source_id, input_source_id) VALUES ($1, $1)`, parent)
	if !errors.As(err, &pgErr) || pgErr.ConstraintName != "source_lineage_inputs_not_self" {
		t.Fatalf("self reference must be rejected by the check constraint, got %v", err)
	}
	_, err = pool.Exec(ctx, `DELETE FROM sources WHERE id = $1`, input)
	// 23001 restrict_violation (ON DELETE RESTRICT), 23503 foreign_key_violation.
	if !errors.As(err, &pgErr) || (pgErr.Code != "23001" && pgErr.Code != "23503") {
		t.Fatalf("an input still referenced by a derivation must not be deletable, got %v", err)
	}
	var ledgerRows int
	if err := pool.QueryRow(ctx, `SELECT count(*) FROM row_change_events WHERE table_name = 'source_lineage_inputs'`).Scan(&ledgerRows); err == nil && ledgerRows != 0 {
		t.Fatalf("lineage inputs must not be ledgered, got %d rows", ledgerRows)
	}
}
