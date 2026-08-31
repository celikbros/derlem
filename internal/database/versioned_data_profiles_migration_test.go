package database

import (
	"context"
	"crypto/sha256"
	"fmt"
	"io/fs"
	"os"
	"sort"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

func TestVersionedDataProfilesMigrationDeclaresAdditiveEvidenceFoundation(t *testing.T) {
	contents, err := migrationFiles.ReadFile("migrations/000024_versioned_data_profiles.sql")
	if err != nil {
		t.Fatalf("read versioned data profiles migration: %v", err)
	}
	migration := string(contents)

	for _, required := range []string{
		"CREATE TABLE contract_spec_artifacts",
		"canonical_bytes bytea NOT NULL",
		"contract artifact sha256 does not match canonical bytes",
		"CREATE TABLE review_rubric_versions",
		"CREATE TABLE review_protocol_versions",
		"CREATE TABLE data_policy_versions",
		"CREATE TABLE export_contract_versions",
		"CREATE TABLE data_profile_versions",
		"CREATE TABLE data_profile_purposes",
		"CREATE TABLE profile_purpose_contract_versions",
		"CREATE TABLE production_runs",
		"CREATE TABLE review_campaigns",
		"CREATE TABLE release_source_contract_snapshots",
		"profile_config_schema_sha256 char(64) NOT NULL",
		"profile_implementation_key text NOT NULL",
		"profile_implementation_digest char(64) NOT NULL",
		"ADD COLUMN review_campaign_id uuid",
		"'pending', 'absent_pre_registry', 'present'",
		"source data profile and provenance are immutable",
		"terminal legacy data profiles cannot be assigned to new sources",
		"source origin does not match production run matrix",
		"release source is not eligible",
		"requires_full_revalidation",
		"ALTER COLUMN data_profile_key SET DEFAULT 'text-document'",
		"SET data_profile_key = 'legacy-auto'",
		"profile_assignment_reason = 'backfilled'",
		"ALTER TABLE sources DISABLE TRIGGER sources_protect_content_purpose",
		"ALTER TABLE sources DISABLE TRIGGER sources_set_updated_at",
		"SET contract_snapshot_status = 'absent_pre_registry'",
		"release contract snapshot incomplete",
		"CREATE TRIGGER contract_spec_artifacts_capture_row_change",
		"CREATE TRIGGER review_campaigns_capture_row_change",
		"CREATE TRIGGER release_source_contract_snapshots_capture_row_change",
		"REVOKE ALL ON FUNCTION contract_spec_artifact_sha256(bytea) FROM PUBLIC",
		"no JSON Canonicalization Scheme claim is implied",
	} {
		if !strings.Contains(migration, required) {
			t.Errorf("migration is missing %q", required)
		}
	}

	for _, forbidden := range []string{
		"DISABLE TRIGGER sources_capture_row_change",
		"INSERT INTO release_source_contract_snapshots",
		"CREATE TABLE translation_pairs",
		"CREATE TABLE reasoning_records",
		"ALTER TABLE documents ADD COLUMN data_profile",
	} {
		if strings.Contains(migration, forbidden) {
			t.Errorf("migration unexpectedly contains %q", forbidden)
		}
	}

	summaryAt := strings.Index(migration, "CREATE OR REPLACE FUNCTION row_change_safe_summary(")
	backfillAt := strings.Index(migration, "UPDATE sources\nSET data_profile_key = 'legacy-auto'")
	if summaryAt < 0 || backfillAt < 0 || summaryAt > backfillAt {
		t.Fatal("safe row summary must be extended before source backfill")
	}
}

func newVersionedProfilesTestPool(t *testing.T, ctx context.Context) (*pgxpool.Pool, string) {
	t.Helper()
	databaseURL := strings.TrimSpace(os.Getenv(`DERLEM_TEST_DATABASE_URL`))
	if databaseURL == `` {
		t.Skip(`DERLEM_TEST_DATABASE_URL is not set`)
	}
	adminPool, err := pgxpool.New(ctx, databaseURL)
	if err != nil {
		t.Fatalf(`open admin pool: %v`, err)
	}
	t.Cleanup(adminPool.Close)
	schemaName := fmt.Sprintf(`derlem_profiles_migration_test_%d`, time.Now().UnixNano())
	schemaIdentifier := pgx.Identifier{schemaName}.Sanitize()
	// pgcrypto'yu izole semadan ONCE ve public'te olustur (bkz. digerleri).
	if _, err := adminPool.Exec(ctx, "CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public"); err != nil {
		t.Fatalf("ensure pgcrypto: %v", err)
	}

	if _, err := adminPool.Exec(ctx, `CREATE SCHEMA `+schemaIdentifier); err != nil {
		t.Fatalf(`create test schema: %v`, err)
	}
	t.Cleanup(func() {
		cleanupCtx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()
		if _, err := adminPool.Exec(cleanupCtx, `DROP SCHEMA `+schemaIdentifier+` CASCADE`); err != nil {
			t.Errorf(`drop test schema: %v`, err)
		}
	})
	config, err := pgxpool.ParseConfig(databaseURL)
	if err != nil {
		t.Fatalf(`parse test database URL: %v`, err)
	}
	config.ConnConfig.RuntimeParams[`search_path`] = schemaName
	pool, err := pgxpool.NewWithConfig(ctx, config)
	if err != nil {
		t.Fatalf(`open isolated pool: %v`, err)
	}
	t.Cleanup(pool.Close)
	return pool, schemaName
}

func applyMigrationsBeforeVersionedProfiles(t *testing.T, ctx context.Context, pool *pgxpool.Pool) {
	t.Helper()
	entries, err := fs.ReadDir(migrationFiles, `migrations`)
	if err != nil {
		t.Fatalf(`read migrations: %v`, err)
	}
	sort.Slice(entries, func(i, j int) bool { return entries[i].Name() < entries[j].Name() })
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), `.sql`) ||
			entry.Name() >= `000024_versioned_data_profiles.sql` {
			continue
		}
		contents, err := migrationFiles.ReadFile(`migrations/` + entry.Name())
		if err != nil {
			t.Fatalf(`read prerequisite migration %s: %v`, entry.Name(), err)
		}
		if _, err := pool.Exec(ctx, string(contents)); err != nil {
			t.Fatalf(`apply prerequisite migration %s: %v`, entry.Name(), err)
		}
	}
}

func TestVersionedDataProfilesMigrationBackfillsAndPinsOnPostgres(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	t.Cleanup(cancel)
	pool, schemaName := newVersionedProfilesTestPool(t, ctx)
	applyMigrationsBeforeVersionedProfiles(t, ctx, pool)

	const objectSHA = `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`
	const secondObjectSHA = `bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb`
	const samplingSentinel = `private-sampling-sentinel-risk-v1`
	const lineageSentinel = `private-lineage-sentinel`
	const licenseSentinel = `private-license-sentinel`
	var actorID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO users(email, password_hash, display_name)
		VALUES ('profiles-migration@example.test', 'test', 'Profiles Migration')
		RETURNING id::text
	`).Scan(&actorID); err != nil {
		t.Fatalf(`insert actor: %v`, err)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
		VALUES
			($1, 'profiles/source.txt', 100, 'text/plain'),
			($2, 'profiles/other.txt', 120, 'text/plain')
	`, objectSHA, secondObjectSHA); err != nil {
		t.Fatalf(`insert storage object: %v`, err)
	}
	var sourceID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO sources(
			name, source_type, content_purpose, license, rights_status,
			language, domain, lineage_ref, object_sha256, byte_size,
			line_count, created_by
		) VALUES (
			'pre-registry source', 'text_corpus', 'pretrain', 'internal',
			'cleared', 'tr', 'mixed', 'source.txt', $1, 100, 2, $2
		) RETURNING id::text
	`, objectSHA, actorID).Scan(&sourceID); err != nil {
		t.Fatalf(`insert pre-registry source: %v`, err)
	}
	var versionBefore int64
	var updatedBefore time.Time
	if err := pool.QueryRow(ctx, `SELECT version, updated_at FROM sources WHERE id = $1`, sourceID).
		Scan(&versionBefore, &updatedBefore); err != nil {
		t.Fatalf(`read source before migration: %v`, err)
	}
	var frozenReleaseID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO releases(name, version, content_purpose, created_by)
		VALUES ('pre-registry release', '1', 'pretrain', $1)
		RETURNING id::text
	`, actorID).Scan(&frozenReleaseID); err != nil {
		t.Fatalf(`insert draft release: %v`, err)
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
	`, frozenReleaseID, sourceID); err != nil {
		t.Fatalf(`insert pre-registry release source: %v`, err)
	}
	if _, err := pool.Exec(ctx, `
		UPDATE releases SET status = 'frozen', manifest_object_sha256 = $2,
			manifest_sha256 = $2, frozen_by = $3, frozen_at = now()
		WHERE id = $1
	`, frozenReleaseID, objectSHA, actorID); err != nil {
		t.Fatalf(`freeze pre-registry release: %v`, err)
	}
	var historicalManifestSHA, historicalReleaseSourceJSON string
	if err := pool.QueryRow(ctx, `
		SELECT manifest_sha256::text FROM releases WHERE id = $1
	`, frozenReleaseID).Scan(&historicalManifestSHA); err != nil {
		t.Fatalf(`read historical manifest identity: %v`, err)
	}
	if err := pool.QueryRow(ctx, `
		SELECT to_jsonb(release_source)::text
		FROM release_sources AS release_source
		WHERE release_id = $1 AND source_id = $2
	`, frozenReleaseID, sourceID).Scan(&historicalReleaseSourceJSON); err != nil {
		t.Fatalf(`read historical release source: %v`, err)
	}
	var migrationStartedAt time.Time
	if err := pool.QueryRow(ctx, `SELECT clock_timestamp()`).Scan(&migrationStartedAt); err != nil {
		t.Fatalf(`read migration start time: %v`, err)
	}
	migration, err := migrationFiles.ReadFile(`migrations/000024_versioned_data_profiles.sql`)
	if err != nil {
		t.Fatalf(`read versioned profiles migration: %v`, err)
	}
	if _, err := pool.Exec(ctx, string(migration)); err != nil {
		t.Fatalf(`apply versioned profiles migration: %v`, err)
	}
	timezoneConn, err := pool.Acquire(ctx)
	if err != nil {
		t.Fatalf(`acquire timezone determinism connection: %v`, err)
	}
	defer timezoneConn.Release()
	var utcCanonical, istanbulCanonical string
	for zone, target := range map[string]*string{
		`UTC`:             &utcCanonical,
		`Europe/Istanbul`: &istanbulCanonical,
	} {
		if _, err := timezoneConn.Exec(ctx, `SET TIME ZONE '`+zone+`'`); err != nil {
			t.Fatalf(`set timezone %s: %v`, zone, err)
		}
		if err := timezoneConn.QueryRow(ctx, `
			SELECT canonical_release_source_snapshot_json(jsonb_build_object(
				'production_run_completed_at',
				'2026-08-21 12:34:56.123456+00'::timestamptz,
				'source_id', gen_random_uuid()
			) - 'source_id')::text
		`).Scan(target); err != nil {
			t.Fatalf(`canonicalize timestamp under %s: %v`, zone, err)
		}
	}
	if utcCanonical != istanbulCanonical {
		t.Fatalf(`snapshot timestamp hash input depends on TimeZone: UTC=%s Istanbul=%s`,
			utcCanonical, istanbulCanonical)
	}
	var profileKey, assignmentReason string
	var versionAfter int64
	var updatedAfter, assignedAt time.Time
	if err := pool.QueryRow(ctx, `
		SELECT data_profile_key, profile_assignment_reason, version,
			updated_at, profile_assigned_at
		FROM sources WHERE id = $1
	`, sourceID).Scan(
		&profileKey, &assignmentReason, &versionAfter, &updatedAfter, &assignedAt,
	); err != nil {
		t.Fatalf(`read source after migration: %v`, err)
	}
	if profileKey != `legacy-auto` || assignmentReason != `backfilled` {
		t.Fatalf(`unexpected legacy backfill: profile=%q reason=%q`, profileKey, assignmentReason)
	}
	if versionAfter != versionBefore || !updatedAfter.Equal(updatedBefore) {
		t.Fatalf(`backfill changed source version metadata`)
	}
	if assignedAt.Before(migrationStartedAt) {
		t.Fatalf(`profile assignment predates migration: assigned=%s start=%s`, assignedAt, migrationStartedAt)
	}
	var snapshotStatus string
	var snapshotChildren int
	if err := pool.QueryRow(ctx, `
		SELECT contract_snapshot_status,
			(SELECT count(*) FROM release_source_contract_snapshots WHERE release_id = releases.id)
		FROM releases WHERE id = $1
	`, frozenReleaseID).Scan(&snapshotStatus, &snapshotChildren); err != nil {
		t.Fatalf(`read historical release evidence: %v`, err)
	}
	if snapshotStatus != `absent_pre_registry` || snapshotChildren != 0 {
		t.Fatalf(`historical release evidence was fabricated: status=%q children=%d`, snapshotStatus, snapshotChildren)
	}
	var historicalManifestAfter, historicalReleaseSourceAfter string
	if err := pool.QueryRow(ctx, `
		SELECT manifest_sha256::text FROM releases WHERE id = $1
	`, frozenReleaseID).Scan(&historicalManifestAfter); err != nil {
		t.Fatalf(`read historical manifest after migration: %v`, err)
	}
	if err := pool.QueryRow(ctx, `
		SELECT to_jsonb(release_source)::text
		FROM release_sources AS release_source
		WHERE release_id = $1 AND source_id = $2
	`, frozenReleaseID, sourceID).Scan(&historicalReleaseSourceAfter); err != nil {
		t.Fatalf(`read historical release source after migration: %v`, err)
	}
	if historicalManifestAfter != historicalManifestSHA ||
		historicalReleaseSourceAfter != historicalReleaseSourceJSON {
		t.Fatal(`legacy migration changed frozen manifest or release source snapshot`)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO releases(
			name, version, content_purpose, status, manifest_object_sha256,
			manifest_sha256, frozen_by, frozen_at, created_by
		) VALUES (
			'direct frozen bypass', '1', 'pretrain', 'frozen', $1,
			$1, $2, now(), $2
		)
	`, objectSHA, actorID); err == nil ||
		!strings.Contains(err.Error(), `must begin as draft`) {
		t.Fatalf(`direct frozen release insert error=%v`, err)
	}
	var backfillAudit int
	if err := pool.QueryRow(ctx, `
		SELECT count(*) FROM audit_events
		WHERE entity_id = $1 AND action = 'source.data_profile_backfilled'
	`, sourceID).Scan(&backfillAudit); err != nil || backfillAudit != 1 {
		t.Fatalf(`source backfill audit count=%d err=%v`, backfillAudit, err)
	}
	var currentSourceID, currentProfile, currentReason string
	if err := pool.QueryRow(ctx, `
		INSERT INTO sources(
			name, source_type, content_purpose, license, rights_status,
			language, domain, lineage_ref, license_evidence_ref,
			object_sha256, byte_size,
			line_count, created_by
		) VALUES (
			'current source', 'text_corpus', 'pretrain', 'internal',
			'cleared', 'tr', 'mixed', $3, $4, $1, 100, 2, $2
		) RETURNING id::text, data_profile_key, profile_assignment_reason
	`, objectSHA, actorID, lineageSentinel, licenseSentinel).Scan(
		&currentSourceID, &currentProfile, &currentReason,
	); err != nil {
		t.Fatalf(`insert current source: %v`, err)
	}
	if currentProfile != `text-document` || currentReason != `declared_at_ingest` {
		t.Fatalf(`unexpected new source defaults: profile=%q reason=%q`, currentProfile, currentReason)
	}
	nonSeedConfigBytes := []byte(`{"unexpected":true}`)
	nonSeedConfigSHA := fmt.Sprintf(`%x`, sha256.Sum256(nonSeedConfigBytes))
	if _, err := pool.Exec(ctx, `
		INSERT INTO contract_spec_artifacts(
			sha256, artifact_kind, canonicalization_key, media_type,
			canonical_bytes, byte_size
		) VALUES ($1, 'profile_config', 'literal-utf8-v1',
			'application/json', $2, $3)
	`, nonSeedConfigSHA, nonSeedConfigBytes, len(nonSeedConfigBytes)); err != nil {
		t.Fatalf(`insert non-seed profile config artifact: %v`, err)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO sources(
			name, source_type, content_purpose, license, rights_status,
			language, domain, lineage_ref, created_by, profile_config_sha256
		) VALUES (
			'wrong v1 config', 'text_corpus', 'pretrain', 'internal',
			'cleared', 'tr', 'mixed', 'wrong-config.txt', $1, $2
		)
	`, actorID, nonSeedConfigSHA); err == nil ||
		!strings.Contains(err.Error(), `sources_v1_seed_profile_config_identity`) {
		t.Fatalf(`non-seed text-document-v1 config error=%v`, err)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO production_runs(
			run_kind, origin_kind, implementation_key, implementation_digest
		) VALUES ('model_generation', 'hybrid', 'bad.matrix', repeat('a', 64))
	`); err == nil {
		t.Fatal(`invalid production run kind/origin matrix unexpectedly succeeded`)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO sources(
			name, source_type, content_purpose, license, rights_status,
			language, domain, lineage_ref, created_by, data_origin
		) VALUES (
			'human without run', 'text_corpus', 'pretrain', 'internal',
			'cleared', 'tr', 'mixed', 'human.txt', $1, 'human'
		)
	`, actorID); err == nil || !strings.Contains(err.Error(), `require a production run`) {
		t.Fatalf(`human source without production run error=%v`, err)
	}
	var configlessRunID, modelRunID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO production_runs(
			run_kind, origin_kind, implementation_key, implementation_digest
		) VALUES ('model_generation', 'model', 'configless.model', repeat('a', 64))
		RETURNING id::text
	`).Scan(&configlessRunID); err != nil {
		t.Fatalf(`insert configless model run: %v`, err)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO sources(
			name, source_type, content_purpose, license, rights_status,
			language, domain, lineage_ref, created_by, data_origin,
			production_run_id
		) VALUES (
			'configless model', 'text_corpus', 'pretrain', 'internal',
			'cleared', 'tr', 'mixed', 'configless.txt', $1, 'model', $2
		)
	`, actorID, configlessRunID); err == nil ||
		!strings.Contains(err.Error(), `require a config digest`) {
		t.Fatalf(`configless model source error=%v`, err)
	}
	if err := pool.QueryRow(ctx, `
		INSERT INTO production_runs(
			run_kind, origin_kind, implementation_key,
			implementation_digest, config_sha256
		) VALUES (
			'model_generation', 'model', 'trusted.model', repeat('a', 64),
			repeat('b', 64)
		) RETURNING id::text
	`).Scan(&modelRunID); err != nil {
		t.Fatalf(`insert valid model run: %v`, err)
	}
	if _, err := timezoneConn.Exec(ctx, `
		CREATE TEMP TABLE production_runs(
			id uuid PRIMARY KEY, run_kind text, origin_kind text,
			config_sha256 char(64)
		)
	`); err != nil {
		t.Fatalf(`create provenance search_path shadow: %v`, err)
	}
	if _, err := timezoneConn.Exec(ctx, `
		INSERT INTO pg_temp.production_runs
		VALUES ($1, 'hybrid_generation', 'hybrid', NULL)
	`, modelRunID); err != nil {
		t.Fatalf(`seed provenance search_path shadow: %v`, err)
	}
	if _, err := timezoneConn.Exec(ctx,
		`SET search_path TO pg_temp, `+pgx.Identifier{schemaName}.Sanitize(),
	); err != nil {
		t.Fatalf(`set hostile provenance search_path: %v`, err)
	}
	if _, err := timezoneConn.Exec(ctx,
		`SELECT `+pgx.Identifier{schemaName}.Sanitize()+
			`.validate_source_production_provenance($1, 'model', $2)`,
		schemaName, modelRunID,
	); err != nil {
		t.Fatalf(`schema-pinned provenance validation used caller shadow: %v`, err)
	}
	insertSource := `
		INSERT INTO sources(
			name, source_type, content_purpose, license, rights_status,
			language, domain, lineage_ref, object_sha256, created_by,
			data_profile_key, data_profile_version, profile_assignment_reason
		) VALUES (
			$1, 'text_corpus', 'pretrain', 'internal', 'cleared',
			'tr', 'mixed', $1 || '.txt', $2, $3, $4, '1', $5
		)`
	for name, args := range map[string][]any{
		`terminal legacy`: {`bad-legacy`, objectSHA, actorID, `legacy-auto`, `declared_at_ingest`},
		`fake backfill`:   {`bad-backfill`, objectSHA, actorID, `text-document`, `backfilled`},
	} {
		if _, err := pool.Exec(ctx, insertSource, args...); err == nil {
			t.Fatalf(`%s insert unexpectedly succeeded`, name)
		}
	}
	if _, err := pool.Exec(ctx, `
		UPDATE sources SET document_sampling_status = 'sampled',
			sampled_document_count = 1, document_sample_generation = 1,
			document_sampling_method = $2
		WHERE id = $1
	`, currentSourceID, samplingSentinel); err != nil {
		t.Fatalf(`mark source sampled: %v`, err)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO document_sample_generations(
			source_id, generation, source_sha256, sampling_method, status, sample_count
		) VALUES ($1, 1, $2, $3, 'active', 1)
	`, currentSourceID, objectSHA, samplingSentinel); err != nil {
		t.Fatalf(`insert sample generation: %v`, err)
	}
	var documentID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO documents(
			source_id, source_ordinal, current_object_sha256, text_preview,
			byte_size, char_count, sampling_method, sample_generation
		) VALUES ($1, 1, $2, 'safe document', 100, 13, $3, 1)
		RETURNING id::text
	`, currentSourceID, objectSHA, samplingSentinel).Scan(&documentID); err != nil {
		t.Fatalf(`insert sampled document: %v`, err)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO document_sample_memberships(
			source_id, generation, document_id, source_ordinal,
			object_sha256, risk_score
		) VALUES ($1, 1, $2, 1, $3, 0)
	`, currentSourceID, documentID, objectSHA); err != nil {
		t.Fatalf(`insert sample membership: %v`, err)
	}
	var campaignID, campaignSHA string
	campaignInsertSQL := `
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
		RETURNING id::text, campaign_contract_sha256::text
	`
	if err := pool.QueryRow(ctx, campaignInsertSQL, currentSourceID, actorID).Scan(
		&campaignID, &campaignSHA,
	); err != nil {
		t.Fatalf(`insert review campaign with DB-derived bundle: %v`, err)
	}
	var campaignBytes []byte
	if err := pool.QueryRow(ctx, `
		SELECT canonical_bytes FROM contract_spec_artifacts
		WHERE artifact_kind = 'contract_bundle' AND sha256 = $1
	`, campaignSHA).Scan(&campaignBytes); err != nil {
		t.Fatalf(`read campaign contract artifact: %v`, err)
	}
	computedCampaignSHA := fmt.Sprintf(`%x`, sha256.Sum256(campaignBytes))
	if campaignSHA != computedCampaignSHA {
		t.Fatalf(`campaign bundle sha mismatch: row=%s bytes=%s`, campaignSHA, computedCampaignSHA)
	}
	forgedCampaignSQL := strings.Replace(
		campaignInsertSQL,
		`contract.spec_sha256, NULL,`,
		`contract.spec_sha256, repeat('b', 64),`,
		1,
	)
	if _, err := pool.Exec(ctx, forgedCampaignSQL, currentSourceID, actorID); err == nil ||
		!strings.Contains(err.Error(), `does not match pinned fields`) {
		t.Fatalf(`forged campaign bundle error=%v`, err)
	}
	if _, err := pool.Exec(ctx, `
		UPDATE review_campaigns
		SET campaign_contract_sha256 = repeat('b', 64)
		WHERE id = $1
	`, campaignID); err == nil {
		t.Fatal(`campaign contract identity unexpectedly mutable`)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO document_review_claims(
			document_id, reviewer_id, claim_token, document_version,
			expires_at, review_campaign_id
		) VALUES ($1, $2, gen_random_uuid(), 1, now() + interval '5 minutes', $3)
	`, documentID, actorID, campaignID); err != nil {
		t.Fatalf(`insert campaign-backed claim: %v`, err)
	}
	if _, err := pool.Exec(ctx, `
		UPDATE document_sample_generations SET sample_count = 2
		WHERE source_id = $1 AND generation = 1
	`, currentSourceID); err == nil || !strings.Contains(err.Error(), `identity is immutable`) {
		t.Fatalf(`sample generation identity mutation error=%v`, err)
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
	`, documentID, actorID, secondObjectSHA, campaignID); err == nil ||
		!strings.Contains(err.Error(), `does not match pinned review campaign`) {
		t.Fatalf(`wrong-object review insert error=%v`, err)
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
	`, documentID, actorID, objectSHA, campaignID); err != nil {
		t.Fatalf(`insert campaign-backed review: %v`, err)
	}
	if _, err := pool.Exec(ctx, `
		UPDATE sources
		SET pii_status = 'clear', approval_status = 'approved_source',
			duplicate_status = 'unique', normalized_dedup_status = 'unique',
			reviewed_document_count = sampled_document_count,
			approved_document_count = sampled_document_count,
			flagged_document_count = 0
		WHERE id = $1
	`, currentSourceID); err != nil {
		t.Fatalf(`mark current source release eligible: %v`, err)
	}
	var releaseID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO releases(name, version, content_purpose, created_by)
		VALUES ('current release', '1', 'pretrain', $1)
		RETURNING id::text
	`, actorID).Scan(&releaseID); err != nil {
		t.Fatalf(`insert current release: %v`, err)
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
	`, releaseID, currentSourceID); err != nil {
		t.Fatalf(`insert current release source: %v`, err)
	}
	addReleaseSource := func(targetReleaseID, targetSourceID string) {
		t.Helper()
		if _, err := pool.Exec(ctx, `
			INSERT INTO release_sources(
				release_id, source_id, source_sha256, source_version,
				source_name, source_type, license, rights_status, language,
				domain, lineage_ref, byte_size, line_count
			)
			SELECT $1, id, object_sha256, version, name, source_type, license,
				rights_status, language, domain, lineage_ref, byte_size, line_count
			FROM sources WHERE id = $2
		`, targetReleaseID, targetSourceID); err != nil {
			t.Fatalf(`insert release source %s/%s: %v`, targetReleaseID, targetSourceID, err)
		}
	}
	createDraftRelease := func(name, targetSourceID string) string {
		t.Helper()
		var targetReleaseID string
		if err := pool.QueryRow(ctx, `
			INSERT INTO releases(name, version, content_purpose, created_by)
			VALUES ($1, '1', 'pretrain', $2)
			RETURNING id::text
		`, name, actorID).Scan(&targetReleaseID); err != nil {
			t.Fatalf(`insert draft release %q: %v`, name, err)
		}
		addReleaseSource(targetReleaseID, targetSourceID)
		return targetReleaseID
	}
	snapshotInsertSQL := `
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
	if _, err := pool.Exec(ctx, snapshotInsertSQL, releaseID, campaignID); err != nil {
		t.Fatalf(`insert release source contract snapshot: %v`, err)
	}
	var snapshotOrigin, snapshotLineageSHA, snapshotLicenseSHA string
	var snapshotGeneration, snapshotCount int
	var snapshotSourceSHA, snapshotMethod string
	var snapshotConfigSchemaSHA, snapshotImplementationKey string
	var snapshotImplementationDigest string
	var snapshotHasRun bool
	if err := pool.QueryRow(ctx, `
		SELECT data_origin, production_run_id IS NOT NULL,
			lineage_ref_sha256::text, license_evidence_ref_sha256::text,
			sample_generation, sample_source_sha256::text,
			sample_sampling_method, sample_count,
			profile_config_schema_sha256::text,
			profile_implementation_key,
			profile_implementation_digest::text
		FROM release_source_contract_snapshots
		WHERE release_id = $1 AND source_id = $2
	`, releaseID, currentSourceID).Scan(
		&snapshotOrigin, &snapshotHasRun, &snapshotLineageSHA,
		&snapshotLicenseSHA, &snapshotGeneration, &snapshotSourceSHA,
		&snapshotMethod, &snapshotCount, &snapshotConfigSchemaSHA,
		&snapshotImplementationKey, &snapshotImplementationDigest,
	); err != nil {
		t.Fatalf(`read DB-derived snapshot evidence: %v`, err)
	}
	expectedLineageSHA := fmt.Sprintf(`%x`, sha256.Sum256([]byte(lineageSentinel)))
	expectedLicenseSHA := fmt.Sprintf(`%x`, sha256.Sum256([]byte(licenseSentinel)))
	if snapshotOrigin != `unknown` || snapshotHasRun ||
		snapshotLineageSHA != expectedLineageSHA ||
		snapshotLicenseSHA != expectedLicenseSHA || snapshotGeneration != 1 ||
		snapshotSourceSHA != objectSHA || snapshotMethod != samplingSentinel ||
		snapshotCount != 1 || len(snapshotConfigSchemaSHA) != 64 ||
		snapshotImplementationKey != `text-document-v1` ||
		len(snapshotImplementationDigest) != 64 {
		t.Fatalf(`unexpected DB-derived snapshot evidence: origin=%q run=%v lineage=%q license=%q generation=%d source=%q method=%q count=%d`,
			snapshotOrigin, snapshotHasRun, snapshotLineageSHA, snapshotLicenseSHA,
			snapshotGeneration, snapshotSourceSHA, snapshotMethod, snapshotCount)
	}
	forgedReleaseID := createDraftRelease(`forged snapshot release`, currentSourceID)
	cloneSnapshotSQL := `
		INSERT INTO release_source_contract_snapshots
		SELECT (jsonb_populate_record(
			NULL::release_source_contract_snapshots,
			to_jsonb(snapshot) || jsonb_build_object('release_id', $1::text) ||
			CASE $4::text
				WHEN 'provenance' THEN jsonb_build_object('data_origin', 'model')
				WHEN 'sample' THEN jsonb_build_object('sample_count', 999)
				WHEN 'profile_implementation' THEN
					jsonb_build_object('profile_implementation_digest', repeat('f', 64))
				ELSE jsonb_build_object(
					'profile_config_schema_sha256', repeat('f', 64)
				)
			END
		)).*
		FROM release_source_contract_snapshots AS snapshot
		WHERE snapshot.release_id = $2 AND snapshot.source_id = $3
	`
	if _, err := pool.Exec(
		ctx, cloneSnapshotSQL, forgedReleaseID, releaseID, currentSourceID,
		`provenance`,
	); err == nil || !strings.Contains(err.Error(), `provenance does not match source`) {
		t.Fatalf(`forged snapshot provenance error=%v`, err)
	}
	if _, err := pool.Exec(
		ctx, cloneSnapshotSQL, forgedReleaseID, releaseID, currentSourceID,
		`sample`,
	); err == nil || !strings.Contains(err.Error(), `sample pins do not match`) {
		t.Fatalf(`forged snapshot sample pins error=%v`, err)
	}
	if _, err := pool.Exec(
		ctx, cloneSnapshotSQL, forgedReleaseID, releaseID, currentSourceID,
		`profile_implementation`,
	); err == nil || !strings.Contains(err.Error(), `does not match data profile`) {
		t.Fatalf(`forged snapshot profile implementation error=%v`, err)
	}
	if _, err := pool.Exec(
		ctx, cloneSnapshotSQL, forgedReleaseID, releaseID, currentSourceID,
		`profile_config_schema`,
	); err == nil || !strings.Contains(err.Error(), `does not match data profile`) {
		t.Fatalf(`forged snapshot profile config schema error=%v`, err)
	}

	var secondSourceID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO sources(
			name, source_type, content_purpose, license, rights_status,
			language, domain, lineage_ref, object_sha256, byte_size,
			line_count, created_by
		) VALUES (
			'second current source', 'text_corpus', 'pretrain', 'internal',
			'cleared', 'tr', 'mixed', 'second-current.txt', $1, 120, 2, $2
		) RETURNING id::text
	`, secondObjectSHA, actorID).Scan(&secondSourceID); err != nil {
		t.Fatalf(`insert second current source: %v`, err)
	}
	if _, err := pool.Exec(ctx, `
		UPDATE sources SET document_sampling_status = 'sampled',
			sampled_document_count = 1, document_sample_generation = 1,
			document_sampling_method = 'risk-second-v1'
		WHERE id = $1
	`, secondSourceID); err != nil {
		t.Fatalf(`mark second source sampled: %v`, err)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO document_sample_generations(
			source_id, generation, source_sha256, sampling_method, status, sample_count
		) VALUES ($1, 1, $2, 'risk-second-v1', 'active', 1)
	`, secondSourceID, secondObjectSHA); err != nil {
		t.Fatalf(`insert second sample generation: %v`, err)
	}
	var secondDocumentID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO documents(
			source_id, source_ordinal, current_object_sha256, text_preview,
			byte_size, char_count, sampling_method, sample_generation
		) VALUES ($1, 1, $2, 'second safe document', 120, 20, 'risk-second-v1', 1)
		RETURNING id::text
	`, secondSourceID, secondObjectSHA).Scan(&secondDocumentID); err != nil {
		t.Fatalf(`insert second sampled document: %v`, err)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO document_sample_memberships(
			source_id, generation, document_id, source_ordinal,
			object_sha256, risk_score
		) VALUES ($1, 1, $2, 1, $3, 0)
	`, secondSourceID, secondDocumentID, secondObjectSHA); err != nil {
		t.Fatalf(`insert second sample membership: %v`, err)
	}
	var secondCampaignID, secondCampaignSHA string
	if err := pool.QueryRow(ctx, campaignInsertSQL, secondSourceID, actorID).Scan(
		&secondCampaignID, &secondCampaignSHA,
	); err != nil {
		t.Fatalf(`insert second review campaign: %v`, err)
	}
	if len(secondCampaignSHA) != 64 {
		t.Fatalf(`unexpected second campaign hash %q`, secondCampaignSHA)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO document_review_claims(
			document_id, reviewer_id, claim_token, document_version,
			expires_at, review_campaign_id
		) VALUES ($1, $2, gen_random_uuid(), 1, now() + interval '5 minutes', $3)
	`, secondDocumentID, actorID, secondCampaignID); err != nil {
		t.Fatalf(`insert second campaign-backed claim: %v`, err)
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
	`, secondDocumentID, actorID, secondObjectSHA, secondCampaignID); err != nil {
		t.Fatalf(`insert second campaign-backed review: %v`, err)
	}
	if _, err := pool.Exec(ctx, `
		UPDATE sources
		SET pii_status = 'clear', approval_status = 'approved_source',
			license_evidence_ref = 'second-private-license-evidence',
			duplicate_status = 'unique', normalized_dedup_status = 'unique',
			reviewed_document_count = sampled_document_count,
			approved_document_count = sampled_document_count,
			flagged_document_count = 0
		WHERE id = $1
	`, secondSourceID); err != nil {
		t.Fatalf(`mark second source release eligible: %v`, err)
	}
	addReleaseSource(releaseID, secondSourceID)
	if _, err := pool.Exec(ctx, snapshotInsertSQL, releaseID, secondCampaignID); err != nil {
		t.Fatalf(`insert second release source contract snapshot: %v`, err)
	}
	staleReleaseID := createDraftRelease(`stale campaign release`, currentSourceID)
	if _, err := pool.Exec(ctx, snapshotInsertSQL, staleReleaseID, campaignID); err != nil {
		t.Fatalf(`insert future-stale release snapshot: %v`, err)
	}
	if _, err := pool.Exec(ctx, `
		UPDATE releases SET contract_snapshot_status = 'present' WHERE id = $1
	`, staleReleaseID); err != nil {
		t.Fatalf(`mark future-stale release snapshot present: %v`, err)
	}
	metadataStaleReleaseID := createDraftRelease(
		`metadata stale release`, currentSourceID,
	)
	if _, err := pool.Exec(ctx, snapshotInsertSQL, metadataStaleReleaseID, campaignID); err != nil {
		t.Fatalf(`insert metadata-stale release snapshot: %v`, err)
	}
	if _, err := pool.Exec(ctx, `
		UPDATE release_sources SET source_name = 'forged stale name'
		WHERE release_id = $1 AND source_id = $2
	`, metadataStaleReleaseID, currentSourceID); err != nil {
		t.Fatalf(`mutate pending release source metadata: %v`, err)
	}
	if _, err := pool.Exec(ctx, `
		UPDATE releases SET contract_snapshot_status = 'present' WHERE id = $1
	`, metadataStaleReleaseID); err == nil ||
		!strings.Contains(err.Error(), `does not match current source`) {
		t.Fatalf(`present transition with stale release metadata error=%v`, err)
	}
	if _, err := pool.Exec(ctx, `
		UPDATE release_sources
		SET source_name = (SELECT name FROM sources WHERE id = $2)
		WHERE release_id = $1 AND source_id = $2
	`, metadataStaleReleaseID, currentSourceID); err != nil {
		t.Fatalf(`restore pending release source metadata: %v`, err)
	}
	eligibilityStaleReleaseID := createDraftRelease(
		`eligibility stale release`, secondSourceID,
	)
	if _, err := pool.Exec(
		ctx, snapshotInsertSQL, eligibilityStaleReleaseID, secondCampaignID,
	); err != nil {
		t.Fatalf(`insert eligibility-stale release snapshot: %v`, err)
	}
	raceReleaseID := createDraftRelease(`release source race`, currentSourceID)
	if _, err := pool.Exec(ctx, snapshotInsertSQL, raceReleaseID, campaignID); err != nil {
		t.Fatalf(`insert race release snapshot: %v`, err)
	}
	raceTx, err := pool.Begin(ctx)
	if err != nil {
		t.Fatalf(`begin release race transaction: %v`, err)
	}
	if _, err := raceTx.Exec(ctx, `
		SELECT id FROM releases WHERE id = $1 FOR UPDATE
	`, raceReleaseID); err != nil {
		_ = raceTx.Rollback(ctx)
		t.Fatalf(`lock race release: %v`, err)
	}
	raceErr := make(chan error, 1)
	go func() {
		_, insertErr := pool.Exec(ctx, `
			INSERT INTO release_sources(
				release_id, source_id, source_sha256, source_version,
				source_name, source_type, license, rights_status, language,
				domain, lineage_ref, byte_size, line_count
			)
			SELECT $1, id, object_sha256, version, name, source_type, license,
				rights_status, language, domain, lineage_ref, byte_size, line_count
			FROM sources WHERE id = $2
		`, raceReleaseID, secondSourceID)
		raceErr <- insertErr
	}()
	if _, err := raceTx.Exec(ctx, `
		UPDATE releases SET contract_snapshot_status = 'present' WHERE id = $1
	`, raceReleaseID); err != nil {
		_ = raceTx.Rollback(ctx)
		t.Fatalf(`derive race release snapshot: %v`, err)
	}
	if err := raceTx.Commit(ctx); err != nil {
		t.Fatalf(`commit release snapshot side of race: %v`, err)
	}
	select {
	case err := <-raceErr:
		if err == nil || !strings.Contains(err.Error(), `contract-snapshotted`) {
			t.Fatalf(`concurrent release source insert error=%v`, err)
		}
	case <-time.After(10 * time.Second):
		t.Fatal(`concurrent release source insert did not unblock`)
	}
	var raceSourceCount, raceSnapshotCount int
	if err := pool.QueryRow(ctx, `
		SELECT
			(SELECT count(*) FROM release_sources WHERE release_id = $1),
			(SELECT count(*) FROM release_source_contract_snapshots WHERE release_id = $1)
	`, raceReleaseID).Scan(&raceSourceCount, &raceSnapshotCount); err != nil {
		t.Fatalf(`read release race invariant: %v`, err)
	}
	if raceSourceCount != 1 || raceSnapshotCount != 1 {
		t.Fatalf(`release race broke source/snapshot parity: sources=%d snapshots=%d`, raceSourceCount, raceSnapshotCount)
	}
	var releaseArtifactKind, releaseSHA, releaseImplementationSHA string
	if err := pool.QueryRow(ctx, `
		UPDATE releases SET contract_snapshot_status = 'present'
		WHERE id = $1
		RETURNING contract_snapshot_artifact_kind,
			contract_snapshot_sha256::text, implementation_bundle_sha256::text
	`, releaseID).Scan(
		&releaseArtifactKind, &releaseSHA, &releaseImplementationSHA,
	); err != nil {
		t.Fatalf(`derive release contract bundle from NULL caller hashes: %v`, err)
	}
	if releaseArtifactKind != `contract_bundle` || len(releaseImplementationSHA) != 64 {
		t.Fatalf(`unexpected DB-derived release identity: kind=%q implementation=%q`, releaseArtifactKind, releaseImplementationSHA)
	}
	var expectedReleaseImplementationSHA string
	if err := pool.QueryRow(ctx, `
		SELECT contract_spec_artifact_sha256(convert_to(string_agg(
			btrim(contract_spec_artifact_sha256(convert_to(
				jsonb_build_object(
					'source_id', snapshot.source_id,
					'profile_implementation_key', snapshot.profile_implementation_key,
					'profile_implementation_digest', snapshot.profile_implementation_digest,
					'purpose_implementation_bundle_sha256', snapshot.implementation_bundle_sha256
				)::text, 'UTF8'
			))::text), '' ORDER BY snapshot.source_id
		), 'UTF8'))::text
		FROM release_source_contract_snapshots AS snapshot
		WHERE snapshot.release_id = $1
	`, releaseID).Scan(&expectedReleaseImplementationSHA); err != nil {
		t.Fatalf(`derive expected fixed-child implementation root: %v`, err)
	}
	if releaseImplementationSHA != expectedReleaseImplementationSHA {
		t.Fatalf(`implementation root mismatch: release=%s expected=%s`,
			releaseImplementationSHA, expectedReleaseImplementationSHA)
	}
	var releaseBytes []byte
	if err := pool.QueryRow(ctx, `
		SELECT canonical_bytes FROM contract_spec_artifacts
		WHERE artifact_kind = 'contract_bundle' AND sha256 = $1
	`, releaseSHA).Scan(&releaseBytes); err != nil {
		t.Fatalf(`read release contract artifact: %v`, err)
	}
	if got := fmt.Sprintf(`%x`, sha256.Sum256(releaseBytes)); got != releaseSHA {
		t.Fatalf(`release artifact sha mismatch: row=%s bytes=%s`, releaseSHA, got)
	}
	if len(releaseBytes) > 1024 {
		t.Fatalf(`fixed-size release envelope is unexpectedly large: %d bytes`, len(releaseBytes))
	}
	var envelopeKeys string
	var envelopeSourceCount int
	if err := pool.QueryRow(ctx, `
		WITH artifact AS (
			SELECT convert_from(canonical_bytes, 'UTF8')::jsonb AS payload
			FROM contract_spec_artifacts
			WHERE artifact_kind = 'contract_bundle' AND sha256 = $1
		)
		SELECT (
			SELECT string_agg(key, ',' ORDER BY key)
			FROM artifact, jsonb_object_keys(artifact.payload) AS keys(key)
		), (payload->>'source_count')::integer
		FROM artifact
	`, releaseSHA).Scan(&envelopeKeys, &envelopeSourceCount); err != nil {
		t.Fatalf(`read release envelope shape: %v`, err)
	}
	const expectedEnvelopeKeys = `bundle_kind,child_snapshot_root_sha256,content_purpose,implementation_bundle_sha256,release_id,source_count`
	if envelopeKeys != expectedEnvelopeKeys || envelopeSourceCount != 2 {
		t.Fatalf(`unexpected release envelope: keys=%q sources=%d`, envelopeKeys, envelopeSourceCount)
	}
	var releaseSHAAfterFailedGate string
	if err := pool.QueryRow(ctx, `
		UPDATE releases
		SET gate_results = jsonb_build_object(
			'status', 'failed', 'reasons', jsonb_build_array('test gate')
		)
		WHERE id = $1
		RETURNING contract_snapshot_sha256::text
	`, releaseID).Scan(&releaseSHAAfterFailedGate); err != nil {
		t.Fatalf(`persist failure gate results on present draft release: %v`, err)
	}
	if releaseSHAAfterFailedGate != releaseSHA {
		t.Fatalf(`gate result write changed contract identity: before=%s after=%s`,
			releaseSHA, releaseSHAAfterFailedGate)
	}
	var largeEnvelopeSize int
	if err := pool.QueryRow(ctx, `
		WITH child_material AS (
			SELECT count(*) AS source_count,
				string_agg(
					btrim(contract_spec_artifact_sha256(
						convert_to(child_number::text, 'UTF8')
					)::text), '' ORDER BY child_number
				) AS child_digests,
				string_agg(
					lpad(child_number::text, 36, '0') || ':' || repeat('a', 64),
					'' ORDER BY child_number
				) AS implementation_digests
			FROM generate_series(1, 10000) AS children(child_number)
		), envelope AS (
			SELECT convert_to(jsonb_build_object(
				'bundle_kind', 'release_contract_snapshot',
				'release_id', $1::uuid,
				'content_purpose', 'pretrain',
				'implementation_bundle_sha256',
					contract_spec_artifact_sha256(convert_to(implementation_digests, 'UTF8')),
				'source_count', source_count,
				'child_snapshot_root_sha256',
					contract_spec_artifact_sha256(convert_to(child_digests, 'UTF8'))
			)::text, 'UTF8') AS bytes
			FROM child_material
		)
		SELECT octet_length(bytes) FROM envelope
	`, releaseID).Scan(&largeEnvelopeSize); err != nil {
		t.Fatalf(`derive synthetic 10000-child fixed envelope: %v`, err)
	}
	if largeEnvelopeSize > 1024 {
		t.Fatalf(`10000-child fixed envelope is unexpectedly large: %d bytes`, largeEnvelopeSize)
	}
	if _, err := pool.Exec(ctx, `
		UPDATE releases SET content_purpose = 'instruction' WHERE id = $1
	`, releaseID); err == nil || !strings.Contains(err.Error(), `identity is immutable`) {
		t.Fatalf(`present release purpose mutation error=%v`, err)
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
	`, releaseID, sourceID); err == nil ||
		!strings.Contains(err.Error(), `contract-snapshotted`) {
		t.Fatalf(`post-present release source insert error=%v`, err)
	}
	if _, err := pool.Exec(ctx, `
		UPDATE document_review_claims SET review_campaign_id = NULL
		WHERE document_id = $1
	`, documentID); err == nil || !strings.Contains(err.Error(), `campaign is immutable`) {
		t.Fatalf(`claim campaign mutation error=%v`, err)
	}
	if _, err := pool.Exec(ctx, `
		DELETE FROM active_document_reviews WHERE document_id = $1
	`, documentID); err == nil ||
		!strings.Contains(err.Error(), `trigger-maintained`) {
		t.Fatalf(`direct active-review projection mutation error=%v`, err)
	}
	var reviewID string
	if err := pool.QueryRow(ctx, `
		SELECT review.id::text
		FROM document_reviews AS review
		JOIN active_document_reviews AS active ON active.review_id = review.id
		WHERE review.document_id = $1
	`, documentID).Scan(&reviewID); err != nil {
		t.Fatalf(`read active review: %v`, err)
	}
	reviewRaceReleaseID := createDraftRelease(
		`review reversal race release`, currentSourceID,
	)
	if _, err := pool.Exec(ctx, snapshotInsertSQL, reviewRaceReleaseID, campaignID); err != nil {
		t.Fatalf(`insert review-race release snapshot: %v`, err)
	}
	reviewRaceTx, err := pool.Begin(ctx)
	if err != nil {
		t.Fatalf(`begin review reversal race transaction: %v`, err)
	}
	if _, err := reviewRaceTx.Exec(ctx, `
		UPDATE releases SET contract_snapshot_status = 'present' WHERE id = $1
	`, reviewRaceReleaseID); err != nil {
		_ = reviewRaceTx.Rollback(ctx)
		t.Fatalf(`derive review-race snapshot: %v`, err)
	}
	reversalErr := make(chan error, 1)
	go func() {
		_, insertErr := pool.Exec(ctx, `
			INSERT INTO document_review_reversals(
				review_id, reversed_by, reason, restored_document_status
			) VALUES ($1, $2, 'serialized reversal test', 'sampled')
		`, reviewID, actorID)
		reversalErr <- insertErr
	}()
	select {
	case err := <-reversalErr:
		_ = reviewRaceTx.Rollback(ctx)
		t.Fatalf(`review reversal did not serialize behind snapshot transition: %v`, err)
	case <-time.After(200 * time.Millisecond):
	}
	if err := reviewRaceTx.Commit(ctx); err != nil {
		t.Fatalf(`commit review-race snapshot transition: %v`, err)
	}
	select {
	case err := <-reversalErr:
		if err != nil {
			t.Fatalf(`serialized review reversal failed after transition: %v`, err)
		}
	case <-time.After(10 * time.Second):
		t.Fatal(`serialized review reversal did not unblock`)
	}
	freezeSQL := `
		UPDATE releases SET status = 'frozen', manifest_object_sha256 = $2,
			manifest_sha256 = $2, frozen_by = $3, frozen_at = now()
		WHERE id = $1`
	if _, err := pool.Exec(ctx, freezeSQL, releaseID, objectSHA, actorID); err == nil ||
		!strings.Contains(err.Error(), `does not cover every active sample document`) {
		t.Fatalf(`freeze with reversed evidence error=%v`, err)
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
	`, documentID, actorID, objectSHA, campaignID); err != nil {
		t.Fatalf(`insert replacement approved review: %v`, err)
	}
	if _, err := pool.Exec(ctx, freezeSQL, releaseID, objectSHA, actorID); err != nil {
		t.Fatalf(`freeze with fresh campaign evidence: %v`, err)
	}
	resampleTx, err := pool.Begin(ctx)
	if err != nil {
		t.Fatalf(`begin resample transaction: %v`, err)
	}
	if _, err := resampleTx.Exec(ctx, `
		UPDATE document_sample_generations SET status = 'superseded'
		WHERE source_id = $1 AND generation = 1
	`, currentSourceID); err != nil {
		_ = resampleTx.Rollback(ctx)
		t.Fatalf(`supersede old sample generation: %v`, err)
	}
	if _, err := resampleTx.Exec(ctx, `
		INSERT INTO document_sample_generations(
			source_id, generation, source_sha256, sampling_method, status, sample_count
		) VALUES ($1, 2, $2, 'risk-resample-v2', 'active', 1)
	`, currentSourceID, objectSHA); err != nil {
		_ = resampleTx.Rollback(ctx)
		t.Fatalf(`insert replacement sample generation: %v`, err)
	}
	var resampledDocumentID string
	if err := resampleTx.QueryRow(ctx, `
		INSERT INTO documents(
			source_id, source_ordinal, current_object_sha256, text_preview,
			byte_size, char_count, sampling_method, sample_generation
		) VALUES ($1, 2, $2, 'resampled document', 100, 18, 'risk-resample-v2', 2)
		RETURNING id::text
	`, currentSourceID, objectSHA).Scan(&resampledDocumentID); err != nil {
		_ = resampleTx.Rollback(ctx)
		t.Fatalf(`insert replacement sampled document: %v`, err)
	}
	if _, err := resampleTx.Exec(ctx, `
		INSERT INTO document_sample_memberships(
			source_id, generation, document_id, source_ordinal,
			object_sha256, risk_score
		) VALUES ($1, 2, $2, 2, $3, 0)
	`, currentSourceID, resampledDocumentID, objectSHA); err != nil {
		_ = resampleTx.Rollback(ctx)
		t.Fatalf(`insert replacement sample membership: %v`, err)
	}
	if _, err := resampleTx.Exec(ctx, `
		UPDATE sources SET document_sample_generation = 2,
			document_sampling_method = 'risk-resample-v2',
			sampled_document_count = 1
		WHERE id = $1
	`, currentSourceID); err != nil {
		_ = resampleTx.Rollback(ctx)
		t.Fatalf(`advance source sample generation: %v`, err)
	}
	if err := resampleTx.Commit(ctx); err != nil {
		t.Fatalf(`commit resample transaction: %v`, err)
	}
	if _, err := pool.Exec(ctx, freezeSQL, staleReleaseID, objectSHA, actorID); err == nil ||
		(!strings.Contains(err.Error(), `not for the current sample generation`) &&
			!strings.Contains(err.Error(), `does not match current source`)) {
		t.Fatalf(`freeze with stale campaign/source evidence error=%v`, err)
	}
	if _, err := pool.Exec(ctx, campaignInsertSQL, currentSourceID, actorID); err == nil ||
		!strings.Contains(err.Error(), `sample pins do not match generation`) {
		t.Fatalf(`create campaign for superseded generation error=%v`, err)
	}

	var moveTargetReleaseID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO releases(name, version, content_purpose, created_by)
		VALUES ('release-source move target', '1', 'pretrain', $1)
		RETURNING id::text
	`, actorID).Scan(&moveTargetReleaseID); err != nil {
		t.Fatalf(`insert release-source move target: %v`, err)
	}
	if _, err := pool.Exec(ctx, `
		UPDATE release_sources SET release_id = $3
		WHERE release_id = $1 AND source_id = $2
	`, releaseID, secondSourceID, moveTargetReleaseID); err == nil ||
		!strings.Contains(err.Error(), `frozen, superseded or contract-snapshotted`) {
		t.Fatalf(`move release source out of frozen release error=%v`, err)
	}

	supersededReleaseID := createDraftRelease(
		`superseded immutability release`, secondSourceID,
	)
	if _, err := pool.Exec(ctx, `
		UPDATE releases SET status = 'superseded' WHERE id = $1
	`, supersededReleaseID); err != nil {
		t.Fatalf(`mark draft release superseded: %v`, err)
	}
	if _, err := pool.Exec(ctx, `
		UPDATE releases SET name = 'mutated superseded release' WHERE id = $1
	`, supersededReleaseID); err == nil ||
		!strings.Contains(err.Error(), `frozen and superseded releases are immutable`) {
		t.Fatalf(`superseded release mutation error=%v`, err)
	}
	if _, err := pool.Exec(ctx, `
		UPDATE release_sources SET source_name = 'mutated snapshot'
		WHERE release_id = $1 AND source_id = $2
	`, supersededReleaseID, secondSourceID); err == nil ||
		!strings.Contains(err.Error(), `frozen, superseded or contract-snapshotted`) {
		t.Fatalf(`superseded release-source mutation error=%v`, err)
	}

	if _, err := pool.Exec(ctx, `
		UPDATE sources SET approval_status = 'sampled_for_review'
		WHERE id = $1
	`, secondSourceID); err != nil {
		t.Fatalf(`make source stale-ineligible: %v`, err)
	}
	if _, err := pool.Exec(ctx, `
		UPDATE releases SET contract_snapshot_status = 'present' WHERE id = $1
	`, eligibilityStaleReleaseID); err == nil ||
		!strings.Contains(err.Error(), `release source is not eligible`) {
		t.Fatalf(`present transition with stale source eligibility error=%v`, err)
	}
	var profilePinSummaryCount int
	if err := pool.QueryRow(ctx, `
		SELECT count(*)
		FROM row_change_events
		WHERE table_name = 'release_source_contract_snapshots'
		  AND after_summary ?& ARRAY[
			'profile_config_schema_artifact_kind',
			'profile_config_schema_sha256',
			'profile_implementation_key',
			'profile_implementation_digest'
		  ]
	`).Scan(&profilePinSummaryCount); err != nil {
		t.Fatalf(`read release child profile-pin safe summaries: %v`, err)
	}
	if profilePinSummaryCount < 2 {
		t.Fatalf(`release child safe summaries omitted profile pins: count=%d`,
			profilePinSummaryCount)
	}

	var leakedSummaryCount int
	if err := pool.QueryRow(ctx, `
		SELECT count(*)
		FROM row_change_events
		WHERE coalesce(before_summary, '{}'::jsonb) ?| ARRAY[
			'canonical_bytes', 'profile_config', 'license_evidence_ref',
			'lineage_ref', 'sample_sampling_method'
		]
		OR coalesce(after_summary, '{}'::jsonb) ?| ARRAY[
			'canonical_bytes', 'profile_config', 'license_evidence_ref',
			'lineage_ref', 'sample_sampling_method'
		]
		OR coalesce(before_summary::text, '') LIKE '%' || $1 || '%'
		OR coalesce(after_summary::text, '') LIKE '%' || $1 || '%'
		OR coalesce(before_summary::text, '') LIKE '%' || $2 || '%'
		OR coalesce(after_summary::text, '') LIKE '%' || $2 || '%'
		OR coalesce(before_summary::text, '') LIKE '%' || $3 || '%'
		OR coalesce(after_summary::text, '') LIKE '%' || $3 || '%'
	`, samplingSentinel, lineageSentinel, licenseSentinel).Scan(&leakedSummaryCount); err != nil {
		t.Fatalf(`audit safe-summary leakage query: %v`, err)
	}
	if leakedSummaryCount != 0 {
		t.Fatalf(`row-change safe summaries leaked %d sensitive values or fields`, leakedSummaryCount)
	}
}
