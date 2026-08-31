package database

import (
	"context"
	"fmt"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

func TestDerivedSourceMigrationSafelyBackfillsValidMetadata(t *testing.T) {
	databaseURL := strings.TrimSpace(os.Getenv("DERLEM_TEST_DATABASE_URL"))
	if databaseURL == "" {
		t.Skip("DERLEM_TEST_DATABASE_URL is not set")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	t.Cleanup(cancel)
	adminPool, err := pgxpool.New(ctx, databaseURL)
	if err != nil {
		t.Fatalf("open admin pool: %v", err)
	}
	t.Cleanup(adminPool.Close)

	schemaName := fmt.Sprintf("derlem_lineage_migration_test_%d", time.Now().UnixNano())
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
		cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cleanupCancel()
		if _, err := adminPool.Exec(cleanupCtx, "DROP SCHEMA "+schemaIdentifier+" CASCADE"); err != nil {
			t.Errorf("drop test schema: %v", err)
		}
	})

	config, err := pgxpool.ParseConfig(databaseURL)
	if err != nil {
		t.Fatalf("parse test database URL: %v", err)
	}
	config.ConnConfig.RuntimeParams["search_path"] = schemaName
	pool, err := pgxpool.NewWithConfig(ctx, config)
	if err != nil {
		t.Fatalf("open isolated pool: %v", err)
	}
	t.Cleanup(pool.Close)

	for _, name := range []string{"000001_initial.sql", "000004_uploads_and_declared_artifacts.sql"} {
		contents, err := migrationFiles.ReadFile("migrations/" + name)
		if err != nil {
			t.Fatalf("read prerequisite migration %s: %v", name, err)
		}
		if _, err := pool.Exec(ctx, string(contents)); err != nil {
			t.Fatalf("apply prerequisite migration %s: %v", name, err)
		}
	}

	var actorID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO users(email, password_hash, display_name)
		VALUES ('migration-lineage@example.test', 'test', 'Migration Test')
		RETURNING id::text
	`).Scan(&actorID); err != nil {
		t.Fatalf("insert actor: %v", err)
	}

	parentID := "11111111-1111-4111-8111-111111111111"
	validChildID := "22222222-2222-4222-8222-222222222222"
	selfChildID := "33333333-3333-4333-8333-333333333333"
	invalidChildID := "44444444-4444-4444-8444-444444444444"
	missingChildID := "55555555-5555-4555-8555-555555555555"
	cycleAID := "77777777-7777-4777-8777-777777777777"
	cycleBID := "88888888-8888-4888-8888-888888888888"

	insertSource := func(id, name string, metadata string) {
		t.Helper()
		_, err := pool.Exec(ctx, `
			INSERT INTO sources(
				id, name, source_type, content_purpose, license, rights_status,
				language, domain, lineage_ref, source_metadata, created_by
			)
			VALUES ($1, $2, 'text_corpus', 'pretrain', 'internal', 'unknown',
				'tr', 'mixed', $2 || '.txt', $3::jsonb, $4)
		`, id, name, metadata, actorID)
		if err != nil {
			t.Fatalf("insert source %s: %v", name, err)
		}
	}

	insertSource(parentID, "parent", `{}`)
	insertSource(validChildID, "valid-child", `{"derived_from_source_id":" 11111111-1111-4111-8111-111111111111 "}`)
	insertSource(selfChildID, "self-child", `{"derived_from_source_id":"33333333-3333-4333-8333-333333333333"}`)
	insertSource(invalidChildID, "invalid-child", `{"derived_from_source_id":"not-a-uuid"}`)
	insertSource(missingChildID, "missing-child", `{"derived_from_source_id":"99999999-9999-4999-8999-999999999999"}`)

	insertSource(cycleAID, "cycle-a", `{"derived_from_source_id":"88888888-8888-4888-8888-888888888888"}`)
	insertSource(cycleBID, "cycle-b", `{"derived_from_source_id":"77777777-7777-4777-8777-777777777777"}`)

	var versionBefore int64
	var updatedBefore time.Time
	if err := pool.QueryRow(ctx,
		"SELECT version, updated_at FROM sources WHERE id = $1", validChildID,
	).Scan(&versionBefore, &updatedBefore); err != nil {
		t.Fatalf("read pre-migration source version: %v", err)
	}

	migration, err := migrationFiles.ReadFile("migrations/000021_derived_source_lineage.sql")
	if err != nil {
		t.Fatalf("read derived lineage migration: %v", err)
	}
	if _, err := pool.Exec(ctx, string(migration)); err == nil || !strings.Contains(err.Error(), "invalid UUID") {
		t.Fatalf("invalid UUID preflight error = %v, want invalid UUID", err)
	}
	if _, err := pool.Exec(ctx, "DELETE FROM sources WHERE id = $1", invalidChildID); err != nil {
		t.Fatalf("delete invalid UUID fixture: %v", err)
	}
	if _, err := pool.Exec(ctx, string(migration)); err == nil || !strings.Contains(err.Error(), "missing/self parent") {
		t.Fatalf("invalid parent preflight error = %v, want missing/self parent", err)
	}
	if _, err := pool.Exec(ctx,
		"DELETE FROM sources WHERE id IN ($1, $2)", selfChildID, missingChildID,
	); err != nil {
		t.Fatalf("delete invalid parent fixtures: %v", err)
	}
	if _, err := pool.Exec(ctx, string(migration)); err == nil || !strings.Contains(err.Error(), "cyclic lineage") {
		t.Fatalf("cycle preflight error = %v, want cyclic lineage", err)
	}
	if _, err := pool.Exec(ctx,
		"DELETE FROM sources WHERE id IN ($1, $2)", cycleAID, cycleBID,
	); err != nil {
		t.Fatalf("delete cycle fixtures: %v", err)
	}
	if _, err := pool.Exec(ctx, string(migration)); err != nil {
		t.Fatalf("apply valid derived lineage migration: %v", err)
	}

	var derivedParent *string
	if err := pool.QueryRow(ctx,
		"SELECT derived_from_source_id::text FROM sources WHERE id = $1", validChildID,
	).Scan(&derivedParent); err != nil {
		t.Fatalf("read valid child lineage: %v", err)
	}
	if derivedParent == nil || *derivedParent != parentID {
		t.Fatalf("valid metadata was not backfilled: %#v", derivedParent)
	}
	var versionAfter int64
	var updatedAfter time.Time
	if err := pool.QueryRow(ctx,
		"SELECT version, updated_at FROM sources WHERE id = $1", validChildID,
	).Scan(&versionAfter, &updatedAfter); err != nil {
		t.Fatalf("read post-migration source version: %v", err)
	}
	if versionAfter != versionBefore || !updatedAfter.Equal(updatedBefore) {
		t.Fatalf(
			"lineage backfill changed source version metadata: before=(%d, %s) after=(%d, %s)",
			versionBefore, updatedBefore, versionAfter, updatedAfter,
		)
	}
	var auditParentID, auditOrigin string
	if err := pool.QueryRow(ctx, `
		SELECT details->>'derived_from_source_id', details->>'origin'
		FROM audit_events
		WHERE action = 'source.lineage_backfilled' AND entity_id = $1
	`, validChildID).Scan(&auditParentID, &auditOrigin); err != nil {
		t.Fatalf("read lineage backfill audit: %v", err)
	}
	if auditParentID != parentID || auditOrigin != "source_metadata" {
		t.Fatalf("unexpected lineage backfill audit: parent=%q origin=%q", auditParentID, auditOrigin)
	}

	if _, err := pool.Exec(ctx, `
		INSERT INTO sources(
			id, name, source_type, content_purpose, license, rights_status,
			language, domain, lineage_ref, source_metadata, created_by,
			derived_from_source_id
		)
		VALUES (
			'66666666-6666-4666-8666-666666666666', 'self-insert',
			'text_corpus', 'pretrain', 'internal', 'unknown', 'tr', 'mixed',
			'self-insert.txt', '{}'::jsonb, $1,
			'66666666-6666-4666-8666-666666666666'
		)
	`, actorID); err == nil {
		t.Fatal("expected self-lineage check constraint to reject an insert")
	}
	if _, err := pool.Exec(ctx,
		"UPDATE sources SET derived_from_source_id = NULL WHERE id = $1", validChildID,
	); err == nil {
		t.Fatal("expected derived lineage to be immutable after creation")
	}
	if _, err := pool.Exec(ctx, "DELETE FROM sources WHERE id = $1", parentID); err == nil {
		t.Fatal("expected parent foreign key to use ON DELETE RESTRICT")
	}
}
