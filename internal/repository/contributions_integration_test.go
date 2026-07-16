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

// TestContributionLifecycleBundlesPoolIntoSource, katkı kuyruğunun tam yaşam
// döngüsünü gerçek PostgreSQL üzerinde doğrular: gönder -> listele -> geri
// çek -> demetle -> kaynak + ingest job'u + audit.
func TestContributionLifecycleBundlesPoolIntoSource(t *testing.T) {
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

	schemaName := fmt.Sprintf("derlem_contrib_test_%d", time.Now().UnixNano())
	schemaIdentifier := pgx.Identifier{schemaName}.Sanitize()
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
	if err := database.Migrate(ctx, pool); err != nil {
		t.Fatalf("migrate isolated schema: %v", err)
	}

	var contributorID, managerID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO users(email, password_hash, display_name)
		VALUES ('katkici@example.test', 'test', 'Katkıcı Kişi')
		RETURNING id::text
	`).Scan(&contributorID); err != nil {
		t.Fatalf("insert contributor: %v", err)
	}
	if err := pool.QueryRow(ctx, `
		INSERT INTO users(email, password_hash, display_name)
		VALUES ('yonetici@example.test', 'test', 'Veri Yöneticisi')
		RETURNING id::text
	`).Scan(&managerID); err != nil {
		t.Fatalf("insert manager: %v", err)
	}

	repo := repository.NewContributions(pool)

	first, err := repo.Submit(ctx, contributorID, domain.SubmitContributionInput{
		TaskType: "qa_pair", Domain: "fizik",
		Prompt: "Işık hızı nedir?", Body: "Yaklaşık 300.000 km/s'dir.",
		AcceptTerms: true,
	})
	if err != nil {
		t.Fatalf("submit first: %v", err)
	}
	if first.Status != "submitted" || first.TermsVersion != domain.ContributionTermsVersion {
		t.Fatalf("unexpected first contribution: %+v", first)
	}
	second, err := repo.Submit(ctx, contributorID, domain.SubmitContributionInput{
		TaskType: "qa_pair", Domain: "fizik",
		Prompt: "Yerçekimi ivmesi kaçtır?", Body: "Deniz seviyesinde yaklaşık 9,81 m/s²'dir.",
		AcceptTerms: true,
	})
	if err != nil {
		t.Fatalf("submit second: %v", err)
	}
	if _, err := repo.Submit(ctx, contributorID, domain.SubmitContributionInput{
		TaskType: "free_text", Domain: "genel",
		Body:        "Serbest metin katkısı: özgün bir paragraf.",
		AcceptTerms: true,
	}); err != nil {
		t.Fatalf("submit free text: %v", err)
	}

	mine, err := repo.ListMine(ctx, contributorID)
	if err != nil {
		t.Fatalf("list mine: %v", err)
	}
	if len(mine) != 3 {
		t.Fatalf("expected 3 own contributions, got %d", len(mine))
	}

	pending, err := repo.ListPending(ctx)
	if err != nil {
		t.Fatalf("list pending: %v", err)
	}
	if len(pending) != 3 {
		t.Fatalf("expected 3 pending contributions, got %d", len(pending))
	}
	if pending[0].ContributorName != "Katkıcı Kişi" {
		t.Fatalf("expected display name in pool, got %q", pending[0].ContributorName)
	}

	// Başkasının katkısı yokmuş gibi davranılır; kendi katkısı geri çekilir,
	// ikinci geri çekme çakışmadır.
	if err := repo.Withdraw(ctx, second.ID, managerID); !errors.Is(err, repository.ErrNotFound) {
		t.Fatalf("foreign withdraw error = %v, want ErrNotFound", err)
	}
	if err := repo.Withdraw(ctx, second.ID, contributorID); err != nil {
		t.Fatalf("withdraw: %v", err)
	}
	if err := repo.Withdraw(ctx, second.ID, contributorID); !errors.Is(err, repository.ErrConflict) {
		t.Fatalf("double withdraw error = %v, want ErrConflict", err)
	}

	stagingRoot := t.TempDir()
	result, err := repo.Bundle(ctx, domain.BundleContributionsInput{
		TaskType: "qa_pair", Name: "fizik_katki_demeti", Language: "tr", Domain: "fizik",
	}, stagingRoot, managerID)
	if err != nil {
		t.Fatalf("bundle qa_pair: %v", err)
	}
	if result.Count != 1 {
		t.Fatalf("expected 1 bundled contribution (one withdrawn), got %d", result.Count)
	}

	var purpose, rights, createdBy string
	if err := pool.QueryRow(ctx, `
		SELECT content_purpose, rights_status, created_by::text FROM sources WHERE id = $1
	`, result.SourceID).Scan(&purpose, &rights, &createdBy); err != nil {
		t.Fatalf("read bundled source: %v", err)
	}
	if purpose != "instruction" || rights != "cleared" || createdBy != managerID {
		t.Fatalf("unexpected source row: purpose=%q rights=%q created_by=%q", purpose, rights, createdBy)
	}

	var jobType, stagedPath string
	var uploadedBytes int64
	if err := pool.QueryRow(ctx, `
		SELECT job_type, payload->>'staged_path', (payload->>'uploaded_bytes')::bigint
		FROM background_jobs WHERE id = $1
	`, result.JobID).Scan(&jobType, &stagedPath, &uploadedBytes); err != nil {
		t.Fatalf("read ingest job: %v", err)
	}
	if jobType != "ingest_staged_file" {
		t.Fatalf("unexpected job type: %q", jobType)
	}
	content, err := os.ReadFile(stagedPath)
	if err != nil {
		t.Fatalf("staged file must exist after commit: %v", err)
	}
	if int64(len(content)) != uploadedBytes {
		t.Fatalf("uploaded_bytes=%d but file has %d bytes", uploadedBytes, len(content))
	}
	if !strings.Contains(string(content), "Soru: Işık hızı nedir?") {
		t.Fatalf("staged file lacks bundled QA text: %s", string(content))
	}
	if strings.Contains(string(content), contributorID) || strings.Contains(string(content), "katkici@example.test") {
		t.Fatalf("contributor identity must not leak into the bundle file")
	}

	var bundledStatus string
	var linkedSource *string
	if err := pool.QueryRow(ctx, `
		SELECT status, source_id::text FROM contributions WHERE id = $1
	`, first.ID).Scan(&bundledStatus, &linkedSource); err != nil {
		t.Fatalf("read bundled contribution: %v", err)
	}
	if bundledStatus != "bundled" || linkedSource == nil || *linkedSource != result.SourceID {
		t.Fatalf("contribution not linked to source: status=%q source=%v", bundledStatus, linkedSource)
	}

	// Demetlenmiş katkı geri çekilemez; boş havuz demetlenemez.
	if err := repo.Withdraw(ctx, first.ID, contributorID); !errors.Is(err, repository.ErrConflict) {
		t.Fatalf("withdraw bundled error = %v, want ErrConflict", err)
	}
	var gateError *repository.GateError
	if _, err := repo.Bundle(ctx, domain.BundleContributionsInput{
		TaskType: "qa_pair", Name: "bos_demet", Language: "tr", Domain: "fizik",
	}, stagingRoot, managerID); !errors.As(err, &gateError) {
		t.Fatalf("empty pool bundle error = %v, want GateError", err)
	}

	// Serbest metin havuzu pretrain kaynağına demetlenir.
	freeResult, err := repo.Bundle(ctx, domain.BundleContributionsInput{
		TaskType: "free_text", Name: "serbest_metin_demeti", Language: "tr", Domain: "genel",
	}, stagingRoot, managerID)
	if err != nil {
		t.Fatalf("bundle free_text: %v", err)
	}
	if err := pool.QueryRow(ctx, `
		SELECT content_purpose FROM sources WHERE id = $1
	`, freeResult.SourceID).Scan(&purpose); err != nil {
		t.Fatalf("read free text source: %v", err)
	}
	if purpose != "pretrain" {
		t.Fatalf("free_text bundle purpose = %q, want pretrain", purpose)
	}

	var auditCount int
	if err := pool.QueryRow(ctx, `
		SELECT count(*) FROM audit_events
		WHERE action IN ('contribution.submitted', 'contribution.withdrawn', 'contributions.bundled')
	`).Scan(&auditCount); err != nil {
		t.Fatalf("count audit events: %v", err)
	}
	if auditCount != 6 { // 3 submit + 1 withdraw + 2 bundle
		t.Fatalf("expected 6 contribution audit events, got %d", auditCount)
	}
}
