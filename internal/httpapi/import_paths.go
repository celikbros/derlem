package httpapi

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

var errInvalidImportPath = errors.New("invalid import path")

// resolveImportFile validates an operator-provided local ingest path before it
// is persisted in a job payload. The worker repeats the same boundary check at
// execution time because the filesystem may change while a job is queued.
func resolveImportFile(importRoot, candidate string) (string, error) {
	if strings.TrimSpace(importRoot) == "" || strings.TrimSpace(candidate) == "" || !filepath.IsAbs(candidate) {
		return "", errInvalidImportPath
	}

	rootAbsolute, err := filepath.Abs(importRoot)
	if err != nil {
		return "", fmt.Errorf("%w: resolve root: %v", errInvalidImportPath, err)
	}
	rootResolved, err := filepath.EvalSymlinks(rootAbsolute)
	if err != nil {
		return "", fmt.Errorf("%w: resolve root: %v", errInvalidImportPath, err)
	}
	rootInfo, err := os.Stat(rootResolved)
	if err != nil || !rootInfo.IsDir() {
		return "", fmt.Errorf("%w: import root is not a directory", errInvalidImportPath)
	}

	candidate = filepath.Clean(candidate)
	lexicalRelative, err := filepath.Rel(rootAbsolute, candidate)
	if err != nil || pathEscapesRoot(lexicalRelative) {
		return "", fmt.Errorf("%w: path is outside import root", errInvalidImportPath)
	}

	current := rootAbsolute
	for _, component := range splitRelativePath(lexicalRelative) {
		current = filepath.Join(current, component)
		info, statErr := os.Lstat(current)
		if statErr != nil {
			return "", fmt.Errorf("%w: inspect path: %v", errInvalidImportPath, statErr)
		}
		if info.Mode()&os.ModeSymlink != 0 {
			return "", fmt.Errorf("%w: symbolic links are not allowed", errInvalidImportPath)
		}
	}

	resolved, err := filepath.EvalSymlinks(candidate)
	if err != nil {
		return "", fmt.Errorf("%w: resolve file: %v", errInvalidImportPath, err)
	}
	resolvedRelative, err := filepath.Rel(rootResolved, resolved)
	if err != nil || pathEscapesRoot(resolvedRelative) {
		return "", fmt.Errorf("%w: resolved path is outside import root", errInvalidImportPath)
	}
	info, err := os.Lstat(resolved)
	if err != nil || !info.Mode().IsRegular() {
		return "", fmt.Errorf("%w: path is not a regular file", errInvalidImportPath)
	}
	return resolved, nil
}

func pathEscapesRoot(relative string) bool {
	return relative == ".." || strings.HasPrefix(relative, ".."+string(os.PathSeparator)) || filepath.IsAbs(relative)
}

func splitRelativePath(relative string) []string {
	if relative == "." {
		return nil
	}
	return strings.Split(relative, string(os.PathSeparator))
}
