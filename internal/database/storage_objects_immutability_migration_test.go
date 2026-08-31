package database

import (
	"context"
	"errors"
	"fmt"
	"os"
	"slices"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

const storageObjectsImmutabilityMigration = "migrations/000025_storage_objects_immutability.sql"

func TestStorageObjectsImmutabilityMigrationIsFailClosed(t *testing.T) {
	contents, err := migrationFiles.ReadFile(storageObjectsImmutabilityMigration)
	if err != nil {
		t.Fatalf("read storage object immutability migration: %v", err)
	}
	migration := string(contents)

	for _, required := range []string{
		"SECURITY DEFINER",
		"SET search_path = pg_catalog",
		"FROM pg_catalog.pg_trigger AS trigger_def",
		"JOIN pg_catalog.pg_proc AS function_def",
		"function_schema IS DISTINCT FROM TG_TABLE_SCHEMA",
		"pg_catalog.pg_advisory_xact_lock(",
		"pg_catalog.hashtextextended(",
		"'derlem.storage_objects.sha256:'",
		"existing_storage_key IS DISTINCT FROM NEW.storage_key",
		"existing_byte_size IS DISTINCT FROM NEW.byte_size",
		"existing_immutable IS DISTINCT FROM NEW.immutable",
		"CREATE TRIGGER storage_objects_verify_insert_identity",
		"CREATE TRIGGER storage_objects_no_update",
		"CREATE TRIGGER storage_objects_no_delete",
		"CREATE TRIGGER storage_objects_no_truncate",
		"REVOKE ALL ON FUNCTION enforce_storage_object_insert_identity() FROM PUBLIC",
		"REVOKE ALL ON FUNCTION reject_storage_object_mutation() FROM PUBLIC",
	} {
		if !strings.Contains(migration, required) {
			t.Errorf("migration is missing %q", required)
		}
	}

	if strings.Contains(migration, "RAISE EXCEPTION NEW.storage_key") ||
		strings.Contains(migration, "RAISE EXCEPTION NEW.media_type") {
		t.Fatal("storage object conflict errors must not disclose metadata")
	}

	versions := expectedMigrationVersions(t)
	if !slices.Contains(versions, "000025_storage_objects_immutability.sql") {
		t.Fatal("migration list is missing 000025 storage object migration")
	}
}

func newStorageObjectsImmutabilityTestPool(
	t *testing.T,
	ctx context.Context,
) (*pgxpool.Pool, string) {
	t.Helper()
	databaseURL := strings.TrimSpace(os.Getenv("DERLEM_TEST_DATABASE_URL"))
	if databaseURL == "" {
		t.Skip("DERLEM_TEST_DATABASE_URL is not set")
	}

	adminPool, err := pgxpool.New(ctx, databaseURL)
	if err != nil {
		t.Fatalf("open admin pool: %v", err)
	}
	t.Cleanup(adminPool.Close)

	schemaName := fmt.Sprintf("derlem_storage_immutable_test_%d", time.Now().UnixNano())
	schemaIdentifier := pgx.Identifier{schemaName}.Sanitize()
	// pgcrypto'yu izole semadan ONCE ve public'te olustur. Izole semanin icinde
	// olusursa (migration 000001 search_path'e kurar) test bitiminde
	// DROP SCHEMA ... CASCADE eklentiyi de siler; paralel kosan diger paketlerin
	// migration'lari o anda 000023/000024'un pgcrypto kontrolunde fail-loud duser.
	if _, err := adminPool.Exec(ctx, "CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public"); err != nil {
		t.Fatalf("ensure pgcrypto: %v", err)
	}

	if _, err := adminPool.Exec(ctx, "CREATE SCHEMA "+schemaIdentifier); err != nil {
		t.Fatalf("create test schema: %v", err)
	}
	t.Cleanup(func() {
		cleanupCtx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()
		if _, err := adminPool.Exec(
			cleanupCtx,
			"DROP SCHEMA "+schemaIdentifier+" CASCADE",
		); err != nil {
			t.Errorf("drop test schema: %v", err)
		}
	})

	config, err := pgxpool.ParseConfig(databaseURL)
	if err != nil {
		t.Fatalf("parse test database URL: %v", err)
	}
	config.ConnConfig.RuntimeParams["search_path"] = schemaName
	config.MaxConns = 8
	config.MinConns = 0
	pool, err := pgxpool.NewWithConfig(ctx, config)
	if err != nil {
		t.Fatalf("open isolated pool: %v", err)
	}
	t.Cleanup(pool.Close)
	if err := Migrate(ctx, pool); err != nil {
		t.Fatalf("apply migration chain: %v", err)
	}
	return pool, schemaName
}

func TestStorageObjectsAreAppendOnlyAndIdempotentOnPostgres(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	t.Cleanup(cancel)
	pool, _ := newStorageObjectsImmutabilityTestPool(t, ctx)

	const objectSHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	const otherSHA = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
	const storageKey = "objects/sha256/aa/aa/" + objectSHA
	if _, err := pool.Exec(ctx, `
		INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
		VALUES ($1, $2, 42, 'text/plain')
	`, objectSHA, storageKey); err != nil {
		t.Fatalf("insert initial storage object: %v", err)
	}

	tag, err := pool.Exec(ctx, `
		INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
		VALUES ($1, $2, 42, 'text/plain')
		ON CONFLICT (sha256) DO NOTHING
	`, objectSHA, storageKey)
	if err != nil {
		t.Fatalf("repeat exact storage object: %v", err)
	}
	if tag.RowsAffected() != 0 {
		t.Fatalf("exact repeat rows affected = %d, want 0", tag.RowsAffected())
	}

	// Media type describes a use of the bytes, not their content-addressed
	// identity. Reusing exact bytes under a compatible textual label is
	// idempotent and retains the first immutable row.
	tag, err = pool.Exec(ctx, `
		INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
		VALUES ($1, $2, 42, 'text/plain; charset=utf-8')
		ON CONFLICT (sha256) DO NOTHING
	`, objectSHA, storageKey)
	if err != nil {
		t.Fatalf("repeat storage object with usage MIME alias: %v", err)
	}
	if tag.RowsAffected() != 0 {
		t.Fatalf("MIME alias repeat rows affected = %d, want 0", tag.RowsAffected())
	}
	var retainedMediaType string
	if err := pool.QueryRow(ctx, `
		SELECT media_type FROM storage_objects WHERE sha256 = $1
	`, objectSHA).Scan(&retainedMediaType); err != nil {
		t.Fatalf("read retained media type: %v", err)
	}
	if retainedMediaType != "text/plain" {
		t.Fatalf("retained media type = %q, want first value", retainedMediaType)
	}

	conflicts := []struct {
		name      string
		key       string
		byteSize  int64
		mediaType string
		immutable bool
	}{
		{"storage key", storageKey + ".other", 42, "text/plain", true},
		{"byte size", storageKey, 43, "text/plain", true},
		{"immutable flag", storageKey, 42, "text/plain", false},
	}
	for _, test := range conflicts {
		t.Run(test.name, func(t *testing.T) {
			_, err := pool.Exec(ctx, `
				INSERT INTO storage_objects(
					sha256, storage_key, byte_size, media_type, immutable
				) VALUES ($1, $2, $3, $4, $5)
				ON CONFLICT (sha256) DO NOTHING
			`, objectSHA, test.key, test.byteSize, test.mediaType, test.immutable)
			if err == nil || !strings.Contains(
				err.Error(),
				"metadata conflicts with existing SHA-256 identity",
			) {
				t.Fatalf("conflicting insert error = %v, want identity conflict", err)
			}
		})
	}

	if _, err := pool.Exec(ctx, `
		INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
		VALUES ($1, $2, 42, 'text/plain')
	`, otherSHA, storageKey); err == nil || !isUniqueViolation(err) {
		t.Fatalf("same key with another SHA error = %v, want unique violation", err)
	}

	mutations := map[string]struct {
		statement  string
		parameters []any
	}{
		"update": {
			"UPDATE storage_objects SET byte_size = byte_size WHERE sha256 = $1",
			[]any{objectSHA},
		},
		"delete": {
			"DELETE FROM storage_objects WHERE sha256 = $1",
			[]any{objectSHA},
		},
		"truncate": {"TRUNCATE storage_objects CASCADE", nil},
	}
	for name, mutation := range mutations {
		t.Run(name, func(t *testing.T) {
			_, err := pool.Exec(ctx, mutation.statement, mutation.parameters...)
			if err == nil || !strings.Contains(err.Error(), "storage_objects are append-only") {
				t.Fatalf("%s error = %v, want append-only rejection", name, err)
			}
		})
	}

	var objectCount, changeCount int
	if err := pool.QueryRow(ctx, `
		SELECT count(*) FROM storage_objects WHERE sha256 = $1
	`, objectSHA).Scan(&objectCount); err != nil {
		t.Fatalf("count storage objects: %v", err)
	}
	if err := pool.QueryRow(ctx, `
		SELECT count(*)
		FROM row_change_events
		WHERE table_name = 'storage_objects'
		  AND operation = 'INSERT'
		  AND row_key->>'sha256' = $1
	`, objectSHA).Scan(&changeCount); err != nil {
		t.Fatalf("count storage object row-change events: %v", err)
	}
	if objectCount != 1 || changeCount != 1 {
		t.Fatalf(
			"storage object count/change count = %d/%d, want 1/1",
			objectCount,
			changeCount,
		)
	}
}

type concurrentStorageObjectInsertResult struct {
	metadataIndex int
	rowsAffected  int64
	err           error
}

func TestStorageObjectConcurrentMetadataConflictCommitsExactlyOne(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	t.Cleanup(cancel)
	pool, _ := newStorageObjectsImmutabilityTestPool(t, ctx)

	const objectSHA = "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
	metadata := []struct {
		key       string
		byteSize  int64
		mediaType string
	}{
		{"objects/sha256/cc/cc/first", 100, "text/plain"},
		{"objects/sha256/cc/cc/second", 200, "application/json"},
	}

	ready := make(chan struct{}, len(metadata))
	start := make(chan struct{})
	results := make(chan concurrentStorageObjectInsertResult, len(metadata))
	for index, candidate := range metadata {
		go func(index int, candidate struct {
			key       string
			byteSize  int64
			mediaType string
		}) {
			connection, err := pool.Acquire(ctx)
			if err != nil {
				ready <- struct{}{}
				results <- concurrentStorageObjectInsertResult{index, 0, err}
				return
			}
			defer connection.Release()
			tx, err := connection.Begin(ctx)
			if err != nil {
				ready <- struct{}{}
				results <- concurrentStorageObjectInsertResult{index, 0, err}
				return
			}
			defer tx.Rollback(context.Background())
			ready <- struct{}{}
			<-start
			tag, err := tx.Exec(ctx, `
				INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
				VALUES ($1, $2, $3, $4)
				ON CONFLICT (sha256) DO NOTHING
			`, objectSHA, candidate.key, candidate.byteSize, candidate.mediaType)
			if err == nil {
				err = tx.Commit(ctx)
			}
			results <- concurrentStorageObjectInsertResult{
				metadataIndex: index,
				rowsAffected:  tag.RowsAffected(),
				err:           err,
			}
		}(index, candidate)
	}
	for range metadata {
		<-ready
	}
	close(start)

	var committed, rejected int
	winner := -1
	for range metadata {
		result := <-results
		if result.err == nil {
			committed++
			winner = result.metadataIndex
			if result.rowsAffected != 1 {
				t.Errorf("committed contender rows affected = %d, want 1", result.rowsAffected)
			}
			continue
		}
		if !strings.Contains(
			result.err.Error(),
			"metadata conflicts with existing SHA-256 identity",
		) {
			t.Errorf("rejected contender error = %v, want identity conflict", result.err)
		}
		rejected++
	}
	if committed != 1 || rejected != 1 || winner < 0 {
		t.Fatalf("committed/rejected/winner = %d/%d/%d, want 1/1/valid", committed, rejected, winner)
	}

	var storedKey, storedMediaType string
	var storedByteSize int64
	if err := pool.QueryRow(ctx, `
		SELECT storage_key, byte_size, media_type
		FROM storage_objects
		WHERE sha256 = $1
	`, objectSHA).Scan(&storedKey, &storedByteSize, &storedMediaType); err != nil {
		t.Fatalf("read concurrent winner: %v", err)
	}
	if storedKey != metadata[winner].key ||
		storedByteSize != metadata[winner].byteSize ||
		storedMediaType != metadata[winner].mediaType {
		t.Fatalf(
			"stored metadata = %q/%d/%q, want winner %d metadata",
			storedKey,
			storedByteSize,
			storedMediaType,
			winner,
		)
	}
}

func isUniqueViolation(err error) bool {
	var pgError *pgconn.PgError
	return errors.As(err, &pgError) && pgError.Code == "23505"
}
