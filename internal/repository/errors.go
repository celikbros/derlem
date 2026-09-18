package repository

import (
	"errors"
	"strings"
)

var (
	ErrNotFound   = errors.New("not found")
	ErrConflict   = errors.New("version conflict")
	ErrForbidden  = errors.New("forbidden")
	ErrSelfReview = errors.New("self review is not allowed")
	// ErrSelfLineage: kaynak kendi girdisi olamaz (000029).
	ErrSelfLineage = errors.New("a source cannot be its own lineage input")
	ErrClaimLost   = errors.New("document review claim is missing, expired, or owned by another reviewer")
)

type GateError struct {
	Reasons []string
}

func (e *GateError) Error() string {
	return "review gate blocked: " + strings.Join(e.Reasons, ", ")
}
