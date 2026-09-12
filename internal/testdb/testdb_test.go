package testdb

import (
	"strings"
	"testing"
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
