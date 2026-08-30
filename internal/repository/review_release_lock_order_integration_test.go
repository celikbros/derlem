package repository_test

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/celikbros/derlem/internal/domain"
	"github.com/celikbros/derlem/internal/repository"
	"github.com/celikbros/derlem/internal/storage"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

// TestDocumentEditAndReleaseCreationUseSourceFirstLockOrder constructs the
// former edit/release deadlock deterministically. A blocker holds the document
// while the edit reaches its document lock. The edit must already hold the
// source boundary, so release creation waits there instead of retaining the
// source while competing for the same document. Once unblocked, the edit wins
// and the release observes the demoted source and fails closed without leaving
// a release or contract snapshot behind.
func TestDocumentEditAndReleaseCreationUseSourceFirstLockOrder(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	t.Cleanup(cancel)
	pool := newReleaseContractTestPool(t, ctx)

	actorID, sourceID, documentID, _, _ :=
		seedReleaseLockOrderFixture(t, ctx, pool)

	blocker, err := pool.Acquire(ctx)
	if err != nil {
		t.Fatalf("acquire document blocker: %v", err)
	}
	t.Cleanup(blocker.Release)
	blockerTx, err := blocker.Begin(ctx)
	if err != nil {
		t.Fatalf("begin document blocker: %v", err)
	}
	blockerOpen := true
	t.Cleanup(func() {
		if blockerOpen {
			_ = blockerTx.Rollback(context.Background())
		}
	})
	var lockedDocumentID string
	if err := blockerTx.QueryRow(ctx, `
		SELECT id::text FROM documents WHERE id = $1 FOR UPDATE
	`, documentID).Scan(&lockedDocumentID); err != nil {
		t.Fatalf("lock document blocker: %v", err)
	}

	editPool := newNamedLockOrderPool(t, ctx, pool, "derlem-lock-order-edit")
	releasePool := newNamedLockOrderPool(t, ctx, pool, "derlem-lock-order-edit-release")
	editRepository := repository.NewDocuments(editPool)
	releaseRepository := repository.NewReleases(releasePool)

	type editResult struct {
		value domain.Document
		err   error
	}
	editDone := make(chan editResult, 1)
	editReason := "lock order verification"
	go func() {
		value, err := editRepository.UpdateContent(
			ctx, documentID, 1,
			storage.Object{
				SHA256:     strings.Repeat("e", 64),
				StorageKey: "tests/lock-order-edited-document.txt",
				ByteSize:   48,
			},
			"Edited lock order document", 26, &editReason, actorID,
		)
		editDone <- editResult{value: value, err: err}
	}()
	waitForNamedLockWait(t, ctx, pool, "derlem-lock-order-edit")

	const releaseName = "Concurrent edit release"
	releaseDone := make(chan error, 1)
	go func() {
		_, err := releaseRepository.Create(ctx, domain.CreateReleaseInput{
			Name: releaseName, Version: "v1",
			ContentPurpose: "instruction", SourceIDs: []string{sourceID},
		}, actorID)
		releaseDone <- err
	}()
	waitForNamedLockWait(t, ctx, pool, "derlem-lock-order-edit-release")

	if err := blockerTx.Commit(ctx); err != nil {
		t.Fatalf("release document blocker: %v", err)
	}
	blockerOpen = false

	edited := <-editDone
	if edited.err != nil {
		assertNotDeadlock(t, "edit document", edited.err)
		t.Fatalf("edit document: %v", edited.err)
	}
	if edited.value.CurrentVersion != 2 ||
		edited.value.CurrentObjectSHA256 != strings.Repeat("e", 64) ||
		edited.value.Status != "edited" {
		t.Fatalf("edited document = %+v", edited.value)
	}

	releaseErr := <-releaseDone
	if releaseErr == nil {
		t.Fatal("release unexpectedly accepted a source after its document changed")
	}
	assertNotDeadlock(t, "create release after edit", releaseErr)
	var gateError *repository.GateError
	if !errors.As(releaseErr, &gateError) {
		t.Fatalf("release error = %v, want eligibility gate", releaseErr)
	}

	var sourceStatus, documentStatus, documentSHA string
	var reviewedCount, approvedCount, documentVersion int64
	var releaseCount, snapshotCount, versionCount, editAuditCount int
	if err := pool.QueryRow(ctx, `
		SELECT source.approval_status,
			source.reviewed_document_count,
			source.approved_document_count,
			document.status, document.current_version,
			document.current_object_sha256,
			(SELECT count(*) FROM releases WHERE name = $3),
			(SELECT count(*)
			 FROM release_source_contract_snapshots AS snapshot
			 JOIN releases AS release ON release.id = snapshot.release_id
			 WHERE release.name = $3),
			(SELECT count(*) FROM document_versions
			 WHERE document_id = $2::uuid AND version = 2),
			(SELECT count(*) FROM audit_events
			 WHERE action = 'document.edited' AND entity_id = $2::uuid)
		FROM sources AS source
		JOIN documents AS document ON document.source_id = source.id
		WHERE source.id = $1::uuid AND document.id = $2::uuid
	`, sourceID, documentID, releaseName).Scan(
		&sourceStatus, &reviewedCount, &approvedCount,
		&documentStatus, &documentVersion, &documentSHA,
		&releaseCount, &snapshotCount, &versionCount, &editAuditCount,
	); err != nil {
		t.Fatalf("read concurrent edit/release outcome: %v", err)
	}
	if sourceStatus != "sampled_for_review" || reviewedCount != 0 ||
		approvedCount != 0 || documentStatus != "edited" ||
		documentVersion != 2 || documentSHA != strings.Repeat("e", 64) ||
		releaseCount != 0 || snapshotCount != 0 || versionCount != 1 ||
		editAuditCount != 1 {
		t.Fatalf(
			"concurrent outcome = source %s reviewed %d approved %d document %s v%d sha %s release %d snapshots %d versions %d audits %d",
			sourceStatus, reviewedCount, approvedCount, documentStatus,
			documentVersion, documentSHA, releaseCount, snapshotCount,
			versionCount, editAuditCount,
		)
	}
}

// TestReviewReversalAndReleaseCreationUseSourceFirstLockOrder constructs the
// former deadlock deterministically. A blocker holds the document while the
// reversal reaches its document lock. Release creation is then started. With
// source -> document ordering the release waits behind the reversal at the
// source boundary; with the old review -> document -> source ordering the two
// operations formed a PostgreSQL deadlock after the blocker was released.
func TestReviewReversalAndReleaseCreationUseSourceFirstLockOrder(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	t.Cleanup(cancel)
	pool := newReleaseContractTestPool(t, ctx)

	actorID, sourceID, documentID, reviewID, campaignID :=
		seedReleaseLockOrderFixture(t, ctx, pool)

	blocker, err := pool.Acquire(ctx)
	if err != nil {
		t.Fatalf("acquire document blocker: %v", err)
	}
	t.Cleanup(blocker.Release)
	blockerTx, err := blocker.Begin(ctx)
	if err != nil {
		t.Fatalf("begin document blocker: %v", err)
	}
	blockerOpen := true
	t.Cleanup(func() {
		if blockerOpen {
			_ = blockerTx.Rollback(context.Background())
		}
	})
	var lockedDocumentID string
	if err := blockerTx.QueryRow(ctx, `
		SELECT id::text FROM documents WHERE id = $1 FOR UPDATE
	`, documentID).Scan(&lockedDocumentID); err != nil {
		t.Fatalf("lock document blocker: %v", err)
	}

	reversalPool := newNamedLockOrderPool(t, ctx, pool, "derlem-lock-order-reversal")
	releasePool := newNamedLockOrderPool(t, ctx, pool, "derlem-lock-order-release")
	reversalRepository := repository.NewDocuments(reversalPool)
	releaseRepository := repository.NewReleases(releasePool)

	type reversalResult struct {
		value domain.ReverseDocumentReviewResult
		err   error
	}
	reversalDone := make(chan reversalResult, 1)
	go func() {
		value, err := reversalRepository.ReverseReview(
			ctx, reviewID,
			domain.ReverseDocumentReviewInput{Reason: "lock order verification"},
			actorID, false,
		)
		reversalDone <- reversalResult{value: value, err: err}
	}()
	waitForNamedLockWait(t, ctx, pool, "derlem-lock-order-reversal")

	releaseDone := make(chan error, 1)
	go func() {
		_, err := releaseRepository.Create(ctx, domain.CreateReleaseInput{
			Name: "Concurrent reversal release", Version: "v1",
			ContentPurpose: "instruction", SourceIDs: []string{sourceID},
		}, actorID)
		releaseDone <- err
	}()
	waitForNamedLockWait(t, ctx, pool, "derlem-lock-order-release")

	if err := blockerTx.Commit(ctx); err != nil {
		t.Fatalf("release document blocker: %v", err)
	}
	blockerOpen = false

	reversed := <-reversalDone
	if reversed.err != nil {
		assertNotDeadlock(t, "reverse review", reversed.err)
		t.Fatalf("reverse review: %v", reversed.err)
	}
	if reversed.value.Review.ReviewCampaignID == nil ||
		*reversed.value.Review.ReviewCampaignID != campaignID {
		t.Fatalf(
			"reversal lost review campaign: got %v want %s",
			reversed.value.Review.ReviewCampaignID, campaignID,
		)
	}

	releaseErr := <-releaseDone
	if releaseErr == nil {
		t.Fatal("release unexpectedly accepted a source after its approval was reversed")
	}
	assertNotDeadlock(t, "create release", releaseErr)
	var gateError *repository.GateError
	if !errors.As(releaseErr, &gateError) {
		t.Fatalf("release error = %v, want eligibility gate", releaseErr)
	}

	var sourceStatus, documentStatus, auditedCampaignID string
	var activeReviewCount, reversalCount int
	if err := pool.QueryRow(ctx, `
		SELECT source.approval_status, document.status,
			(SELECT count(*) FROM active_document_reviews
			 WHERE review_id = $3::uuid),
			(SELECT count(*) FROM document_review_reversals
			 WHERE review_id = $3::uuid),
			(SELECT details->>'review_campaign_id'
			 FROM audit_events
			 WHERE action = 'document.review_reversed'
			   AND entity_id = $2::uuid
			 ORDER BY created_at DESC, id DESC LIMIT 1)
		FROM sources AS source
		JOIN documents AS document ON document.source_id = source.id
		WHERE source.id = $1 AND document.id = $2
	`, sourceID, documentID, reviewID).Scan(
		&sourceStatus, &documentStatus, &activeReviewCount, &reversalCount,
		&auditedCampaignID,
	); err != nil {
		t.Fatalf("read concurrent outcome: %v", err)
	}
	if sourceStatus != "sampled_for_review" || documentStatus != "sampled" ||
		activeReviewCount != 0 || reversalCount != 1 ||
		auditedCampaignID != campaignID {
		t.Fatalf(
			"concurrent outcome = source %s document %s active %d reversals %d campaign %s",
			sourceStatus, documentStatus, activeReviewCount, reversalCount,
			auditedCampaignID,
		)
	}
}

func seedReleaseLockOrderFixture(
	t *testing.T,
	ctx context.Context,
	pool *pgxpool.Pool,
) (actorID, sourceID, documentID, reviewID, campaignID string) {
	t.Helper()
	if err := pool.QueryRow(ctx, `
		INSERT INTO users(email, password_hash, display_name)
		VALUES ('lock-order@example.test', 'test', 'Lock Order Test')
		RETURNING id::text
	`).Scan(&actorID); err != nil {
		t.Fatalf("insert lock-order actor: %v", err)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
		VALUES
			(repeat('c', 64), 'tests/lock-order-source.jsonl', 128, 'application/x-ndjson'),
			(repeat('d', 64), 'tests/lock-order-document.txt', 32, 'text/plain')
	`); err != nil {
		t.Fatalf("insert lock-order objects: %v", err)
	}
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
			'Lock-order source', 'jsonl', 'instruction', 'internal', 'cleared',
			'tr', 'general', 'tests/license.txt', 'lock-order-test',
			repeat('c', 64), 128, 1, 1, 'clear', 'approved_source', $1,
			'unique', 'unique', 'sampled', 1, 1, 1, 0, 1,
			'risk-stratified-sha256-v1'
		)
		RETURNING id::text
	`, actorID).Scan(&sourceID); err != nil {
		t.Fatalf("insert lock-order source: %v", err)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO document_sample_generations(
			source_id, generation, source_sha256, sampling_method,
			status, sample_count
		)
		VALUES ($1, 1, repeat('c', 64), 'risk-stratified-sha256-v1', 'active', 1)
	`, sourceID); err != nil {
		t.Fatalf("insert lock-order sample generation: %v", err)
	}
	if err := pool.QueryRow(ctx, `
		INSERT INTO documents(
			source_id, source_ordinal, current_object_sha256, text_preview,
			byte_size, char_count, status, sampling_method,
			is_active, sample_generation
		)
		VALUES (
			$1, 1, repeat('d', 64), 'Lock order document', 32, 19,
			'approved', 'risk-stratified-sha256-v1', true, 1
		)
		RETURNING id::text
	`, sourceID).Scan(&documentID); err != nil {
		t.Fatalf("insert lock-order document: %v", err)
	}
	insertActiveDocumentSampleMemberships(t, ctx, pool, sourceID)
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
		t.Fatalf("insert lock-order campaign: %v", err)
	}
	if err := pool.QueryRow(ctx, `
		INSERT INTO document_reviews(
			document_id, reviewer_id, review_campaign_id, decision, reason,
			rubric_version, quality_score, language_quality_score,
			coherence_score, information_density_score, cleanliness_score,
			document_version, object_sha256, review_context
		)
		VALUES (
			$1, $2, $3::uuid, 'approved', NULL, 'multidimensional-v1',
			5, 5, 5, 5, 5, 1, repeat('d', 64),
			jsonb_build_object(
				'source_id', $4::text, 'previous_status', 'sampled',
				'sampling_method', 'risk-stratified-sha256-v1',
				'sample_generation', 1, 'review_campaign_id', $3::text
			)
		)
		RETURNING id::text
	`, documentID, actorID, campaignID, sourceID).Scan(&reviewID); err != nil {
		t.Fatalf("insert lock-order review: %v", err)
	}
	return actorID, sourceID, documentID, reviewID, campaignID
}

func newNamedLockOrderPool(
	t *testing.T,
	ctx context.Context,
	base *pgxpool.Pool,
	applicationName string,
) *pgxpool.Pool {
	t.Helper()
	config := base.Config().Copy()
	config.ConnConfig.RuntimeParams["application_name"] = applicationName
	config.MaxConns = 1
	config.MinConns = 0
	pool, err := pgxpool.NewWithConfig(ctx, config)
	if err != nil {
		t.Fatalf("open %s pool: %v", applicationName, err)
	}
	t.Cleanup(pool.Close)
	return pool
}

func waitForNamedLockWait(
	t *testing.T,
	ctx context.Context,
	pool *pgxpool.Pool,
	applicationName string,
) {
	t.Helper()
	deadline := time.Now().Add(10 * time.Second)
	for time.Now().Before(deadline) {
		var waiting bool
		if err := pool.QueryRow(ctx, `
			SELECT EXISTS (
				SELECT 1 FROM pg_stat_activity
				WHERE application_name = $1
				  AND wait_event_type = 'Lock'
			)
		`, applicationName).Scan(&waiting); err != nil {
			t.Fatalf("inspect %s wait state: %v", applicationName, err)
		}
		if waiting {
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatalf("%s did not reach a lock wait", applicationName)
}

func assertNotDeadlock(t *testing.T, operation string, err error) {
	t.Helper()
	var pgError *pgconn.PgError
	if errors.As(err, &pgError) && pgError.Code == "40P01" {
		t.Fatalf("%s encountered PostgreSQL deadlock: %v", operation, err)
	}
	if err != nil && errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("%s timed out waiting on lock order: %v", operation, err)
	}
}
