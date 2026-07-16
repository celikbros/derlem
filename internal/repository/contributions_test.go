package repository

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestBuildContributionJSONLFormatsQAPairs(t *testing.T) {
	payload, err := buildContributionJSONL("qa_pair", []bundleItem{
		{ID: "id-1", Prompt: "Işık hızı nedir?", Body: "Yaklaşık 300.000 km/s'dir."},
		{ID: "id-2", Prompt: "Soru 2", Body: "Cevap 2"},
	})
	if err != nil {
		t.Fatalf("build jsonl: %v", err)
	}

	lines := strings.Split(strings.TrimRight(string(payload), "\n"), "\n")
	if len(lines) != 2 {
		t.Fatalf("expected 2 lines, got %d: %q", len(lines), string(payload))
	}

	var record map[string]string
	if err := json.Unmarshal([]byte(lines[0]), &record); err != nil {
		t.Fatalf("line 0 is not valid JSON: %v", err)
	}
	if record["id"] != "id-1" {
		t.Fatalf("unexpected id: %q", record["id"])
	}
	if record["text"] != "Soru: Işık hızı nedir?\n\nCevap: Yaklaşık 300.000 km/s'dir." {
		t.Fatalf("unexpected qa text: %q", record["text"])
	}
	if strings.Contains(lines[0], `\u`) {
		t.Fatalf("expected raw UTF-8 output, got escaped sequence: %s", lines[0])
	}
}

func TestBuildContributionJSONLKeepsFreeTextVerbatim(t *testing.T) {
	payload, err := buildContributionJSONL("free_text", []bundleItem{
		{ID: "id-1", Body: "Birinci satır.\nİkinci satır aynı belgede."},
	})
	if err != nil {
		t.Fatalf("build jsonl: %v", err)
	}

	lines := strings.Split(strings.TrimRight(string(payload), "\n"), "\n")
	if len(lines) != 1 {
		t.Fatalf("multi-line body must stay a single JSONL line, got %d lines", len(lines))
	}
	var record map[string]string
	if err := json.Unmarshal([]byte(lines[0]), &record); err != nil {
		t.Fatalf("line is not valid JSON: %v", err)
	}
	if record["text"] != "Birinci satır.\nİkinci satır aynı belgede." {
		t.Fatalf("unexpected text: %q", record["text"])
	}
}

func TestContentPurposeForTaskType(t *testing.T) {
	if purpose := contentPurposeForTaskType("qa_pair"); purpose != "instruction" {
		t.Fatalf("qa_pair purpose = %q, want instruction", purpose)
	}
	if purpose := contentPurposeForTaskType("free_text"); purpose != "pretrain" {
		t.Fatalf("free_text purpose = %q, want pretrain", purpose)
	}
}
