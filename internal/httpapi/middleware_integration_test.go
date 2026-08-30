package httpapi

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/celikbros/derlem/internal/auth"
	"github.com/celikbros/derlem/internal/database"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

func TestMiddlewarePersistsRedactedHTTPRequestAudit(t *testing.T) {
	databaseURL := strings.TrimSpace(os.Getenv("DERLEM_TEST_DATABASE_URL"))
	if databaseURL == "" {
		t.Skip("DERLEM_TEST_DATABASE_URL is not set")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	t.Cleanup(cancel)
	adminPool, err := pgxpool.New(ctx, databaseURL)
	if err != nil {
		t.Fatalf("open admin pool: %v", err)
	}
	t.Cleanup(adminPool.Close)

	schemaName := fmt.Sprintf("derlem_http_audit_test_%d", time.Now().UnixNano())
	schemaIdentifier := pgx.Identifier{schemaName}.Sanitize()
	if _, err := adminPool.Exec(ctx, "CREATE SCHEMA "+schemaIdentifier); err != nil {
		t.Fatalf("create test schema: %v", err)
	}
	t.Cleanup(func() {
		cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cleanupCancel()
		if _, err := adminPool.Exec(cleanupCtx, "DROP SCHEMA "+schemaIdentifier+" CASCADE"); err != nil {
			t.Errorf("drop test schema: %v", err)
		}
	})

	config, err := pgxpool.ParseConfig(databaseURL)
	if err != nil {
		t.Fatalf("parse database URL: %v", err)
	}
	config.ConnConfig.RuntimeParams["search_path"] = schemaName
	pool, err := pgxpool.NewWithConfig(ctx, config)
	if err != nil {
		t.Fatalf("open isolated pool: %v", err)
	}
	t.Cleanup(pool.Close)
	if err := database.Migrate(ctx, pool); err != nil {
		t.Fatalf("migrate isolated schema: %v", err)
	}

	var actorID string
	if err := pool.QueryRow(ctx, `
		INSERT INTO users(email, password_hash, display_name)
		VALUES ('http-audit@example.test', 'not-a-real-password', 'HTTP Audit')
		RETURNING id::text
	`).Scan(&actorID); err != nil {
		t.Fatalf("insert actor: %v", err)
	}

	server := &Server{
		pool:     pool,
		tokens:   auth.NewTokenManager("01234567890123456789012345678901", "http-audit-test", time.Hour),
		sessions: auth.NewSessionStore(pool, time.Hour),
		loginLimiter: auth.NewLoginLimiter(pool, auth.LoginRatePolicy{
			AccountFailureLimit: 20,
			IPFailureLimit:      40,
			FailureWindow:       time.Hour,
			LockoutDuration:     time.Hour,
		}, "01234567890123456789012345678901"),
		logger: slog.New(slog.NewTextHandler(io.Discard, nil)),
	}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /api/v1/audit-probe/{id}", func(w http.ResponseWriter, r *http.Request) {
		setRequestAuditPrincipal(r.Context(), auth.Claims{
			Subject: actorID,
			Roles:   []string{"moderator"},
			JWTID:   "raw-session-marker-must-not-leak",
		})
		writeError(w, http.StatusForbidden, "forbidden", "private-response-marker")
	})
	handler := server.middleware(mux)
	request := httptest.NewRequest(
		http.MethodGet,
		"http://api.test/api/v1/audit-probe/private-path-marker?token=private-query-marker",
		nil,
	)
	request.Header.Set("Authorization", "Bearer private-authorization-marker")
	request.Header.Set("User-Agent", "private-user-agent-marker")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusForbidden {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusForbidden)
	}

	requestID := response.Header().Get("X-Request-ID")
	var storedActorID string
	var details string
	if err := pool.QueryRow(ctx, `
		SELECT actor_id::text, details::text
		FROM audit_events
		WHERE request_id = $1::uuid AND action = 'http.request'
	`, requestID).Scan(&storedActorID, &details); err != nil {
		t.Fatalf("read HTTP audit event: %v", err)
	}
	if storedActorID != actorID {
		t.Fatalf("actor id = %s, want %s", storedActorID, actorID)
	}
	for _, required := range []string{
		`"method": "GET"`,
		`"status": 403`,
		`"failure_code": "forbidden"`,
		`"route_pattern": "GET /api/v1/audit-probe/{id}"`,
		`"roles": ["moderator"]`,
	} {
		if !strings.Contains(details, required) {
			t.Errorf("audit details missing %q: %s", required, details)
		}
	}
	for _, forbidden := range []string{
		"private-path-marker",
		"private-query-marker",
		"private-authorization-marker",
		"private-user-agent-marker",
		"private-response-marker",
		"raw-session-marker-must-not-leak",
	} {
		if strings.Contains(details, forbidden) {
			t.Errorf("audit details leaked %q: %s", forbidden, details)
		}
	}

	protectedMux := http.NewServeMux()
	protectedMux.Handle(
		"GET /api/v1/admin-probe",
		server.authenticate(requireRoles("admin")(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
			writeJSON(w, http.StatusOK, map[string]string{"status": "unexpected"})
		}))),
	)
	protectedHandler := server.middleware(protectedMux)

	missingTokenRequest := httptest.NewRequest(
		http.MethodGet,
		"http://api.test/api/v1/admin-probe",
		nil,
	)
	missingTokenResponse := httptest.NewRecorder()
	protectedHandler.ServeHTTP(missingTokenResponse, missingTokenRequest)
	if missingTokenResponse.Code != http.StatusUnauthorized {
		t.Fatalf("missing-token status = %d, want %d", missingTokenResponse.Code, http.StatusUnauthorized)
	}
	missingTokenDetails := readHTTPRequestAuditDetails(
		t, ctx, pool, missingTokenResponse.Header().Get("X-Request-ID"),
	)
	for _, required := range []string{
		`"status": 401`,
		`"failure_code": "unauthorized"`,
		`"route_pattern": "GET /api/v1/admin-probe"`,
	} {
		if !strings.Contains(missingTokenDetails, required) {
			t.Errorf("missing-token audit details missing %q: %s", required, missingTokenDetails)
		}
	}

	jwtID, err := auth.NewSessionID()
	if err != nil {
		t.Fatalf("new session id: %v", err)
	}
	token, expiresAt, err := server.tokens.Issue(
		actorID,
		"http-audit@example.test",
		[]string{"moderator"},
		jwtID,
		1,
	)
	if err != nil {
		t.Fatalf("issue moderator token: %v", err)
	}
	if err := server.sessions.Create(ctx, jwtID, actorID, 1, expiresAt); err != nil {
		t.Fatalf("create moderator session: %v", err)
	}
	forbiddenRequest := httptest.NewRequest(
		http.MethodGet,
		"http://api.test/api/v1/admin-probe",
		nil,
	)
	forbiddenRequest.Header.Set("Authorization", "Bearer "+token)
	forbiddenResponse := httptest.NewRecorder()
	protectedHandler.ServeHTTP(forbiddenResponse, forbiddenRequest)
	if forbiddenResponse.Code != http.StatusForbidden {
		t.Fatalf("role-forbidden status = %d, want %d", forbiddenResponse.Code, http.StatusForbidden)
	}
	forbiddenDetails := readHTTPRequestAuditDetails(
		t, ctx, pool, forbiddenResponse.Header().Get("X-Request-ID"),
	)
	for _, required := range []string{
		`"status": 403`,
		`"failure_code": "forbidden"`,
		`"roles": ["moderator"]`,
	} {
		if !strings.Contains(forbiddenDetails, required) {
			t.Errorf("role-forbidden audit details missing %q: %s", required, forbiddenDetails)
		}
	}
	if strings.Contains(forbiddenDetails, jwtID) {
		t.Errorf("role-forbidden audit leaked raw session id: %s", forbiddenDetails)
	}

	loginMux := http.NewServeMux()
	loginMux.HandleFunc("POST /api/v1/auth/login", server.login)
	loginHandler := server.middleware(loginMux)
	loginRequest := httptest.NewRequest(
		http.MethodPost,
		"http://api.test/api/v1/auth/login",
		bytes.NewBufferString(`{"email":"http-audit@example.test","password":"wrong-password"}`),
	)
	loginRequest.Header.Set("Content-Type", "application/json")
	loginResponse := httptest.NewRecorder()
	loginHandler.ServeHTTP(loginResponse, loginRequest)
	if loginResponse.Code != http.StatusUnauthorized {
		t.Fatalf("invalid-login status = %d, want %d", loginResponse.Code, http.StatusUnauthorized)
	}
	loginDetails := readHTTPRequestAuditDetails(
		t, ctx, pool, loginResponse.Header().Get("X-Request-ID"),
	)
	for _, required := range []string{
		`"status": 401`,
		`"failure_code": "invalid_credentials"`,
		`"route_pattern": "POST /api/v1/auth/login"`,
	} {
		if !strings.Contains(loginDetails, required) {
			t.Errorf("invalid-login audit details missing %q: %s", required, loginDetails)
		}
	}
	for _, forbidden := range []string{"http-audit@example.test", "wrong-password"} {
		if strings.Contains(loginDetails, forbidden) {
			t.Errorf("invalid-login audit leaked %q: %s", forbidden, loginDetails)
		}
	}
}

func readHTTPRequestAuditDetails(
	t *testing.T,
	ctx context.Context,
	pool *pgxpool.Pool,
	requestID string,
) string {
	t.Helper()
	var details string
	if err := pool.QueryRow(ctx, `
		SELECT details::text
		FROM audit_events
		WHERE request_id = $1::uuid AND action = 'http.request'
	`, requestID).Scan(&details); err != nil {
		t.Fatalf("read HTTP audit event %s: %v", requestID, err)
	}
	return details
}
