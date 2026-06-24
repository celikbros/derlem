package repository

import (
	"errors"
	"strings"
)

var (
	ErrNotFound   = errors.New("not found")
	ErrConflict   = errors.New("version conflict")
	ErrSelfReview = errors.New("self review is not allowed")
)

type GateError struct {
	Reasons []string
}

func (e *GateError) Error() string {
	return "review gate blocked: " + strings.Join(e.Reasons, ", ")
}
