package storage

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"io"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

func TestLocalStoreIsContentAddressedAndIdempotent(t *testing.T) {
	store, err := NewLocal(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	contents := "birinci\nikinci\n"

	first, err := store.Put(context.Background(), strings.NewReader(contents))
	if err != nil {
		t.Fatal(err)
	}
	exists, err := store.Exists(context.Background(), first.SHA256)
	if err != nil {
		t.Fatal(err)
	}
	if !exists {
		t.Fatal("published object does not exist")
	}
	second, err := store.Put(context.Background(), strings.NewReader(contents))
	if err != nil {
		t.Fatal(err)
	}
	if first != second {
		t.Fatalf("objects differ: first=%#v second=%#v", first, second)
	}
	reader, err := store.Open(context.Background(), first.SHA256)
	if err != nil {
		t.Fatal(err)
	}
	defer reader.Close()
	stored, err := io.ReadAll(reader)
	if err != nil {
		t.Fatal(err)
	}
	if string(stored) != contents {
		t.Fatalf("unexpected contents: %q", stored)
	}
	path, err := store.pathForDigest(first.SHA256)
	if err != nil {
		t.Fatal(err)
	}
	info, err := os.Lstat(path)
	if err != nil {
		t.Fatal(err)
	}
	if !info.Mode().IsRegular() {
		t.Fatalf("published object is not regular: %s", info.Mode())
	}
	// Windows does not expose its read-only file attribute through portable
	// FileMode permission bits, so enforce the POSIX assertion where the mode
	// is meaningful. Put still applies os.Chmod on every platform.
	if os.PathSeparator == '\\' {
		writable, openErr := os.OpenFile(path, os.O_WRONLY, 0)
		if openErr == nil {
			_ = writable.Close()
			t.Fatal("published object can be opened for writing")
		}
	} else if info.Mode().Perm()&0o222 != 0 {
		t.Fatalf("published object is writable: %s", info.Mode())
	}
}

func TestLocalStoreDoesNotExposeObjectBeforeAtomicPublish(t *testing.T) {
	store, err := NewLocal(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	contents := []byte("complete object bytes")
	digest := digestForTest(contents)

	publishReached := make(chan struct{})
	releasePublish := make(chan struct{})
	store.linkFile = func(oldPath, newPath string) error {
		close(publishReached)
		<-releasePublish
		return os.Link(oldPath, newPath)
	}

	type result struct {
		object Object
		err    error
	}
	resultCh := make(chan result, 1)
	go func() {
		object, putErr := store.Put(context.Background(), strings.NewReader(string(contents)))
		resultCh <- result{object: object, err: putErr}
	}()

	waitForSignal(t, publishReached, "writer did not reach atomic publication")
	exists, err := store.Exists(context.Background(), digest)
	if err != nil {
		t.Fatal(err)
	}
	if exists {
		t.Fatal("final object became visible before atomic publication")
	}
	close(releasePublish)

	select {
	case got := <-resultCh:
		if got.err != nil {
			t.Fatal(got.err)
		}
		if got.object.SHA256 != digest {
			t.Fatalf("unexpected digest: got %s, want %s", got.object.SHA256, digest)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("writer did not finish")
	}
	assertStoredBytes(t, store, digest, contents)
}

func TestLocalStoreConcurrentIdenticalWritersValidateWinner(t *testing.T) {
	store, err := NewLocal(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	contents := []byte(strings.Repeat("aynı içerik\n", 1024))

	var mutex sync.Mutex
	writersAtPublish := 0
	bothReady := make(chan struct{})
	store.linkFile = func(oldPath, newPath string) error {
		mutex.Lock()
		writersAtPublish++
		if writersAtPublish == 2 {
			close(bothReady)
		}
		mutex.Unlock()
		<-bothReady
		return os.Link(oldPath, newPath)
	}

	type result struct {
		object Object
		err    error
	}
	results := make(chan result, 2)
	for range 2 {
		go func() {
			object, putErr := store.Put(context.Background(), strings.NewReader(string(contents)))
			results <- result{object: object, err: putErr}
		}()
	}

	waitForSignal(t, bothReady, "writers did not reach publication together")
	var objects [2]Object
	for i := range 2 {
		select {
		case got := <-results:
			if got.err != nil {
				t.Fatalf("writer %d failed: %v", i, got.err)
			}
			objects[i] = got.object
		case <-time.After(5 * time.Second):
			t.Fatalf("writer %d did not finish", i)
		}
	}
	if objects[0] != objects[1] {
		t.Fatalf("concurrent results differ: %#v != %#v", objects[0], objects[1])
	}
	assertStoredBytes(t, store, objects[0].SHA256, contents)
}

func TestLocalStoreRejectsCorruptExistingDigestPath(t *testing.T) {
	store, err := NewLocal(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	wanted := []byte("right object")
	corrupt := []byte("wrong object")
	if len(wanted) != len(corrupt) {
		t.Fatal("test fixture sizes must match")
	}
	digest := digestForTest(wanted)
	target, err := store.pathForDigest(digest)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(target, corrupt, 0o444); err != nil {
		t.Fatal(err)
	}

	if _, err := store.Put(context.Background(), strings.NewReader(string(wanted))); err == nil {
		t.Fatal("expected corrupt existing object to be rejected")
	} else if !strings.Contains(err.Error(), "digest mismatch") {
		t.Fatalf("unexpected error: %v", err)
	}
	assertStoredBytes(t, store, digest, corrupt)
}

func TestLocalStoreRejectsPartialExistingDigestPath(t *testing.T) {
	store, err := NewLocal(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	wanted := []byte("complete expected object")
	digest := digestForTest(wanted)
	target, err := store.pathForDigest(digest)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(target, []byte("partial"), 0o444); err != nil {
		t.Fatal(err)
	}

	if _, err := store.Put(context.Background(), strings.NewReader(string(wanted))); err == nil {
		t.Fatal("expected partial existing object to be rejected")
	} else if !strings.Contains(err.Error(), "size mismatch") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestLocalStoreRejectsVanishedConcurrentWinner(t *testing.T) {
	store, err := NewLocal(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	contents := []byte("object without a real winning publisher")
	digest := digestForTest(contents)
	store.linkFile = func(_, _ string) error { return os.ErrExist }

	if _, err := store.Put(context.Background(), strings.NewReader(string(contents))); err == nil {
		t.Fatal("expected missing concurrent winner to be rejected")
	} else if !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("unexpected error: %v", err)
	}
	exists, err := store.Exists(context.Background(), digest)
	if err != nil {
		t.Fatal(err)
	}
	if exists {
		t.Fatal("missing winner path unexpectedly exists")
	}
}

func TestLocalStoreRejectsNonRegularExistingDigestPath(t *testing.T) {
	store, err := NewLocal(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	contents := []byte("object whose digest path is a directory")
	digest := digestForTest(contents)
	target, err := store.pathForDigest(digest)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(target, 0o755); err != nil {
		t.Fatal(err)
	}

	if _, err := store.Put(context.Background(), strings.NewReader(string(contents))); err == nil {
		t.Fatal("expected non-regular existing object to be rejected")
	} else if !strings.Contains(err.Error(), "not a regular file") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestLocalStoreReaderFailureLeavesNoFinalObject(t *testing.T) {
	store, err := NewLocal(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	contents := []byte("bytes delivered before the reader fails")
	digest := digestForTest(contents)
	readerErr := errors.New("injected reader failure")
	reader := &failAfterDataReader{data: contents, err: readerErr}

	if _, err := store.Put(context.Background(), reader); !errors.Is(err, readerErr) {
		t.Fatalf("expected reader failure, got %v", err)
	}
	exists, err := store.Exists(context.Background(), digest)
	if err != nil {
		t.Fatal(err)
	}
	if exists {
		t.Fatal("reader failure left a final object")
	}
}

func TestLocalStorePublishFailureLeavesNoFinalObject(t *testing.T) {
	store, err := NewLocal(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	contents := []byte("bytes whose atomic publication fails")
	digest := digestForTest(contents)
	publishErr := errors.New("injected publication failure")
	store.linkFile = func(_, _ string) error { return publishErr }

	if _, err := store.Put(context.Background(), strings.NewReader(string(contents))); !errors.Is(err, publishErr) {
		t.Fatalf("expected publication failure, got %v", err)
	}
	exists, err := store.Exists(context.Background(), digest)
	if err != nil {
		t.Fatal(err)
	}
	if exists {
		t.Fatal("publication failure left a final object")
	}
}

func TestLocalStoreCanceledContextLeavesNoFinalObject(t *testing.T) {
	store, err := NewLocal(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	contents := []byte("canceled object")
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	if _, err := store.Put(ctx, strings.NewReader(string(contents))); !errors.Is(err, context.Canceled) {
		t.Fatalf("expected context cancellation, got %v", err)
	}
	exists, err := store.Exists(context.Background(), digestForTest(contents))
	if err != nil {
		t.Fatal(err)
	}
	if exists {
		t.Fatal("canceled write left a final object")
	}
}

func TestLocalStoreRejectsInvalidDigest(t *testing.T) {
	store, err := NewLocal(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	if _, err := store.Open(context.Background(), "not-a-digest"); err == nil {
		t.Fatal("expected invalid digest to fail")
	}
}

type failAfterDataReader struct {
	data []byte
	err  error
	done bool
}

func (r *failAfterDataReader) Read(buffer []byte) (int, error) {
	if r.done {
		return 0, r.err
	}
	r.done = true
	return copy(buffer, r.data), nil
}

func digestForTest(contents []byte) string {
	digest := sha256.Sum256(contents)
	return hex.EncodeToString(digest[:])
}

func assertStoredBytes(t *testing.T, store *LocalStore, digest string, want []byte) {
	t.Helper()
	reader, err := store.Open(context.Background(), digest)
	if err != nil {
		t.Fatal(err)
	}
	got, readErr := io.ReadAll(reader)
	closeErr := reader.Close()
	if readErr != nil || closeErr != nil {
		t.Fatalf("read stored object: read=%v close=%v", readErr, closeErr)
	}
	if string(got) != string(want) {
		t.Fatalf("unexpected stored bytes: got %q, want %q", got, want)
	}
}

func waitForSignal(t *testing.T, signal <-chan struct{}, message string) {
	t.Helper()
	select {
	case <-signal:
	case <-time.After(5 * time.Second):
		t.Fatal(message)
	}
}
