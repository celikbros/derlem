package repository

import (
	"errors"
	"testing"
)

func TestDocumentPreview(t *testing.T) {
	preview := DocumentPreview("  birinci\n\nikinci   üçüncü  ")
	if preview != "birinci ikinci üçüncü" {
		t.Fatalf("DocumentPreview() = %q", preview)
	}

	long := make([]rune, 300)
	for index := range long {
		long[index] = 'a'
	}
	preview = DocumentPreview(string(long))
	if len([]rune(preview)) != 241 || []rune(preview)[240] != '…' {
		t.Fatalf("long preview was not rune-safe: length=%d", len([]rune(preview)))
	}
}

func TestNormalizeDocumentReview(t *testing.T) {
	reason := "  ayrıntılı gerekçe  "
	status, normalizedReason, err := normalizeDocumentReview("rejected", &reason, 4)
	if err != nil || status != "rejected" || normalizedReason == nil || *normalizedReason != "ayrıntılı gerekçe" {
		t.Fatalf("unexpected normalized review: status=%q reason=%v error=%v", status, normalizedReason, err)
	}

	if _, _, err := normalizeDocumentReview("approved", nil, 0); err == nil {
		t.Fatal("missing quality score was accepted")
	} else {
		var gateError *GateError
		if !errors.As(err, &gateError) || gateError.Reasons[0] != "quality_score_required" {
			t.Fatalf("unexpected quality score error: %v", err)
		}
	}
	if _, _, err := normalizeDocumentReview("sensitive_review", nil, 3); err == nil {
		t.Fatal("missing reason was accepted")
	}
}
