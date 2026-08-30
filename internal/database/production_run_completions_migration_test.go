package database

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

func TestProductionRunCompletionsMigrationDeclaresCanonicalEvidence(t *testing.T) {
	contents, err := migrationFiles.ReadFile(
		"migrations/000026_production_run_completions.sql",
	)
	if err != nil {
		t.Fatalf("read production run completions migration: %v", err)
	}
	migration := string(contents)

	for _, required := range []string{
		"CREATE TABLE production_run_completions",
		"production_run_id uuid PRIMARY KEY",
		"job_id uuid NOT NULL UNIQUE",
		"output_manifest_sha256 char(64) NOT NULL",
		"output_sha256 char(64) NOT NULL",
		"REFERENCES storage_objects(sha256) ON DELETE RESTRICT",
		"output_byte_size bigint NOT NULL CHECK (output_byte_size > 0)",
		"output_record_count bigint NOT NULL CHECK (output_record_count > 0)",
		"completed_at timestamptz NOT NULL",
		"production_runs_are_intent_only",
		"SET search_path = pg_catalog",
		"production completion validator schema mismatch",
		"production_run_completions are append-only",
		"completed production job evidence is immutable",
		"ADD COLUMN production_run_completion_job_id uuid",
		"ADD COLUMN production_run_output_manifest_sha256 char(64)",
		"ADD COLUMN production_run_output_sha256 char(64)",
		"ADD COLUMN production_run_output_byte_size bigint",
		"ADD COLUMN production_run_output_record_count bigint",
		"ADD COLUMN production_run_completed_at_utc text",
		"release_source_snapshots_completion_shape",
		"release_source_snapshots_completion_fkey",
		"release_source_snapshots_completion_output_fkey",
		"CREATE TRIGGER zz_release_source_contract_snapshots_pin_completion",
		"CREATE TRIGGER zz_releases_validate_completion_snapshot_transition",
		"release source identity does not match production completion output",
		"source.line_count AS source_line_count",
		`'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'`,
		"CREATE TRIGGER production_run_completions_capture_row_change",
		"row_change_safe_summary_v25",
		"'production_run_completion_job_id'",
		"'production_run_output_manifest_sha256'",
		"'production_run_output_sha256'",
		"'production_run_output_byte_size'",
		"'production_run_output_record_count'",
		"'production_run_completed_at_utc'",
		"REVOKE ALL ON FUNCTION validate_production_run_completion() FROM PUBLIC",
	} {
		if !strings.Contains(migration, required) {
			t.Errorf("migration is missing %q", required)
		}
	}
	if !strings.Contains(migration, `output_sha256 char(64) NOT NULL
        REFERENCES storage_objects(sha256) ON DELETE RESTRICT`) {
		t.Error("output SHA is not pinned to an immutable storage object")
	}

	for _, forbidden := range []string{
		"staged_path', row_data",
		"system_prompt', row_data",
		"prompt_template', row_data",
		"payload', row_data",
		"result', row_data",
		"last_error', row_data",
	} {
		if strings.Contains(migration, forbidden) {
			t.Errorf("safe summary unexpectedly contains %q", forbidden)
		}
	}
}

func newProductionCompletionTestPool(
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

	schemaName := fmt.Sprintf(
		"derlem_production_completion_test_%d",
		time.Now().UnixNano(),
	)
	schemaIdentifier := pgx.Identifier{schemaName}.Sanitize()
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

type productionCompletionFixture struct {
	runID       string
	jobID       string
	manifestSHA string
	outputSHA   string
	byteSize    int64
	recordCount int64
	completedAt time.Time
}

type generatedReleaseFixture struct {
	productionCompletionFixture
	actorID    string
	sourceID   string
	campaignID string
	releaseID  string
	sourceSHA  string
}

const generatedReleaseSnapshotInsertSQL = `
	INSERT INTO release_source_contract_snapshots(
		release_id, source_id, data_profile_key, data_profile_version,
		content_purpose, profile_config_sha256, payload_schema_sha256,
		field_extraction_sha256, rubric_key, rubric_version, rubric_sha256,
		protocol_key, protocol_version, protocol_sha256,
		pii_policy_key, pii_policy_version, pii_policy_sha256,
		dedup_policy_key, dedup_policy_version, dedup_policy_sha256,
		leakage_policy_key, leakage_policy_version, leakage_policy_sha256,
		purpose_contract_version, purpose_contract_sha256,
		export_contract_key, export_contract_version, export_contract_sha256,
		review_campaign_id, review_evidence_status,
		implementation_bundle_sha256
	)
	SELECT $1, campaign.source_id, campaign.data_profile_key,
		campaign.data_profile_version, campaign.content_purpose,
		campaign.profile_config_sha256, profile.payload_schema_sha256,
		profile.field_extraction_sha256, campaign.rubric_key,
		campaign.rubric_version, rubric.spec_sha256,
		campaign.protocol_key, campaign.protocol_version, protocol.spec_sha256,
		campaign.pii_policy_key, campaign.pii_policy_version, pii.spec_sha256,
		campaign.dedup_policy_key, campaign.dedup_policy_version, dedup.spec_sha256,
		campaign.leakage_policy_key, campaign.leakage_policy_version,
		leakage.spec_sha256, campaign.purpose_contract_version,
		campaign.purpose_contract_sha256, profile.export_contract_key,
		profile.export_contract_version, export.spec_sha256,
		campaign.id, 'campaign_pinned', campaign.implementation_bundle_sha256
	FROM review_campaigns AS campaign
	JOIN data_profile_versions AS profile
	  ON profile.data_profile_key = campaign.data_profile_key
	 AND profile.data_profile_version = campaign.data_profile_version
	JOIN review_rubric_versions AS rubric
	  ON rubric.rubric_key = campaign.rubric_key
	 AND rubric.rubric_version = campaign.rubric_version
	JOIN review_protocol_versions AS protocol
	  ON protocol.protocol_key = campaign.protocol_key
	 AND protocol.protocol_version = campaign.protocol_version
	JOIN data_policy_versions AS pii
	  ON pii.policy_kind = 'pii' AND pii.policy_key = campaign.pii_policy_key
	 AND pii.policy_version = campaign.pii_policy_version
	JOIN data_policy_versions AS dedup
	  ON dedup.policy_kind = 'dedup' AND dedup.policy_key = campaign.dedup_policy_key
	 AND dedup.policy_version = campaign.dedup_policy_version
	JOIN data_policy_versions AS leakage
	  ON leakage.policy_kind = 'leakage'
	 AND leakage.policy_key = campaign.leakage_policy_key
	 AND leakage.policy_version = campaign.leakage_policy_version
	JOIN export_contract_versions AS export
	  ON export.export_contract_key = profile.export_contract_key
	 AND export.export_contract_version = profile.export_contract_version
	WHERE campaign.id = $2
`

func insertProductionRunIntent(
	t *testing.T,
	ctx context.Context,
	querier interface {
		QueryRow(context.Context, string, ...any) pgx.Row
	},
	origin string,
) string {
	t.Helper()
	runKind := "model_generation"
	if origin == "hybrid" {
		runKind = "hybrid_generation"
	}
	var runID string
	if err := querier.QueryRow(ctx, `
		INSERT INTO production_runs(
			run_kind, origin_kind, implementation_key,
			implementation_digest, config_sha256
		)
		VALUES ($1, $2, 'tests.generator.v1', repeat('a', 64), repeat('b', 64))
		RETURNING id::text
	`, runKind, origin).Scan(&runID); err != nil {
		t.Fatalf("insert production run intent: %v", err)
	}
	return runID
}

func insertCompletedGenerationJob(
	t *testing.T,
	ctx context.Context,
	querier interface {
		QueryRow(context.Context, string, ...any) pgx.Row
	},
	runID, status, manifestSHA, outputSHA string,
	byteSize, recordCount int64,
	sentinel string,
) (string, time.Time) {
	t.Helper()
	var jobID string
	var completedAt time.Time
	if err := querier.QueryRow(ctx, `
		INSERT INTO background_jobs(
			job_type, status, payload, result, completed_at
		)
		VALUES (
			'distill_source', $2,
			jsonb_build_object(
				'production_run_id', $1::text,
				'staged_path', $7::text,
				'system_prompt', $7::text
			),
			jsonb_build_object(
				'production_run_id', $1::text,
				'manifest_sha256', $3::text,
				'output_sha256', $4::text,
				'output_byte_size', $5::bigint,
				'document_count', $6::bigint,
				'private_result', $7::text
			),
			now()
		)
		RETURNING id::text, completed_at
	`, runID, status, manifestSHA, outputSHA, byteSize, recordCount, sentinel).Scan(
		&jobID,
		&completedAt,
	); err != nil {
		t.Fatalf("insert generation job: %v", err)
	}
	return jobID, completedAt
}

func seedProductionCompletion(
	t *testing.T,
	ctx context.Context,
	pool *pgxpool.Pool,
	sentinel string,
) productionCompletionFixture {
	t.Helper()
	fixture := productionCompletionFixture{
		manifestSHA: strings.Repeat("c", 64),
		outputSHA:   strings.Repeat("d", 64),
		byteSize:    321,
		recordCount: 7,
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
		VALUES
			($1, 'tests/completion-manifest.json', 99, 'application/json'),
			($2, 'tests/completion-output.jsonl', $3, 'application/x-ndjson')
	`, fixture.manifestSHA, fixture.outputSHA, fixture.byteSize); err != nil {
		t.Fatalf("insert completion storage objects: %v", err)
	}
	fixture.runID = insertProductionRunIntent(t, ctx, pool, "model")
	fixture.jobID, fixture.completedAt = insertCompletedGenerationJob(
		t,
		ctx,
		pool,
		fixture.runID,
		"succeeded",
		fixture.manifestSHA,
		fixture.outputSHA,
		fixture.byteSize,
		fixture.recordCount,
		sentinel,
	)
	if _, err := pool.Exec(ctx, `
		INSERT INTO production_run_completions(
			production_run_id, job_id, output_manifest_sha256,
			output_sha256, output_byte_size, output_record_count,
			completed_at
		)
		VALUES ($1, $2, $3, $4, $5, $6, $7)
	`,
		fixture.runID,
		fixture.jobID,
		fixture.manifestSHA,
		fixture.outputSHA,
		fixture.byteSize,
		fixture.recordCount,
		fixture.completedAt,
	); err != nil {
		t.Fatalf("insert production completion: %v", err)
	}
	return fixture
}

func seedGeneratedRelease(
	t *testing.T,
	ctx context.Context,
	pool *pgxpool.Pool,
	origin string,
	withCompletion bool,
	sourceMatchesCompletion bool,
	sourceLineCount int64,
	sentinel string,
) generatedReleaseFixture {
	t.Helper()
	fixture := generatedReleaseFixture{
		productionCompletionFixture: productionCompletionFixture{
			manifestSHA: strings.Repeat("6", 64),
			outputSHA:   strings.Repeat("7", 64),
			byteSize:    417,
			recordCount: 1,
		},
		sourceSHA: strings.Repeat("7", 64),
	}
	if !sourceMatchesCompletion {
		fixture.sourceSHA = strings.Repeat("8", 64)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
		VALUES
			($1, 'tests/release-completion-manifest.json', 97, 'application/json'),
			($2, 'tests/release-completion-output.jsonl', $3, 'application/x-ndjson')
	`, fixture.manifestSHA, fixture.outputSHA, fixture.byteSize); err != nil {
		t.Fatalf("insert generated release completion objects: %v", err)
	}
	if !sourceMatchesCompletion {
		if _, err := pool.Exec(ctx, `
			INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
			VALUES ($1, 'tests/release-mismatched-source.jsonl', 418, 'application/x-ndjson')
		`, fixture.sourceSHA); err != nil {
			t.Fatalf("insert mismatched generated source object: %v", err)
		}
	}

	fixture.runID = insertProductionRunIntent(t, ctx, pool, origin)
	fixture.jobID, fixture.completedAt = insertCompletedGenerationJob(
		t, ctx, pool, fixture.runID, "succeeded", fixture.manifestSHA,
		fixture.outputSHA, fixture.byteSize, fixture.recordCount, sentinel,
	)
	if withCompletion {
		if _, err := pool.Exec(ctx, `
			INSERT INTO production_run_completions(
				production_run_id, job_id, output_manifest_sha256,
				output_sha256, output_byte_size, output_record_count,
				completed_at
			)
			VALUES ($1, $2, $3, $4, $5, $6, $7)
		`, fixture.runID, fixture.jobID, fixture.manifestSHA, fixture.outputSHA,
			fixture.byteSize, fixture.recordCount, fixture.completedAt); err != nil {
			t.Fatalf("insert generated release completion: %v", err)
		}
	}

	if err := pool.QueryRow(ctx, `
		INSERT INTO users(email, password_hash, display_name)
		VALUES ('generated-release@example.test', 'test', 'Generated Release')
		RETURNING id::text
	`).Scan(&fixture.actorID); err != nil {
		t.Fatalf("insert generated release actor: %v", err)
	}
	sourceByteSize := fixture.byteSize
	if !sourceMatchesCompletion {
		sourceByteSize++
	}
	if err := pool.QueryRow(ctx, `
		INSERT INTO sources(
			name, source_type, content_purpose, license, rights_status,
			language, domain, lineage_ref, license_evidence_ref,
			object_sha256, byte_size, line_count, created_by,
			data_origin, production_run_id
		) VALUES (
			'generated release source', 'text_corpus', 'pretrain', 'internal',
			'cleared', 'tr', 'mixed', $6, $6, $1, $2, $7, $3, $4, $5
		) RETURNING id::text
	`, fixture.sourceSHA, sourceByteSize, fixture.actorID, origin,
		fixture.runID, sentinel, sourceLineCount).Scan(&fixture.sourceID); err != nil {
		t.Fatalf("insert generated release source: %v", err)
	}
	if _, err := pool.Exec(ctx, `
		UPDATE sources
		SET document_sampling_status = 'sampled',
			sampled_document_count = 1,
			document_sample_generation = 1,
			document_sampling_method = 'completion-release-sample-v1'
		WHERE id = $1
	`, fixture.sourceID); err != nil {
		t.Fatalf("mark generated source sampled: %v", err)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO document_sample_generations(
			source_id, generation, source_sha256, sampling_method,
			status, sample_count
		) VALUES ($1, 1, $2, 'completion-release-sample-v1', 'active', 1)
	`, fixture.sourceID, fixture.sourceSHA); err != nil {
		t.Fatalf("insert generated sample generation: %v", err)
	}
	var documentID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO documents(
			source_id, source_ordinal, current_object_sha256, text_preview,
			byte_size, char_count, sampling_method, sample_generation
		) VALUES (
			$1, 1, $2, 'generated safe document', $3, 23,
			'completion-release-sample-v1', 1
		) RETURNING id::text
	`, fixture.sourceID, fixture.sourceSHA, sourceByteSize).Scan(&documentID); err != nil {
		t.Fatalf("insert generated sample document: %v", err)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO document_sample_memberships(
			source_id, generation, document_id, source_ordinal,
			object_sha256, risk_score
		) VALUES ($1, 1, $2, 1, $3, 0)
	`, fixture.sourceID, documentID, fixture.sourceSHA); err != nil {
		t.Fatalf("insert generated sample membership: %v", err)
	}
	if err := pool.QueryRow(ctx, `
		INSERT INTO review_campaigns(
			source_id, sample_generation, data_profile_key, data_profile_version,
			content_purpose, profile_config_sha256, rubric_key, rubric_version,
			purpose_contract_version, protocol_key, protocol_version,
			pii_policy_key, pii_policy_version, dedup_policy_key,
			dedup_policy_version, leakage_policy_key, leakage_policy_version,
			purpose_contract_sha256, campaign_contract_sha256,
			implementation_bundle_sha256, created_by
		)
		SELECT source.id, 1, source.data_profile_key, source.data_profile_version,
			source.content_purpose, source.profile_config_sha256,
			profile.rubric_key, profile.rubric_version,
			contract.purpose_contract_version, contract.protocol_key,
			contract.protocol_version, contract.pii_policy_key,
			contract.pii_policy_version, contract.dedup_policy_key,
			contract.dedup_policy_version, contract.leakage_policy_key,
			contract.leakage_policy_version, contract.spec_sha256, NULL,
			contract.implementation_bundle_sha256, $2
		FROM sources AS source
		JOIN data_profile_versions AS profile
		  ON profile.data_profile_key = source.data_profile_key
		 AND profile.data_profile_version = source.data_profile_version
		JOIN profile_purpose_contract_versions AS contract
		  ON contract.data_profile_key = source.data_profile_key
		 AND contract.data_profile_version = source.data_profile_version
		 AND contract.content_purpose = source.content_purpose
		WHERE source.id = $1 AND contract.purpose_contract_version = '1'
		RETURNING id::text
	`, fixture.sourceID, fixture.actorID).Scan(&fixture.campaignID); err != nil {
		t.Fatalf("insert generated review campaign: %v", err)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO document_review_claims(
			document_id, reviewer_id, claim_token, document_version,
			expires_at, review_campaign_id
		) VALUES ($1, $2, gen_random_uuid(), 1, now() + interval '5 minutes', $3)
	`, documentID, fixture.actorID, fixture.campaignID); err != nil {
		t.Fatalf("insert generated review claim: %v", err)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO document_reviews(
			document_id, reviewer_id, decision, quality_score,
			document_version, object_sha256, rubric_version,
			language_quality_score, coherence_score,
			information_density_score, cleanliness_score, review_campaign_id
		) VALUES (
			$1, $2, 'approved', 5, 1, $3, 'multidimensional-v1',
			5, 5, 5, 5, $4
		)
	`, documentID, fixture.actorID, fixture.sourceSHA,
		fixture.campaignID); err != nil {
		t.Fatalf("insert generated campaign review: %v", err)
	}
	if _, err := pool.Exec(ctx, `
		UPDATE sources
		SET pii_status = 'clear', approval_status = 'approved_source',
			duplicate_status = 'unique', normalized_dedup_status = 'unique',
			reviewed_document_count = sampled_document_count,
			approved_document_count = sampled_document_count,
			flagged_document_count = 0
		WHERE id = $1
	`, fixture.sourceID); err != nil {
		t.Fatalf("mark generated source release eligible: %v", err)
	}
	fixture.releaseID = createGeneratedDraftRelease(
		t, ctx, pool, fixture.actorID, fixture.sourceID, "generated release",
	)
	return fixture
}

func createGeneratedDraftRelease(
	t *testing.T,
	ctx context.Context,
	pool *pgxpool.Pool,
	actorID, sourceID, name string,
) string {
	t.Helper()
	var releaseID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO releases(name, version, content_purpose, created_by)
		VALUES ($1, gen_random_uuid()::text, 'pretrain', $2)
		RETURNING id::text
	`, name, actorID).Scan(&releaseID); err != nil {
		t.Fatalf("insert generated draft release: %v", err)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO release_sources(
			release_id, source_id, source_sha256, source_version,
			source_name, source_type, license, rights_status, language,
			domain, lineage_ref, byte_size, line_count
		)
		SELECT $1, id, object_sha256, version, name, source_type, license,
			rights_status, language, domain, lineage_ref, byte_size, line_count
		FROM sources WHERE id = $2
	`, releaseID, sourceID); err != nil {
		t.Fatalf("insert generated release source: %v", err)
	}
	return releaseID
}

func TestProductionRunCompletionIsExactAppendOnlyEvidenceOnPostgres(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	t.Cleanup(cancel)
	pool, _ := newProductionCompletionTestPool(t, ctx)
	const sentinel = "private-prompt-and-path-sentinel"
	fixture := seedProductionCompletion(t, ctx, pool, sentinel)

	var storedJobID, manifestSHA, outputSHA string
	var byteSize, recordCount int64
	var completedAt time.Time
	if err := pool.QueryRow(ctx, `
		SELECT job_id::text, output_manifest_sha256, output_sha256,
			output_byte_size, output_record_count, completed_at
		FROM production_run_completions
		WHERE production_run_id = $1
	`, fixture.runID).Scan(
		&storedJobID,
		&manifestSHA,
		&outputSHA,
		&byteSize,
		&recordCount,
		&completedAt,
	); err != nil {
		t.Fatalf("read production completion: %v", err)
	}
	if storedJobID != fixture.jobID || strings.TrimSpace(manifestSHA) != fixture.manifestSHA ||
		strings.TrimSpace(outputSHA) != fixture.outputSHA || byteSize != fixture.byteSize ||
		recordCount != fixture.recordCount || !completedAt.Equal(fixture.completedAt) {
		t.Fatalf(
			"stored completion mismatch: job=%s manifest=%s output=%s size=%d count=%d completed=%s",
			storedJobID,
			manifestSHA,
			outputSHA,
			byteSize,
			recordCount,
			completedAt,
		)
	}

	retryTag, err := pool.Exec(ctx, `
		INSERT INTO production_run_completions(
			production_run_id, job_id, output_manifest_sha256,
			output_sha256, output_byte_size, output_record_count,
			completed_at
		)
		VALUES ($1, $2, $3, $4, $5, $6, $7)
		ON CONFLICT (production_run_id) DO NOTHING
	`, fixture.runID, fixture.jobID, fixture.manifestSHA, fixture.outputSHA,
		fixture.byteSize, fixture.recordCount, fixture.completedAt)
	if err != nil || retryTag.RowsAffected() != 0 {
		t.Fatalf(
			"exact idempotent retry result = rows %d error %v, want 0/nil",
			retryTag.RowsAffected(),
			err,
		)
	}

	_, err = pool.Exec(ctx, `
		INSERT INTO production_run_completions(
			production_run_id, job_id, output_manifest_sha256,
			output_sha256, output_byte_size, output_record_count,
			completed_at
		)
		VALUES ($1, $2, $3, $4, $5, $6, $7)
	`, fixture.runID, fixture.jobID, fixture.manifestSHA, fixture.outputSHA,
		fixture.byteSize, fixture.recordCount, fixture.completedAt)
	if err == nil || !productionCompletionUniqueViolation(err) {
		t.Fatalf("duplicate completion error = %v, want unique violation", err)
	}
	_, err = pool.Exec(ctx, `
		INSERT INTO production_run_completions(
			production_run_id, job_id, output_manifest_sha256,
			output_sha256, output_byte_size, output_record_count,
			completed_at
		)
		VALUES ($1, $2, $3, repeat('9', 64), $4, $5, $6)
		ON CONFLICT (production_run_id) DO NOTHING
	`, fixture.runID, fixture.jobID, fixture.manifestSHA,
		fixture.byteSize, fixture.recordCount, fixture.completedAt)
	if err == nil || !strings.Contains(
		err.Error(),
		"production completion output does not match job result",
	) {
		t.Fatalf("conflicting idempotent retry error = %v, want mismatch", err)
	}

	for name, mutation := range map[string]struct {
		statement string
		args      []any
	}{
		"update": {
			"UPDATE production_run_completions SET output_byte_size = output_byte_size WHERE production_run_id = $1",
			[]any{fixture.runID},
		},
		"delete": {
			"DELETE FROM production_run_completions WHERE production_run_id = $1",
			[]any{fixture.runID},
		},
		"truncate": {"TRUNCATE production_run_completions CASCADE", nil},
	} {
		t.Run(name, func(t *testing.T) {
			_, err := pool.Exec(ctx, mutation.statement, mutation.args...)
			if err == nil || !strings.Contains(
				err.Error(),
				"production_run_completions are append-only",
			) {
				t.Fatalf("%s error = %v, want append-only rejection", name, err)
			}
		})
	}

	if _, err := pool.Exec(ctx, `
		UPDATE background_jobs
		SET result = result || jsonb_build_object('output_byte_size', 999)
		WHERE id = $1
	`, fixture.jobID); err == nil || !strings.Contains(
		err.Error(),
		"completed production job evidence is immutable",
	) {
		t.Fatalf("completed job mutation error = %v, want immutable rejection", err)
	}

	var operation string
	var rowKey, afterSummary []byte
	if err := pool.QueryRow(ctx, `
		SELECT operation, row_key::text, after_summary::text
		FROM row_change_events
		WHERE table_name = 'production_run_completions'
		  AND row_key->>'production_run_id' = $1
		ORDER BY id DESC
		LIMIT 1
	`, fixture.runID).Scan(&operation, &rowKey, &afterSummary); err != nil {
		t.Fatalf("read completion row-change evidence: %v", err)
	}
	ledgerText := string(rowKey) + string(afterSummary)
	if operation != "INSERT" || strings.Contains(ledgerText, sentinel) ||
		strings.Contains(ledgerText, "staged_path") ||
		strings.Contains(ledgerText, "system_prompt") ||
		strings.Contains(ledgerText, "private_result") {
		t.Fatalf("unsafe completion ledger evidence: %s", ledgerText)
	}
	var summary map[string]any
	if err := json.Unmarshal(afterSummary, &summary); err != nil {
		t.Fatalf("decode completion summary: %v", err)
	}
	if len(summary) != 7 || summary["production_run_id"] != fixture.runID ||
		summary["job_id"] != fixture.jobID {
		t.Fatalf("unexpected safe completion summary: %#v", summary)
	}
	var completionChangeCount int
	if err := pool.QueryRow(ctx, `
		SELECT count(*)
		FROM row_change_events
		WHERE table_name = 'production_run_completions'
		  AND row_key->>'production_run_id' = $1
	`, fixture.runID).Scan(&completionChangeCount); err != nil {
		t.Fatalf("count completion row-change evidence: %v", err)
	}
	if completionChangeCount != 1 {
		t.Fatalf(
			"completion row-change count after retry = %d, want 1",
			completionChangeCount,
		)
	}
}

func TestProductionRunCompletionRejectsMismatchedAndFailedJobsOnPostgres(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	t.Cleanup(cancel)
	pool, _ := newProductionCompletionTestPool(t, ctx)

	manifestSHA := strings.Repeat("e", 64)
	outputSHA := strings.Repeat("f", 64)
	if _, err := pool.Exec(ctx, `
		INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
		VALUES
			($1, 'tests/rejected-completion-manifest.json', 88, 'application/json'),
			($2, 'tests/rejected-completion-output.jsonl', 100, 'application/x-ndjson')
	`, manifestSHA, outputSHA); err != nil {
		t.Fatalf("insert rejected completion storage objects: %v", err)
	}

	t.Run("output mismatch", func(t *testing.T) {
		runID := insertProductionRunIntent(t, ctx, pool, "model")
		jobID, completedAt := insertCompletedGenerationJob(
			t, ctx, pool, runID, "succeeded", manifestSHA, outputSHA, 100, 2, "x",
		)
		_, err := pool.Exec(ctx, `
			INSERT INTO production_run_completions(
				production_run_id, job_id, output_manifest_sha256,
				output_sha256, output_byte_size, output_record_count,
				completed_at
			)
			VALUES ($1, $2, $3, repeat('1', 64), 100, 2, $4)
		`, runID, jobID, manifestSHA, completedAt)
		if err == nil || !strings.Contains(
			err.Error(),
			"production completion output does not match job result",
		) {
			t.Fatalf("mismatched output error = %v", err)
		}
	})

	t.Run("failed job", func(t *testing.T) {
		runID := insertProductionRunIntent(t, ctx, pool, "model")
		jobID, completedAt := insertCompletedGenerationJob(
			t, ctx, pool, runID, "failed", manifestSHA, outputSHA, 100, 2, "x",
		)
		_, err := pool.Exec(ctx, `
			INSERT INTO production_run_completions(
				production_run_id, job_id, output_manifest_sha256,
				output_sha256, output_byte_size, output_record_count,
				completed_at
			)
			VALUES ($1, $2, $3, $4, 100, 2, $5)
		`, runID, jobID, manifestSHA, outputSHA, completedAt)
		if err == nil || !strings.Contains(
			err.Error(),
			"production completion job is not successful generation evidence",
		) {
			t.Fatalf("failed job completion error = %v", err)
		}
	})

	t.Run("missing output storage object", func(t *testing.T) {
		missingOutputSHA := strings.Repeat("3", 64)
		runID := insertProductionRunIntent(t, ctx, pool, "model")
		jobID, completedAt := insertCompletedGenerationJob(
			t, ctx, pool, runID, "succeeded", manifestSHA, missingOutputSHA, 101, 3, "x",
		)
		_, err := pool.Exec(ctx, `
			INSERT INTO production_run_completions(
				production_run_id, job_id, output_manifest_sha256,
				output_sha256, output_byte_size, output_record_count,
				completed_at
			)
			VALUES ($1, $2, $3, $4, 101, 3, $5)
		`, runID, jobID, manifestSHA, missingOutputSHA, completedAt)
		if err == nil {
			t.Fatal("production completion accepted a missing output storage object")
		}
		var pgError *pgconn.PgError
		if !errors.As(err, &pgError) || pgError.Code != "23503" {
			t.Fatalf("missing output object error = %v, want foreign-key violation", err)
		}
	})

	t.Run("output storage size mismatch", func(t *testing.T) {
		runID := insertProductionRunIntent(t, ctx, pool, "model")
		jobID, completedAt := insertCompletedGenerationJob(
			t, ctx, pool, runID, "succeeded", manifestSHA, outputSHA, 101, 3, "x",
		)
		_, err := pool.Exec(ctx, `
			INSERT INTO production_run_completions(
				production_run_id, job_id, output_manifest_sha256,
				output_sha256, output_byte_size, output_record_count,
				completed_at
			)
			VALUES ($1, $2, $3, $4, 101, 3, $5)
		`, runID, jobID, manifestSHA, outputSHA, completedAt)
		if err == nil || !strings.Contains(
			err.Error(),
			"production completion output storage evidence does not match",
		) {
			t.Fatalf("output storage size mismatch error = %v", err)
		}
	})

	t.Run("wrong run", func(t *testing.T) {
		jobRunID := insertProductionRunIntent(t, ctx, pool, "model")
		completionRunID := insertProductionRunIntent(t, ctx, pool, "model")
		jobID, completedAt := insertCompletedGenerationJob(
			t, ctx, pool, jobRunID, "succeeded", manifestSHA, outputSHA, 100, 2, "x",
		)
		_, err := pool.Exec(ctx, `
			INSERT INTO production_run_completions(
				production_run_id, job_id, output_manifest_sha256,
				output_sha256, output_byte_size, output_record_count,
				completed_at
			)
			VALUES ($1, $2, $3, $4, 100, 2, $5)
		`, completionRunID, jobID, manifestSHA, outputSHA, completedAt)
		if err == nil || !strings.Contains(
			err.Error(),
			"production completion job is not successful generation evidence",
		) {
			t.Fatalf("wrong-run completion error = %v", err)
		}
	})

	t.Run("zero-size output", func(t *testing.T) {
		zeroSizeOutputSHA := strings.Repeat("4", 64)
		if _, err := pool.Exec(ctx, `
			INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
			VALUES ($1, 'tests/zero-size-completion-output.jsonl', 0, 'application/x-ndjson')
		`, zeroSizeOutputSHA); err != nil {
			t.Fatalf("insert zero-size output object: %v", err)
		}
		runID := insertProductionRunIntent(t, ctx, pool, "model")
		jobID, completedAt := insertCompletedGenerationJob(
			t, ctx, pool, runID, "succeeded", manifestSHA, zeroSizeOutputSHA, 0, 2, "x",
		)
		_, err := pool.Exec(ctx, `
			INSERT INTO production_run_completions(
				production_run_id, job_id, output_manifest_sha256,
				output_sha256, output_byte_size, output_record_count,
				completed_at
			)
			VALUES ($1, $2, $3, $4, 0, 2, $5)
		`, runID, jobID, manifestSHA, zeroSizeOutputSHA, completedAt)
		if err == nil {
			t.Fatal("zero-size production output was accepted")
		}
		var pgError *pgconn.PgError
		if !errors.As(err, &pgError) || pgError.Code != "23514" {
			t.Fatalf("zero-size output error = %v, want check violation", err)
		}
	})
}

func TestProductionRunCompletionPinsModelReleaseAndTopHashAcrossTimezonesOnPostgres(
	t *testing.T,
) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	t.Cleanup(cancel)
	pool, _ := newProductionCompletionTestPool(t, ctx)
	const sentinel = "private-release-completion-prompt-and-path"
	fixture := seedGeneratedRelease(
		t, ctx, pool, "model", true, true, 1, sentinel,
	)
	if _, err := pool.Exec(
		ctx, generatedReleaseSnapshotInsertSQL, fixture.releaseID, fixture.campaignID,
	); err != nil {
		t.Fatalf("insert model release completion snapshot: %v", err)
	}

	var jobID, manifestSHA, outputSHA, completedUTC string
	var byteSize, recordCount int64
	if err := pool.QueryRow(ctx, `
		SELECT production_run_completion_job_id::text,
			production_run_output_manifest_sha256::text,
			production_run_output_sha256::text,
			production_run_output_byte_size,
			production_run_output_record_count,
			production_run_completed_at_utc
		FROM release_source_contract_snapshots
		WHERE release_id = $1 AND source_id = $2
	`, fixture.releaseID, fixture.sourceID).Scan(
		&jobID, &manifestSHA, &outputSHA, &byteSize, &recordCount, &completedUTC,
	); err != nil {
		t.Fatalf("read release completion pins: %v", err)
	}
	expectedCompletedUTC := fixture.completedAt.UTC().Format(
		"2006-01-02T15:04:05.000000Z",
	)
	if jobID != fixture.jobID || strings.TrimSpace(manifestSHA) != fixture.manifestSHA ||
		strings.TrimSpace(outputSHA) != fixture.outputSHA || byteSize != fixture.byteSize ||
		recordCount != fixture.recordCount || completedUTC != expectedCompletedUTC {
		t.Fatalf(
			"release completion pins mismatch: job=%s manifest=%s output=%s size=%d count=%d completed=%s",
			jobID, manifestSHA, outputSHA, byteSize, recordCount, completedUTC,
		)
	}

	var snapshotSummary []byte
	if err := pool.QueryRow(ctx, `
		SELECT after_summary::text
		FROM row_change_events
		WHERE table_name = 'release_source_contract_snapshots'
		  AND row_key->>'release_id' = $1
		  AND row_key->>'source_id' = $2
		ORDER BY id DESC LIMIT 1
	`, fixture.releaseID, fixture.sourceID).Scan(&snapshotSummary); err != nil {
		t.Fatalf("read release completion snapshot ledger: %v", err)
	}
	ledgerText := string(snapshotSummary)
	for _, safePin := range []string{
		fixture.jobID, fixture.manifestSHA, fixture.outputSHA,
		expectedCompletedUTC,
	} {
		if !strings.Contains(ledgerText, safePin) {
			t.Fatalf("release snapshot ledger is missing safe completion pin %q: %s", safePin, ledgerText)
		}
	}
	if strings.Contains(ledgerText, sentinel) || strings.Contains(ledgerText, `"payload":`) ||
		strings.Contains(ledgerText, `"result":`) ||
		strings.Contains(ledgerText, "staged_path") ||
		strings.Contains(ledgerText, "system_prompt") ||
		strings.Contains(ledgerText, "private_result") {
		t.Fatalf("unsafe release completion snapshot ledger: %s", ledgerText)
	}

	connection, err := pool.Acquire(ctx)
	if err != nil {
		t.Fatalf("acquire release timezone connection: %v", err)
	}
	defer connection.Release()
	if _, err := connection.Exec(ctx, "SET TIME ZONE 'UTC'"); err != nil {
		t.Fatalf("set UTC for release present transition: %v", err)
	}
	var presentSHA string
	if err := connection.QueryRow(ctx, `
		UPDATE releases SET contract_snapshot_status = 'present'
		WHERE id = $1
		RETURNING contract_snapshot_sha256::text
	`, fixture.releaseID).Scan(&presentSHA); err != nil {
		t.Fatalf("mark model release snapshot present: %v", err)
	}

	var artifactChildRoot, derivedChildRoot, originalChild, forgedChild string
	if err := connection.QueryRow(ctx, `
		WITH snapshot AS (
			SELECT canonical_release_source_snapshot_json(to_jsonb(child)) AS payload
			FROM release_source_contract_snapshots AS child
			WHERE child.release_id = $1 AND child.source_id = $2
		), child_hashes AS (
			SELECT
				btrim(contract_spec_artifact_sha256(
					convert_to(payload::text, 'UTF8')
				)::text) AS original_child,
				btrim(contract_spec_artifact_sha256(convert_to(
					jsonb_set(payload, '{production_run_output_sha256}',
						to_jsonb(repeat('9', 64)))::text,
					'UTF8'
				))::text) AS forged_child
			FROM snapshot
		), artifact AS (
			SELECT convert_from(canonical_bytes, 'UTF8')::jsonb AS payload
			FROM contract_spec_artifacts
			WHERE artifact_kind = 'contract_bundle' AND sha256 = $3
		)
		SELECT artifact.payload->>'child_snapshot_root_sha256',
			contract_spec_artifact_sha256(convert_to(original_child, 'UTF8'))::text,
			original_child, forged_child
		FROM artifact, child_hashes
	`, fixture.releaseID, fixture.sourceID, presentSHA).Scan(
		&artifactChildRoot, &derivedChildRoot, &originalChild, &forgedChild,
	); err != nil {
		t.Fatalf("verify release top completion commitment: %v", err)
	}
	if strings.TrimSpace(derivedChildRoot) != artifactChildRoot || originalChild == forgedChild {
		t.Fatalf(
			"release top does not commit completion pins: artifact=%s derived=%s original=%s forged=%s",
			artifactChildRoot, derivedChildRoot, originalChild, forgedChild,
		)
	}

	if _, err := connection.Exec(ctx, "SET TIME ZONE 'Europe/Istanbul'"); err != nil {
		t.Fatalf("set Istanbul for release freeze transition: %v", err)
	}
	var frozenSHA string
	if err := connection.QueryRow(ctx, `
		UPDATE releases
		SET status = 'frozen', manifest_object_sha256 = $2,
			manifest_sha256 = $2, frozen_by = $3, frozen_at = now()
		WHERE id = $1
		RETURNING contract_snapshot_sha256::text
	`, fixture.releaseID, fixture.outputSHA, fixture.actorID).Scan(&frozenSHA); err != nil {
		t.Fatalf("freeze model release under non-UTC timezone: %v", err)
	}
	if frozenSHA != presentSHA {
		t.Fatalf("release contract hash changed across TimeZone: present=%s frozen=%s", presentSHA, frozenSHA)
	}
}

func TestProductionRunCompletionReleaseEvidenceFailsClosedOnPostgres(t *testing.T) {
	t.Run("model without completion", func(t *testing.T) {
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
		t.Cleanup(cancel)
		pool, _ := newProductionCompletionTestPool(t, ctx)
		fixture := seedGeneratedRelease(
			t, ctx, pool, "model", false, true, 1, "missing-completion",
		)
		_, err := pool.Exec(
			ctx, generatedReleaseSnapshotInsertSQL, fixture.releaseID, fixture.campaignID,
		)
		if err == nil || !strings.Contains(
			err.Error(),
			"model or hybrid release source requires production completion evidence",
		) {
			t.Fatalf("model snapshot without completion error = %v", err)
		}
	})

	t.Run("source output SHA and size mismatch", func(t *testing.T) {
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
		t.Cleanup(cancel)
		pool, _ := newProductionCompletionTestPool(t, ctx)
		fixture := seedGeneratedRelease(
			t, ctx, pool, "model", true, false, 1, "source-output-mismatch",
		)
		_, err := pool.Exec(
			ctx, generatedReleaseSnapshotInsertSQL, fixture.releaseID, fixture.campaignID,
		)
		if err == nil || !strings.Contains(
			err.Error(),
			"release source identity does not match production completion output",
		) {
			t.Fatalf("source/output identity mismatch error = %v", err)
		}
	})

	t.Run("source record count mismatch", func(t *testing.T) {
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
		t.Cleanup(cancel)
		pool, _ := newProductionCompletionTestPool(t, ctx)
		fixture := seedGeneratedRelease(
			t, ctx, pool, "model", true, true, 2, "record-count-mismatch",
		)
		_, err := pool.Exec(
			ctx, generatedReleaseSnapshotInsertSQL, fixture.releaseID, fixture.campaignID,
		)
		if err == nil || !strings.Contains(
			err.Error(),
			"release source identity does not match production completion output",
		) {
			t.Fatalf("source/output record-count mismatch error = %v", err)
		}
	})

	t.Run("forged completion pin", func(t *testing.T) {
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
		t.Cleanup(cancel)
		pool, _ := newProductionCompletionTestPool(t, ctx)
		fixture := seedGeneratedRelease(
			t, ctx, pool, "model", true, true, 1, "forged-completion-pin",
		)
		forgedSQL := strings.Replace(
			generatedReleaseSnapshotInsertSQL,
			"implementation_bundle_sha256\n\t)",
			"implementation_bundle_sha256, production_run_output_record_count\n\t)",
			1,
		)
		forgedSQL = strings.Replace(
			forgedSQL,
			"campaign.id, 'campaign_pinned', campaign.implementation_bundle_sha256",
			"campaign.id, 'campaign_pinned', campaign.implementation_bundle_sha256, 999",
			1,
		)
		_, err := pool.Exec(ctx, forgedSQL, fixture.releaseID, fixture.campaignID)
		if err == nil || !strings.Contains(
			err.Error(),
			"release production completion pins do not match evidence",
		) {
			t.Fatalf("forged completion pin error = %v", err)
		}
	})
}

func TestProductionRunCompletionPinsHybridReleaseOnPostgres(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	t.Cleanup(cancel)
	pool, _ := newProductionCompletionTestPool(t, ctx)
	fixture := seedGeneratedRelease(
		t, ctx, pool, "hybrid", true, true, 1, "hybrid-completion",
	)
	if _, err := pool.Exec(
		ctx, generatedReleaseSnapshotInsertSQL, fixture.releaseID, fixture.campaignID,
	); err != nil {
		t.Fatalf("insert hybrid release completion snapshot: %v", err)
	}
	var origin, runID, jobID string
	if err := pool.QueryRow(ctx, `
		SELECT data_origin, production_run_id::text,
			production_run_completion_job_id::text
		FROM release_source_contract_snapshots
		WHERE release_id = $1 AND source_id = $2
	`, fixture.releaseID, fixture.sourceID).Scan(&origin, &runID, &jobID); err != nil {
		t.Fatalf("read hybrid release completion pins: %v", err)
	}
	if origin != "hybrid" || runID != fixture.runID || jobID != fixture.jobID {
		t.Fatalf("unexpected hybrid completion pins: origin=%s run=%s job=%s", origin, runID, jobID)
	}
}

func TestProductionRunCompletionValidatorIgnoresTemporaryShadowTables(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	t.Cleanup(cancel)
	pool, _ := newProductionCompletionTestPool(t, ctx)

	manifestSHA := strings.Repeat("1", 64)
	outputSHA := strings.Repeat("2", 64)
	if _, err := pool.Exec(ctx, `
		INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
		VALUES ($1, 'tests/shadow-manifest.json', 77, 'application/json')
	`, manifestSHA); err != nil {
		t.Fatalf("insert shadow-test manifest: %v", err)
	}
	runID := insertProductionRunIntent(t, ctx, pool, "model")
	jobID, completedAt := insertCompletedGenerationJob(
		t, ctx, pool, runID, "failed", manifestSHA, outputSHA, 100, 2, "shadow",
	)

	connection, err := pool.Acquire(ctx)
	if err != nil {
		t.Fatalf("acquire shadow-test connection: %v", err)
	}
	defer connection.Release()
	if _, err := connection.Exec(ctx, `
		CREATE TEMP TABLE background_jobs (
			id uuid PRIMARY KEY,
			job_type text,
			status text,
			payload jsonb,
			result jsonb,
			completed_at timestamptz
		)
	`); err != nil {
		t.Fatalf("create shadow background_jobs: %v", err)
	}
	if _, err := connection.Exec(ctx, `
		INSERT INTO pg_temp.background_jobs(
			id, job_type, status, payload, result, completed_at
		)
		VALUES (
			$1, 'distill_source', 'succeeded',
			jsonb_build_object('production_run_id', $2::text),
			jsonb_build_object(
				'production_run_id', $2::text,
				'manifest_sha256', $3::text,
				'output_sha256', $4::text,
				'output_byte_size', 100,
				'document_count', 2
			),
			$5
		)
	`, jobID, runID, manifestSHA, outputSHA, completedAt); err != nil {
		t.Fatalf("insert shadow background job: %v", err)
	}

	_, err = connection.Exec(ctx, `
		INSERT INTO production_run_completions(
			production_run_id, job_id, output_manifest_sha256,
			output_sha256, output_byte_size, output_record_count,
			completed_at
		)
		VALUES ($1, $2, $3, $4, 100, 2, $5)
	`, runID, jobID, manifestSHA, outputSHA, completedAt)
	if err == nil || !strings.Contains(
		err.Error(),
		"production completion job is not successful generation evidence",
	) {
		t.Fatalf("shadow table completion error = %v", err)
	}
}

func productionCompletionUniqueViolation(err error) bool {
	var pgError *pgconn.PgError
	return errors.As(err, &pgError) && pgError.Code == "23505"
}
