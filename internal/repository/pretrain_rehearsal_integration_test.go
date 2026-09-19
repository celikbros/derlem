package repository_test

import (
	"bufio"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
	"time"
	"unicode/utf8"

	"github.com/celikbros/derlem/internal/domain"
	"github.com/celikbros/derlem/internal/repository"
	"github.com/jackc/pgx/v5/pgxpool"
)

// TASK-018 — pretrain taslak → QueueFreeze provasının Go yarısı.
//
// 100k dilim (99.007 satır aday + 43 satır sınav seti) izole bir _test
// şemasına pretrain/holdout kaynak olarak ekilir; 200 belge örneklenir ve
// kaynağı açan kullanıcıdan FARKLI ikinci bir kullanıcı tarafından onaylanır;
// taslak Releases.Create ile açılır (sözleşme anlık görüntüsü DB'de türetilir)
// ve QueueFreeze bir freeze_release işi kuyruğa alır. Sınav seti yokken aynı
// çağrı eval_reference_missing ile reddedilir (TASK-017).
//
// Sonuç satırları worker/tests/fixtures/pretrain_rehearsal/ altına JSON olarak
// yazılır; Python yarısı (worker/tests/test_pretrain_rehearsal_integration.py)
// aynı satırları taze bir şemaya yükleyip freeze_release ve export_release
// işlerini süreç içinde koşturur. İki yarı ayrı süreçlerdir; onları bu fixture
// bağlar. Yükleme sırasında DB tetikleyicileri anlık görüntüyü güncel sözleşme
// kayıt defterine karşı yeniden doğrular; kayıt defteri değişirse Python yarısı
// kırmızı olur (sapma testi).
//
// Fixture'ı yeniden üretmek için:
//
//	DERLEM_UPDATE_GOLDEN=1 go test ./internal/repository/ -run TestPretrainRehearsal -v
//
// Dilim metni git'e girmez (203 MB); varsayılan konumu var/olcum-2026-09-17,
// DERLEM_PRETRAIN_SLICE_DIR ile değiştirilir. Dilim yoksa test AÇIKÇA atlanır
// (nedeni yazılır); sessiz atlama değildir.
const (
	rehearsalSliceDirEnv     = "DERLEM_PRETRAIN_SLICE_DIR"
	rehearsalDefaultSliceDir = "../../var/olcum-2026-09-17"
	rehearsalCandidateFile   = "dilim-100k_v3.txt"
	rehearsalHoldoutFile     = "dilim-100k_v3_heldout.txt"
	rehearsalFixturePath     = "../../worker/tests/fixtures/pretrain_rehearsal/slice100k.fixture.json"
	rehearsalFixtureSchema   = "derlem.pretrain-rehearsal-fixture.v1"
	rehearsalSampleSize      = 200
	rehearsalSamplingMethod  = "risk-stratified-sha256-v1"
	rehearsalRubricVersion   = "multidimensional-v1"
	rehearsalPreviewRunes    = 120
)

// rehearsalStableSnapshotKeys, sözleşme kayıt defterinden gelen ve koşudan
// koşuya değişmemesi gereken anlık görüntü sütunları. Kimlikler (release_id,
// source_id, review_campaign_id), zaman damgaları ve belge kimliklerini
// hash'leyen üyelik kökü bilerek dışarıda: her koşuda yeni UUID üretilir.
var rehearsalStableSnapshotKeys = []string{
	"data_profile_key", "data_profile_version", "content_purpose", "data_origin",
	"profile_config_artifact_kind", "profile_config_sha256",
	"profile_config_schema_artifact_kind", "profile_config_schema_sha256",
	"payload_schema_sha256", "field_extraction_sha256",
	"profile_implementation_key", "profile_implementation_digest",
	"rubric_key", "rubric_version", "rubric_sha256",
	"protocol_key", "protocol_version", "protocol_sha256",
	"pii_policy_key", "pii_policy_version", "pii_policy_sha256",
	"dedup_policy_key", "dedup_policy_version", "dedup_policy_sha256",
	"leakage_policy_key", "leakage_policy_version", "leakage_policy_sha256",
	"purpose_contract_version", "purpose_contract_sha256",
	"export_contract_key", "export_contract_version", "export_contract_sha256",
	"review_evidence_status", "implementation_bundle_sha256",
	"license_evidence_ref_sha256", "lineage_ref_sha256",
	"sample_generation", "sample_source_sha256", "sample_sampling_method",
	"sample_count", "sample_membership_count",
}

// rehearsalTableOrder, Python yükleyicisinin yabancı anahtar sırasına göre
// izlediği tablo sırası. contract_spec_artifacts iki paket satırı taşır
// (kampanya sözleşmesi + sürüm anlık görüntüsü) ve onları türeten
// tetikleyicilerden önce yüklenir. releases satırı 'pending' olarak eklenir;
// anlık görüntüler yüklendikten sonra 'present'e geçirilir ve bu geçişte DB
// tetikleyicisi paket SHA'sını yeniden türetip fixture'dakiyle karşılaştırır.
var rehearsalTableOrder = []string{
	"users", "storage_objects", "sources", "document_sample_generations",
	"documents", "document_sample_memberships", "contract_spec_artifacts",
	"review_campaigns", "document_reviews", "releases", "release_sources",
	"release_source_contract_snapshots", "background_jobs",
}

type rehearsalSliceObject struct {
	File       string `json:"file"`
	SHA256     string `json:"sha256"`
	StorageKey string `json:"storage_key"`
	ByteSize   int64  `json:"byte_size"`
	LineCount  int64  `json:"line_count"`
}

type rehearsalFixtureHeader struct {
	SchemaVersion string `json:"schema_version"`
	GeneratedBy   string `json:"generated_by"`
	GeneratedAt   string `json:"generated_at"`
	Slice         struct {
		Candidate rehearsalSliceObject `json:"candidate"`
		Holdout   rehearsalSliceObject `json:"holdout"`
	} `json:"slice"`
	SampleSize      int      `json:"sample_size"`
	CreatorID       string   `json:"creator_id"`
	ReviewerID      string   `json:"reviewer_id"`
	SourceID        string   `json:"source_id"`
	HoldoutSourceID string   `json:"holdout_source_id"`
	ReleaseID       string   `json:"release_id"`
	FreezeJobID     string   `json:"freeze_job_id"`
	TableOrder      []string `json:"table_order"`
}

type rehearsalFixture struct {
	rehearsalFixtureHeader
	Tables map[string][]json.RawMessage `json:"tables"`
}

type rehearsalSampledLine struct {
	Ordinal int64
	Text    string
}

func TestPretrainRehearsal(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
	t.Cleanup(cancel)

	sliceDir := strings.TrimSpace(os.Getenv(rehearsalSliceDirEnv))
	if sliceDir == "" {
		sliceDir = rehearsalDefaultSliceDir
	}
	candidatePath := filepath.Join(sliceDir, rehearsalCandidateFile)
	holdoutPath := filepath.Join(sliceDir, rehearsalHoldoutFile)
	for _, path := range []string{candidatePath, holdoutPath} {
		if _, err := os.Stat(path); err != nil {
			t.Skipf("100k slice is not available (%v); the slice text is not committed. "+
				"Point %s at a directory holding %s and %s to run the rehearsal.",
				err, rehearsalSliceDirEnv, rehearsalCandidateFile, rehearsalHoldoutFile)
		}
	}

	pool := newReleaseContractTestPool(t, ctx)
	storeRoot := filepath.Join(t.TempDir(), "store")

	creatorID := rehearsalInsertUser(t, ctx, pool, "pretrain-rehearsal-creator@example.test", "Rehearsal Creator")
	reviewerID := rehearsalInsertUser(t, ctx, pool, "pretrain-rehearsal-reviewer@example.test", "Rehearsal Reviewer")

	// --- pretrain kaynak: dilim adayı geçici CAS deposuna kopyalanır ------------
	started := time.Now()
	candidate := rehearsalIngestObject(t, storeRoot, candidatePath)
	t.Logf("candidate ingested: sha256=%s bytes=%d lines=%d in %s",
		candidate.SHA256, candidate.ByteSize, candidate.LineCount, time.Since(started).Round(time.Millisecond))
	if _, err := pool.Exec(ctx, `
		INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
		VALUES ($1, $2, $3, 'text/plain')
	`, candidate.SHA256, candidate.StorageKey, candidate.ByteSize); err != nil {
		t.Fatalf("insert candidate storage object: %v", err)
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
			'Gardas clean candidate v3 - 100k slice (rehearsal)', 'text_corpus', 'pretrain',
			'internal', 'cleared', 'tr', 'general',
			'tests/pretrain-rehearsal-rights-evidence.md (scratch database only)',
			'var/olcum-2026-09-17/dilim-100k_v3.txt',
			$1, $2, $3, $3, 'clear', 'approved_source', $4,
			'unique', 'unique', 'sampled', $5, $5, $5, 0, 1, $6
		)
		RETURNING id::text
	`, candidate.SHA256, candidate.ByteSize, candidate.LineCount, creatorID,
		rehearsalSampleSize, rehearsalSamplingMethod).Scan(&sourceID); err != nil {
		t.Fatalf("insert pretrain source: %v", err)
	}
	if _, err := pool.Exec(ctx, `
		INSERT INTO document_sample_generations(
			source_id, generation, source_sha256, sampling_method, status, sample_count
		)
		VALUES ($1, 1, $2, $3, 'active', $4)
	`, sourceID, candidate.SHA256, rehearsalSamplingMethod, rehearsalSampleSize); err != nil {
		t.Fatalf("insert sample generation: %v", err)
	}

	// 200 belge: satır sayısına yayılmış deterministik adımlarla seçilir; belge
	// nesnesi worker'ın örnekleyicisi gibi satır metninin UTF-8 SHA-256'sıdır.
	// Belge nesneleri diske yazılmaz: dondurma ve dışa aktarma yalnız kaynak
	// nesnesini okur.
	sampled := rehearsalSampleLines(t, candidatePath, candidate.LineCount, rehearsalSampleSize)
	documentIDs := make([]string, 0, len(sampled))
	documentSHAs := make([]string, 0, len(sampled))
	for _, line := range sampled {
		digest := sha256.Sum256([]byte(line.Text))
		documentSHA := hex.EncodeToString(digest[:])
		if _, err := pool.Exec(ctx, `
			INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
			VALUES ($1, $2, $3, 'text/plain')
			ON CONFLICT (sha256) DO NOTHING
		`, documentSHA, rehearsalStorageKey(documentSHA), len(line.Text)); err != nil {
			t.Fatalf("insert document storage object (ordinal %d): %v", line.Ordinal, err)
		}
		var documentID string
		if err := pool.QueryRow(ctx, `
			INSERT INTO documents(
				source_id, source_ordinal, current_object_sha256, text_preview,
				byte_size, char_count, status, sampling_method, is_active, sample_generation
			)
			VALUES ($1, $2, $3, $4, $5, $6, 'approved', $7, true, 1)
			RETURNING id::text
		`, sourceID, line.Ordinal, documentSHA, rehearsalPreview(line.Text),
			len(line.Text), utf8.RuneCountInString(line.Text), rehearsalSamplingMethod,
		).Scan(&documentID); err != nil {
			t.Fatalf("insert document (ordinal %d): %v", line.Ordinal, err)
		}
		if _, err := pool.Exec(ctx, `
			INSERT INTO document_sample_memberships(
				source_id, generation, document_id, source_ordinal, object_sha256, risk_score, risk_reasons
			)
			VALUES ($1, 1, $2, $3, $4, 0, '{}'::text[])
		`, sourceID, documentID, line.Ordinal, documentSHA); err != nil {
			t.Fatalf("insert sample membership (ordinal %d): %v", line.Ordinal, err)
		}
		documentIDs = append(documentIDs, documentID)
		documentSHAs = append(documentSHAs, documentSHA)
	}

	// Kampanya, üyelikler yerleştikten sonra açılır: tetikleyici üyelik kökünü
	// ekleme anında türetir.
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
	`, sourceID, creatorID).Scan(&campaignID); err != nil {
		t.Fatalf("insert review campaign: %v", err)
	}
	// 200 onay, kaynağı açan kullanıcıdan farklı ikinci kullanıcıdan.
	for index, documentID := range documentIDs {
		if _, err := pool.Exec(ctx, `
			INSERT INTO document_reviews(
				document_id, reviewer_id, decision, quality_score, document_version, object_sha256, rubric_version,
				language_quality_score, coherence_score, information_density_score, cleanliness_score, review_campaign_id
			)
			VALUES ($1, $2, 'approved', 4, 1, $3, $4, 4, 4, 4, 4, $5)
		`, documentID, reviewerID, documentSHAs[index], rehearsalRubricVersion, campaignID); err != nil {
			t.Fatalf("insert approving review %d: %v", index, err)
		}
	}

	releases := repository.NewReleases(pool)

	// --- kardeş vaka: sınav seti YOK → 422 eval_reference_missing (TASK-017) --
	sibling, err := releases.Create(ctx, domain.CreateReleaseInput{
		Name: "Pretrain rehearsal (no holdout)", Version: "v1", ContentPurpose: "pretrain",
		SourceIDs: []string{sourceID},
	}, creatorID)
	if err != nil {
		t.Fatalf("create sibling draft: %v", err)
	}
	if sibling.ContractSnapshotStatus != "present" {
		t.Fatalf("sibling draft has no contract snapshot: %+v", sibling)
	}
	_, err = releases.QueueFreeze(ctx, sibling.ID, creatorID)
	var gateError *repository.GateError
	if !errors.As(err, &gateError) || len(gateError.Reasons) != 1 || gateError.Reasons[0] != "eval_reference_missing" {
		t.Fatalf("sibling without holdout: expected eval_reference_missing gate error, got %v", err)
	}
	var queued int
	if err := pool.QueryRow(ctx, `SELECT count(*) FROM background_jobs WHERE job_type = 'freeze_release'`).Scan(&queued); err != nil || queued != 0 {
		t.Fatalf("no freeze job may be queued when the gate refuses (count=%d, err=%v)", queued, err)
	}

	// --- sınav seti: 43 satırlık held-out, holdout amaçlı kaynak -------------
	holdout := rehearsalIngestObject(t, storeRoot, holdoutPath)
	if _, err := pool.Exec(ctx, `
		INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
		VALUES ($1, $2, $3, 'text/plain')
	`, holdout.SHA256, holdout.StorageKey, holdout.ByteSize); err != nil {
		t.Fatalf("insert holdout storage object: %v", err)
	}
	var holdoutSourceID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO sources(
			name, source_type, content_purpose, license, rights_status, language, domain,
			license_evidence_ref, lineage_ref, object_sha256, byte_size, line_count, document_count,
			created_by, duplicate_status
		)
		VALUES (
			'Gardas clean candidate v3 - 100k slice held-out (rehearsal)', 'text_corpus', 'holdout',
			'internal', 'cleared', 'tr', 'general',
			'tests/pretrain-rehearsal-rights-evidence.md (scratch database only)',
			'var/olcum-2026-09-17/dilim-100k_v3_heldout.txt',
			$1, $2, $3, $3, $4, 'unique'
		)
		RETURNING id::text
	`, holdout.SHA256, holdout.ByteSize, holdout.LineCount, creatorID).Scan(&holdoutSourceID); err != nil {
		t.Fatalf("insert holdout source: %v", err)
	}

	// --- ana vaka: taslak + QueueFreeze -----------------------------------------
	release, err := releases.Create(ctx, domain.CreateReleaseInput{
		Name: "Pretrain rehearsal 100k", Version: "v1", ContentPurpose: "pretrain",
		SourceIDs: []string{sourceID},
	}, creatorID)
	if err != nil {
		t.Fatalf("create pretrain draft: %v", err)
	}
	if release.ContractSnapshotStatus != "present" ||
		release.ContractSnapshotArtifactKind == nil || *release.ContractSnapshotArtifactKind != "contract_bundle" ||
		release.ContractSnapshotSHA256 == nil || len(*release.ContractSnapshotSHA256) != 64 ||
		release.ImplementationBundleSHA256 == nil || len(*release.ImplementationBundleSHA256) != 64 {
		t.Fatalf("pretrain draft contract snapshot was not derived: %+v", release)
	}
	var artifactMatches bool
	if err := pool.QueryRow(ctx, `
		SELECT artifact.sha256 = contract_spec_artifact_sha256(artifact.canonical_bytes)
		FROM contract_spec_artifacts AS artifact
		WHERE artifact.artifact_kind = 'contract_bundle' AND artifact.sha256 = $1
	`, *release.ContractSnapshotSHA256).Scan(&artifactMatches); err != nil || !artifactMatches {
		t.Fatalf("contract bundle artifact does not verify (matches=%v err=%v)", artifactMatches, err)
	}

	jobID, err := releases.QueueFreeze(ctx, release.ID, creatorID)
	if err != nil || jobID == "" {
		t.Fatalf("queue freeze with holdout present: job=%q err=%v", jobID, err)
	}
	var jobType, jobStatus, payloadReleaseID, payloadSnapshotSHA string
	if err := pool.QueryRow(ctx, `
		SELECT job_type, status, payload->>'release_id', payload->>'contract_snapshot_sha256'
		FROM background_jobs WHERE id = $1
	`, jobID).Scan(&jobType, &jobStatus, &payloadReleaseID, &payloadSnapshotSHA); err != nil {
		t.Fatalf("read freeze job row: %v", err)
	}
	if jobType != "freeze_release" || jobStatus != "queued" || payloadReleaseID != release.ID ||
		payloadSnapshotSHA != *release.ContractSnapshotSHA256 {
		t.Fatalf("unexpected freeze job row: type=%s status=%s release=%s sha=%s",
			jobType, jobStatus, payloadReleaseID, payloadSnapshotSHA)
	}
	t.Logf("draft %s: contract_snapshot_sha256=%s implementation_bundle_sha256=%s freeze job=%s",
		release.ID, *release.ContractSnapshotSHA256, *release.ImplementationBundleSHA256, jobID)

	// --- fixture: Python yarısına giden satırlar --------------------------------
	fixture := rehearsalFixture{Tables: map[string][]json.RawMessage{}}
	fixture.SchemaVersion = rehearsalFixtureSchema
	fixture.GeneratedBy = "DERLEM_UPDATE_GOLDEN=1 go test ./internal/repository/ -run TestPretrainRehearsal (TASK-018)"
	fixture.GeneratedAt = time.Now().UTC().Format(time.RFC3339)
	fixture.Slice.Candidate = candidate
	fixture.Slice.Holdout = holdout
	fixture.SampleSize = rehearsalSampleSize
	fixture.CreatorID = creatorID
	fixture.ReviewerID = reviewerID
	fixture.SourceID = sourceID
	fixture.HoldoutSourceID = holdoutSourceID
	fixture.ReleaseID = release.ID
	fixture.FreezeJobID = jobID
	fixture.TableOrder = rehearsalTableOrder
	queries := map[string]struct {
		sql  string
		args []any
	}{
		"users": {`SELECT to_jsonb(t) FROM users AS t WHERE t.id = ANY($1::uuid[]) ORDER BY t.email`,
			[]any{[]string{creatorID, reviewerID}}},
		"storage_objects": {`SELECT to_jsonb(t) FROM storage_objects AS t
			WHERE t.sha256 = ANY($1::text[])
			   OR t.sha256 IN (SELECT current_object_sha256 FROM documents WHERE source_id = $2)
			ORDER BY t.sha256`, []any{[]string{candidate.SHA256, holdout.SHA256}, sourceID}},
		"sources": {`SELECT to_jsonb(t) FROM sources AS t WHERE t.id = ANY($1::uuid[]) ORDER BY t.content_purpose`,
			[]any{[]string{sourceID, holdoutSourceID}}},
		"document_sample_generations": {`SELECT to_jsonb(t) FROM document_sample_generations AS t WHERE t.source_id = $1`,
			[]any{sourceID}},
		"documents": {`SELECT to_jsonb(t) FROM documents AS t WHERE t.source_id = $1 ORDER BY t.source_ordinal`,
			[]any{sourceID}},
		"document_sample_memberships": {`SELECT to_jsonb(t) FROM document_sample_memberships AS t WHERE t.source_id = $1 ORDER BY t.source_ordinal`,
			[]any{sourceID}},
		"contract_spec_artifacts": {`SELECT to_jsonb(t) FROM contract_spec_artifacts AS t
			WHERE t.artifact_kind = 'contract_bundle'
			  AND (t.sha256 = $1 OR t.sha256 IN (SELECT campaign_contract_sha256 FROM review_campaigns WHERE id = $2))
			ORDER BY t.sha256`, []any{*release.ContractSnapshotSHA256, campaignID}},
		"review_campaigns": {`SELECT to_jsonb(t) FROM review_campaigns AS t WHERE t.id = $1`, []any{campaignID}},
		"document_reviews": {`SELECT to_jsonb(t) FROM document_reviews AS t
			WHERE t.review_campaign_id = $1 ORDER BY t.created_at, t.id`, []any{campaignID}},
		"releases":        {`SELECT to_jsonb(t) FROM releases AS t WHERE t.id = $1`, []any{release.ID}},
		"release_sources": {`SELECT to_jsonb(t) FROM release_sources AS t WHERE t.release_id = $1 ORDER BY t.source_id`, []any{release.ID}},
		"release_source_contract_snapshots": {`SELECT to_jsonb(t) FROM release_source_contract_snapshots AS t
			WHERE t.release_id = $1 ORDER BY t.source_id`, []any{release.ID}},
		"background_jobs": {`SELECT to_jsonb(t) FROM background_jobs AS t WHERE t.id = $1`, []any{jobID}},
	}
	for _, table := range rehearsalTableOrder {
		query := queries[table]
		rows, err := pool.Query(ctx, query.sql, query.args...)
		if err != nil {
			t.Fatalf("export %s: %v", table, err)
		}
		for rows.Next() {
			var raw []byte
			if err := rows.Scan(&raw); err != nil {
				rows.Close()
				t.Fatalf("scan %s row: %v", table, err)
			}
			var compact bytes.Buffer
			if err := json.Compact(&compact, raw); err != nil {
				rows.Close()
				t.Fatalf("compact %s row: %v", table, err)
			}
			fixture.Tables[table] = append(fixture.Tables[table], json.RawMessage(compact.Bytes()))
		}
		if err := rows.Err(); err != nil {
			rows.Close()
			t.Fatalf("iterate %s: %v", table, err)
		}
		rows.Close()
	}
	expectedCounts := map[string]int{
		"users": 2, "storage_objects": 2 + rehearsalSampleSize, "sources": 2,
		"document_sample_generations": 1, "documents": rehearsalSampleSize,
		"document_sample_memberships": rehearsalSampleSize, "contract_spec_artifacts": 2,
		"review_campaigns": 1, "document_reviews": rehearsalSampleSize, "releases": 1,
		"release_sources": 1, "release_source_contract_snapshots": 1, "background_jobs": 1,
	}
	for table, expected := range expectedCounts {
		if got := len(fixture.Tables[table]); got != expected {
			t.Fatalf("fixture table %s: expected %d rows, got %d", table, expected, got)
		}
	}

	if os.Getenv("DERLEM_UPDATE_GOLDEN") == "1" {
		if err := os.MkdirAll(filepath.Dir(rehearsalFixturePath), 0o755); err != nil {
			t.Fatalf("create fixture directory: %v", err)
		}
		if err := os.WriteFile(rehearsalFixturePath, rehearsalEncodeFixture(t, fixture), 0o644); err != nil {
			t.Fatalf("write fixture: %v", err)
		}
		t.Logf("fixture written: %s", rehearsalFixturePath)
		return
	}

	// Sapma denetimi: kayıt defterinden gelen anlık görüntü sütunları ve dilim
	// kimliği, git'teki fixture ile aynı olmalı. Kimlikler her koşuda değişir.
	committedBytes, err := os.ReadFile(rehearsalFixturePath)
	if err != nil {
		t.Fatalf("read committed fixture (generate it with DERLEM_UPDATE_GOLDEN=1): %v", err)
	}
	var committed rehearsalFixture
	if err := json.Unmarshal(committedBytes, &committed); err != nil {
		t.Fatalf("parse committed fixture: %v", err)
	}
	if committed.SchemaVersion != rehearsalFixtureSchema {
		t.Fatalf("committed fixture schema %q != %q", committed.SchemaVersion, rehearsalFixtureSchema)
	}
	if committed.Slice.Candidate != candidate || committed.Slice.Holdout != holdout {
		t.Fatalf("slice identity drifted from the committed fixture (regenerate with DERLEM_UPDATE_GOLDEN=1):\ncommitted=%+v\nfresh=%+v",
			committed.Slice, fixture.Slice)
	}
	if len(committed.Tables["release_source_contract_snapshots"]) != 1 {
		t.Fatalf("committed fixture must hold exactly one contract snapshot row")
	}
	var committedSnapshot, freshSnapshot map[string]any
	if err := json.Unmarshal(committed.Tables["release_source_contract_snapshots"][0], &committedSnapshot); err != nil {
		t.Fatalf("parse committed snapshot: %v", err)
	}
	if err := json.Unmarshal(fixture.Tables["release_source_contract_snapshots"][0], &freshSnapshot); err != nil {
		t.Fatalf("parse fresh snapshot: %v", err)
	}
	for _, key := range rehearsalStableSnapshotKeys {
		if !reflect.DeepEqual(committedSnapshot[key], freshSnapshot[key]) {
			t.Fatalf("contract registry drifted from the committed fixture at %s: committed=%v fresh=%v "+
				"(regenerate with DERLEM_UPDATE_GOLDEN=1 and rerun the Python half)",
				key, committedSnapshot[key], freshSnapshot[key])
		}
	}
	t.Logf("committed fixture verified against fresh snapshot (%d stable keys)", len(rehearsalStableSnapshotKeys))
}

func rehearsalInsertUser(t *testing.T, ctx context.Context, pool *pgxpool.Pool, email, name string) string {
	t.Helper()
	var id string
	if err := pool.QueryRow(ctx, `
		INSERT INTO users(email, password_hash, display_name)
		VALUES ($1, 'test', $2)
		RETURNING id::text
	`, email, name).Scan(&id); err != nil {
		t.Fatalf("insert user %s: %v", email, err)
	}
	return id
}

func rehearsalStorageKey(sha string) string {
	return "objects/sha256/" + sha[:2] + "/" + sha[2:4] + "/" + sha
}

// rehearsalIngestObject, dosyayı worker'ın CAS yerleşimiyle (objects/sha256/
// aa/bb/<sha>) geçici depoya kopyalar; SHA-256, bayt ve satır sayısını döndürür.
func rehearsalIngestObject(t *testing.T, storeRoot, path string) rehearsalSliceObject {
	t.Helper()
	source, err := os.Open(path)
	if err != nil {
		t.Fatalf("open %s: %v", path, err)
	}
	defer source.Close()
	tempDir := filepath.Join(storeRoot, ".tmp")
	if err := os.MkdirAll(tempDir, 0o755); err != nil {
		t.Fatalf("create temp dir: %v", err)
	}
	temp, err := os.CreateTemp(tempDir, "ingest-")
	if err != nil {
		t.Fatalf("create temp object: %v", err)
	}
	tempName := temp.Name()
	hasher := sha256.New()
	var byteSize, lineCount int64
	var lastByte byte
	buffer := make([]byte, 1<<20)
	for {
		n, readErr := source.Read(buffer)
		if n > 0 {
			chunk := buffer[:n]
			hasher.Write(chunk)
			if _, err := temp.Write(chunk); err != nil {
				t.Fatalf("write temp object: %v", err)
			}
			byteSize += int64(n)
			lineCount += int64(bytes.Count(chunk, []byte{'\n'}))
			lastByte = chunk[n-1]
		}
		if readErr == io.EOF {
			break
		}
		if readErr != nil {
			t.Fatalf("read %s: %v", path, readErr)
		}
	}
	if byteSize > 0 && lastByte != '\n' {
		lineCount++
	}
	if err := temp.Close(); err != nil {
		t.Fatalf("close temp object: %v", err)
	}
	sha := hex.EncodeToString(hasher.Sum(nil))
	key := rehearsalStorageKey(sha)
	target := filepath.Join(storeRoot, filepath.FromSlash(key))
	if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
		t.Fatalf("create object dir: %v", err)
	}
	if err := os.Rename(tempName, target); err != nil {
		t.Fatalf("publish object: %v", err)
	}
	return rehearsalSliceObject{
		File: filepath.Base(path), SHA256: sha, StorageKey: key,
		ByteSize: byteSize, LineCount: lineCount,
	}
}

// rehearsalSampleLines, 1'den başlayan sıra numaralarıyla lineCount/size adımlı
// deterministik bir örnek seçer ve satır metnini (kırpılmış) döndürür.
func rehearsalSampleLines(t *testing.T, path string, lineCount int64, size int) []rehearsalSampledLine {
	t.Helper()
	if lineCount < int64(size) {
		t.Fatalf("slice has %d lines, fewer than the %d-document sample", lineCount, size)
	}
	stride := lineCount / int64(size)
	wanted := make(map[int64]struct{}, size)
	for index := 0; index < size; index++ {
		wanted[1+int64(index)*stride] = struct{}{}
	}
	file, err := os.Open(path)
	if err != nil {
		t.Fatalf("open %s: %v", path, err)
	}
	defer file.Close()
	scanner := bufio.NewScanner(file)
	scanner.Buffer(make([]byte, 1<<20), 8<<20)
	var ordinal int64
	sampled := make([]rehearsalSampledLine, 0, size)
	for scanner.Scan() {
		ordinal++
		if _, ok := wanted[ordinal]; !ok {
			continue
		}
		text := strings.TrimSpace(scanner.Text())
		if text == "" {
			t.Fatalf("sampled line %d is empty; the slice must not contain blank lines", ordinal)
		}
		sampled = append(sampled, rehearsalSampledLine{Ordinal: ordinal, Text: text})
	}
	if err := scanner.Err(); err != nil {
		t.Fatalf("scan %s: %v", path, err)
	}
	if len(sampled) != size {
		t.Fatalf("sampled %d lines, expected %d", len(sampled), size)
	}
	return sampled
}

func rehearsalPreview(text string) string {
	if utf8.RuneCountInString(text) <= rehearsalPreviewRunes {
		return text
	}
	runes := []rune(text)
	return string(runes[:rehearsalPreviewRunes])
}

// rehearsalEncodeFixture, başlığı girintili, tablo satırlarını satır başına bir
// kayıt olarak yazar: dosya git'te okunur kalır ve gereksiz büyümez.
func rehearsalEncodeFixture(t *testing.T, fixture rehearsalFixture) []byte {
	t.Helper()
	header, err := json.MarshalIndent(fixture.rehearsalFixtureHeader, "", "  ")
	if err != nil {
		t.Fatalf("encode fixture header: %v", err)
	}
	var out bytes.Buffer
	out.Write(bytes.TrimSuffix(bytes.TrimSpace(header), []byte("}")))
	out.WriteString(",\n  \"tables\": {\n")
	for index, table := range fixture.TableOrder {
		fmt.Fprintf(&out, "    %q: [\n", table)
		rows := fixture.Tables[table]
		for rowIndex, row := range rows {
			out.WriteString("      ")
			out.Write(row)
			if rowIndex < len(rows)-1 {
				out.WriteString(",")
			}
			out.WriteString("\n")
		}
		out.WriteString("    ]")
		if index < len(fixture.TableOrder)-1 {
			out.WriteString(",")
		}
		out.WriteString("\n")
	}
	out.WriteString("  }\n}\n")
	return out.Bytes()
}
