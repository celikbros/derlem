package httpapi

import (
	"testing"
	"time"

	"github.com/celikbros/derlem/internal/domain"
)

func TestCreateSourceValidationRequiresKnownPurpose(t *testing.T) {
	input := domain.CreateSourceInput{
		Name: "Source", SourceType: "jsonl", ContentPurpose: "model-specific",
		License: "internal", RightsStatus: "unknown", Language: "tr",
		Domain: "general", LineageRef: "source.jsonl",
	}
	if message := normalizeAndValidateSource(&input); message == "" {
		t.Fatal("expected unknown content purpose to fail")
	}
}

func TestUpdateSourceValidationRequiresEvidenceForClearedRights(t *testing.T) {
	input := domain.UpdateSourceInput{
		Name: "Source", SourceType: "jsonl", License: "internal",
		RightsStatus: "cleared", Language: "tr", Domain: "general",
		LineageRef: "source.jsonl", Version: 1,
	}
	if message := normalizeAndValidateSourceUpdate(&input); message == "" {
		t.Fatal("expected missing license evidence to fail")
	}
}

func TestCursorRoundTrip(t *testing.T) {
	createdAt := time.Date(2026, 6, 24, 1, 2, 3, 456, time.UTC)
	encoded := encodeCursor(createdAt, "source-id")
	decodedTime, decodedID, err := decodeCursor(encoded)
	if err != nil {
		t.Fatal(err)
	}
	if !decodedTime.Equal(createdAt) || decodedID != "source-id" {
		t.Fatalf("unexpected cursor: time=%v id=%q", decodedTime, decodedID)
	}
}
