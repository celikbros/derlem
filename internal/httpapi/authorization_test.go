package httpapi

import (
	"context"
	"net/http"
	"net/http/httptest"
	"slices"
	"strings"
	"testing"

	"github.com/celikbros/derlem/internal/auth"
)

func TestProtectedRoutesHaveExplicitKnownRoles(t *testing.T) {
	seen := map[string]bool{}
	for _, route := range protectedRoutes(&Server{}) {
		if strings.TrimSpace(route.pattern) == "" || route.handler == nil {
			t.Fatalf("invalid protected route: %#v", route)
		}
		if seen[route.pattern] {
			t.Fatalf("duplicate protected route %q", route.pattern)
		}
		seen[route.pattern] = true
		if len(route.roles) == 0 {
			t.Fatalf("route %q has no roles", route.pattern)
		}
		for _, role := range route.roles {
			if !slices.Contains(applicationRoles, role) {
				t.Fatalf("route %q contains unknown role %q", route.pattern, role)
			}
		}
	}
}

func TestReadRouteAuthorizationMatrix(t *testing.T) {
	workspace := []string{roleAdmin, roleDataManager, roleEditor, roleModerator, roleExpertReviewer}
	reviewers := []string{roleAdmin, roleModerator, roleExpertReviewer}
	releases := []string{roleAdmin, roleDataManager, roleConsumerTeam}
	expected := map[string][]string{
		"GET /api/v1/sources":                                    workspace,
		"GET /api/v1/sources/{id}":                               workspace,
		"GET /api/v1/sources/{id}/reviews":                       workspace,
		"GET /api/v1/sources/{id}/pii-scans":                     workspace,
		"GET /api/v1/sources/{id}/documents":                     workspace,
		"GET /api/v1/sources/{id}/document-quality-summary":      workspace,
		"GET /api/v1/sources/{id}/document-sample-generations":   workspace,
		"GET /api/v1/documents/{id}":                             workspace,
		"GET /api/v1/documents/{id}/reviews":                     workspace,
		"GET /api/v1/jobs":                                       {roleAdmin, roleDataManager},
		"GET /api/v1/releases":                                   releases,
		"GET /api/v1/releases/{id}":                              releases,
		"GET /api/v1/releases/{id}/manifest":                     releases,
		"GET /api/v1/releases/{id}/exports/{format}/artifact":    releases,
		"GET /api/v1/releases/{id}/exports/{format}/manifest":    releases,
		"GET /api/v1/releases/{id}/sources/{source_id}/artifact": releases,
		"GET /api/v1/similarity-calibrations":                    reviewers,
		"GET /api/v1/similarity-calibrations/{id}/pairs":         reviewers,
		"GET /api/v1/similarity-pairs/{id}":                      reviewers,
	}

	tested := map[string]bool{}
	for _, route := range protectedRoutes(&Server{}) {
		if !strings.HasPrefix(route.pattern, "GET ") {
			continue
		}
		allowed, ok := expected[route.pattern]
		if !ok {
			t.Fatalf("GET route %q is missing from the authorization test matrix", route.pattern)
		}
		tested[route.pattern] = true
		for _, role := range applicationRoles {
			t.Run(route.pattern+"/"+role, func(t *testing.T) {
				assertRoleAccess(t, route.roles, role, slices.Contains(allowed, role))
			})
		}
	}
	if len(tested) != len(expected) {
		t.Fatalf("tested %d GET routes, matrix contains %d", len(tested), len(expected))
	}
}

func TestConsumerCannotReadDraftRelease(t *testing.T) {
	if canReadDraftReleases([]string{roleConsumerTeam}) {
		t.Fatal("consumer must not read draft releases")
	}
	if !canReadDraftReleases([]string{roleAdmin}) {
		t.Fatal("admin must read draft releases")
	}
	if !canReadDraftReleases([]string{roleDataManager}) {
		t.Fatal("data manager must read draft releases")
	}
}

func assertRoleAccess(t *testing.T, allowedRoles []string, role string, wantAllowed bool) {
	t.Helper()
	called := false
	next := http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		called = true
		w.WriteHeader(http.StatusNoContent)
	})
	request := httptest.NewRequest(http.MethodGet, "/", nil)
	request = request.WithContext(context.WithValue(
		request.Context(),
		principalKey{},
		auth.Claims{Roles: []string{role}},
	))
	response := httptest.NewRecorder()
	requireRoles(allowedRoles...)(next).ServeHTTP(response, request)

	if wantAllowed {
		if !called || response.Code != http.StatusNoContent {
			t.Fatalf("role %q was denied: called=%v status=%d", role, called, response.Code)
		}
		return
	}
	if called || response.Code != http.StatusForbidden {
		t.Fatalf("role %q was not denied: called=%v status=%d", role, called, response.Code)
	}
}
