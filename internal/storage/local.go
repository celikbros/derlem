package storage

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
)

type LocalStore struct {
	root     string
	linkFile func(string, string) error
}

func NewLocal(root string) (*LocalStore, error) {
	absoluteRoot, err := filepath.Abs(root)
	if err != nil {
		return nil, fmt.Errorf("resolve storage root: %w", err)
	}
	if err := os.MkdirAll(filepath.Join(absoluteRoot, ".tmp"), 0o700); err != nil {
		return nil, fmt.Errorf("create storage temp directory: %w", err)
	}
	if err := os.MkdirAll(filepath.Join(absoluteRoot, "objects", "sha256"), 0o755); err != nil {
		return nil, fmt.Errorf("create storage object directory: %w", err)
	}
	return &LocalStore{root: absoluteRoot, linkFile: os.Link}, nil
}

func (s *LocalStore) Put(ctx context.Context, reader io.Reader) (Object, error) {
	temp, err := os.CreateTemp(filepath.Join(s.root, ".tmp"), "ingest-*")
	if err != nil {
		return Object{}, fmt.Errorf("create temp object: %w", err)
	}
	tempPath := temp.Name()
	tempClosed := false
	published := false
	defer func() {
		if !tempClosed {
			_ = temp.Close()
		}
		// Before publication the temporary file is not shared, so making it
		// writable again is safe and lets Windows remove a read-only temp file.
		// After publication it is a hard link to the immutable object; changing
		// its mode would also change the published object on POSIX filesystems.
		if !published {
			_ = os.Chmod(tempPath, 0o600)
		}
		_ = os.Remove(tempPath)
	}()

	hash := sha256.New()
	written, copyErr := copyWithContext(ctx, io.MultiWriter(temp, hash), reader)
	if copyErr != nil {
		return Object{}, fmt.Errorf("write temp object: %w", copyErr)
	}
	if err := temp.Sync(); err != nil {
		return Object{}, fmt.Errorf("sync temp object: %w", err)
	}
	if err := temp.Chmod(0o444); err != nil {
		return Object{}, fmt.Errorf("mark temp object read-only: %w", err)
	}
	if err := temp.Sync(); err != nil {
		return Object{}, fmt.Errorf("sync read-only temp object: %w", err)
	}
	if err := temp.Close(); err != nil {
		return Object{}, fmt.Errorf("close temp object: %w", err)
	}
	tempClosed = true

	digest := hex.EncodeToString(hash.Sum(nil))
	key := filepath.ToSlash(filepath.Join("objects", "sha256", digest[:2], digest[2:4], digest))
	target := filepath.Join(s.root, filepath.FromSlash(key))
	if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
		return Object{}, fmt.Errorf("create object prefix: %w", err)
	}

	linkFile := s.linkFile
	if linkFile == nil {
		linkFile = os.Link
	}
	err = linkFile(tempPath, target)
	if errors.Is(err, os.ErrExist) {
		if err := validateExistingObject(ctx, target, digest, written); err != nil {
			return Object{}, fmt.Errorf("validate existing immutable object: %w", err)
		}
		return Object{SHA256: digest, StorageKey: key, ByteSize: written}, nil
	}
	if err != nil {
		return Object{}, fmt.Errorf("publish immutable object: %w", err)
	}
	published = true
	// Remove the staging name before applying the final-name mode. On Windows,
	// deleting one hard-link name can refresh the remaining name's attributes.
	// The deferred cleanup retries if this best-effort removal is interrupted.
	_ = os.Remove(tempPath)
	// Windows stores the read-only attribute per directory entry, so a newly
	// created hard link may not reflect the source entry's attribute. Applying
	// the mode to the published name is redundant on POSIX and required on
	// Windows.
	if err := os.Chmod(target, 0o444); err != nil {
		_ = os.Remove(target)
		return Object{}, fmt.Errorf("mark published object read-only: %w", err)
	}
	return Object{SHA256: digest, StorageKey: key, ByteSize: written}, nil
}

func validateExistingObject(ctx context.Context, target, expectedDigest string, expectedSize int64) error {
	before, err := os.Lstat(target)
	if err != nil {
		return fmt.Errorf("inspect object: %w", err)
	}
	if !before.Mode().IsRegular() {
		return fmt.Errorf("object path is not a regular file (mode %s)", before.Mode())
	}
	if before.Size() != expectedSize {
		return fmt.Errorf("object size mismatch: got %d, want %d", before.Size(), expectedSize)
	}

	file, err := os.Open(target)
	if err != nil {
		return fmt.Errorf("open object: %w", err)
	}
	opened, err := file.Stat()
	if err != nil {
		_ = file.Close()
		return fmt.Errorf("inspect opened object: %w", err)
	}
	if !opened.Mode().IsRegular() || !os.SameFile(before, opened) {
		_ = file.Close()
		return errors.New("object path changed while opening")
	}

	hash := sha256.New()
	read, readErr := copyWithContext(ctx, hash, file)
	closeErr := file.Close()
	if readErr != nil {
		return fmt.Errorf("hash object: %w", readErr)
	}
	if closeErr != nil {
		return fmt.Errorf("close object: %w", closeErr)
	}
	if read != expectedSize {
		return fmt.Errorf("object size changed while hashing: got %d, want %d", read, expectedSize)
	}
	actualDigest := hex.EncodeToString(hash.Sum(nil))
	if actualDigest != expectedDigest {
		return fmt.Errorf("object digest mismatch: got %s, want %s", actualDigest, expectedDigest)
	}

	after, err := os.Lstat(target)
	if err != nil {
		return fmt.Errorf("reinspect object: %w", err)
	}
	if !after.Mode().IsRegular() || !os.SameFile(before, after) {
		return errors.New("object path changed while validating")
	}
	return nil
}

func (s *LocalStore) Open(_ context.Context, digest string) (io.ReadCloser, error) {
	path, err := s.pathForDigest(digest)
	if err != nil {
		return nil, err
	}
	return os.Open(path)
}

func (s *LocalStore) Exists(_ context.Context, digest string) (bool, error) {
	path, err := s.pathForDigest(digest)
	if err != nil {
		return false, err
	}
	_, err = os.Stat(path)
	if err == nil {
		return true, nil
	}
	if errors.Is(err, os.ErrNotExist) {
		return false, nil
	}
	return false, err
}

func (s *LocalStore) pathForDigest(digest string) (string, error) {
	if len(digest) != 64 {
		return "", errors.New("sha256 digest must contain 64 hexadecimal characters")
	}
	if _, err := hex.DecodeString(digest); err != nil {
		return "", errors.New("sha256 digest must be hexadecimal")
	}
	return filepath.Join(s.root, "objects", "sha256", digest[:2], digest[2:4], digest), nil
}

func copyWithContext(ctx context.Context, destination io.Writer, source io.Reader) (int64, error) {
	buffer := make([]byte, 1024*1024)
	var total int64
	for {
		if err := ctx.Err(); err != nil {
			return total, err
		}
		read, readErr := source.Read(buffer)
		if read > 0 {
			written, writeErr := destination.Write(buffer[:read])
			total += int64(written)
			if writeErr != nil {
				return total, writeErr
			}
			if written != read {
				return total, io.ErrShortWrite
			}
		}
		if readErr == io.EOF {
			return total, nil
		}
		if readErr != nil {
			return total, readErr
		}
	}
}
