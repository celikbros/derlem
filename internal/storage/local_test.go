package storage

import (
	"context"
	"io"
	"strings"
	"testing"
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
