// Package testdb, veritabanına bağlı entegrasyon testlerinin bağlantı adresini
// tek yerden verir ve arkalarında kalan izole şemaları süpürür. Kuralları:
//
//  1. Adres yoksa test SESSİZCE ATLANMAZ. Ya açıkça atlanır
//     (DERLEM_SKIP_DB_TESTS=1) ya da kırmızı olur. 2026-09'da 29 Go testi aylarca
//     sessizce atlandı ve "go test ./..." yeşil derken demetleme, freeze kapısı
//     ve migration testleri hiç çalışmıyordu.
//  2. Adres, adı _test ile bitmeyen bir veritabanına işaret ediyorsa hiçbir test
//     ona dokunmadan durur. Testler izole şema açıp CASCADE ile düşürür;
//     2026-08-21'de bu adres çalışma veritabanına yöneltilmiş ve iki test şeması
//     orada kalmıştı.
//  3. Süreci öldürülen bir koşunun (Ctrl+C, go test -timeout) bıraktığı izole
//     şemalar her paketin TestMain'inde süpürülür. Şema adı oluşturulma zamanını
//     taşır; yalnız adındaki zamana göre kanıtlanabilir biçimde eski olanlar
//     düşürülür, eşzamanlı koşan başka bir test sürecinin canlı şemasına
//     dokunulmaz. İçinde eklenti bulunan şema düşürülmez: CASCADE eklentiyi
//     veritabanının tamamından siler (pgcrypto yarışı, 2026-09).
package testdb

import (
	"context"
	"fmt"
	"os"
	"regexp"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
)

const (
	// EnvVar, entegrasyon testlerinin kullandığı veritabanı adresi.
	EnvVar = "DERLEM_TEST_DATABASE_URL"
	// SkipEnvVar, PostgreSQL olmayan makinede veritabanı testlerini BİLEREK
	// atlamak için; sessiz atlamanın tek meşru karşılığı.
	SkipEnvVar = "DERLEM_SKIP_DB_TESTS"
	// LeakedSchemaAge, bu yaştan eski test şeması sızmış sayılır. Tam Go paketi
	// ~70 sn, worker paketi ~20 sn sürer; bir saat, eşzamanlı koşan başka bir
	// test sürecinin canlı şemasına dokunmamak için geniş pay.
	LeakedSchemaAge = time.Hour
)

// testSchemaPattern, izole test şemasının adı: derlem_<etiket>_test_<unixnano>.
// Worker şemalarında sonda 8 haneli hex benzersizlik eki bulunur. Zaman taşımayan
// adlar (eski worker şemalarındaki salt uuid) hiçbir zaman eşleşmez.
var testSchemaPattern = regexp.MustCompile(`^derlem_[a-z0-9_]+_test_([0-9]{19})(?:_[0-9a-f]{8})?$`)

// URL, test veritabanı adresini döndürür; adres yoksa ya da çalışma
// veritabanına işaret ediyorsa testi durdurur.
func URL(t testing.TB) string {
	t.Helper()
	raw := strings.TrimSpace(os.Getenv(EnvVar))
	if raw == "" {
		if strings.TrimSpace(os.Getenv(SkipEnvVar)) != "" {
			t.Skipf("%s is not set and %s is set: database-backed test skipped deliberately", EnvVar, SkipEnvVar)
		}
		t.Fatalf(
			"%s is not set. Point it at a scratch database whose name ends in _test "+
				"(scripts/test.ps1 derives it from .env), or set %s=1 to skip database-backed tests on purpose.",
			EnvVar, SkipEnvVar,
		)
	}
	if err := RequireScratchDatabase(raw); err != nil {
		t.Fatalf("%s: %v", EnvVar, err)
	}
	return raw
}

// RequireScratchDatabase, adresin veritabanı adının _test ile bittiğini
// doğrular. Hem URL hem "key=value" conninfo biçimini kabul eder.
func RequireScratchDatabase(rawURL string) error {
	config, err := pgx.ParseConfig(rawURL)
	if err != nil {
		return fmt.Errorf("parse connection string: %w", err)
	}
	if !strings.HasSuffix(config.Database, "_test") {
		return fmt.Errorf(
			"database %q is not a scratch database: the name must end in _test "+
				"(integration tests create and drop schemas with CASCADE; never point this at the working database)",
			config.Database,
		)
	}
	return nil
}

// SchemaCreatedAt, test şemasının adındaki oluşturulma zamanını döndürür; ad
// test şeması biçiminde değilse false.
func SchemaCreatedAt(name string) (time.Time, bool) {
	match := testSchemaPattern.FindStringSubmatch(name)
	if match == nil {
		return time.Time{}, false
	}
	nanos, err := strconv.ParseInt(match[1], 10, 64)
	if err != nil {
		return time.Time{}, false
	}
	return time.Unix(0, nanos), true
}

// SweepResult, bir süpürmenin düşürdüğü ve eklenti içerdiği için bilerek
// düşürmediği şemalar.
type SweepResult struct {
	Dropped []string
	Skipped []string
}

// SweepLeakedSchemas, adındaki oluşturulma zamanı olderThan'dan eski test
// şemalarını düşürür. Önce RequireScratchDatabase'i uygular: çalışma
// veritabanında asla şema düşürmez.
func SweepLeakedSchemas(ctx context.Context, rawURL string, olderThan time.Duration) (SweepResult, error) {
	var result SweepResult
	if err := RequireScratchDatabase(rawURL); err != nil {
		return result, err
	}
	conn, err := pgx.Connect(ctx, rawURL)
	if err != nil {
		return result, fmt.Errorf("connect: %w", err)
	}
	defer conn.Close(ctx)

	rows, err := conn.Query(ctx, `SELECT nspname FROM pg_namespace WHERE nspname LIKE 'derlem%'`)
	if err != nil {
		return result, fmt.Errorf("list schemas: %w", err)
	}
	names, err := pgx.CollectRows(rows, pgx.RowTo[string])
	if err != nil {
		return result, fmt.Errorf("read schemas: %w", err)
	}

	cutoff := time.Now().Add(-olderThan)
	for _, name := range names {
		createdAt, ok := SchemaCreatedAt(name)
		if !ok || !createdAt.Before(cutoff) {
			continue
		}
		var extensionCount int
		if err := conn.QueryRow(ctx, `
			SELECT count(*) FROM pg_extension AS extension
			JOIN pg_namespace AS namespace ON namespace.oid = extension.extnamespace
			WHERE namespace.nspname = $1
		`, name).Scan(&extensionCount); err != nil {
			return result, fmt.Errorf("inspect extensions in %s: %w", name, err)
		}
		if extensionCount > 0 {
			result.Skipped = append(result.Skipped, name)
			continue
		}
		if _, err := conn.Exec(ctx, "DROP SCHEMA IF EXISTS "+pgx.Identifier{name}.Sanitize()+" CASCADE"); err != nil {
			return result, fmt.Errorf("drop leaked schema %s: %w", name, err)
		}
		result.Dropped = append(result.Dropped, name)
	}
	return result, nil
}

// SweepBeforeTests, TestMain'den çağrılır: adres varsa ve test veritabanıysa
// sızmış şemaları süpürür, sonucu stderr'e yazar. Adres yoksa ya da çalışma
// veritabanına işaret ediyorsa hiçbir şey yapmaz — o durumu her test URL(t) ile
// kendisi kırmızı gösterir. Süpürme hatası testleri durdurmaz ama görünür yazılır.
func SweepBeforeTests() {
	raw := strings.TrimSpace(os.Getenv(EnvVar))
	if raw == "" || RequireScratchDatabase(raw) != nil {
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	result, err := SweepLeakedSchemas(ctx, raw, LeakedSchemaAge)
	for _, name := range result.Dropped {
		fmt.Fprintf(os.Stderr, "testdb: dropped leaked test schema %s (older than %s)\n", name, LeakedSchemaAge)
	}
	for _, name := range result.Skipped {
		fmt.Fprintf(os.Stderr,
			"testdb: NOT dropping leaked test schema %s: it contains an extension, and CASCADE would remove "+
				"that extension from the whole database. Move it first (ALTER EXTENSION ... SET SCHEMA public).\n",
			name)
	}
	if err != nil {
		fmt.Fprintf(os.Stderr, "testdb: leaked schema sweep failed: %v\n", err)
	}
}
