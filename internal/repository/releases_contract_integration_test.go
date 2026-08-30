package repository_test

import (
	"context"
	"errors"
	"fmt"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/celikbros/derlem/internal/database"
	"github.com/celikbros/derlem/internal/domain"
	"github.com/celikbros/derlem/internal/repository"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

func TestReleaseContractSnapshotIsDBDerivedAndFreezeFailsClosed(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	t.Cleanup(cancel)
	pool := newReleaseContractTestPool(t, ctx)

	var actorID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO users(email, password_hash, display_name)
		VALUES ('release-contract@example.test', 'test', 'Release Contract Test')
		RETURNING id::text
	`).Scan(&actorID); err != nil {
		t.Fatalf("insert actor: %v", err)
	}

	sourceSHA := strings.Repeat("a", 64)
	documentSHA := strings.Repeat("b", 64)
	if _, err := pool.Exec(ctx, `
		INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
		VALUES
			($1, 'tests/release-source.jsonl', 128, 'application/x-ndjson'),
			($2, 'tests/release-document.txt', 32, 'text/plain')
	`, sourceSHA, documentSHA); err != nil {
		t.Fatalf("insert storage objects: %v", err)
	}

	var sourceID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO sources(
			name, source_type, content_purpose, license, rights_status,
			language, domain, license_evidence_ref, lineage_ref,
			object_sha256, byte_size, line_count, document_count,
			pii_status, approval_status, created_by,
			duplicate_status, normalized_dedup_status,
			document_sampling_status, sampled_document_count,
			reviewed_document_count, approved_document_count,
			flagged_document_count, document_sample_generation,
			document_sampling_method
		)
		VALUES (
			'Release source', 'jsonl', 'instruction', 'internal', 'cleared',
			'tr', 'general', 'tests/license.txt', 'release-contract-test',
			$1, 128, 1, 1, 'clear', 'approved_source', $2,
			'unique', 'unique', 'sampled', 1, 1, 1, 0, 1,
			'risk-stratified-sha256-v1'
		)
		RETURNING id::text
	`, sourceSHA, actorID).Scan(&sourceID); err != nil {
		t.Fatalf("insert source: %v", err)
	}

	if _, err := pool.Exec(ctx, `
		INSERT INTO document_sample_generations(
			source_id, generation, source_sha256, sampling_method,
			status, sample_count
		)
		VALUES ($1, 1, $2, 'risk-stratified-sha256-v1', 'active', 1)
	`, sourceID, sourceSHA); err != nil {
		t.Fatalf("insert sample generation: %v", err)
	}

	var documentID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO documents(
			source_id, source_ordinal, current_object_sha256, text_preview,
			byte_size, char_count, status, sampling_method,
			is_active, sample_generation
		)
		VALUES (
			$1, 1, $2, 'Sözleşmeli belge', 32, 18, 'approved',
			'risk-stratified-sha256-v1', true, 1
		)
		RETURNING id::text
	`, sourceID, documentSHA).Scan(&documentID); err != nil {
		t.Fatalf("insert document: %v", err)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO document_sample_memberships(
			source_id, generation, document_id, source_ordinal,
			object_sha256, risk_score, risk_reasons
		)
		VALUES ($1, 1, $2, 1, $3, 0, '{}'::text[])
	`, sourceID, documentID, documentSHA); err != nil {
		t.Fatalf("insert sample membership: %v", err)
	}

	var campaignID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO review_campaigns(
			source_id, sample_generation, data_profile_key,
			data_profile_version, content_purpose, profile_config_sha256,
			rubric_key, rubric_version, purpose_contract_version,
			protocol_key, protocol_version,
			pii_policy_key, pii_policy_version,
			dedup_policy_key, dedup_policy_version,
			leakage_policy_key, leakage_policy_version,
			purpose_contract_sha256,
			implementation_bundle_sha256, created_by
		)
		SELECT source.id, 1, source.data_profile_key,
			source.data_profile_version, source.content_purpose,
			source.profile_config_sha256, profile.rubric_key,
			profile.rubric_version, contract.purpose_contract_version,
			contract.protocol_key, contract.protocol_version,
			contract.pii_policy_key, contract.pii_policy_version,
			contract.dedup_policy_key, contract.dedup_policy_version,
			contract.leakage_policy_key, contract.leakage_policy_version,
			contract.spec_sha256,
			contract.implementation_bundle_sha256, $2
		FROM sources AS source
		JOIN data_profile_versions AS profile
		  ON profile.data_profile_key = source.data_profile_key
		 AND profile.data_profile_version = source.data_profile_version
		JOIN profile_purpose_contract_versions AS contract
		  ON contract.data_profile_key = source.data_profile_key
		 AND contract.data_profile_version = source.data_profile_version
		 AND contract.content_purpose = source.content_purpose
		 AND contract.purpose_contract_version = '1'
		WHERE source.id = $1
		RETURNING id::text
	`, sourceID, actorID).Scan(&campaignID); err != nil {
		t.Fatalf("insert review campaign: %v", err)
	}

	if _, err := pool.Exec(ctx, `
		INSERT INTO document_reviews(
			document_id, reviewer_id, decision, quality_score,
			document_version, object_sha256, rubric_version,
			language_quality_score, coherence_score,
			information_density_score, cleanliness_score,
			review_campaign_id
		)
		VALUES (
			$1, $2, 'approved', 4, 1, $3, 'multidimensional-v1',
			4, 4, 4, 4, $4
		)
	`, documentID, actorID, documentSHA, campaignID); err != nil {
		t.Fatalf("insert campaign review: %v", err)
	}

	releases := repository.NewReleases(pool)
	release, err := releases.Create(ctx, domain.CreateReleaseInput{
		Name: "Contract release", Version: "v1", ContentPurpose: "instruction",
		SourceIDs: []string{sourceID},
	}, actorID)
	if err != nil {
		t.Fatalf("create release: %v", err)
	}
	if release.ContractSnapshotStatus != "present" ||
		release.ContractSnapshotArtifactKind == nil ||
		*release.ContractSnapshotArtifactKind != "contract_bundle" ||
		release.ContractSnapshotSHA256 == nil ||
		len(*release.ContractSnapshotSHA256) != 64 ||
		release.ImplementationBundleSHA256 == nil ||
		len(*release.ImplementationBundleSHA256) != 64 {
		t.Fatalf("release contract snapshot was not derived: %+v", release)
	}

	var artifactMatches bool
	var evidenceStatus, snapshottedCampaign string
	var dataOrigin, licenseEvidenceSHA256, lineageSHA256 string
	var productionRunID, productionRunImplementationDigest *string
	var sampleGeneration, sampleCount int
	var sampleSourceSHA256, sampleSamplingMethod string
	var sampleJobID *string
	if err := pool.QueryRow(ctx, `
		SELECT artifact.sha256 = contract_spec_artifact_sha256(artifact.canonical_bytes),
			snapshot.review_evidence_status, snapshot.review_campaign_id::text,
			snapshot.data_origin, snapshot.production_run_id::text,
			snapshot.production_run_implementation_digest,
			snapshot.license_evidence_ref_sha256, snapshot.lineage_ref_sha256,
			snapshot.sample_generation, snapshot.sample_source_sha256,
			snapshot.sample_sampling_method, snapshot.sample_count,
			snapshot.sample_job_id::text
		FROM releases AS release
		JOIN contract_spec_artifacts AS artifact
		  ON artifact.artifact_kind = release.contract_snapshot_artifact_kind
		 AND artifact.sha256 = release.contract_snapshot_sha256
		JOIN release_source_contract_snapshots AS snapshot
		  ON snapshot.release_id = release.id
		WHERE release.id = $1
	`, release.ID).Scan(
		&artifactMatches, &evidenceStatus, &snapshottedCampaign,
		&dataOrigin, &productionRunID, &productionRunImplementationDigest,
		&licenseEvidenceSHA256, &lineageSHA256, &sampleGeneration,
		&sampleSourceSHA256, &sampleSamplingMethod, &sampleCount, &sampleJobID,
	); err != nil {
		t.Fatalf("read release contract evidence: %v", err)
	}
	if !artifactMatches || evidenceStatus != "campaign_pinned" ||
		snapshottedCampaign != campaignID {
		t.Fatalf(
			"unexpected contract evidence: artifact=%v status=%s campaign=%s",
			artifactMatches, evidenceStatus, snapshottedCampaign,
		)
	}
	if dataOrigin != "unknown" || productionRunID != nil ||
		productionRunImplementationDigest != nil || len(licenseEvidenceSHA256) != 64 ||
		len(lineageSHA256) != 64 || sampleGeneration != 1 ||
		sampleSourceSHA256 != sourceSHA ||
		sampleSamplingMethod != "risk-stratified-sha256-v1" || sampleCount != 1 ||
		sampleJobID != nil {
		t.Fatalf(
			"unexpected provenance/sample snapshot: origin=%s run=%v run_digest=%v license=%s lineage=%s sample=%d/%s/%s/%d job=%v",
			dataOrigin, productionRunID, productionRunImplementationDigest,
			licenseEvidenceSHA256, lineageSHA256, sampleGeneration,
			sampleSourceSHA256, sampleSamplingMethod, sampleCount, sampleJobID,
		)
	}

	if _, err := releases.QueueFreeze(ctx, release.ID, actorID); err != nil {
		t.Fatalf("queue freeze with present contract: %v", err)
	}

	if _, err := pool.Exec(ctx, `
		ALTER TABLE sources
		DISABLE TRIGGER sources_reject_terminal_legacy_insert
	`); err != nil {
		t.Fatalf("disable terminal legacy trigger for migrated fixture: %v", err)
	}
	var legacySourceID string
	err = pool.QueryRow(ctx, `
		INSERT INTO sources(
			name, source_type, content_purpose, license, rights_status,
			language, domain, license_evidence_ref, lineage_ref,
			object_sha256, byte_size, line_count, document_count,
			pii_status, approval_status, created_by,
			duplicate_status, normalized_dedup_status,
			document_sampling_status, sampled_document_count,
			reviewed_document_count, approved_document_count,
			flagged_document_count, document_sample_generation,
			document_sampling_method, data_profile_key,
			data_profile_version, profile_assignment_reason
		)
		VALUES (
			'Backfilled legacy source', 'jsonl', 'instruction', 'internal',
			'cleared', 'tr', 'general', 'tests/license.txt',
			'backfilled-release-contract-test', $1, 128, 1, 1,
			'clear', 'approved_source', $2, 'unique', 'unique',
			'sampled', 1, 1, 1, 0, 1, 'risk-stratified-sha256-v1',
			'legacy-auto', '1', 'backfilled'
		)
		RETURNING id::text
	`, sourceSHA, actorID).Scan(&legacySourceID)
	if _, enableErr := pool.Exec(ctx, `
		ALTER TABLE sources
		ENABLE TRIGGER sources_reject_terminal_legacy_insert
	`); enableErr != nil {
		t.Fatalf("re-enable terminal legacy trigger: %v", enableErr)
	}
	if err != nil {
		t.Fatalf("insert migrated legacy fixture: %v", err)
	}

	if _, err := pool.Exec(ctx, `
		INSERT INTO document_sample_generations(
			source_id, generation, source_sha256, sampling_method,
			status, sample_count
		)
		VALUES ($1, 1, $2, 'risk-stratified-sha256-v1', 'active', 1)
	`, legacySourceID, sourceSHA); err != nil {
		t.Fatalf("insert legacy sample generation: %v", err)
	}
	var legacyDocumentID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO documents(
			source_id, source_ordinal, current_object_sha256, text_preview,
			byte_size, char_count, status, sampling_method,
			is_active, sample_generation
		)
		VALUES (
			$1, 1, $2, 'Registry öncesi belge', 32, 21, 'approved',
			'risk-stratified-sha256-v1', true, 1
		)
		RETURNING id::text
	`, legacySourceID, documentSHA).Scan(&legacyDocumentID); err != nil {
		t.Fatalf("insert legacy document: %v", err)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO document_sample_memberships(
			source_id, generation, document_id, source_ordinal,
			object_sha256, risk_score, risk_reasons
		)
		VALUES ($1, 1, $2, 1, $3, 0, '{}'::text[])
	`, legacySourceID, legacyDocumentID, documentSHA); err != nil {
		t.Fatalf("insert legacy sample membership: %v", err)
	}
	// Migration 000024 rejects newly-created reviews without a pinned campaign.
	// Disable only that validation trigger while seeding a genuine historical
	// pre-registry review; the active-review registration trigger stays enabled.
	if _, err := pool.Exec(ctx, `
		ALTER TABLE document_reviews
		DISABLE TRIGGER document_reviews_validate_campaign
	`); err != nil {
		t.Fatalf("disable campaign validation for pre-registry fixture: %v", err)
	}
	_, legacyReviewErr := pool.Exec(ctx, `
		INSERT INTO document_reviews(
			document_id, reviewer_id, decision, quality_score,
			document_version, object_sha256, rubric_version
		)
		VALUES ($1, $2, 'approved', 4, 1, $3, 'overall-v1')
	`, legacyDocumentID, actorID, documentSHA)
	if _, err := pool.Exec(ctx, `
		ALTER TABLE document_reviews
		ENABLE TRIGGER document_reviews_validate_campaign
	`); err != nil {
		t.Fatalf("re-enable campaign validation after pre-registry fixture: %v", err)
	}
	if legacyReviewErr != nil {
		t.Fatalf("insert pre-registry review: %v", legacyReviewErr)
	}

	legacyRelease, err := releases.Create(ctx, domain.CreateReleaseInput{
		Name: "Legacy contract release", Version: "v1",
		ContentPurpose: "instruction", SourceIDs: []string{legacySourceID},
	}, actorID)
	if err != nil {
		t.Fatalf("create legacy release: %v", err)
	}
	var legacyEvidenceStatus, legacyContractVersion string
	if err := pool.QueryRow(ctx, `
		SELECT review_evidence_status, purpose_contract_version
		FROM release_source_contract_snapshots
		WHERE release_id = $1 AND source_id = $2
	`, legacyRelease.ID, legacySourceID).Scan(
		&legacyEvidenceStatus, &legacyContractVersion,
	); err != nil {
		t.Fatalf("read legacy release snapshot: %v", err)
	}
	if legacyEvidenceStatus != "absent_pre_registry" ||
		legacyContractVersion != "1" {
		t.Fatalf(
			"legacy evidence floated: status=%s purpose_contract=%s",
			legacyEvidenceStatus, legacyContractVersion,
		)
	}

	var pendingReleaseID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO releases(name, version, content_purpose, created_by)
		VALUES ('Missing contract', 'v1', 'instruction', $1)
		RETURNING id::text
	`, actorID).Scan(&pendingReleaseID); err != nil {
		t.Fatalf("insert pending release: %v", err)
	}
	_, err = releases.QueueFreeze(ctx, pendingReleaseID, actorID)
	var gateError *repository.GateError
	if !errors.As(err, &gateError) ||
		len(gateError.Reasons) != 1 ||
		gateError.Reasons[0] != "release_contract_snapshot_missing" {
		t.Fatalf("missing snapshot did not fail closed: %v", err)
	}
}

func newReleaseContractTestPool(
	t *testing.T,
	ctx context.Context,
) *pgxpool.Pool {
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

	schemaName := fmt.Sprintf("derlem_release_contract_test_%d", time.Now().UnixNano())
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
	if err := database.Migrate(ctx, pool); err != nil {
		t.Fatalf("migrate isolated schema: %v", err)
	}
	return pool
}
