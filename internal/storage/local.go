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
	root string
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
	return &LocalStore{root: absoluteRoot}, nil
}

func (s *LocalStore) Put(ctx context.Context, reader io.Reader) (Object, error) {
	temp, err := os.CreateTemp(filepath.Join(s.root, ".tmp"), "ingest-*")
	if err != nil {
		return Object{}, fmt.Errorf("create temp object: %w", err)
	}
	tempPath := temp.Name()
	defer os.Remove(tempPath)

	hash := sha256.New()
	written, copyErr := copyWithContext(ctx, io.MultiWriter(temp, hash), reader)
	closeErr := temp.Close()
	if copyErr != nil {
		return Object{}, fmt.Errorf("write temp object: %w", copyErr)
	}
	if closeErr != nil {
		return Object{}, fmt.Errorf("close temp object: %w", closeErr)
	}

	digest := hex.EncodeToString(hash.Sum(nil))
	key := filepath.ToSlash(filepath.Join("objects", "sha256", digest[:2], digest[2:4], digest))
	target := filepath.Join(s.root, filepath.FromSlash(key))
	if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
		return Object{}, fmt.Errorf("create object prefix: %w", err)
	}

	targetFile, err := os.OpenFile(target, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o444)
	if errors.Is(err, os.ErrExist) {
		return Object{SHA256: digest, StorageKey: key, ByteSize: written}, nil
	}
	if err != nil {
		return Object{}, fmt.Errorf("create immutable object: %w", err)
	}

	sourceFile, err := os.Open(tempPath)
	if err != nil {
		targetFile.Close()
		os.Remove(target)
		return Object{}, fmt.Errorf("reopen temp object: %w", err)
	}
	_, copyErr = copyWithContext(ctx, targetFile, sourceFile)
	sourceCloseErr := sourceFile.Close()
	targetCloseErr := targetFile.Close()
	if copyErr != nil || sourceCloseErr != nil || targetCloseErr != nil {
		os.Remove(target)
		return Object{}, fmt.Errorf("finalize immutable object: copy=%v source_close=%v target_close=%v", copyErr, sourceCloseErr, targetCloseErr)
	}
	if err := os.Chmod(target, 0o444); err != nil {
		return Object{}, fmt.Errorf("mark object read-only: %w", err)
	}
	return Object{SHA256: digest, StorageKey: key, ByteSize: written}, nil
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
