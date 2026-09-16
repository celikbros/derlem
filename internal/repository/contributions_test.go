package repository

import (
	"bytes"
	"encoding/json"
	"os"
	"strings"
	"testing"

	"github.com/celikbros/derlem/internal/domain"
)

// goldenBundleFixture, Go demet yayınının Python ayrıştırıcısıyla ortak
// sözleşmesi. CI'da backend ve worker ayrı işlerdir; iki dili bağlayan tek şey
// bu dosyadır. Yeniden üretmek için: DERLEM_UPDATE_GOLDEN=1 go test ./internal/repository/ -run Golden
const goldenBundleFixture = "../../data_samples/example_contribution_bundles.jsonl"

func stringPointer(value string) *string { return &value }

func goldenBundleItems() (qaPairs, editPairs []bundleItem) {
	qaPairs = []bundleItem{
		{
			ID: "00000000-0000-4000-8000-000000000001", Domain: "fizik",
			Prompt: "Işık hızı nedir?", Body: "Boşlukta yaklaşık 299.792 km/s'dir.",
			Payload: map[string]string{"knowledge_source": "Fizik 10 ders kitabı, s. 45"}, DataOrigin: "human",
		},
		{
			ID: "00000000-0000-4000-8000-000000000002", Domain: "",
			Prompt: "Yerçekimi ivmesi kaçtır?", Body: "Deniz seviyesinde yaklaşık 9,81 m/s²'dir.",
			Payload: map[string]string{}, DataOrigin: "hybrid", ModelID: stringPointer("model-x"),
		},
	}
	editPairs = []bundleItem{
		{
			ID: "00000000-0000-4000-8000-000000000003", Domain: "fizik",
			Prompt: "Ses boşlukta yayılır mı?", Body: "Hayır; ses yayılmak için bir ortam ister.",
			Payload: map[string]string{
				"original_response": "Evet, ses her yerde yayılır.",
				"edit_note":         "Fiziksel olarak yanlış olan cevap düzeltildi.",
				"knowledge_source":  "Bilim belgeseli",
			},
			DataOrigin: "human",
		},
	}
	return qaPairs, editPairs
}

func buildGoldenBundle(t *testing.T) []byte {
	t.Helper()
	qaPairs, editPairs := goldenBundleItems()
	var golden bytes.Buffer
	for _, part := range []struct {
		taskType string
		items    []bundleItem
	}{{"qa_pair", qaPairs}, {"response_edit_pair", editPairs}} {
		purpose, err := contentPurposeForTaskType(part.taskType)
		if err != nil {
			t.Fatalf("purpose for %s: %v", part.taskType, err)
		}
		payload, err := buildContributionJSONL(part.taskType, purpose, "tr", part.items)
		if err != nil {
			t.Fatalf("build %s bundle: %v", part.taskType, err)
		}
		golden.Write(payload)
	}
	return golden.Bytes()
}

func decodeLines(t *testing.T, payload []byte) []map[string]any {
	t.Helper()
	lines := strings.Split(strings.TrimRight(string(payload), "\n"), "\n")
	records := make([]map[string]any, 0, len(lines))
	for index, line := range lines {
		var record map[string]any
		if err := json.Unmarshal([]byte(line), &record); err != nil {
			t.Fatalf("line %d is not valid JSON: %v", index, err)
		}
		records = append(records, record)
	}
	return records
}

func TestContributionBundleGoldenFixture(t *testing.T) {
	built := buildGoldenBundle(t)
	if os.Getenv("DERLEM_UPDATE_GOLDEN") == "1" {
		if err := os.WriteFile(goldenBundleFixture, built, 0o644); err != nil {
			t.Fatalf("write golden fixture: %v", err)
		}
	}
	golden, err := os.ReadFile(goldenBundleFixture)
	if err != nil {
		t.Fatalf("read golden fixture (regenerate with DERLEM_UPDATE_GOLDEN=1): %v", err)
	}
	if !bytes.Equal(built, golden) {
		t.Fatalf("bundle emission drifted from %s; if intended, regenerate it AND run the worker contract test.\nbuilt:\n%s\ngolden:\n%s",
			goldenBundleFixture, built, golden)
	}
}

func TestBuildContributionJSONLEmitsCanonicalQAPairs(t *testing.T) {
	qaPairs, _ := goldenBundleItems()
	payload, err := buildContributionJSONL("qa_pair", "instruction", "tr", qaPairs)
	if err != nil {
		t.Fatalf("build jsonl: %v", err)
	}
	if strings.Contains(string(payload), `\u`) {
		t.Fatalf("expected raw UTF-8 output, got escaped sequences: %s", payload)
	}
	records := decodeLines(t, payload)
	if len(records) != 2 {
		t.Fatalf("expected 2 records, got %d", len(records))
	}

	first := records[0]
	for key, want := range map[string]string{
		"schema_version":  "derlem.canonical-sample.v1",
		"record_type":     "conversation",
		"sample_id":       "00000000-0000-4000-8000-000000000001",
		"content_purpose": "instruction",
		"task_type":       "qa_pair",
		"language":        "tr",
		"domain":          "fizik",
		"train_policy":    "assistant_only",
	} {
		if first[key] != want {
			t.Errorf("%s = %v, want %q", key, first[key], want)
		}
	}
	messages := first["messages"].([]any)
	user := messages[0].(map[string]any)
	assistant := messages[1].(map[string]any)
	if user["role"] != "user" || user["content"] != "Işık hızı nedir?" ||
		assistant["role"] != "assistant" || assistant["content"] != "Boşlukta yaklaşık 299.792 km/s'dir." {
		t.Fatalf("question/answer not carried as separate messages: %v", messages)
	}
	if source := first["metadata"].(map[string]any)["knowledge_source"]; source != "Fizik 10 ders kitabı, s. 45" {
		t.Fatalf("knowledge source must travel in metadata, got %v", source)
	}

	second := records[1]
	if _, present := second["domain"]; present {
		t.Fatal("an empty domain must be omitted: the canonical parser rejects empty strings")
	}
	metadata := second["metadata"].(map[string]any)
	if metadata["data_origin"] != "hybrid" || metadata["model_id"] != "model-x" {
		t.Fatalf("origin and model id must travel in metadata, got %v", metadata)
	}
	for _, record := range records {
		if _, present := record["created_by"]; present {
			t.Fatal("contributor identity must never be written into the bundle")
		}
	}
}

func TestBuildContributionJSONLEmitsEditPairAsPreference(t *testing.T) {
	_, editPairs := goldenBundleItems()
	payload, err := buildContributionJSONL("response_edit_pair", "preference", "tr", editPairs)
	if err != nil {
		t.Fatalf("build jsonl: %v", err)
	}
	record := decodeLines(t, payload)[0]
	if record["record_type"] != "preference" || record["content_purpose"] != "preference" {
		t.Fatalf("edit pair must be a preference record: %v", record)
	}
	preference := record["preference"].(map[string]any)
	chosen := preference["chosen"].([]any)[0].(map[string]any)
	rejected := preference["rejected"].([]any)[0].(map[string]any)
	if chosen["content"] != "Hayır; ses yayılmak için bir ortam ister." {
		t.Fatalf("chosen must be the edited answer, got %v", chosen)
	}
	if rejected["content"] != "Evet, ses her yerde yayılır." {
		t.Fatalf("rejected must be the original answer, got %v", rejected)
	}
	metadata := record["metadata"].(map[string]any)
	if metadata["edit_note"] != "Fiziksel olarak yanlış olan cevap düzeltildi." ||
		metadata["knowledge_source"] != "Bilim belgeseli" {
		t.Fatalf("remaining payload keys must travel in metadata, got %v", metadata)
	}
	if _, present := metadata["original_response"]; present {
		t.Fatal("original_response is the rejected branch; it must not be duplicated into metadata")
	}
}

func TestBuildContributionJSONLKeepsFreeTextVerbatim(t *testing.T) {
	payload, err := buildContributionJSONL("free_text", "pretrain", "tr", []bundleItem{
		{ID: "id-1", Body: "Birinci satır.\nİkinci satır aynı belgede.", DataOrigin: "human"},
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
	if record["text"] != "Birinci satır.\nİkinci satır aynı belgede." || len(record) != 2 {
		t.Fatalf("free text must stay a plain {id,text} line, got %v", record)
	}
}

func TestBuildContributionJSONLRefusesEditPairWithoutRejectedBranch(t *testing.T) {
	_, editPairs := goldenBundleItems()
	editPairs[0].Payload = map[string]string{}
	if _, err := buildContributionJSONL("response_edit_pair", "preference", "tr", editPairs); err == nil {
		t.Fatal("an edit pair without original_response must not be emitted with an empty rejected branch")
	}
}

func TestBuildContributionJSONLRefusesUnknownTaskType(t *testing.T) {
	if _, err := buildContributionJSONL("translation_pair", "instruction", "tr", nil); err == nil {
		t.Fatal("a task type without a registry emission must be refused")
	}
}

// TestContentPurposeForTaskType, kayıt defterindeki HER tipin bir içerik amacı
// eşlemesi ve demet yayın biçimi olduğunu zorlar: yeni tip eklenip biri
// unutulursa üretimde kalıcı yanlış kaynak ya da kayıp alan yerine burada kırmızı
// test çıkar.
func TestContentPurposeForTaskType(t *testing.T) {
	want := map[string]string{"qa_pair": "instruction", "free_text": "pretrain", "response_edit_pair": "preference"}
	for taskType, entry := range domain.ContributionTaskTypes {
		purpose, err := contentPurposeForTaskType(taskType)
		if err != nil {
			t.Fatalf("registry task type %q has no content_purpose mapping: %v", taskType, err)
		}
		if expected, ok := want[taskType]; ok && purpose != expected {
			t.Fatalf("%s purpose = %q, want %s", taskType, purpose, expected)
		}
		if entry.BundleEmission == "" {
			t.Fatalf("registry task type %q has no bundle emission", taskType)
		}
	}
	if _, err := contentPurposeForTaskType("translation"); err == nil {
		t.Fatal("unknown task type must not fall through to a default content purpose")
	}
}
