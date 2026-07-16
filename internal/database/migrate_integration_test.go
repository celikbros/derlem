package database

import (
	"context"
	"fmt"
	"io/fs"
	"os"
	"reflect"
	"sort"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type appliedMigration struct {
	version   string
	checksum  string
	appliedAt time.Time
}

func TestMigrateAppliesAllMigrationsAndIsIdempotent(t *testing.T) {
	databaseURL := strings.TrimSpace(os.Getenv("DERLEM_TEST_DATABASE_URL"))
	if databaseURL == "" {
		t.Skip("DERLEM_TEST_DATABASE_URL is not set")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	t.Cleanup(cancel)

	adminConfig, err := pgxpool.ParseConfig(databaseURL)
	if err != nil {
		t.Fatalf("parse DERLEM_TEST_DATABASE_URL: %v", err)
	}
	adminConfig.MaxConns = 2
	adminConfig.MinConns = 0

	adminPool, err := pgxpool.NewWithConfig(ctx, adminConfig)
	if err != nil {
		t.Fatalf("open test database: %v", err)
	}
	t.Cleanup(adminPool.Close)
	if err := adminPool.Ping(ctx); err != nil {
		t.Fatalf("ping test database: %v", err)
	}

	schemaName := fmt.Sprintf("derlem_migration_test_%d", time.Now().UnixNano())
	schemaIdentifier := pgx.Identifier{schemaName}.Sanitize()
	if _, err := adminPool.Exec(ctx, "CREATE SCHEMA "+schemaIdentifier); err != nil {
		t.Fatalf("create isolated test schema: %v", err)
	}
	t.Cleanup(func() {
		cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cleanupCancel()
		if _, err := adminPool.Exec(cleanupCtx, "DROP SCHEMA "+schemaIdentifier+" CASCADE"); err != nil {
			t.Errorf("drop isolated test schema: %v", err)
		}
	})

	migrationConfig, err := pgxpool.ParseConfig(databaseURL)
	if err != nil {
		t.Fatalf("parse migration database URL: %v", err)
	}
	migrationConfig.ConnConfig.RuntimeParams["search_path"] = schemaName
	migrationConfig.MaxConns = 4
	migrationConfig.MinConns = 0

	migrationPool, err := pgxpool.NewWithConfig(ctx, migrationConfig)
	if err != nil {
		t.Fatalf("open isolated migration pool: %v", err)
	}
	t.Cleanup(migrationPool.Close)
	if err := migrationPool.Ping(ctx); err != nil {
		t.Fatalf("ping isolated migration pool: %v", err)
	}
	if _, err := migrationPool.Exec(ctx, `
		CREATE TABLE schema_migrations (
			version text PRIMARY KEY,
			applied_at timestamptz NOT NULL DEFAULT now()
		)
	`); err != nil {
		t.Fatalf("create legacy schema_migrations shape: %v", err)
	}

	expectedVersions := expectedMigrationVersions(t)
	legacyContents, err := migrationFiles.ReadFile("migrations/" + expectedVersions[0])
	if err != nil {
		t.Fatalf("read first migration for legacy setup: %v", err)
	}
	if _, err := migrationPool.Exec(ctx, string(legacyContents)); err != nil {
		t.Fatalf("apply first migration with legacy runner shape: %v", err)
	}
	if _, err := migrationPool.Exec(ctx,
		"INSERT INTO schema_migrations(version) VALUES ($1)",
		expectedVersions[0],
	); err != nil {
		t.Fatalf("record first legacy migration without checksum: %v", err)
	}
	if err := Migrate(ctx, migrationPool); err != nil {
		t.Fatalf("first migration run: %v", err)
	}
	firstRun := appliedMigrations(t, ctx, migrationPool)
	assertAppliedVersions(t, firstRun, expectedVersions)

	if err := Migrate(ctx, migrationPool); err != nil {
		t.Fatalf("second migration run: %v", err)
	}
	secondRun := appliedMigrations(t, ctx, migrationPool)
	assertAppliedVersions(t, secondRun, expectedVersions)
	if !reflect.DeepEqual(secondRun, firstRun) {
		t.Fatalf("second migration run changed schema_migrations: first=%v second=%v", firstRun, secondRun)
	}

	if _, err := migrationPool.Exec(ctx,
		"UPDATE schema_migrations SET checksum = 'tampered' WHERE version = $1",
		expectedVersions[0],
	); err != nil {
		t.Fatalf("tamper migration checksum: %v", err)
	}
	if err := Migrate(ctx, migrationPool); err == nil || !strings.Contains(err.Error(), "checksum mismatch") {
		t.Fatalf("Migrate() after checksum tamper error = %v, want checksum mismatch", err)
	}
}

func expectedMigrationVersions(t *testing.T) []string {
	t.Helper()

	entries, err := fs.ReadDir(migrationFiles, "migrations")
	if err != nil {
		t.Fatalf("read embedded migration files: %v", err)
	}

	versions := make([]string, 0, len(entries))
	for _, entry := range entries {
		if !entry.IsDir() && strings.HasSuffix(entry.Name(), ".sql") {
			versions = append(versions, entry.Name())
		}
	}
	sort.Strings(versions)
	if len(versions) == 0 {
		t.Fatal("no migration files found")
	}
	for i, version := range versions {
		expectedPrefix := fmt.Sprintf("%06d_", i+1)
		if !strings.HasPrefix(version, expectedPrefix) {
			t.Fatalf("migration chain is not contiguous at %q; expected prefix %q", version, expectedPrefix)
		}
	}

	return versions
}

func appliedMigrations(t *testing.T, ctx context.Context, pool *pgxpool.Pool) []appliedMigration {
	t.Helper()

	rows, err := pool.Query(ctx, "SELECT version, checksum, applied_at FROM schema_migrations ORDER BY version")
	if err != nil {
		t.Fatalf("query applied migrations: %v", err)
	}
	defer rows.Close()

	var migrations []appliedMigration
	for rows.Next() {
		var migration appliedMigration
		if err := rows.Scan(&migration.version, &migration.checksum, &migration.appliedAt); err != nil {
			t.Fatalf("scan applied migration: %v", err)
		}
		migrations = append(migrations, migration)
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("iterate applied migrations: %v", err)
	}

	return migrations
}

func assertAppliedVersions(t *testing.T, applied []appliedMigration, expected []string) {
	t.Helper()

	if len(applied) != len(expected) {
		t.Fatalf("applied migration count = %d, migration file count = %d", len(applied), len(expected))
	}
	for i := range expected {
		if applied[i].version != expected[i] {
			t.Fatalf("applied migration %d = %q, expected %q", i, applied[i].version, expected[i])
		}
		if len(applied[i].checksum) != 64 {
			t.Fatalf("migration %q checksum length = %d, want 64", applied[i].version, len(applied[i].checksum))
		}
	}
}
