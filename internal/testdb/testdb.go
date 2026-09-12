// Package testdb, veritabanına bağlı entegrasyon testlerinin bağlantı adresini
// tek yerden verir. İki kuralı vardır:
//
//  1. Adres yoksa test SESSİZCE ATLANMAZ. Ya açıkça atlanır
//     (DERLEM_SKIP_DB_TESTS=1) ya da kırmızı olur. 2026-09'da 29 Go testi aylarca
//     sessizce atlandı ve "go test ./..." yeşil derken demetleme, freeze kapısı
//     ve migration testleri hiç çalışmıyordu.
//  2. Adres, adı _test ile bitmeyen bir veritabanına işaret ediyorsa hiçbir test
//     ona dokunmadan durur. Testler izole şema açıp CASCADE ile düşürür;
//     2026-08-21'de bu adres çalışma veritabanına yöneltilmiş ve iki test şeması
//     orada kalmıştı.
package testdb

import (
	"fmt"
	"os"
	"strings"
	"testing"

	"github.com/jackc/pgx/v5"
)

const (
	// EnvVar, entegrasyon testlerinin kullandığı veritabanı adresi.
	EnvVar = "DERLEM_TEST_DATABASE_URL"
	// SkipEnvVar, PostgreSQL olmayan makinede veritabanı testlerini BİLEREK
	// atlamak için; sessiz atlamanın tek meşru karşılığı.
	SkipEnvVar = "DERLEM_SKIP_DB_TESTS"
)

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
