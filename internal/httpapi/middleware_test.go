package httpapi

import (
	"context"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"regexp"
	"testing"

	"github.com/celikbros/derlem/internal/auth"
)

func TestMiddlewareAddsRequestIDAndCapturesResponse(t *testing.T) {
	server := &Server{
		logger:    slog.New(slog.NewTextHandler(io.Discard, nil)),
		webOrigin: "http://localhost:3000",
	}
	handler := server.middleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if state := requestAuditStateFrom(r.Context()); state == nil || state.RequestID == "" {
			t.Fatal("request audit state was not attached")
		}
		w.WriteHeader(http.StatusAccepted)
		_, _ = w.Write([]byte("ok"))
	}))

	request := httptest.NewRequest(http.MethodPost, "http://api.test/api/v1/example", nil)
	request.Header.Set("Origin", "http://localhost:3000")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)

	if response.Code != http.StatusAccepted {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusAccepted)
	}
	requestID := response.Header().Get("X-Request-ID")
	uuidV4 := regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`)
	if !uuidV4.MatchString(requestID) {
		t.Fatalf("X-Request-ID = %q, want UUID v4", requestID)
	}
	if got := response.Header().Get("Access-Control-Allow-Methods"); got != "GET, POST, PATCH, DELETE, OPTIONS" {
		t.Fatalf("Access-Control-Allow-Methods = %q", got)
	}
	if got := response.Header().Get("Access-Control-Expose-Headers"); got != "X-Request-ID" {
		t.Fatalf("Access-Control-Expose-Headers = %q", got)
	}
}

func TestRequireRolesMarksForbiddenAuditState(t *testing.T) {
	state := &requestAuditState{RequestID: "00000000-0000-4000-8000-000000000000"}
	ctx := context.WithValue(context.Background(), requestAuditKey{}, state)
	ctx = context.WithValue(ctx, principalKey{}, auth.Claims{
		Subject: "11111111-1111-4111-8111-111111111111",
		Roles:   []string{"moderator"},
	})
	request := httptest.NewRequest(http.MethodGet, "http://api.test/api/v1/admin", nil).WithContext(ctx)
	response := httptest.NewRecorder()
	handler := requireRoles("admin")(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		t.Fatal("forbidden request reached handler")
	}))

	handler.ServeHTTP(response, request)

	if response.Code != http.StatusForbidden {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusForbidden)
	}
	if state.FailureCode != "forbidden" {
		t.Fatalf("failure code = %q, want forbidden", state.FailureCode)
	}
}

func TestSetRequestAuditPrincipalHashesSessionIdentity(t *testing.T) {
	state := &requestAuditState{}
	ctx := context.WithValue(context.Background(), requestAuditKey{}, state)
	claims := auth.Claims{
		Subject: "11111111-1111-4111-8111-111111111111",
		Roles:   []string{"moderator"},
		JWTID:   "raw-session-secret",
	}

	setRequestAuditPrincipal(ctx, claims)

	if state.ActorID != claims.Subject {
		t.Fatalf("actor id = %q", state.ActorID)
	}
	if state.SessionHash == "" || state.SessionHash == claims.JWTID {
		t.Fatal("session identity must be stored only as a non-empty hash")
	}
}

func TestWriteErrorMarksAuditFailureCode(t *testing.T) {
	state := &requestAuditState{}
	response := httptest.NewRecorder()
	recorder := &responseStatusRecorder{ResponseWriter: response, auditState: state}

	writeError(recorder, http.StatusUnauthorized, "invalid_credentials", "private message")

	if state.FailureCode != "invalid_credentials" {
		t.Fatalf("failure code = %q, want invalid_credentials", state.FailureCode)
	}
	if response.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusUnauthorized)
	}
}
