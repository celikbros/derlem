package httpapi

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"slices"
	"strings"
	"testing"
)

func TestReviewThresholdRouteIsAdminOnlyAndNotDuplicated(t *testing.T) {
	existing := map[string]bool{}
	for _, route := range protectedRoutes(&Server{}) {
		existing[route.pattern] = true
	}
	routes := reviewThresholdRoutes(&Server{})
	if len(routes) != 1 || routes[0].pattern != "PUT /api/v1/sources/{id}/pretrain-review-threshold" {
		t.Fatalf("unexpected threshold routes: %#v", routes)
	}
	for _, route := range routes {
		if existing[route.pattern] || route.handler == nil {
			t.Fatalf("invalid threshold route %q", route.pattern)
		}
		if !slices.Equal(route.roles, []string{roleAdmin}) {
			t.Fatalf("threshold route roles = %v, want admin only", route.roles)
		}
		for _, role := range applicationRoles {
			assertRoleAccess(t, route.roles, role, role == roleAdmin)
		}
	}
}

func TestParsePretrainReviewThreshold(t *testing.T) {
	tests := []struct {
		raw    string
		ok     bool
		isNull bool
		value  float64
	}{
		{"10", true, false, 10},
		{"10.5", true, false, 10.5},
		{"null", true, true, 0},
		{"", false, false, 0},
		{`"10"`, false, false, 0},
		{"true", false, false, 0},
	}
	for _, test := range tests {
		value, ok := parsePretrainReviewThreshold(json.RawMessage(test.raw))
		if ok != test.ok {
			t.Fatalf("parse(%q) ok = %v, want %v", test.raw, ok, test.ok)
		}
		if !ok {
			continue
		}
		if test.isNull != (value == nil) || (value != nil && *value != test.value) {
			t.Fatalf("parse(%q) = %v", test.raw, value)
		}
	}
}

func TestSetPretrainReviewThresholdRequiresTheKey(t *testing.T) {
	server := &Server{}
	request := httptest.NewRequest(http.MethodPut, "/api/v1/sources/x/pretrain-review-threshold", strings.NewReader(`{}`))
	response := httptest.NewRecorder()
	server.setPretrainReviewThreshold(response, request)
	if response.Code != http.StatusUnprocessableEntity {
		t.Fatalf("status = %d, want 422", response.Code)
	}
	request = httptest.NewRequest(http.MethodPut, "/api/v1/sources/x/pretrain-review-threshold",
		strings.NewReader(`{"threshold": 10}`))
	response = httptest.NewRecorder()
	server.setPretrainReviewThreshold(response, request)
	if response.Code != http.StatusBadRequest {
		t.Fatalf("unknown field status = %d, want 400", response.Code)
	}
}
