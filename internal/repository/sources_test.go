package repository

import "testing"

func TestDistillationJobPayloadContainsNoCredentialSelector(t *testing.T) {
	payload := distillationJobPayload("source-id", DistillationInput{
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
}
