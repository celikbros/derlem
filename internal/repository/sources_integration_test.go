package repository_test

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"strings"
	"testing"
	"time"

	"github.com/celikbros/derlem/internal/database"
	"github.com/celikbros/derlem/internal/domain"
	"github.com/celikbros/derlem/internal/repository"
	"github.com/celikbros/derlem/internal/testdb"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

func TestSourceCreatePersistsDerivedParentAndRejectsMissingParent(t *testing.T) {
	databaseURL := testdb.URL(t)

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	t.Cleanup(cancel)
	adminPool, err := pgxpool.New(ctx, databaseURL)
	if err != nil {
		t.Fatalf("open admin pool: %v", err)
	}
	t.Cleanup(adminPool.Close)

	schemaName := fmt.Sprintf("derlem_sources_test_%d", time.Now().UnixNano())
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
	if err := database.Migrate(ctx, pool); err != nil {
		t.Fatalf("migrate isolated schema: %v", err)
	}

	var actorID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO users(email, password_hash, display_name)
		VALUES ('lineage@example.test', 'test', 'Lineage Manager')
		RETURNING id::text
	`).Scan(&actorID); err != nil {
		t.Fatalf("insert actor: %v", err)
	}

	repo := repository.NewSources(pool)
	parent, err := repo.Create(ctx, domain.CreateSourceInput{
		Name: "raw-parent", SourceType: "text_corpus", ContentPurpose: "pretrain",
		License: "internal", RightsStatus: "unknown", Language: "tr",
		Domain: "mixed", LineageRef: "raw-parent.txt",
	}, actorID)
	if err != nil {
		t.Fatalf("create parent: %v", err)
	}

	child, err := repo.Create(ctx, domain.CreateSourceInput{
		Name: "clean-child", SourceType: "text_corpus", ContentPurpose: "pretrain",
		License: "internal", RightsStatus: "unknown", Language: "tr",
		Domain: "mixed", LineageRef: "clean-child.manifest.json",
		DerivedFromSourceID: &parent.ID,
	}, actorID)
	if err != nil {
		t.Fatalf("create child: %v", err)
	}
	if child.DerivedFromSourceID == nil || *child.DerivedFromSourceID != parent.ID {
		t.Fatalf("unexpected child parent: %#v", child.DerivedFromSourceID)
	}

	updated, err := repo.Update(ctx, child.ID, domain.UpdateSourceInput{
		Name: "clean-child-renamed", SourceType: child.SourceType,
		License: child.License, RightsStatus: child.RightsStatus,
		Language: child.Language, Domain: child.Domain,
		LineageRef: child.LineageRef, Version: child.Version,
	}, actorID)
	if err != nil {
		t.Fatalf("update child: %v", err)
	}
	if updated.DerivedFromSourceID == nil || *updated.DerivedFromSourceID != parent.ID {
		t.Fatalf("source update changed derived parent: %#v", updated.DerivedFromSourceID)
	}

	var auditedParentID *string
	if err := pool.QueryRow(ctx, `
		SELECT details->>'derived_from_source_id'
		FROM audit_events
		WHERE action = 'source.created' AND entity_id = $1
	`, child.ID).Scan(&auditedParentID); err != nil {
		t.Fatalf("read source creation audit: %v", err)
	}
	if auditedParentID == nil || *auditedParentID != parent.ID {
		t.Fatalf("unexpected audited parent: %#v", auditedParentID)
	}

	missingParentID := "00000000-0000-4000-8000-000000000999"
	_, err = repo.Create(ctx, domain.CreateSourceInput{
		Name: "orphan", SourceType: "text_corpus", ContentPurpose: "pretrain",
		License: "internal", RightsStatus: "unknown", Language: "tr",
		Domain: "mixed", LineageRef: "orphan.txt",
		DerivedFromSourceID: &missingParentID,
	}, actorID)
	if !errors.Is(err, repository.ErrNotFound) {
		t.Fatalf("missing parent error = %v, want ErrNotFound", err)
	}

	if _, err := pool.Exec(ctx, "DELETE FROM sources WHERE id = $1", parent.ID); err == nil {
		t.Fatal("expected ON DELETE RESTRICT to protect the derived parent")
	}
}

func TestQueueDistillationPinsImmutableProductionProvenanceBeforeJob(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	t.Cleanup(cancel)
	pool := newReleaseContractTestPool(t, ctx)

	var actorID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO users(email, password_hash, display_name)
		VALUES ('distillation-provenance@example.test', 'test', 'Distillation Provenance')
		RETURNING id::text
	`).Scan(&actorID); err != nil {
		t.Fatalf("insert actor: %v", err)
	}

	repo := repository.NewSources(pool)
	source, err := repo.Create(ctx, domain.CreateSourceInput{
		Name: "model-generated-source", SourceType: "jsonl",
		ContentPurpose: "instruction", License: "internal",
		RightsStatus: "unknown", Language: "tr", Domain: "general",
		LineageRef: "distillation-run",
	}, actorID)
	if err != nil {
		t.Fatalf("create source: %v", err)
	}
	if source.DataOrigin != "unknown" || source.ProductionRunID != nil {
		t.Fatalf("unexpected initial provenance: %+v", source)
	}

	input := repository.DistillationInput{
		Provider: "echo", Model: "echo-v1", SystemPrompt: "YalnÄ±z TÃ¼rkÃ§e yaz.",
		PromptTemplate: "{konu} hakkÄ±nda yaz.", Topics: []string{"fizik"},
		Count: 1, MaxTokens: 512, Temperature: 0.7, SourceName: "provenance-test",
	}
	jobID, err := repo.QueueDistillation(ctx, source.ID, input, actorID)
	if err != nil {
		t.Fatalf("queue distillation: %v", err)
	}

	updated, err := repo.Get(ctx, source.ID)
	if err != nil {
		t.Fatalf("get source: %v", err)
	}
	if updated.DataOrigin != "model" || updated.ProductionRunID == nil {
		t.Fatalf("distillation provenance was not finalized: %+v", updated)
	}

	var runKind, originKind, implementationKey, implementationDigest, configSHA256 string
	if err := pool.QueryRow(ctx, `
		SELECT run_kind, origin_kind, implementation_key,
			implementation_digest, config_sha256
		FROM production_runs
		WHERE id = $1
	`, *updated.ProductionRunID).Scan(
		&runKind, &originKind, &implementationKey,
		&implementationDigest, &configSHA256,
	); err != nil {
		t.Fatalf("read production run: %v", err)
	}
	if runKind != "model_generation" || originKind != "model" ||
		implementationKey != "derlem.worker.distill_source.v1" ||
		len(implementationDigest) != 64 || len(configSHA256) != 64 {
		t.Fatalf(
			"unexpected production run: kind=%s origin=%s key=%s implementation=%s config=%s",
			runKind, originKind, implementationKey, implementationDigest, configSHA256,
		)
	}

	var payloadSourceID, payloadRunID string
	if err := pool.QueryRow(ctx, `
		SELECT payload->>'source_id', payload->>'production_run_id'
		FROM background_jobs
		WHERE id = $1 AND job_type = 'distill_source'
	`, jobID).Scan(&payloadSourceID, &payloadRunID); err != nil {
		t.Fatalf("read distillation job: %v", err)
	}
	if payloadSourceID != source.ID || payloadRunID != *updated.ProductionRunID {
		t.Fatalf("job provenance mismatch: source=%s run=%s", payloadSourceID, payloadRunID)
	}

	var auditContainsOnlyEvidence bool
	if err := pool.QueryRow(ctx, `
		SELECT details - ARRAY[
			'job_id', 'production_run_id', 'config_sha256', 'implementation_digest'
		]::text[] = '{}'::jsonb
		FROM audit_events
		WHERE action = 'source.distillation_queued' AND entity_id = $1
	`, source.ID).Scan(&auditContainsOnlyEvidence); err != nil {
		t.Fatalf("read distillation audit: %v", err)
	}
	if !auditContainsOnlyEvidence {
		t.Fatal("distillation audit disclosed fields beyond IDs and hashes")
	}

	// Once provenance has been pinned to a production run, even a permanently
	// failed distillation must not fall back to an unrelated browser/server
	// upload carrying that run's identity.
	if _, err := pool.Exec(ctx, `
		UPDATE background_jobs
		SET status = 'failed', last_error = 'simulated terminal failure'
		WHERE id = $1
	`, jobID); err != nil {
		t.Fatalf("mark distillation failed: %v", err)
	}
	if _, err := repo.QueueStagedIngest(
		ctx, source.ID, `C:\\staging\\forged.txt`, "forged.txt", 7, actorID,
	); !errors.Is(err, repository.ErrConflict) {
		t.Fatalf("post-distillation staged ingest error = %v, want ErrConflict", err)
	}
	if _, err := repo.QueueLocalIngest(
		ctx, source.ID, `C:\\imports\\forged.txt`, actorID,
	); !errors.Is(err, repository.ErrConflict) {
		t.Fatalf("post-distillation local ingest error = %v, want ErrConflict", err)
	}

	if _, err := repo.QueueDistillation(ctx, source.ID, input, actorID); !errors.Is(err, repository.ErrConflict) {
		t.Fatalf("second distillation error = %v, want ErrConflict", err)
	}
	var runCount int
	if err := pool.QueryRow(ctx, `
		SELECT count(*) FROM production_runs WHERE created_by = $1
	`, actorID).Scan(&runCount); err != nil {
		t.Fatalf("count production runs: %v", err)
	}
	if runCount != 1 {
		t.Fatalf("production run count = %d, want 1", runCount)
	}
	if _, err := pool.Exec(ctx, `
		UPDATE production_runs SET config_sha256 = repeat('f', 64) WHERE id = $1
	`, *updated.ProductionRunID); err == nil {
		t.Fatal("production run unexpectedly allowed mutation")
	}
}

// Çoklu girdi soyu (000029): oluştururken yazılır, okunurken gelir, güncellemede
// nil dokunmaz / liste değiştirir; kendine referans ve var olmayan girdi reddedilir.
func TestSourceLineageInputsRoundTrip(t *testing.T) {
	databaseURL := testdb.URL(t)
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	t.Cleanup(cancel)
	adminPool, err := pgxpool.New(ctx, databaseURL)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	t.Cleanup(adminPool.Close)
	schemaName := fmt.Sprintf("derlem_lineage_inputs_test_%d", time.Now().UnixNano())
	schemaIdentifier := pgx.Identifier{schemaName}.Sanitize()
	if _, err := adminPool.Exec(ctx, "CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public"); err != nil {
		t.Fatalf("ensure pgcrypto: %v", err)
	}
	if _, err := adminPool.Exec(ctx, "CREATE SCHEMA "+schemaIdentifier); err != nil {
		t.Fatalf("create test schema: %v", err)
	}
	t.Cleanup(func() {
		cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), time.Minute)
		defer cleanupCancel()
		_, _ = adminPool.Exec(cleanupCtx, "DROP SCHEMA "+schemaIdentifier+" CASCADE")
	})
	config, err := pgxpool.ParseConfig(databaseURL)
	if err != nil {
		t.Fatalf("parse config: %v", err)
	}
	config.ConnConfig.RuntimeParams["search_path"] = schemaName + ",public"
	pool, err := pgxpool.NewWithConfig(ctx, config)
	if err != nil {
		t.Fatalf("connect schema pool: %v", err)
	}
	t.Cleanup(pool.Close)
	if err := database.Migrate(ctx, pool); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	var actorID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO users(email, password_hash, display_name)
		VALUES ('lineage-inputs@example.test', 'test', 'Lineage Inputs')
		RETURNING id::text
	`).Scan(&actorID); err != nil {
		t.Fatalf("insert actor: %v", err)
	}
	repo := repository.NewSources(pool)
	base := domain.CreateSourceInput{
		SourceType: "text_corpus", ContentPurpose: "pretrain", License: "unknown",
		RightsStatus: "unknown", Language: "tr", Domain: "mixed", LineageRef: "test",
	}
	create := func(name string, inputs ...string) domain.Source {
		input := base
		input.Name = name
		input.LineageInputSourceIDs = inputs
		source, err := repo.Create(ctx, input, actorID)
		if err != nil {
			t.Fatalf("create %s: %v", name, err)
		}
		return source
	}
	rawA := create("raw-a")
	rawB := create("raw-b")
	if len(rawA.LineageInputSourceIDs) != 0 {
		t.Fatalf("a source without inputs must report an empty list, got %#v", rawA.LineageInputSourceIDs)
	}

	parent := create("parent", rawB.ID, rawA.ID)
	want := []string{rawA.ID, rawB.ID}
	sort.Strings(want)
	if strings.Join(parent.LineageInputSourceIDs, ",") != strings.Join(want, ",") {
		t.Fatalf("inputs not persisted in sorted order: %#v", parent.LineageInputSourceIDs)
	}
	fetched, err := repo.Get(ctx, parent.ID)
	if err != nil {
		t.Fatalf("get parent: %v", err)
	}
	if strings.Join(fetched.LineageInputSourceIDs, ",") != strings.Join(want, ",") {
		t.Fatalf("inputs not read back: %#v", fetched.LineageInputSourceIDs)
	}

	update := domain.UpdateSourceInput{
		Name: parent.Name, SourceType: parent.SourceType, License: parent.License,
		RightsStatus: parent.RightsStatus, Language: parent.Language, Domain: parent.Domain,
		LineageRef: parent.LineageRef, Version: parent.Version,
	}
	untouched, err := repo.Update(ctx, parent.ID, update, actorID)
	if err != nil {
		t.Fatalf("update without inputs: %v", err)
	}
	if len(untouched.LineageInputSourceIDs) != 2 {
		t.Fatalf("nil inputs must leave the list untouched, got %#v", untouched.LineageInputSourceIDs)
	}
	update.Version = untouched.Version
	update.LineageInputSourceIDs = []string{rawA.ID}
	narrowed, err := repo.Update(ctx, parent.ID, update, actorID)
	if err != nil {
		t.Fatalf("update with inputs: %v", err)
	}
	if strings.Join(narrowed.LineageInputSourceIDs, ",") != rawA.ID {
		t.Fatalf("inputs not replaced: %#v", narrowed.LineageInputSourceIDs)
	}

	update.Version = narrowed.Version
	update.LineageInputSourceIDs = []string{parent.ID}
	if _, err := repo.Update(ctx, parent.ID, update, actorID); !errors.Is(err, repository.ErrSelfLineage) {
		t.Fatalf("self input must be rejected, got %v", err)
	}
	missing := base
	missing.Name = "orphan"
	missing.LineageInputSourceIDs = []string{"00000000-0000-4000-8000-000000000000"}
	if _, err := repo.Create(ctx, missing, actorID); !errors.Is(err, repository.ErrNotFound) {
		t.Fatalf("missing input must be rejected, got %v", err)
	}
}
