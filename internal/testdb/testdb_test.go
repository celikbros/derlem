package testdb

import (
	"context"
	"fmt"
	"slices"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
)

func TestRequireScratchDatabaseAcceptsTestSuffix(t *testing.T) {
	for _, raw := range []string{
		"postgres://derlem:derlem@localhost:5432/derlem_test?sslmode=disable",
		"postgresql://u:p@localhost/derlem_ci_test",
		"host=localhost dbname=derlem_worker_test user=u password=p",
	} {
		if err := RequireScratchDatabase(raw); err != nil {
			t.Errorf("%q: unexpected error: %v", raw, err)
		}
	}
}

func TestRequireScratchDatabaseRejectsWorkingDatabase(t *testing.T) {
	for _, raw := range []string{
		"postgres://derlem:derlem@localhost:5432/derlem?sslmode=disable",
		"postgresql://u:p@localhost/derlem_production",
		"host=localhost dbname=derlem user=u",
	} {
		err := RequireScratchDatabase(raw)
		if err == nil {
			t.Errorf("%q: expected rejection, got nil", raw)
			continue
		}
		if !strings.Contains(err.Error(), "_test") {
			t.Errorf("%q: error must name the rule, got: %v", raw, err)
		}
	}
}

// URL'nin kendisi ortam değişkenine bağlı; ortam yokken t.Fatal çağırdığı
// için burada yalnız "explicit skip" dalı sınanır.
func TestURLSkipsOnlyWhenAskedTo(t *testing.T) {
	t.Setenv(EnvVar, "")
	t.Setenv(SkipEnvVar, "1")
	var skipped bool
	t.Run("explicit skip", func(t *testing.T) {
		t.Cleanup(func() { skipped = t.Skipped() })
		_ = URL(t)
	})
	if !skipped {
		t.Fatal("URL must skip (not fail) when DERLEM_SKIP_DB_TESTS is set")
	}
}

func TestSchemaCreatedAtParsesOnlyTimestampedTestSchemas(t *testing.T) {
	// 2026-08-21'de çalışma veritabanına sızan şemanın gerçek adı.
	createdAt, ok := SchemaCreatedAt("derlem_claim_test_1787335360053578500")
	if !ok || createdAt.UTC().Format(time.RFC3339) != "2026-08-21T18:02:40Z" {
		t.Fatalf("go-style name: got %v, ok=%v", createdAt.UTC(), ok)
	}
	if _, ok := SchemaCreatedAt("derlem_pii_worker_test_1787335360053578500_deadbeef"); !ok {
		t.Fatal("worker-style name with an 8-hex suffix must parse")
	}
	for _, name := range []string{
		"public",
		"pg_catalog",
		// Eski worker adları zaman taşımaz: yaşları kanıtlanamaz, asla süpürülmez.
		"derlem_worker_test_0123456789abcdef0123456789abcdef",
		"derlem_claim_test_123",
		"derlem_claim_test_1787335360053578500_xyz",
		"derlem_claim_test_1787335360053578500; DROP SCHEMA public",
	} {
		if _, ok := SchemaCreatedAt(name); ok {
			t.Errorf("%q must not be treated as a timestamped test schema", name)
		}
	}
}

// Süpürme testlerinin "eski" şeması 11 dakika önce oluşturulmuş gibi adlandırılır
// ve 10 dakika eşiğiyle süpürülür. go test ./... paketleri paralel koşar ve her
// paketin TestMain'i 1 saat eşiğiyle süpürür; bu yaş onların eşiğinin altında
// kaldığı için başka bir paket bu testin şemasını ondan önce silemez.
const sweepTestThreshold = 10 * time.Minute

func sweepTestSchemaName(label string, age time.Duration) string {
	return fmt.Sprintf("derlem_%s_test_%d", label, time.Now().Add(-age).UnixNano())
}

func schemaExists(t *testing.T, ctx context.Context, conn *pgx.Conn, name string) bool {
	t.Helper()
	var exists bool
	if err := conn.QueryRow(ctx, `SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = $1)`, name).Scan(&exists); err != nil {
		t.Fatalf("check schema %s: %v", name, err)
	}
	return exists
}

func connectForSweepTest(t *testing.T) (context.Context, *pgx.Conn, string) {
	t.Helper()
	databaseURL := URL(t)
	ctx, cancel := context.WithTimeout(context.Background(), time.Minute)
	t.Cleanup(cancel)
	conn, err := pgx.Connect(ctx, databaseURL)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	t.Cleanup(func() { conn.Close(context.Background()) })
	return ctx, conn, databaseURL
}

func createSchemasForSweepTest(t *testing.T, ctx context.Context, conn *pgx.Conn, names ...string) {
	t.Helper()
	for _, name := range names {
		identifier := pgx.Identifier{name}.Sanitize()
		if _, err := conn.Exec(ctx, "CREATE SCHEMA "+identifier); err != nil {
			t.Fatalf("create schema %s: %v", name, err)
		}
		t.Cleanup(func() {
			if _, err := conn.Exec(context.Background(), "DROP SCHEMA IF EXISTS "+identifier+" CASCADE"); err != nil {
				t.Errorf("cleanup schema %s: %v", name, err)
			}
		})
	}
}

func TestSweepLeakedSchemasDropsOnlyProvablyOldSchemas(t *testing.T) {
	ctx, conn, databaseURL := connectForSweepTest(t)
	old := sweepTestSchemaName("sweeper_old", 11*time.Minute)
	fresh := sweepTestSchemaName("sweeper_fresh", 0)
	createSchemasForSweepTest(t, ctx, conn, old, fresh)

	result, err := SweepLeakedSchemas(ctx, databaseURL, sweepTestThreshold)
	if err != nil {
		t.Fatalf("sweep: %v", err)
	}
	if !slices.Contains(result.Dropped, old) {
		t.Fatalf("old schema %s was not reported dropped: %+v", old, result)
	}
	if slices.Contains(result.Dropped, fresh) {
		t.Fatalf("fresh schema %s must not be dropped: %+v", fresh, result)
	}
	if schemaExists(t, ctx, conn, old) {
		t.Fatalf("old schema %s still exists", old)
	}
	if !schemaExists(t, ctx, conn, fresh) {
		t.Fatalf("fresh schema %s was removed", fresh)
	}
}

// Sızmış şemada eklenti varsa CASCADE onu veritabanının tamamından siler;
// süpürücü böyle bir şemayı düşürmek yerine raporlamalı.
func TestSweepLeakedSchemasNeverDropsASchemaHoldingAnExtension(t *testing.T) {
	ctx, conn, databaseURL := connectForSweepTest(t)
	holder := sweepTestSchemaName("sweeper_extension", 11*time.Minute)
	createSchemasForSweepTest(t, ctx, conn, holder)
	if _, err := conn.Exec(ctx, "CREATE EXTENSION citext WITH SCHEMA "+pgx.Identifier{holder}.Sanitize()); err != nil {
		t.Fatalf(
			"install citext into %s: %v (this test needs the contrib extension citext available and not "+
				"already installed in the scratch database)", holder, err)
	}
	t.Cleanup(func() {
		if _, err := conn.Exec(context.Background(), "DROP EXTENSION IF EXISTS citext"); err != nil {
			t.Errorf("cleanup citext: %v", err)
		}
	})

	result, err := SweepLeakedSchemas(ctx, databaseURL, sweepTestThreshold)
	if err != nil {
		t.Fatalf("sweep: %v", err)
	}
	if slices.Contains(result.Dropped, holder) {
		t.Fatalf("schema %s holding an extension was dropped: %+v", holder, result)
	}
	if !slices.Contains(result.Skipped, holder) {
		t.Fatalf("schema %s holding an extension was not reported as skipped: %+v", holder, result)
	}
	if !schemaExists(t, ctx, conn, holder) {
		t.Fatalf("schema %s holding an extension no longer exists", holder)
	}
}
