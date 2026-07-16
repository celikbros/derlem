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
}

func TestContributionValidationRejectsBadInput(t *testing.T) {
	cases := map[string]domain.SubmitContributionInput{
		"unknown task type": {TaskType: "translation", Body: "metin", AcceptTerms: true},
		"qa without prompt": {TaskType: "qa_pair", Body: "cevap", AcceptTerms: true},
		"empty body":        {TaskType: "free_text", Body: "   ", AcceptTerms: true},
		"terms not acked":   {TaskType: "free_text", Body: "metin", AcceptTerms: false},
		"body too long":     {TaskType: "free_text", Body: strings.Repeat("a", 100001), AcceptTerms: true},
		"prompt too long":   {TaskType: "qa_pair", Prompt: strings.Repeat("s", 10001), Body: "cevap", AcceptTerms: true},
		"domain too long":   {TaskType: "free_text", Domain: strings.Repeat("d", 101), Body: "metin", AcceptTerms: true},
	}
	for name, input := range cases {
		if reasons := normalizeAndValidateContribution(&input); len(reasons) == 0 {
			t.Errorf("%s: expected validation reasons, got none", name)
		}
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
