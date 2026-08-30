package repository

import (
	"strings"
	"testing"
)

func TestDistillationJobPayloadContainsNoCredentialSelector(t *testing.T) {
	payload := distillationJobPayload("source-id", "run-id", DistillationInput{
		Provider:       "anthropic",
		Model:          "claude-opus-4-8",
		PromptTemplate: "{konu} hakkında yaz.",
		Topics:         []string{"fizik"},
	})

	if _, exists := payload["api_key_env"]; exists {
		t.Fatal("distillation job payload must not contain api_key_env")
	}
	if payload["provider"] != "anthropic" || payload["source_id"] != "source-id" {
		t.Fatalf("unexpected distillation payload: %#v", payload)
	}
	if payload["production_run_id"] != "run-id" {
		t.Fatalf("production run is not pinned in job payload: %#v", payload)
	}
}

func TestDistillationEvidenceDigestsAreDeterministicAndSensitiveToConfiguration(t *testing.T) {
	input := DistillationInput{
		Provider: "anthropic", Model: "claude-opus-4-8",
		SystemPrompt:   "Yaln\u0131z T\u00fcrk\u00e7e yaz.",
		PromptTemplate: "{konu} hakk\u0131nda yaz.",
		Topics:         []string{"fizik", "kimya"}, Count: 2, MaxTokens: 2048,
		Temperature: 0.7, SourceName: "distill-v1",
	}
	first, err := distillationConfigSHA256(input)
	if err != nil {
		t.Fatal(err)
	}
	second, err := distillationConfigSHA256(input)
	if err != nil {
		t.Fatal(err)
	}
	if first != second || len(first) != 64 {
		t.Fatalf("configuration digest is not deterministic SHA256: %q %q", first, second)
	}
	if first != "f8fa0f802fbb9e56fd233ac1d3069718c74e4def772dc558a976151f708c2a8c" {
		t.Fatalf("configuration digest broke the cross-runtime vector: %q", first)
	}
	input.Temperature = 0.8
	changed, err := distillationConfigSHA256(input)
	if err != nil {
		t.Fatal(err)
	}
	if changed == first {
		t.Fatal("configuration digest did not bind temperature")
	}
	implementation := distillationImplementationDigest()
	if len(implementation) != 64 || strings.Trim(implementation, "0123456789abcdef") != "" {
		t.Fatalf("implementation digest is not lowercase SHA256: %q", implementation)
	}
}
