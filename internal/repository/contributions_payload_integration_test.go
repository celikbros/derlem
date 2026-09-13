package repository_test

import (
	"context"
	"errors"
	"fmt"
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

// TestContributionPayloadRoundTripAndBundleGuards, TASK-002 S3'ün depo katmanını
// gerçek PostgreSQL üzerinde doğrular: payload ve köken saklanıp geri okunur,
// audit ayrıntısına içerik sızmaz, ve kanonik yayın (S4) gelene kadar hiçbir
// katkı payload'ı ya da kökeni kaybedilerek demetlenemez.
func TestContributionPayloadRoundTripAndBundleGuards(t *testing.T) {
	ctx, pool := newContributionPayloadTestPool(t)

	var contributorID, managerID string
	for _, user := range []struct {
		email, name string
		target      *string
	}{
		{"payload-katkici@example.test", "Payload Katkıcı", &contributorID},
		{"payload-yonetici@example.test", "Payload Yönetici", &managerID},
	} {
		if err := pool.QueryRow(ctx, `
			INSERT INTO users(email, password_hash, display_name)
			VALUES ($1, 'test', $2)
			RETURNING id::text
		`, user.email, user.name).Scan(user.target); err != nil {
			t.Fatalf("insert user %s: %v", user.email, err)
		}
	}

	repo := repository.NewContributions(pool)
	const rawMarker = "HAM-ICERIK-S3"

	editPair, err := repo.Submit(ctx, contributorID, domain.SubmitContributionInput{
		TaskType: "response_edit_pair", Domain: "fizik",
		Prompt: "Işık hızı nedir?", Body: "Boşlukta yaklaşık 299.792 km/s'dir.",
		Payload: map[string]string{
			"original_response": "Saniyede 300 km'dir. " + rawMarker,
			"edit_note":         "Birim düzeltildi.",
		},
		AcceptTerms: true,
	})
	if err != nil {
		t.Fatalf("submit edit pair: %v", err)
	}
	if editPair.Payload["original_response"] != "Saniyede 300 km'dir. "+rawMarker ||
		editPair.Payload["edit_note"] != "Birim düzeltildi." {
		t.Fatalf("payload did not round-trip: %+v", editPair.Payload)
	}
	if editPair.DataOrigin != "human" || editPair.ModelID != nil {
		t.Fatalf("origin defaults wrong: origin=%q model_id=%v", editPair.DataOrigin, editPair.ModelID)
	}

	hybrid, err := repo.Submit(ctx, contributorID, domain.SubmitContributionInput{
		TaskType: "qa_pair", Domain: "fizik",
		Prompt: "Yerçekimi ivmesi kaçtır?", Body: "Yaklaşık 9,81 m/s².",
		DataOrigin: "hybrid", ModelID: "model-x", AcceptTerms: true,
	})
	if err != nil {
		t.Fatalf("submit hybrid qa pair: %v", err)
	}
	if hybrid.ModelID == nil || *hybrid.ModelID != "model-x" || len(hybrid.Payload) != 0 {
		t.Fatalf("hybrid qa pair stored wrongly: model_id=%v payload=%v", hybrid.ModelID, hybrid.Payload)
	}

	human, err := repo.Submit(ctx, contributorID, domain.SubmitContributionInput{
		TaskType: "qa_pair", Domain: "fizik",
		Prompt: "Ses boşlukta yayılır mı?", Body: "Hayır; ses yayılmak için ortam ister.",
		AcceptTerms: true,
	})
	if err != nil {
		t.Fatalf("submit human qa pair: %v", err)
	}

	mine, err := repo.ListMine(ctx, contributorID)
	if err != nil {
		t.Fatalf("list mine: %v", err)
	}
	pending, err := repo.ListPending(ctx)
	if err != nil {
		t.Fatalf("list pending: %v", err)
	}
	for label, payloads := range map[string][]map[string]string{
		"mine":    payloadsByID(mine, editPair.ID),
		"pending": pendingPayloadsByID(pending, editPair.ID),
	} {
		if len(payloads) != 1 || payloads[0]["original_response"] != "Saniyede 300 km'dir. "+rawMarker {
			t.Fatalf("%s listing lost the edit pair payload: %v", label, payloads)
		}
	}

	// Payload'lı tip bugünkü demet satırına sığmaz: açıkça reddedilmeli.
	var gateError *repository.GateError
	if _, err := repo.Bundle(ctx, domain.BundleContributionsInput{
		TaskType: "response_edit_pair", Name: "duzeltme_demeti", Language: "tr", Domain: "fizik",
	}, t.TempDir(), managerID); !errors.As(err, &gateError) {
		t.Fatalf("bundling response_edit_pair must be refused with a GateError, got %v", err)
	}

	// qa_pair demeti yalnız insan kökenli katkıyı alır; karma kökenli havuzda kalır.
	result, err := repo.Bundle(ctx, domain.BundleContributionsInput{
		TaskType: "qa_pair", Name: "fizik_insan_demeti", Language: "tr", Domain: "fizik",
	}, t.TempDir(), managerID)
	if err != nil {
		t.Fatalf("bundle human qa pairs: %v", err)
	}
	if result.Count != 1 {
		t.Fatalf("expected only the human qa pair bundled, got %d", result.Count)
	}
	for id, want := range map[string]string{
		human.ID:    "bundled",
		hybrid.ID:   "submitted",
		editPair.ID: "submitted",
	} {
		var status string
		if err := pool.QueryRow(ctx, `SELECT status FROM contributions WHERE id = $1`, id).Scan(&status); err != nil {
			t.Fatalf("read status %s: %v", id, err)
		}
		if status != want {
			t.Fatalf("contribution %s status = %q, want %q", id, status, want)
		}
	}

	var auditText string
	if err := pool.QueryRow(ctx, `
		SELECT COALESCE(string_agg(details::text, E'\n'), '')
		FROM audit_events WHERE action = 'contribution.submitted'
	`).Scan(&auditText); err != nil {
		t.Fatalf("read submit audit: %v", err)
	}
	if strings.Contains(auditText, rawMarker) || strings.Contains(auditText, "Işık hızı") {
		t.Fatalf("submit audit details leaked contribution content: %s", auditText)
	}
	if !strings.Contains(auditText, `"data_origin": "hybrid"`) || !strings.Contains(auditText, `"model_id": "model-x"`) {
		t.Fatalf("submit audit details must record origin and model id: %s", auditText)
	}
}

func payloadsByID(items []domain.Contribution, id string) []map[string]string {
	payloads := make([]map[string]string, 0)
	for _, item := range items {
		if item.ID == id {
			payloads = append(payloads, item.Payload)
		}
	}
	return payloads
}

func pendingPayloadsByID(items []domain.PendingContribution, id string) []map[string]string {
	payloads := make([]map[string]string, 0)
	for _, item := range items {
		if item.ID == id {
			payloads = append(payloads, item.Payload)
		}
	}
	return payloads
}

func newContributionPayloadTestPool(t *testing.T) (context.Context, *pgxpool.Pool) {
	t.Helper()
	databaseURL := testdb.URL(t)

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	t.Cleanup(cancel)
	adminPool, err := pgxpool.New(ctx, databaseURL)
	if err != nil {
		t.Fatalf("open admin pool: %v", err)
	}
	t.Cleanup(adminPool.Close)

	schemaName := fmt.Sprintf("derlem_contrib_payload_test_%d", time.Now().UnixNano())
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
	return ctx, pool
}
