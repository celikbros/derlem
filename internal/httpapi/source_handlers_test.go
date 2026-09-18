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

func TestCreateSourceValidationRejectsInvalidDerivedParentID(t *testing.T) {
	parentID := "not-a-uuid"
	input := domain.CreateSourceInput{
		Name: "Source", SourceType: "jsonl", ContentPurpose: "pretrain",
		License: "internal", RightsStatus: "unknown", Language: "tr",
		Domain: "general", LineageRef: "source.jsonl", DerivedFromSourceID: &parentID,
	}
	if message := normalizeAndValidateSource(&input); !strings.Contains(message, "UUID") {
		t.Fatalf("unexpected validation message: %q", message)
	}
}

func TestCreateSourceValidationNormalizesDerivedParentID(t *testing.T) {
	parentID := " 06AC330E-350F-45F0-B596-3DD4AA1DBC57 "
	input := domain.CreateSourceInput{
		Name: "Source", SourceType: "jsonl", ContentPurpose: "pretrain",
		License: "internal", RightsStatus: "unknown", Language: "tr",
		Domain: "general", LineageRef: "source.jsonl", DerivedFromSourceID: &parentID,
	}
	if message := normalizeAndValidateSource(&input); message != "" {
		t.Fatalf("unexpected validation failure: %s", message)
	}
	if input.DerivedFromSourceID == nil || *input.DerivedFromSourceID != "06ac330e-350f-45f0-b596-3dd4aa1dbc57" {
		t.Fatalf("parent id was not normalized: %#v", input.DerivedFromSourceID)
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

// Çoklu girdi soyu (000029): kimlikler kanonik UUID olmalı, küçük harfe
// çevrilir, tekrarları atılır ve sıralanır; güncellemede nil "dokunma" demektir.
func TestCreateSourceValidationNormalizesLineageInputIDs(t *testing.T) {
	input := domain.CreateSourceInput{
		Name: "Source", SourceType: "jsonl", ContentPurpose: "pretrain",
		License: "internal", RightsStatus: "unknown", Language: "tr",
		Domain: "general", LineageRef: "source.jsonl",
		LineageInputSourceIDs: []string{
			" 0A178606-2B3C-4D5E-8F90-123456789ABC ",
			"0a178606-2b3c-4d5e-8f90-123456789abc",
			"00000000-0000-4000-8000-000000000001",
		},
	}
	if message := normalizeAndValidateSource(&input); message != "" {
		t.Fatalf("unexpected validation message: %q", message)
	}
	want := []string{"00000000-0000-4000-8000-000000000001", "0a178606-2b3c-4d5e-8f90-123456789abc"}
	if strings.Join(input.LineageInputSourceIDs, ",") != strings.Join(want, ",") {
		t.Fatalf("lineage inputs not normalized: %#v", input.LineageInputSourceIDs)
	}

	input.LineageInputSourceIDs = []string{"not-a-uuid"}
	if message := normalizeAndValidateSource(&input); !strings.Contains(message, "UUID") {
		t.Fatalf("invalid lineage input must be rejected, got %q", message)
	}
}

func TestUpdateSourceValidationKeepsNilLineageInputsUntouched(t *testing.T) {
	input := domain.UpdateSourceInput{
		Name: "Source", SourceType: "jsonl", License: "internal", RightsStatus: "unknown",
		Language: "tr", Domain: "general", LineageRef: "source.jsonl", Version: 1,
	}
	if message := normalizeAndValidateSourceUpdate(&input); message != "" {
		t.Fatalf("unexpected validation message: %q", message)
	}
	if input.LineageInputSourceIDs != nil {
		t.Fatal("nil lineage inputs must stay nil so the repository leaves the list untouched")
	}
	input.LineageInputSourceIDs = []string{}
	if message := normalizeAndValidateSourceUpdate(&input); message != "" || input.LineageInputSourceIDs == nil {
		t.Fatalf("an empty list must survive as an explicit clear, got %q / %#v", message, input.LineageInputSourceIDs)
	}
}
