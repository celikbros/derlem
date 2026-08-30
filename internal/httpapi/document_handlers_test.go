package httpapi

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"io"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/celikbros/derlem/internal/storage"
)

type documentObjectStore struct {
	content string
	err     error
}

func (store documentObjectStore) Put(context.Context, io.Reader) (storage.Object, error) {
	return storage.Object{}, errors.New("unexpected Put")
}

func (store documentObjectStore) Open(context.Context, string) (io.ReadCloser, error) {
	if store.err != nil {
		return nil, store.err
	}
	return io.NopCloser(strings.NewReader(store.content)), nil
}

func (store documentObjectStore) Exists(context.Context, string) (bool, error) {
	return false, errors.New("unexpected Exists")
}

func TestReadDocumentObjectVerifiesDigest(t *testing.T) {
	content := "T\u00fcrk\u00e7e inceleme metni\n"
	digest := sha256.Sum256([]byte(content))
	server := &Server{objectStore: documentObjectStore{content: content}}

	got, err := server.readDocumentObject(
		httptest.NewRequest("GET", "/", nil),
		hex.EncodeToString(digest[:]),
	)
	if err != nil {
		t.Fatalf("read verified document: %v", err)
	}
	if got != content {
		t.Fatalf("content changed: got %q want %q", got, content)
	}
}

func TestReadDocumentObjectRejectsDigestMismatch(t *testing.T) {
	server := &Server{objectStore: documentObjectStore{content: "tampered content"}}
	expectedDigest := sha256.Sum256([]byte("expected content"))

	content, err := server.readDocumentObject(
		httptest.NewRequest("GET", "/", nil),
		hex.EncodeToString(expectedDigest[:]),
	)
	if err == nil || err.Error() != "document object digest mismatch" {
		t.Fatalf("expected digest mismatch, got content=%q err=%v", content, err)
	}
	if content != "" {
		t.Fatalf("mismatched content leaked: %q", content)
	}
}
