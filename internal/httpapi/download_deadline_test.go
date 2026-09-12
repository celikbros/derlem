package httpapi

import (
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

// slowReader, govdeyi parca parca ve aralarda bekleyerek uretir. Boylece yazma
// evresi sunucunun WriteTimeout suresini kat kat asar; hata bu durumda ortaya
// cikiyor, yuk buyuklugunden veya soket tamponundan bagimsiz olarak.
type slowReader struct {
	chunk     []byte
	remaining int
	delay     time.Duration
}

func (s *slowReader) Read(target []byte) (int, error) {
	if s.remaining == 0 {
		return 0, io.EOF
	}
	time.Sleep(s.delay)
	s.remaining--
	return copy(target, s.chunk), nil
}

const (
	testChunkSize  = 256 * 1024
	testChunkCount = 4
	testChunkDelay = 150 * time.Millisecond
	// Yazma evresi ~600 ms surer; sunucu suresi bunun cok altinda.
	testWriteTimeout = 200 * time.Millisecond
	testDeadlineStep = int64(64 * 1024)
)

func newSlowReader() *slowReader {
	return &slowReader{
		chunk:     make([]byte, testChunkSize),
		remaining: testChunkCount,
		delay:     testChunkDelay,
	}
}

// serveAndFetch, verilen govde kopyalayicisiyla gercek bir http.Server ayaga
// kaldirir ve tum govdeyi indirmeyi dener. httptest.NewRecorder bu testi
// yapamaz: kaydedicide yazma suresi diye bir sey yoktur, dolayisiyla hem hatali
// hem duzeltilmis kod gecer.
func serveAndFetch(t *testing.T, copyBody func(http.ResponseWriter, io.Reader) (int64, error)) (int, error) {
	t.Helper()

	server := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		if _, err := copyBody(w, newSlowReader()); err != nil {
			t.Logf("sunucu tarafi yazma hatasi: %v", err)
		}
	}))
	server.Config.WriteTimeout = testWriteTimeout
	server.Start()
	defer server.Close()

	response, err := server.Client().Get(server.URL)
	if err != nil {
		return 0, err
	}
	defer response.Body.Close()

	body, err := io.ReadAll(response.Body)
	return len(body), err
}

func TestCopyDownloadBodyOutlivesWriteTimeout(t *testing.T) {
	expected := testChunkSize * testChunkCount

	received, err := serveAndFetch(t, func(w http.ResponseWriter, source io.Reader) (int64, error) {
		return copyRefreshingDeadline(w, source, testDeadlineStep, testWriteTimeout)
	})
	if err != nil {
		t.Fatalf("indirme yarida kesildi: %v (alinan %d/%d bayt)", err, received, expected)
	}
	if received != expected {
		t.Fatalf("govde eksik: alinan %d bayt, beklenen %d", received, expected)
	}
}

// TestPlainCopyIsCutByWriteTimeout, yukaridaki testin bos yere gecmedigini
// gosterir: ayni akis duz io.Copy ile kopyalandiginda transfer kesilir. Bu
// kontrol olmadan ilk test hatayi yakaladigini kanitlayamaz.
func TestPlainCopyIsCutByWriteTimeout(t *testing.T) {
	expected := testChunkSize * testChunkCount

	received, err := serveAndFetch(t, func(w http.ResponseWriter, source io.Reader) (int64, error) {
		return io.Copy(w, source)
	})
	if err == nil && received == expected {
		t.Fatalf(
			"duz io.Copy tum govdeyi gonderdi (%d bayt); bu test WriteTimeout'u "+
				"tetikleyemiyor, dolayisiyla asil test de bir sey kanitlamiyor",
			received,
		)
	}
}

// TestCopyDownloadBodyDropsStalledClient, sureyi tamamen kaldirmadigimizi
// dogrular: okumayi birakan istemcide yazma hata vermelidir, yoksa acik nesne
// dosyasi ve goroutine sonsuza kadar tutulur.
func TestCopyDownloadBodyDropsStalledClient(t *testing.T) {
	writeResult := make(chan error, 1)

	server := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		// Istemcinin okumayi birakmasi icin govde soket tamponunu asacak
		// kadar buyuk; sure kisa tutuldu ki test hizli bitsin.
		source := &slowReader{chunk: make([]byte, testChunkSize), remaining: 4096}
		_, err := copyRefreshingDeadline(w, source, testDeadlineStep, 300*time.Millisecond)
		writeResult <- err
	}))
	server.Config.WriteTimeout = testWriteTimeout
	server.Start()
	defer server.Close()

	response, err := server.Client().Get(server.URL)
	if err != nil {
		t.Fatalf("istek basarisiz: %v", err)
	}
	// Govdeyi hic okumadan bekle: sunucunun tazelenen suresi dolmali.
	select {
	case writeErr := <-writeResult:
		if writeErr == nil {
			t.Fatal("okumayi birakan istemcide yazma hata vermedi; sure tamamen kaldirilmis olabilir")
		}
	case <-time.After(15 * time.Second):
		t.Fatal("okumayi birakan istemci kopmadi; yazma suresi tazelenmek yerine kaldirilmis olabilir")
	}
	response.Body.Close()
}
