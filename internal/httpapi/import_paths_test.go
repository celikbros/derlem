package httpapi

import (
	"errors"
	"os"
	"path/filepath"
	"testing"
)

func TestResolveImportFileAcceptsRegularFileUnderRoot(t *testing.T) {
	base := t.TempDir()
	root := filepath.Join(base, "import")
	path := filepath.Join(root, "nested", "source.jsonl")
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte("{}\n"), 0o600); err != nil {
		t.Fatal(err)
	}

	resolved, err := resolveImportFile(root, path)
	if err != nil {
		t.Fatal(err)
	}
	want, err := filepath.EvalSymlinks(path)
	if err != nil {
		t.Fatal(err)
	}
	if resolved != want {
		t.Fatalf("resolved path = %q, want %q", resolved, want)
	}
}

func TestResolveImportFileRejectsInvalidTargets(t *testing.T) {
	base := t.TempDir()
	root := filepath.Join(base, "import")
	if err := os.MkdirAll(root, 0o700); err != nil {
		t.Fatal(err)
	}
	outside := filepath.Join(base, "outside.txt")
	if err := os.WriteFile(outside, []byte("outside"), 0o600); err != nil {
		t.Fatal(err)
	}

	tests := map[string]string{
		"empty":        "",
		"relative":     filepath.Join("import", "source.txt"),
		"outside root": outside,
		"directory":    root,
		"missing":      filepath.Join(root, "missing.txt"),
	}
	for name, path := range tests {
		t.Run(name, func(t *testing.T) {
			if _, err := resolveImportFile(root, path); !errors.Is(err, errInvalidImportPath) {
				t.Fatalf("error = %v, want errInvalidImportPath", err)
			}
		})
	}
}

func TestResolveImportFileRejectsSymlinkComponents(t *testing.T) {
	base := t.TempDir()
	root := filepath.Join(base, "import")
	outsideDirectory := filepath.Join(base, "outside")
	if err := os.MkdirAll(root, 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(outsideDirectory, 0o700); err != nil {
		t.Fatal(err)
	}
	outside := filepath.Join(outsideDirectory, "source.txt")
	if err := os.WriteFile(outside, []byte("outside"), 0o600); err != nil {
		t.Fatal(err)
	}

	fileLink := filepath.Join(root, "source-link.txt")
	if err := os.Symlink(outside, fileLink); err != nil {
		t.Skipf("symlinks are unavailable: %v", err)
	}
	if _, err := resolveImportFile(root, fileLink); !errors.Is(err, errInvalidImportPath) {
		t.Fatalf("file symlink error = %v, want errInvalidImportPath", err)
	}

	directoryLink := filepath.Join(root, "directory-link")
	if err := os.Symlink(outsideDirectory, directoryLink); err != nil {
		t.Fatal(err)
	}
	if _, err := resolveImportFile(root, filepath.Join(directoryLink, "source.txt")); !errors.Is(err, errInvalidImportPath) {
		t.Fatalf("directory symlink error = %v, want errInvalidImportPath", err)
	}
}
