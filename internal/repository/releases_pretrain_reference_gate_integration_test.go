package repository_test

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/celikbros/derlem/internal/domain"
	"github.com/celikbros/derlem/internal/repository"
)

// Sınav seti olmadan pretrain sürümü dondurulmaz (TASK-017). Kapı yalnız
// pretrain amacında çalışır; referans seçimi worker'ın dekontaminasyon
// kapısıyla aynıdır (eval/holdout amaçlı, nesnesi olan, kopya olmayan kaynak).
func TestQueueFreezeRefusesPretrainWithoutEvalReference(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	t.Cleanup(cancel)
	pool := newReleaseContractTestPool(t, ctx)

	var actorID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO users(email, password_hash, display_name)
		VALUES ('pretrain-gate@example.test', 'test', 'Pretrain Gate Test')
		RETURNING id::text
	`).Scan(&actorID); err != nil {
		t.Fatalf("insert actor: %v", err)
	}
	sourceSHA := strings.Repeat("c", 64)
	documentSHA := strings.Repeat("d", 64)
	holdoutSHA := strings.Repeat("e", 64)
	if _, err := pool.Exec(ctx, `
		INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
		VALUES
			($1, 'tests/pretrain-source.txt', 128, 'text/plain'),
			($2, 'tests/pretrain-document.txt', 32, 'text/plain'),
			($3, 'tests/holdout-source.txt', 64, 'text/plain')
	`, sourceSHA, documentSHA, holdoutSHA); err != nil {
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
			'Pretrain source', 'text_corpus', 'pretrain', 'internal', 'cleared',
			'tr', 'general', 'tests/license.txt', 'pretrain-gate-test',
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
			source_id, generation, source_sha256, sampling_method, status, sample_count
		)
		VALUES ($1, 1, $2, 'risk-stratified-sha256-v1', 'active', 1)
	`, sourceID, sourceSHA); err != nil {
		t.Fatalf("insert sample generation: %v", err)
	}
	var documentID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO documents(
			source_id, source_ordinal, current_object_sha256, text_preview,
			byte_size, char_count, status, sampling_method, is_active, sample_generation
		)
		VALUES ($1, 1, $2, 'Pretrain belge', 32, 14, 'approved', 'risk-stratified-sha256-v1', true, 1)
		RETURNING id::text
	`, sourceID, documentSHA).Scan(&documentID); err != nil {
		t.Fatalf("insert document: %v", err)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO document_sample_memberships(
			source_id, generation, document_id, source_ordinal, object_sha256, risk_score, risk_reasons
		)
		VALUES ($1, 1, $2, 1, $3, 0, '{}'::text[])
	`, sourceID, documentID, documentSHA); err != nil {
		t.Fatalf("insert sample membership: %v", err)
	}
	var campaignID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO review_campaigns(
			source_id, sample_generation, data_profile_key, data_profile_version, content_purpose,
			profile_config_sha256, rubric_key, rubric_version, purpose_contract_version,
			protocol_key, protocol_version, pii_policy_key, pii_policy_version,
			dedup_policy_key, dedup_policy_version, leakage_policy_key, leakage_policy_version,
			purpose_contract_sha256, implementation_bundle_sha256, created_by
		)
		SELECT source.id, 1, source.data_profile_key, source.data_profile_version, source.content_purpose,
			source.profile_config_sha256, profile.rubric_key, profile.rubric_version, contract.purpose_contract_version,
			contract.protocol_key, contract.protocol_version, contract.pii_policy_key, contract.pii_policy_version,
			contract.dedup_policy_key, contract.dedup_policy_version, contract.leakage_policy_key, contract.leakage_policy_version,
			contract.spec_sha256, contract.implementation_bundle_sha256, $2
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
			document_id, reviewer_id, decision, quality_score, document_version, object_sha256, rubric_version,
			language_quality_score, coherence_score, information_density_score, cleanliness_score, review_campaign_id
		)
		VALUES ($1, $2, 'approved', 4, 1, $3, 'multidimensional-v1', 4, 4, 4, 4, $4)
	`, documentID, actorID, documentSHA, campaignID); err != nil {
		t.Fatalf("insert campaign review: %v", err)
	}

	releases := repository.NewReleases(pool)
	release, err := releases.Create(ctx, domain.CreateReleaseInput{
		Name: "Pretrain release", Version: "v1", ContentPurpose: "pretrain", SourceIDs: []string{sourceID},
	}, actorID)
	if err != nil {
		t.Fatalf("create pretrain release: %v", err)
	}
	if release.ContractSnapshotStatus != "present" {
		t.Fatalf("pretrain draft has no contract snapshot: %+v", release)
	}

	// Sınav seti yok → dondurma reddedilir; sürüm taslak kalır, iş kuyruğa girmez.
	_, err = releases.QueueFreeze(ctx, release.ID, actorID)
	var gateError *repository.GateError
	if !errors.As(err, &gateError) || len(gateError.Reasons) != 1 || gateError.Reasons[0] != "eval_reference_missing" {
		t.Fatalf("expected eval_reference_missing gate error, got %v", err)
	}
	var queued int
	if err := pool.QueryRow(ctx, `SELECT count(*) FROM background_jobs WHERE job_type = 'freeze_release'`).Scan(&queued); err != nil || queued != 0 {
		t.Fatalf("no freeze job may be queued when the gate refuses (count=%d, err=%v)", queued, err)
	}

	// Held-out kaynağı kaydedilince (nesnesi var, kopya değil) dondurma kuyruğa girer.
	if _, err := pool.Exec(ctx, `
		INSERT INTO sources(
			name, source_type, content_purpose, license, rights_status, language, domain, lineage_ref,
			object_sha256, byte_size, line_count, created_by, duplicate_status
		)
		VALUES (
			'Held-out', 'text_corpus', 'holdout', 'unknown', 'unknown', 'tr', 'general', 'pretrain-gate-test',
			$1, 64, 1, $2, 'unique'
		)
	`, holdoutSHA, actorID); err != nil {
		t.Fatalf("insert holdout source: %v", err)
	}
	jobID, err := releases.QueueFreeze(ctx, release.ID, actorID)
	if err != nil || jobID == "" {
		t.Fatalf("freeze must queue once a holdout reference exists, got job=%q err=%v", jobID, err)
	}
}
