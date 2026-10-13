package repository_test

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"testing"
	"time"

	"github.com/celikbros/derlem/internal/database"
	"github.com/celikbros/derlem/internal/domain"
	"github.com/celikbros/derlem/internal/repository"
	"github.com/celikbros/derlem/internal/testdb"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

func TestQueueHFImportCreatesSourceAndJobAtomically(t *testing.T) {
	databaseURL := testdb.URL(t)

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	t.Cleanup(cancel)
	adminPool, err := pgxpool.New(ctx, databaseURL)
	if err != nil {
		t.Fatalf("open admin pool: %v", err)
	}
	t.Cleanup(adminPool.Close)

	schemaName := fmt.Sprintf("derlem_hfimport_test_%d", time.Now().UnixNano())
	schemaIdentifier := pgx.Identifier{schemaName}.Sanitize()
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
	if err := database.Migrate(ctx, pool); err != nil {
		t.Fatalf("migrate isolated schema: %v", err)
	}

	var actorID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO users(email, password_hash, display_name)
		VALUES ('hf-import@example.test', 'test', 'HF Import Admin')
		RETURNING id::text
	`).Scan(&actorID); err != nil {
		t.Fatalf("insert actor: %v", err)
	}

	repo := repository.NewSources(pool)
	evidence := "docs/haklar/hf-fineweb2-hq.md"
	note := "FineWeb2-HQ tur_Latn ilk alim"
	input := domain.CreateSourceInput{
		Name: "HF: epfml-fineweb2-hq", SourceType: "hf_dataset", ContentPurpose: "pretrain",
		License: "hf-card:pending", RightsStatus: "restricted", Language: "tr", Domain: "general",
		LicenseEvidenceRef: &evidence, LineageRef: "hf-import pending: adapter=epfml-fineweb2-hq.yaml",
	}
	adapterPath := "/srv/derlem/adapters/epfml-fineweb2-hq.yaml"
	source, jobID, err := repo.QueueHFImport(ctx, input, adapterPath, &note, actorID)
	if err != nil {
		t.Fatalf("queue hf import: %v", err)
	}
	if source.SourceType != "hf_dataset" || source.ObjectSHA256 != nil || source.ApprovalStatus != "source_registered" {
		t.Fatalf("unexpected source: %#v", source)
	}

	var jobType, status string
	var payload []byte
	if err := pool.QueryRow(ctx, `SELECT job_type, status, payload FROM background_jobs WHERE id = $1`, jobID).Scan(&jobType, &status, &payload); err != nil {
		t.Fatalf("load job: %v", err)
	}
	var decoded map[string]string
	if err := json.Unmarshal(payload, &decoded); err != nil {
		t.Fatal(err)
	}
	if jobType != "import_hf_dataset" || status != "queued" || decoded["source_id"] != source.ID ||
		decoded["adapter_path"] != adapterPath || decoded["lineage_note"] != note {
		t.Fatalf("unexpected job: type=%s status=%s payload=%v", jobType, status, decoded)
	}
	jobs, err := repo.ListJobs(ctx, source.ID, 10)
	if err != nil || len(jobs) != 1 || jobs[0].ID != jobID {
		t.Fatalf("job is not readable by source: %v %#v", err, jobs)
	}
	var audits int
	if err := pool.QueryRow(ctx, `
		SELECT count(*) FROM audit_events
		WHERE entity_id = $1 AND action IN ('source.created', 'source.ingest_queued')
	`, source.ID).Scan(&audits); err != nil || audits != 2 {
		t.Fatalf("audit events = %d (%v), want 2", audits, err)
	}

	if _, _, err := repo.QueueHFImport(ctx, input, adapterPath, nil, actorID); !errors.Is(err, repository.ErrConflict) {
		t.Fatalf("second active import err = %v, want ErrConflict", err)
	}
	var sources int
	if err := pool.QueryRow(ctx, `SELECT count(*) FROM sources WHERE source_type = 'hf_dataset'`).Scan(&sources); err != nil || sources != 1 {
		t.Fatalf("conflicting request left a source behind: %d (%v)", sources, err)
	}
}
