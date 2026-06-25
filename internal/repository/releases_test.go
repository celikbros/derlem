package repository

import (
	"slices"
	"testing"

	"github.com/celikbros/derlem/internal/domain"
)

func TestNormalizeReleaseInputDeduplicatesSources(t *testing.T) {
	input := domain.CreateReleaseInput{
		Name: "  Türkçe instruction  ", Version: " v1 ", ContentPurpose: " instruction ",
		SourceIDs: []string{"source-a", " source-a ", "", "source-b"},
	}
	NormalizeReleaseInput(&input)
	if input.Name != "Türkçe instruction" || input.Version != "v1" || input.ContentPurpose != "instruction" {
		t.Fatalf("release fields were not normalized: %#v", input)
	}
	if !slices.Equal(input.SourceIDs, []string{"source-a", "source-b"}) {
		t.Fatalf("unexpected source IDs: %#v", input.SourceIDs)
	}
}

func TestReleaseInputGateReasons(t *testing.T) {
	valid := domain.CreateReleaseInput{
		Name: "Instruction", Version: "v1", ContentPurpose: "instruction",
		SourceIDs: []string{"source-a"},
	}
	if reasons := ReleaseInputGateReasons(valid); len(reasons) != 0 {
		t.Fatalf("valid input was blocked: %v", reasons)
	}

	invalid := domain.CreateReleaseInput{ContentPurpose: "model-specific"}
	reasons := ReleaseInputGateReasons(invalid)
	for _, expected := range []string{"invalid_name", "invalid_version", "invalid_content_purpose", "invalid_source_count"} {
		if !slices.Contains(reasons, expected) {
			t.Fatalf("missing %q in %v", expected, reasons)
		}
	}
}
