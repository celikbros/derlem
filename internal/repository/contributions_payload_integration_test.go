package repository_test

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
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

// TestContributionPayloadRoundTripAndCanonicalBundles, TASK-002 S3–S4'ün depo
// katmanını gerçek PostgreSQL üzerinde doğrular: payload ve köken saklanıp geri
// okunur, audit ayrıntısına içerik sızmaz, ve demet düzeltme çiftini ve model
// kökenli soru-cevabı hiçbir alanı kaybetmeden kanonik kayıt olarak yazar.
func TestContributionPayloadRoundTripAndCanonicalBundles(t *testing.T) {
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
	const rawMarker = "HAM-ICERIK-S4"

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
		editPair.DataOrigin != "human" || editPair.ModelID != nil {
		t.Fatalf("edit pair did not round-trip: payload=%v origin=%q model_id=%v",
			editPair.Payload, editPair.DataOrigin, editPair.ModelID)
	}

	hybrid, err := repo.Submit(ctx, contributorID, domain.SubmitContributionInput{
		TaskType: "qa_pair", Domain: "fizik",
		Prompt: "Yerçekimi ivmesi kaçtır?", Body: "Yaklaşık 9,81 m/s².",
		DataOrigin: "hybrid", ModelID: "model-x", AcceptTerms: true,
	})
	if err != nil {
		t.Fatalf("submit hybrid qa pair: %v", err)
	}
	human, err := repo.Submit(ctx, contributorID, domain.SubmitContributionInput{
		TaskType: "qa_pair", Domain: "fizik",
		Prompt: "Ses boşlukta yayılır mı?", Body: "Hayır; ses yayılmak için ortam ister.",
		AcceptTerms: true,
	})
	if err != nil {
		t.Fatalf("submit human qa pair: %v", err)
	}

	pending, err := repo.ListPending(ctx)
	if err != nil {
		t.Fatalf("list pending: %v", err)
	}
	var listedPayload map[string]string
	for _, item := range pending {
		if item.ID == editPair.ID {
			listedPayload = item.Payload
		}
	}
	if listedPayload["original_response"] != "Saniyede 300 km'dir. "+rawMarker {
		t.Fatalf("pending listing lost the edit pair payload: %v", listedPayload)
	}

	editResult, err := repo.Bundle(ctx, domain.BundleContributionsInput{
		TaskType: "response_edit_pair", Name: "duzeltme_demeti", Language: "tr", Domain: "fizik",
	}, t.TempDir(), managerID)
	if err != nil {
		t.Fatalf("bundle edit pairs: %v", err)
	}
	editRecords := stagedRecords(t, ctx, pool, editResult)
	if editResult.Count != 1 || len(editRecords) != 1 {
		t.Fatalf("expected 1 bundled edit pair, got count=%d records=%d", editResult.Count, len(editRecords))
	}
	if sourcePurpose(t, ctx, pool, editResult.SourceID) != "preference" {
		t.Fatal("edit pair bundle source must have content_purpose preference")
	}
	editRecord := editRecords[0]
	preference := editRecord["preference"].(map[string]any)
	rejected := preference["rejected"].([]any)[0].(map[string]any)
	chosen := preference["chosen"].([]any)[0].(map[string]any)
	if editRecord["record_type"] != "preference" || editRecord["sample_id"] != editPair.ID ||
		rejected["content"] != "Saniyede 300 km'dir. "+rawMarker ||
		chosen["content"] != "Boşlukta yaklaşık 299.792 km/s'dir." {
		t.Fatalf("edit pair lost a field in the bundle: %v", editRecord)
	}
	if editRecord["metadata"].(map[string]any)["edit_note"] != "Birim düzeltildi." {
		t.Fatalf("edit note lost in the bundle: %v", editRecord["metadata"])
	}

	qaResult, err := repo.Bundle(ctx, domain.BundleContributionsInput{
		TaskType: "qa_pair", Name: "fizik_soru_cevap_demeti", Language: "tr", Domain: "fizik",
	}, t.TempDir(), managerID)
	if err != nil {
		t.Fatalf("bundle qa pairs: %v", err)
	}
	qaRecords := stagedRecords(t, ctx, pool, qaResult)
	if qaResult.Count != 2 || len(qaRecords) != 2 {
		t.Fatalf("human and hybrid qa pairs must both be bundled, got count=%d records=%d", qaResult.Count, len(qaRecords))
	}
	originByID := map[string]map[string]any{}
	for _, record := range qaRecords {
		if record["record_type"] != "conversation" {
			t.Fatalf("qa pair must be a conversation record: %v", record)
		}
		originByID[record["sample_id"].(string)] = record["metadata"].(map[string]any)
	}
	if originByID[human.ID]["data_origin"] != "human" {
		t.Fatalf("human origin lost: %v", originByID[human.ID])
	}
	if originByID[hybrid.ID]["data_origin"] != "hybrid" || originByID[hybrid.ID]["model_id"] != "model-x" {
		t.Fatalf("hybrid origin or model id lost: %v", originByID[hybrid.ID])
	}

	var remaining int
	if err := pool.QueryRow(ctx, `SELECT count(*) FROM contributions WHERE status = 'submitted'`).Scan(&remaining); err != nil {
		t.Fatalf("count remaining: %v", err)
	}
	if remaining != 0 {
		t.Fatalf("every contribution must be bundled, %d still submitted", remaining)
	}

	var auditText string
	if err := pool.QueryRow(ctx, `
		SELECT COALESCE(string_agg(details::text, E'\n'), '')
		FROM audit_events WHERE action IN ('contribution.submitted', 'contributions.bundled', 'source.created')
	`).Scan(&auditText); err != nil {
		t.Fatalf("read audit: %v", err)
	}
	if strings.Contains(auditText, rawMarker) || strings.Contains(auditText, "Işık hızı") {
		t.Fatalf("audit details leaked contribution content: %s", auditText)
	}
	if !strings.Contains(auditText, `"data_origin": "hybrid"`) || !strings.Contains(auditText, `"model_id": "model-x"`) {
		t.Fatalf("submit audit details must record origin and model id: %s", auditText)
	}
	for _, record := range append(editRecords, qaRecords...) {
		if strings.Contains(fmt.Sprint(record), contributorID) {
			t.Fatal("contributor identity must never be written into the bundle file")
		}
	}
}

func stagedRecords(t *testing.T, ctx context.Context, pool *pgxpool.Pool, result domain.ContributionBundleResult) []map[string]any {
	t.Helper()
	var stagedPath string
	if err := pool.QueryRow(ctx, `
		SELECT payload->>'staged_path' FROM background_jobs WHERE id = $1
	`, result.JobID).Scan(&stagedPath); err != nil {
		t.Fatalf("read staged path: %v", err)
	}
	content, err := os.ReadFile(stagedPath)
	if err != nil {
		t.Fatalf("read staged bundle: %v", err)
	}
	records := make([]map[string]any, 0)
	for _, line := range strings.Split(strings.TrimRight(string(content), "\n"), "\n") {
		var record map[string]any
		if err := json.Unmarshal([]byte(line), &record); err != nil {
			t.Fatalf("staged line is not JSON: %v", err)
		}
		records = append(records, record)
	}
	return records
}

func sourcePurpose(t *testing.T, ctx context.Context, pool *pgxpool.Pool, sourceID string) string {
	t.Helper()
	var purpose string
	if err := pool.QueryRow(ctx, `SELECT content_purpose FROM sources WHERE id = $1`, sourceID).Scan(&purpose); err != nil {
		t.Fatalf("read source purpose: %v", err)
	}
	return purpose
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
