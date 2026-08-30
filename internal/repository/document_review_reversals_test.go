package repository

import (
	"context"
	"encoding/json"
	"errors"
	"testing"

	"github.com/celikbros/derlem/internal/domain"
)

func TestReverseReviewRequiresReasonBeforeStartingTransaction(t *testing.T) {
	_, err := (&Documents{}).ReverseReview(
		context.Background(), "review-id",
		domain.ReverseDocumentReviewInput{Reason: "   "}, "actor-id", false,
	)
	var gateError *GateError
	if !errors.As(err, &gateError) || len(gateError.Reasons) != 1 || gateError.Reasons[0] != "reason_required" {
		t.Fatalf("missing reason error = %v", err)
	}
}

func TestPreviousReviewDocumentStatus(t *testing.T) {
	for _, status := range []string{"sampled", "edited"} {
		contextJSON, err := json.Marshal(map[string]string{"previous_status": status})
		if err != nil {
			t.Fatal(err)
		}
		got, ok := previousReviewDocumentStatus(contextJSON)
		if !ok || got != status {
			t.Fatalf("previousReviewDocumentStatus(%q) = %q, %v", status, got, ok)
		}
	}
	for _, contextJSON := range []json.RawMessage{
		nil,
		json.RawMessage(`{}`),
		json.RawMessage(`{"previous_status":"approved"}`),
		json.RawMessage(`not-json`),
	} {
		if got, ok := previousReviewDocumentStatus(contextJSON); ok || got != "" {
			t.Fatalf("invalid context accepted: input=%q got=%q ok=%v", contextJSON, got, ok)
		}
	}
}

func TestReviewedDocumentStatus(t *testing.T) {
	tests := map[string]string{
		"approved": "approved", "rejected": "rejected",
		"sensitive_review": "sensitive_review", "unknown": "",
	}
	for decision, want := range tests {
		if got := reviewedDocumentStatus(decision); got != want {
			t.Fatalf("reviewedDocumentStatus(%q) = %q, want %q", decision, got, want)
		}
	}
}
