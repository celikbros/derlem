package repository

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/celikbros/derlem/internal/domain"
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

// TestContentPurposeForTaskType, kayıt defterindeki HER tipin bir içerik amacı
// eşlemesi olduğunu zorlar: yeni tip eklenip amacı unutulursa üretimde kalıcı
// yanlış kaynak yerine burada kırmızı test çıkar.
func TestContentPurposeForTaskType(t *testing.T) {
	want := map[string]string{"qa_pair": "instruction", "free_text": "pretrain"}
	for taskType := range domain.ContributionTaskTypes {
		purpose, err := contentPurposeForTaskType(taskType)
		if err != nil {
			t.Fatalf("registry task type %q has no content_purpose mapping: %v", taskType, err)
		}
		if expected, ok := want[taskType]; ok && purpose != expected {
			t.Fatalf("%s purpose = %q, want %s", taskType, purpose, expected)
		}
	}
	if _, err := contentPurposeForTaskType("translation"); err == nil {
		t.Fatal("unknown task type must not fall through to a default content purpose")
	}
}
