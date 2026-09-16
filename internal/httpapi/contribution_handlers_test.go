package httpapi

import (
	"net/http"
	"net/http/httptest"
	"slices"
	"strings"
	"testing"

	"github.com/celikbros/derlem/internal/domain"
)

func TestContributionValidationAcceptsQAPair(t *testing.T) {
	input := domain.SubmitContributionInput{
		TaskType:    "qa_pair",
		Domain:      "fizik",
		Prompt:      "Newton'un ikinci yasası nedir?",
		Body:        "Kuvvet, kütle ile ivmenin çarpımıdır.",
		AcceptTerms: true,
	}
	if reasons := normalizeAndValidateContribution(&input); len(reasons) != 0 {
		t.Fatalf("expected valid input, got reasons: %v", reasons)
	}
	if input.DataOrigin != "human" {
		t.Fatalf("data origin default = %q, want human", input.DataOrigin)
	}
}

func TestContributionValidationRejectsBadInput(t *testing.T) {
	cases := map[string]domain.SubmitContributionInput{
		"unknown task type": {TaskType: "translation", Body: "metin", AcceptTerms: true},
		"qa without prompt": {TaskType: "qa_pair", Body: "cevap", AcceptTerms: true},
		// Serbest metinde soru alanı demete girmez; kabul edip düşürmek yerine reddedilir.
		"free text with prompt": {TaskType: "free_text", Prompt: "soru", Body: "metin", AcceptTerms: true},
		"empty body":            {TaskType: "free_text", Body: "   ", AcceptTerms: true},
		"terms not acked":       {TaskType: "free_text", Body: "metin", AcceptTerms: false},
		"body too long":         {TaskType: "free_text", Body: strings.Repeat("a", 100001), AcceptTerms: true},
		"prompt too long":       {TaskType: "qa_pair", Prompt: strings.Repeat("s", 10001), Body: "cevap", AcceptTerms: true},
		"domain too long":       {TaskType: "free_text", Domain: strings.Repeat("d", 101), Body: "metin", AcceptTerms: true},
	}
	for name, input := range cases {
		if reasons := normalizeAndValidateContribution(&input); len(reasons) == 0 {
			t.Errorf("%s: expected validation reasons, got none", name)
		}
	}
}

func TestContributionValidationNamesEveryRegisteredTaskType(t *testing.T) {
	input := domain.SubmitContributionInput{TaskType: "translation", Body: "metin", AcceptTerms: true}
	reasons := normalizeAndValidateContribution(&input)
	joined := strings.Join(reasons, " ")
	for taskType := range domain.ContributionTaskTypes {
		if !strings.Contains(joined, taskType) {
			t.Errorf("unknown-type message does not name registered type %q: %v", taskType, reasons)
		}
	}
}

func validEditPair() domain.SubmitContributionInput {
	return domain.SubmitContributionInput{
		TaskType: "response_edit_pair",
		Domain:   "fizik",
		Prompt:   "Işık hızı nedir?",
		Body:     "Boşlukta yaklaşık 299.792 km/s'dir.",
		Payload: map[string]string{
			"original_response": "  Saniyede 300 km'dir.  ",
			"edit_note":         "Birim ve büyüklük düzeltildi.",
		},
		AcceptTerms: true,
	}
}

func TestContributionValidationAcceptsAndNormalizesEditPair(t *testing.T) {
	input := validEditPair()
	input.Payload["edit_note"] = "   "

	if reasons := normalizeAndValidateContribution(&input); len(reasons) != 0 {
		t.Fatalf("expected valid edit pair, got reasons: %v", reasons)
	}
	if input.Payload["original_response"] != "Saniyede 300 km'dir." {
		t.Fatalf("payload value not trimmed: %q", input.Payload["original_response"])
	}
	if _, present := input.Payload["edit_note"]; present {
		t.Fatal("empty optional payload key must be dropped, not stored as an empty string")
	}
}

func TestContributionValidationRejectsBadEditPairsAndOrigins(t *testing.T) {
	cases := map[string]struct {
		mutate func(*domain.SubmitContributionInput)
		reason string
	}{
		"missing original response": {
			mutate: func(input *domain.SubmitContributionInput) { delete(input.Payload, "original_response") },
			reason: "Orijinal cevap zorunludur",
		},
		"unknown payload key is named": {
			mutate: func(input *domain.SubmitContributionInput) { input.Payload["score"] = "5" },
			reason: "payload.score bu görev tipinde kullanılmaz",
		},
		"edit changes only whitespace": {
			mutate: func(input *domain.SubmitContributionInput) {
				input.Payload["original_response"] = "Boşlukta   yaklaşık\n299.792 km/s'dir."
			},
			reason: "Orijinal cevap ile Düzeltilmiş cevap aynı",
		},
		"edit pair without prompt": {
			mutate: func(input *domain.SubmitContributionInput) { input.Prompt = "  " },
			reason: "soru boş olamaz",
		},
		"original response too long": {
			mutate: func(input *domain.SubmitContributionInput) {
				input.Payload["original_response"] = strings.Repeat("ç", 100001)
			},
			reason: "Orijinal cevap 100000 karakteri aşamaz",
		},
		"payload on a type that declares none": {
			mutate: func(input *domain.SubmitContributionInput) {
				input.TaskType = "qa_pair"
				input.Payload = map[string]string{"original_response": "x"}
			},
			reason: "payload.original_response bu görev tipinde kullanılmaz",
		},
		"model origin without model id": {
			mutate: func(input *domain.SubmitContributionInput) { input.DataOrigin = "model" },
			reason: "model adı zorunludur",
		},
		"human origin with model id": {
			mutate: func(input *domain.SubmitContributionInput) { input.ModelID = "model-x" },
			reason: "yalnız model ya da karma kökenli",
		},
		"unknown origin": {
			mutate: func(input *domain.SubmitContributionInput) { input.DataOrigin = "robot" },
			reason: "Köken unknown, human, model veya hybrid",
		},
		"model id too long": {
			mutate: func(input *domain.SubmitContributionInput) {
				input.DataOrigin = "hybrid"
				input.ModelID = strings.Repeat("m", 201)
			},
			reason: "Model adı 200 karakteri aşamaz",
		},
	}
	for name, tc := range cases {
		input := validEditPair()
		tc.mutate(&input)
		reasons := normalizeAndValidateContribution(&input)
		if !slices.ContainsFunc(reasons, func(reason string) bool { return strings.Contains(reason, tc.reason) }) {
			t.Errorf("%s: want a reason containing %q, got %v", name, tc.reason, reasons)
		}
	}
}

func TestContributionValidationAcceptsHybridOriginWithModelID(t *testing.T) {
	input := validEditPair()
	input.DataOrigin = "hybrid"
	input.ModelID = "model-x"
	if reasons := normalizeAndValidateContribution(&input); len(reasons) != 0 {
		t.Fatalf("expected valid hybrid edit pair, got reasons: %v", reasons)
	}
}

func TestBundleValidationDefaultsLanguage(t *testing.T) {
	input := domain.BundleContributionsInput{TaskType: "qa_pair", Name: "katkilar", Domain: "genel"}
	if reasons := normalizeAndValidateBundle(&input); len(reasons) != 0 {
		t.Fatalf("expected valid input, got reasons: %v", reasons)
	}
	if input.Language != "tr" {
		t.Fatalf("expected default language tr, got %q", input.Language)
	}
}

func TestBundleValidationRequiresNameAndDomain(t *testing.T) {
	input := domain.BundleContributionsInput{TaskType: "free_text"}
	reasons := normalizeAndValidateBundle(&input)
	if len(reasons) != 2 {
		t.Fatalf("expected 2 reasons (name, domain), got %v", reasons)
	}
}

func TestSubmitContributionRejectsInvalidPayloadBeforeRepository(t *testing.T) {
	request := httptest.NewRequest(http.MethodPost, "/api/v1/contributions", strings.NewReader(`{
		"task_type":"qa_pair",
		"body":"cevap var soru yok",
		"accept_terms":true
	}`))
	response := httptest.NewRecorder()

	(&Server{}).submitContribution(response, request)

	if response.Code != http.StatusUnprocessableEntity {
		t.Fatalf("unexpected status: got %d want %d", response.Code, http.StatusUnprocessableEntity)
	}
	if !strings.Contains(response.Body.String(), `"code":"contribution_validation_failed"`) {
		t.Fatalf("unexpected response body: %s", response.Body.String())
	}
}

func TestContributionSubmitClosedToReviewers(t *testing.T) {
	const pattern = "POST /api/v1/contributions"
	for _, route := range protectedRoutes(&Server{}) {
		if route.pattern != pattern {
			continue
		}
		if !slices.Equal(route.roles, []string{roleAdmin, roleContributor}) {
			t.Fatalf("contribution submit roles = %v, want admin+contributor", route.roles)
		}
		for _, role := range applicationRoles {
			assertRoleAccess(t, route.roles, role, role == roleAdmin || role == roleContributor)
		}
		return
	}
	t.Fatalf("route %q not found", pattern)
}

func TestContributionPoolAndBundleAreManagerOnly(t *testing.T) {
	for _, pattern := range []string{"GET /api/v1/contributions", "POST /api/v1/contribution-bundles"} {
		found := false
		for _, route := range protectedRoutes(&Server{}) {
			if route.pattern != pattern {
				continue
			}
			found = true
			if !slices.Equal(route.roles, []string{roleAdmin, roleDataManager}) {
				t.Fatalf("%s roles = %v, want admin+data_manager", pattern, route.roles)
			}
			for _, role := range applicationRoles {
				assertRoleAccess(t, route.roles, role, role == roleAdmin || role == roleDataManager)
			}
		}
		if !found {
			t.Fatalf("route %q not found", pattern)
		}
	}
}
