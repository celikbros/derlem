package repository_test

import (
	"context"
	"errors"
	"fmt"
	"slices"
	"testing"
	"time"

	"github.com/celikbros/derlem/internal/database"
	"github.com/celikbros/derlem/internal/domain"
	"github.com/celikbros/derlem/internal/repository"
	"github.com/celikbros/derlem/internal/testdb"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// TASK-048: eşik ölçümden önce konur. Bu test DB katmanını (000030) ve
// repository kilidini birlikte sınar: eşik yalnız pretrain kaynakta, ilk
// inceleme izinden önce yazılır; sonrasında hem SetPretrainReviewThreshold hem
// doğrudan UPDATE reddedilir. Kapı fonksiyonu Go formülüyle aynı sonucu verir.
func TestPretrainReviewThresholdLocksOnceReviewStarts(t *testing.T) {
	databaseURL := testdb.URL(t)

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	t.Cleanup(cancel)
	adminPool, err := pgxpool.New(ctx, databaseURL)
	if err != nil {
		t.Fatalf("open admin pool: %v", err)
	}
	t.Cleanup(adminPool.Close)

	schemaName := fmt.Sprintf("derlem_review_threshold_test_%d", time.Now().UnixNano())
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
		VALUES ('threshold@example.test', 'test', 'Threshold Owner')
		RETURNING id::text
	`).Scan(&actorID); err != nil {
		t.Fatalf("insert actor: %v", err)
	}

	repo := repository.NewSources(pool)
	create := func(name, purpose string) domain.Source {
		t.Helper()
		source, err := repo.Create(ctx, domain.CreateSourceInput{
			Name: name, SourceType: "text_corpus", ContentPurpose: purpose,
			License: "internal", RightsStatus: "unknown", Language: "tr",
			Domain: "mixed", LineageRef: name + ".txt",
		}, actorID)
		if err != nil {
			t.Fatalf("create %s: %v", name, err)
		}
		return source
	}
	pretrain := create("threshold-pretrain", "pretrain")
	instruction := create("threshold-instruction", "instruction")
	if pretrain.PretrainReviewRejectThreshold != nil {
		t.Fatalf("new source has a threshold: %v", *pretrain.PretrainReviewRejectThreshold)
	}

	ten := 10.0
	updated, err := repo.SetPretrainReviewThreshold(ctx, pretrain.ID, &ten, actorID)
	if err != nil {
		t.Fatalf("set threshold before review: %v", err)
	}
	if updated.PretrainReviewRejectThreshold == nil || *updated.PretrainReviewRejectThreshold != 10 {
		t.Fatalf("threshold not stored: %#v", updated.PretrainReviewRejectThreshold)
	}

	var gate *repository.GateError
	if _, err := repo.SetPretrainReviewThreshold(ctx, instruction.ID, &ten, actorID); !errors.As(err, &gate) ||
		!slices.Contains(gate.Reasons, "content_purpose_not_pretrain") {
		t.Fatalf("instruction threshold error = %v", err)
	}
	if _, err := pool.Exec(ctx,
		"UPDATE sources SET pretrain_review_reject_threshold = 10 WHERE id = $1", instruction.ID,
	); err == nil {
		t.Fatal("check constraint accepted a threshold on an instruction source")
	}

	// İlk inceleme izi: kaynak düzeyi inceleme kaydı.
	if _, err := pool.Exec(ctx, `
		INSERT INTO reviews(source_id, reviewer_id, decision, reason, source_version, review_context)
		VALUES ($1, $2, 'rejected', 'threshold lock test', $3, '{}'::jsonb)
	`, pretrain.ID, actorID, updated.Version); err != nil {
		t.Fatalf("insert first review trace: %v", err)
	}
	twenty := 20.0
	if _, err := repo.SetPretrainReviewThreshold(ctx, pretrain.ID, &twenty, actorID); !errors.As(err, &gate) ||
		!slices.Contains(gate.Reasons, "pretrain_review_threshold_locked_review_started") {
		t.Fatalf("threshold change after review start error = %v", err)
	}
	if _, err := pool.Exec(ctx,
		"UPDATE sources SET pretrain_review_reject_threshold = 20 WHERE id = $1", pretrain.ID,
	); err == nil {
		t.Fatal("DB trigger accepted a threshold change after review started")
	}
	if _, err := pool.Exec(ctx,
		"UPDATE sources SET pretrain_review_reject_threshold = NULL WHERE id = $1", pretrain.ID,
	); err == nil {
		t.Fatal("DB trigger accepted clearing the threshold after review started")
	}

	gateCases := []struct {
		purpose   string
		threshold *float64
		approved  int64
		flagged   int64
		want      bool
	}{
		{"pretrain", &ten, 180, 20, true},
		{"pretrain", &ten, 179, 21, false},
		{"pretrain", nil, 180, 20, false},
		{"pretrain", nil, 200, 0, true},
		{"instruction", &ten, 199, 1, false},
		{"instruction", nil, 200, 0, true},
	}
	for _, c := range gateCases {
		var passed bool
		if err := pool.QueryRow(ctx,
			"SELECT source_document_review_gate_passes($1, $2::numeric, 200, $3 + $4, $3, $4)",
			c.purpose, c.threshold, c.approved, c.flagged,
		).Scan(&passed); err != nil {
			t.Fatalf("gate function: %v", err)
		}
		if passed != c.want {
			t.Fatalf("gate(%s, %v, %d/%d) = %v, want %v", c.purpose, c.threshold, c.flagged, 200, passed, c.want)
		}
	}
}
