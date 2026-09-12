package httpapi

import (
	"os"
	"testing"

	"github.com/celikbros/derlem/internal/testdb"
)

// TestMain, paketin testlerinden önce süreci öldürülmüş eski koşuların bıraktığı
// izole şemaları süpürür (TASK-008).
func TestMain(m *testing.M) {
	testdb.SweepBeforeTests()
	os.Exit(m.Run())
}
