package storage

import (
	"context"
	"io"
)

type Object struct {
	SHA256     string
	StorageKey string
	ByteSize   int64
}

type Store interface {
	Put(context.Context, io.Reader) (Object, error)
	Open(context.Context, string) (io.ReadCloser, error)
	Exists(context.Context, string) (bool, error)
}
