package httpapi

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/celikbros/derlem/internal/domain"
	"github.com/celikbros/derlem/internal/repository"
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

func TestDistillationProviderAllowlist(t *testing.T) {
	for _, provider := range []string{"anthropic", "openai", "google", "xai", "alibaba", "echo"} {
		if !distillationProviders[provider] {
			t.Errorf("expected provider %q to be allowed", provider)
		}
	}
	for _, provider := range []string{"", "Anthropic", "custom", "https://attacker.invalid"} {
		if distillationProviders[provider] {
			t.Errorf("expected provider %q to be rejected", provider)
		}
	}
}

func TestDistillationRequestRejectsCredentialSelector(t *testing.T) {
	request := httptest.NewRequest(http.MethodPost, "/api/v1/sources/source-id/distill", strings.NewReader(`{
		"provider":"anthropic",
		"model":"claude-opus-4-8",
		"api_key_env":"DATABASE_URL",
		"prompt_template":"fizik hakkında yaz",
		"count":1
	}`))
	response := httptest.NewRecorder()
	var input repository.DistillationInput

	if decodeJSON(response, request, &input) {
		t.Fatal("api_key_env must not be accepted by the distillation API contract")
	}
	if response.Code != http.StatusBadRequest {
		t.Fatalf("unexpected status: got %d want %d", response.Code, http.StatusBadRequest)
	}
}

func TestDistillSourceRejectsProviderOutsideAllowlist(t *testing.T) {
	request := httptest.NewRequest(http.MethodPost, "/api/v1/sources/source-id/distill", strings.NewReader(`{
		"provider":"custom",
		"model":"anything",
		"prompt_template":"fizik hakkında yaz",
		"count":1
	}`))
	request.SetPathValue("id", "source-id")
	response := httptest.NewRecorder()

	(&Server{}).distillSource(response, request)

	if response.Code != http.StatusUnprocessableEntity {
		t.Fatalf("unexpected status: got %d want %d", response.Code, http.StatusUnprocessableEntity)
	}
	if !strings.Contains(response.Body.String(), `"code":"invalid_provider"`) {
		t.Fatalf("unexpected response body: %s", response.Body.String())
	}
}
