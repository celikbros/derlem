package httpapi

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"net/http"
	"runtime/debug"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/celikbros/derlem/internal/auth"
)

type principalKey struct{}
type requestAuditKey struct{}

type requestAuditState struct {
	RequestID   string
	ActorID     string
	Roles       []string
	SessionHash string
	FailureCode string
}

type responseStatusRecorder struct {
	http.ResponseWriter
	statusCode int
	bytes      int64
	auditState *requestAuditState
}

func (w *responseStatusRecorder) WriteHeader(statusCode int) {
	if w.statusCode != 0 {
		return
	}
	w.statusCode = statusCode
	w.ResponseWriter.WriteHeader(statusCode)
}

func (w *responseStatusRecorder) Write(body []byte) (int, error) {
	if w.statusCode == 0 {
		w.WriteHeader(http.StatusOK)
	}
	written, err := w.ResponseWriter.Write(body)
	w.bytes += int64(written)
	return written, err
}

func (w *responseStatusRecorder) Unwrap() http.ResponseWriter {
	return w.ResponseWriter
}

func (w *responseStatusRecorder) markAuditFailure(code string) {
	if w.auditState != nil {
		w.auditState.FailureCode = code
	}
}

func (s *Server) authenticate(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		token, err := auth.BearerToken(r.Header.Get("Authorization"))
		if err != nil {
			markRequestAuditFailure(r.Context(), "unauthorized")
			writeError(w, http.StatusUnauthorized, "unauthorized", "Oturum açmanız gerekiyor.")
			return
		}
		claims, err := s.tokens.Parse(token)
		if err != nil {
			markRequestAuditFailure(r.Context(), "invalid_token")
			writeError(w, http.StatusUnauthorized, "invalid_token", "Oturum süresi dolmuş veya token geçersiz.")
			return
		}
		setRequestAuditPrincipal(r.Context(), claims)
		if err := s.sessions.Validate(r.Context(), claims); err != nil {
			if errors.Is(err, auth.ErrInvalidSession) || errors.Is(err, auth.ErrExpiredSession) || errors.Is(err, auth.ErrRevokedSession) || errors.Is(err, auth.ErrStalePrincipal) {
				markRequestAuditFailure(r.Context(), "invalid_session")
				writeError(w, http.StatusUnauthorized, "invalid_session", "Oturum sona ermiş veya yetkiler değişmiş. Yeniden giriş yapın.")
				return
			}
			markRequestAuditFailure(r.Context(), "auth_unavailable")
			s.logger.Error("session validation failed", "error", err)
			writeError(w, http.StatusServiceUnavailable, "auth_unavailable", "Oturum doğrulama servisi geçici olarak kullanılamıyor.")
			return
		}
		ctx := context.WithValue(r.Context(), principalKey{}, claims)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

func requireRoles(roles ...string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			principal, ok := principalFrom(r.Context())
			if !ok {
				markRequestAuditFailure(r.Context(), "unauthorized")
				writeError(w, http.StatusUnauthorized, "unauthorized", "Oturum açmanız gerekiyor.")
				return
			}
			if hasAnyRole(principal.Roles, roles) {
				next.ServeHTTP(w, r)
				return
			}
			markRequestAuditFailure(r.Context(), "forbidden")
			writeError(w, http.StatusForbidden, "forbidden", "Bu işlem için yetkiniz bulunmuyor.")
		})
	}
}

func principalFrom(ctx context.Context) (auth.Claims, bool) {
	principal, ok := ctx.Value(principalKey{}).(auth.Claims)
	return principal, ok
}

func requestAuditStateFrom(ctx context.Context) *requestAuditState {
	state, _ := ctx.Value(requestAuditKey{}).(*requestAuditState)
	return state
}

func setRequestAuditPrincipal(ctx context.Context, claims auth.Claims) {
	state := requestAuditStateFrom(ctx)
	if state == nil {
		return
	}
	state.ActorID = claims.Subject
	state.Roles = append([]string(nil), claims.Roles...)
	state.SessionHash = auth.SessionIDHash(claims.JWTID)
}

func markRequestAuditFailure(ctx context.Context, code string) {
	state := requestAuditStateFrom(ctx)
	if state != nil {
		state.FailureCode = code
	}
}

func (s *Server) middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		started := time.Now()
		requestID, err := newRequestID()
		if err != nil {
			s.logger.Error("request id generation failed", "error", err)
			writeError(w, http.StatusServiceUnavailable, "request_id_unavailable", "İstek güvenli biçimde başlatılamadı.")
			return
		}
		auditState := &requestAuditState{RequestID: requestID}
		r = r.WithContext(context.WithValue(r.Context(), requestAuditKey{}, auditState))
		recorder := &responseStatusRecorder{ResponseWriter: w, auditState: auditState}
		recorder.Header().Set("X-Request-ID", requestID)
		defer func() {
			if recovered := recover(); recovered != nil {
				auditState.FailureCode = "panic"
				s.logger.Error("panic recovered", "panic", recovered, "stack", string(debug.Stack()))
				writeError(recorder, http.StatusInternalServerError, "internal_error", "Beklenmeyen bir hata oluştu.")
			}
			duration := time.Since(started)
			statusCode := recorder.statusCode
			if statusCode == 0 {
				statusCode = http.StatusOK
			}
			if statusCode >= http.StatusBadRequest && auditState.FailureCode == "" {
				auditState.FailureCode = "http_" + strconv.Itoa(statusCode)
			}
			routePattern := r.Pattern
			if routePattern == "" {
				routePattern = "unmatched"
			}
			s.logger.Info("request",
				"request_id", requestID,
				"actor_id", auditState.ActorID,
				"method", r.Method,
				"route_pattern", routePattern,
				"status", statusCode,
				"duration", duration,
			)
			if strings.HasPrefix(r.URL.Path, "/api/") {
				s.recordHTTPRequestAudit(r, auditState, statusCode, recorder.bytes, duration)
			}
		}()

		recorder.Header().Set("X-Content-Type-Options", "nosniff")
		recorder.Header().Set("X-Frame-Options", "DENY")
		recorder.Header().Set("Referrer-Policy", "no-referrer")
		if origin := r.Header.Get("Origin"); origin != "" && origin == s.webOrigin {
			recorder.Header().Set("Access-Control-Allow-Origin", origin)
			recorder.Header().Set("Vary", "Origin")
			recorder.Header().Set("Access-Control-Allow-Headers", "Authorization, Content-Type")
			recorder.Header().Set("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
			recorder.Header().Set("Access-Control-Expose-Headers", "X-Request-ID")
			if r.Method == http.MethodOptions {
				recorder.WriteHeader(http.StatusNoContent)
				return
			}
		}
		next.ServeHTTP(recorder, r)
	})
}

func newRequestID() (string, error) {
	raw := make([]byte, 16)
	if _, err := rand.Read(raw); err != nil {
		return "", err
	}
	raw[6] = (raw[6] & 0x0f) | 0x40
	raw[8] = (raw[8] & 0x3f) | 0x80
	encoded := hex.EncodeToString(raw)
	return encoded[0:8] + "-" + encoded[8:12] + "-" + encoded[12:16] + "-" + encoded[16:20] + "-" + encoded[20:32], nil
}

func (s *Server) recordHTTPRequestAudit(
	r *http.Request,
	state *requestAuditState,
	statusCode int,
	responseBytes int64,
	duration time.Duration,
) {
	if s.pool == nil || state == nil {
		return
	}
	roles := append([]string(nil), state.Roles...)
	sort.Strings(roles)
	pattern := r.Pattern
	if pattern == "" {
		pattern = "unmatched"
	}
	details := map[string]any{
		"method":         r.Method,
		"route_pattern":  pattern,
		"status":         statusCode,
		"duration_ms":    duration.Milliseconds(),
		"response_bytes": responseBytes,
		"roles":          roles,
	}
	if state.SessionHash != "" {
		details["session_hash"] = state.SessionHash
	}
	if state.FailureCode != "" {
		details["failure_code"] = state.FailureCode
	}
	encodedDetails, err := json.Marshal(details)
	if err != nil {
		s.logger.Error("request audit encoding failed", "request_id", state.RequestID, "error", err)
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	var actorID any
	if state.ActorID != "" {
		actorID = state.ActorID
	}
	if _, err := s.pool.Exec(ctx, `
		INSERT INTO audit_events(request_id, actor_id, action, entity_type, details)
		VALUES ($1::uuid, $2::uuid, 'http.request', 'http_request', $3::jsonb)
	`, state.RequestID, actorID, encodedDetails); err != nil {
		s.logger.Error("request audit persistence failed", "request_id", state.RequestID, "error", err)
	}
}
