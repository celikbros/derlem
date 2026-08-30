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

func TestRowChangeEventsMigrationHasRedactedFailClosedCoverage(t *testing.T) {
	contents, err := migrationFiles.ReadFile("migrations/000023_row_change_events.sql")
	if err != nil {
		t.Fatalf("read row change migration: %v", err)
	}
	migration := string(contents)

	for _, required := range []string{
		"CREATE TABLE row_change_events",
		"SECURITY DEFINER",
		"SET search_path = pg_catalog",
		"FROM pg_catalog.pg_extension AS extension",
		"JOIN pg_catalog.pg_namespace AS namespace",
		"WHERE extension.extname = 'pgcrypto'",
		"FROM pg_catalog.pg_trigger AS trigger_def",
		"JOIN pg_catalog.pg_proc AS function_def",
		"namespace.oid = function_def.pronamespace",
		"trigger_def.tgrelid = TG_RELID",
		"trigger_def.tgname = TG_NAME",
		"NOT trigger_def.tgisinternal",
		"audit_schema IS DISTINCT FROM TG_TABLE_SCHEMA",
		"row-change audit schema mismatch for %.%",
		"format('SELECT %I.row_change_safe_summary($1, $2)', audit_schema)",
		"old_data IS NOT NULL AND before_data IS NULL",
		"new_data IS NOT NULL AND after_data IS NULL",
		"safe row-change summary is not configured for %.%",
		"REVOKE ALL ON FUNCTION capture_row_change_event() FROM PUBLIC",
		"REVOKE ALL ON FUNCTION row_change_safe_summary(text, jsonb) FROM PUBLIC",
		"CREATE TRIGGER row_change_events_no_update",
		"CREATE TRIGGER row_change_events_no_delete",
		"CREATE TRIGGER row_change_events_no_truncate",
		"CREATE TRIGGER roles_capture_row_change",
		"CREATE TRIGGER users_capture_row_change",
		"CREATE TRIGGER user_roles_capture_row_change",
		"CREATE TRIGGER storage_objects_capture_row_change",
		"CREATE TRIGGER sources_capture_row_change",
		"CREATE TRIGGER reviews_capture_row_change",
		"CREATE TRIGGER pii_scans_capture_row_change",
		"CREATE TRIGGER documents_capture_row_change",
		"CREATE TRIGGER document_versions_capture_row_change",
		"CREATE TRIGGER document_sample_generations_capture_row_change",
		"CREATE TRIGGER document_sample_memberships_capture_row_change",
		"CREATE TRIGGER document_reviews_capture_row_change",
		"CREATE TRIGGER document_review_reversals_capture_row_change",
		"CREATE TRIGGER similarity_calibration_runs_capture_row_change",
		"CREATE TRIGGER similarity_review_pairs_capture_row_change",
		"CREATE TRIGGER similarity_pair_reviews_capture_row_change",
		"CREATE TRIGGER releases_capture_row_change",
		"CREATE TRIGGER release_sources_capture_row_change",
		"CREATE TRIGGER release_exports_capture_row_change",
	} {
		if !strings.Contains(migration, required) {
			t.Errorf("migration is missing %q", required)
		}
	}

	for _, excludedTable := range []string{
		"audit_events",
		"background_jobs",
		"auth_sessions",
		"login_rate_limits",
		"document_review_claims",
		"document_fingerprints",
		"contributions",
		"active_document_reviews",
	} {
		unexpected := "CREATE TRIGGER " + excludedTable + "_capture_row_change"
		if strings.Contains(migration, unexpected) {
			t.Errorf("excluded table %q has a generic capture trigger", excludedTable)
		}
	}

	// Match value extraction, not comments or changed-column names. These fields
	// may be observed transiently to compute which column changed, but their
	// values must never enter a summary or summary hash.
	for _, forbiddenExtraction := range []string{
		"'email', row_data->",
		"'password_hash', row_data->",
		"'display_name', row_data->",
		"'storage_key', row_data->",
		"'source_url', row_data->",
		"'license_evidence_ref', row_data->",
		"'lineage_ref', row_data->",
		"'source_metadata', row_data->",
		"'findings', row_data->",
		"'external_id', row_data->",
		"'text_preview', row_data->",
		"'risk_reasons', row_data->",
		"'reason', row_data->",
		"'review_context', row_data->",
		"'source_snapshot', row_data->",
		"'left_text_preview', row_data->",
		"'right_text_preview', row_data->",
		"'gate_results', row_data->",
		"'last_error', row_data->",
		"'record_type_counts', row_data->",
		"'jti_hash', row_data->",
		"'prompt', row_data->",
		"'body', row_data->",
	} {
		if strings.Contains(migration, forbiddenExtraction) {
			t.Errorf("sensitive value extraction is present: %q", forbiddenExtraction)
		}
	}

	if strings.Contains(migration, "digest(convert_to(row_data") ||
		strings.Contains(migration, "digest(convert_to(old_data") ||
		strings.Contains(migration, "digest(convert_to(new_data") {
		t.Fatal("raw rows must never be hashed; only redacted summaries may be hashed")
	}
	if strings.Contains(migration, "public.digest") {
		t.Fatal("pgcrypto functions must use the extension's installed schema")
	}
	if strings.Contains(
		migration,
		"format('SELECT %I.row_change_safe_summary($1, $2)', TG_TABLE_SCHEMA)",
	) {
		t.Fatal("safe-summary lookup must use the verified trigger-function schema")
	}
	if !strings.Contains(
		migration,
		"        audit_schema\n    )\n    USING TG_TABLE_SCHEMA, TG_TABLE_NAME",
	) {
		t.Fatal("ledger insert must target the verified trigger-function schema")
	}
	lastCaptureTrigger := strings.LastIndex(
		migration,
		"CREATE TRIGGER release_exports_capture_row_change",
	)
	revokeCapture := strings.Index(
		migration,
		"REVOKE ALL ON FUNCTION capture_row_change_event() FROM PUBLIC",
	)
	revokeSummary := strings.Index(
		migration,
		"REVOKE ALL ON FUNCTION row_change_safe_summary(text, jsonb) FROM PUBLIC",
	)
	if lastCaptureTrigger < 0 || revokeCapture < lastCaptureTrigger ||
		revokeSummary < lastCaptureTrigger {
		t.Fatal("audit helper EXECUTE grants must be revoked after triggers are installed")
	}
}

func TestRowChangeEventsCaptureDirectSQLWithoutSensitiveValues(t *testing.T) {
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

	schemaName := fmt.Sprintf("derlem_row_change_test_%d", time.Now().UnixNano())
	schemaIdentifier := pgx.Identifier{schemaName}.Sanitize()
	if _, err := adminPool.Exec(ctx, "CREATE SCHEMA "+schemaIdentifier); err != nil {
		t.Fatalf("create test schema: %v", err)
	}
	t.Cleanup(func() {
		cleanupCtx, cleanupCancel := context.WithTimeout(
			context.Background(), 30*time.Second,
		)
		defer cleanupCancel()
		if _, err := adminPool.Exec(
			cleanupCtx, "DROP SCHEMA "+schemaIdentifier+" CASCADE",
		); err != nil {
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
	if err := Migrate(ctx, pool); err != nil {
		t.Fatalf("migrate isolated schema: %v", err)
	}

	const (
		oldEmailMarker    = "row-change-old-pii@example.test"
		newEmailMarker    = "row-change-new-pii@example.test"
		passwordMarker    = "ROW_CHANGE_PASSWORD_SECRET_7f6b"
		displayNameMarker = "ROW_CHANGE_PII_NAME_53f8"
		storagePathMarker = "ROW_CHANGE_PRIVATE_PATH_3a9c"
		tokenMarker       = "ROW_CHANGE_API_TOKEN_f109"
		bodyMarker        = "ROW_CHANGE_RAW_BODY_42ce"
	)

	var actorID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO users(email, password_hash, display_name)
		VALUES ($1, $2, $3)
		RETURNING id::text
	`, oldEmailMarker, passwordMarker, displayNameMarker).Scan(&actorID); err != nil {
		t.Fatalf("insert user fixture: %v", err)
	}
	if _, err := pool.Exec(ctx, `
		UPDATE users
		SET email = $2, password_hash = $3, display_name = $4, status = 'disabled'
		WHERE id = $1
	`, actorID, newEmailMarker, passwordMarker+"-new", displayNameMarker+" New"); err != nil {
		t.Fatalf("direct SQL user update: %v", err)
	}

	var operation, rowKey, changedColumns, beforeSummary, afterSummary string
	var beforeHash, afterHash *string
	if err := pool.QueryRow(ctx, `
		SELECT operation, row_key::text, changed_columns::text,
		       before_summary::text, after_summary::text,
		       before_hash::text, after_hash::text
		FROM row_change_events
		WHERE table_schema = $1 AND table_name = 'users'
		  AND operation = 'UPDATE' AND row_key->>'id' = $2
		ORDER BY id DESC
		LIMIT 1
	`, schemaName, actorID).Scan(
		&operation, &rowKey, &changedColumns, &beforeSummary, &afterSummary,
		&beforeHash, &afterHash,
	); err != nil {
		t.Fatalf("read direct SQL row-change event: %v", err)
	}
	if operation != "UPDATE" || !strings.Contains(rowKey, actorID) {
		t.Fatalf("unexpected row-change identity: operation=%q key=%q", operation, rowKey)
	}
	for _, column := range []string{
		"email", "password_hash", "display_name", "status", "auth_version",
	} {
		if !strings.Contains(changedColumns, column) {
			t.Errorf("changed columns %q are missing %q", changedColumns, column)
		}
	}
	if !strings.Contains(beforeSummary, `"status": "active"`) ||
		!strings.Contains(afterSummary, `"status": "disabled"`) {
		t.Fatalf("unexpected safe summaries: before=%s after=%s", beforeSummary, afterSummary)
	}
	if beforeHash == nil || len(*beforeHash) != 64 || afterHash == nil || len(*afterHash) != 64 {
		t.Fatalf("summary hashes are not SHA256: before=%v after=%v", beforeHash, afterHash)
	}

	const objectSHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	if _, err := pool.Exec(ctx, `
		INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
		VALUES ($1, $2, 128, 'text/plain')
	`, objectSHA, `C:\private\`+storagePathMarker+`\corpus.txt`); err != nil {
		t.Fatalf("insert storage fixture: %v", err)
	}

	var sourceID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO sources(
			name, source_type, content_purpose, license, rights_status,
			language, domain, source_url, license_evidence_ref, lineage_ref,
			object_sha256, source_metadata, created_by
		)
		VALUES (
			$1, 'text_corpus', 'pretrain', 'internal', 'unknown',
			'tr', 'mixed', $2, $3, $4, $5,
			jsonb_build_object(
				'api_token', $6::text,
				'body', $7::text,
				'email', $8::text
			), $9
		)
		RETURNING id::text
	`,
		"source-"+displayNameMarker,
		"https://example.test/download?token="+tokenMarker,
		`C:\private\`+storagePathMarker+`\license.txt`,
		`C:\private\`+storagePathMarker+`\lineage.json`,
		objectSHA, tokenMarker, bodyMarker, newEmailMarker, actorID,
	).Scan(&sourceID); err != nil {
		t.Fatalf("insert source fixture: %v", err)
	}
	if _, err := pool.Exec(ctx,
		"UPDATE sources SET rights_status = 'cleared' WHERE id = $1", sourceID,
	); err != nil {
		t.Fatalf("direct SQL source update: %v", err)
	}

	if _, err := pool.Exec(ctx, `
		INSERT INTO contributions(
			contributor_id, task_type, prompt, body, terms_ack_version
		)
		VALUES ($1, 'free_text', $2, $3, 'test-v1')
	`, actorID, tokenMarker, bodyMarker); err != nil {
		t.Fatalf("insert excluded raw contribution: %v", err)
	}

	var capturedEventText string
	if err := pool.QueryRow(ctx, `
		SELECT COALESCE(string_agg(
			database_role || '|' || table_schema || '|' || table_name || '|' ||
			operation || '|' || row_key::text || '|' || changed_columns::text || '|' ||
			COALESCE(before_summary::text, '') || '|' ||
			COALESCE(after_summary::text, '') || '|' ||
			COALESCE(before_hash::text, '') || '|' || COALESCE(after_hash::text, ''),
			E'\n'
		), '')
		FROM row_change_events
		WHERE table_schema = $1
	`, schemaName).Scan(&capturedEventText); err != nil {
		t.Fatalf("read captured event payloads: %v", err)
	}
	for _, secret := range []string{
		oldEmailMarker, newEmailMarker, passwordMarker, displayNameMarker,
		storagePathMarker, tokenMarker, bodyMarker,
	} {
		if strings.Contains(capturedEventText, secret) {
			t.Errorf("row-change ledger leaked marker %q", secret)
		}
	}

	var contributionEvents int
	if err := pool.QueryRow(ctx, `
		SELECT count(*) FROM row_change_events
		WHERE table_schema = $1 AND table_name = 'contributions'
	`, schemaName).Scan(&contributionEvents); err != nil {
		t.Fatalf("count contribution events: %v", err)
	}
	if contributionEvents != 0 {
		t.Fatalf("raw contribution table produced %d generic events", contributionEvents)
	}

	requiredTriggers := []string{
		"users_capture_row_change",
		"sources_capture_row_change",
		"document_reviews_capture_row_change",
		"document_review_reversals_capture_row_change",
		"releases_capture_row_change",
	}
	var requiredTriggerCount int
	if err := pool.QueryRow(ctx, `
		SELECT count(*)
		FROM pg_trigger AS trigger
		JOIN pg_class AS relation ON relation.oid = trigger.tgrelid
		JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
		WHERE namespace.nspname = $1 AND NOT trigger.tgisinternal
		  AND trigger.tgname = ANY($2::text[])
	`, schemaName, requiredTriggers).Scan(&requiredTriggerCount); err != nil {
		t.Fatalf("count required row-change triggers: %v", err)
	}
	if requiredTriggerCount != len(requiredTriggers) {
		t.Fatalf("found %d/%d required row-change triggers", requiredTriggerCount, len(requiredTriggers))
	}

	var excludedTriggerCount int
	if err := pool.QueryRow(ctx, `
		SELECT count(*)
		FROM pg_trigger AS trigger
		JOIN pg_class AS relation ON relation.oid = trigger.tgrelid
		JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
		WHERE namespace.nspname = $1 AND NOT trigger.tgisinternal
		  AND trigger.tgname LIKE '%\_capture\_row\_change' ESCAPE '\'
		  AND relation.relname = ANY($2::text[])
	`, schemaName, []string{
		"audit_events", "background_jobs", "auth_sessions", "login_rate_limits",
		"document_review_claims", "document_fingerprints", "contributions",
		"active_document_reviews",
	}).Scan(&excludedTriggerCount); err != nil {
		t.Fatalf("count excluded row-change triggers: %v", err)
	}
	if excludedTriggerCount != 0 {
		t.Fatalf("found %d generic triggers on explicitly excluded tables", excludedTriggerCount)
	}

	var eventCountBefore int
	if err := pool.QueryRow(ctx, "SELECT count(*) FROM row_change_events").Scan(&eventCountBefore); err != nil {
		t.Fatalf("count events before append-only checks: %v", err)
	}
	for name, statement := range map[string]string{
		"update":   "UPDATE row_change_events SET database_role = database_role",
		"delete":   "DELETE FROM row_change_events",
		"truncate": "TRUNCATE row_change_events",
	} {
		if _, err := pool.Exec(ctx, statement); err == nil ||
			!strings.Contains(err.Error(), "append-only") {
			t.Errorf("%s row_change_events error = %v, want append-only", name, err)
		}
	}
	var eventCountAfter int
	if err := pool.QueryRow(ctx, "SELECT count(*) FROM row_change_events").Scan(&eventCountAfter); err != nil {
		t.Fatalf("count events after append-only checks: %v", err)
	}
	if eventCountAfter != eventCountBefore {
		t.Fatalf("append-only checks changed event count: before=%d after=%d", eventCountBefore, eventCountAfter)
	}
}
