package httpapi

import (
	"errors"
	"fmt"
	"math"
	"net"
	"net/http"
	"strings"
	"time"

	"github.com/celikbros/derlem/internal/auth"
	"github.com/jackc/pgx/v5"
)

type loginRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

const (
	maxLoginEmailBytes    = 320
	maxLoginPasswordBytes = 1024
)

func (s *Server) login(w http.ResponseWriter, r *http.Request) {
	var request loginRequest
	if !decodeJSON(w, r, &request) {
		return
	}
	request.Email = strings.ToLower(strings.TrimSpace(request.Email))
	if request.Email == "" || request.Password == "" {
		writeError(w, http.StatusBadRequest, "missing_credentials", "E-posta ve parola zorunludur.")
		return
	}
	if len(request.Email) > maxLoginEmailBytes || len(request.Password) > maxLoginPasswordBytes {
		writeError(w, http.StatusBadRequest, "invalid_credentials", "E-posta veya parola geçersiz.")
		return
	}
	rateKeys := s.loginLimiter.Keys(request.Email, clientIP(r))
	retryAfter, err := s.loginLimiter.Check(r.Context(), rateKeys)
	if err != nil {
		s.logger.Error("login rate-limit check failed", "error", err)
		writeError(w, http.StatusServiceUnavailable, "auth_unavailable", "Oturum servisi geçici olarak kullanılamıyor.")
		return
	}
	if retryAfter > 0 {
		shouldLog, err := s.loginLimiter.RecordBlockedAttempt(r.Context(), rateKeys)
		if err != nil {
			s.logger.Error("audit blocked login failed", "error", err)
			writeError(w, http.StatusServiceUnavailable, "auth_unavailable", "Oturum servisi geçici olarak kullanılamıyor.")
			return
		}
		if shouldLog {
			s.logRateLimitedLogin(rateKeys, retryAfter)
		}
		writeRateLimited(w, retryAfter)
		return
	}

	var userID, email, passwordHash, status string
	var authVersion int64
	var roles []string
	err = s.pool.QueryRow(r.Context(), `
		SELECT u.id::text, u.email, u.password_hash, u.status, u.auth_version,
			COALESCE(
				array_agg(ur.role_name ORDER BY ur.role_name)
				FILTER (WHERE ur.role_name IS NOT NULL),
				ARRAY[]::text[]
			)
		FROM users u
		LEFT JOIN user_roles ur ON ur.user_id = u.id
		WHERE u.email = $1
		GROUP BY u.id
	`, request.Email).Scan(&userID, &email, &passwordHash, &status, &authVersion, &roles)
	userFound := err == nil
	if err != nil && !errors.Is(err, pgx.ErrNoRows) {
		s.logger.Error("login query failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Oturum açılamadı.")
		return
	}
	passwordValid := auth.CheckPassword(passwordHash, request.Password)
	if !userFound || !passwordValid || status != "active" {
		reason := "invalid_credentials"
		if userFound && status != "active" {
			reason = "user_disabled"
		}
		retryAfter, rateErr := s.loginLimiter.RecordFailure(r.Context(), rateKeys, userID, reason)
		if rateErr != nil {
			s.logger.Error("record login failure failed", "error", rateErr)
			writeError(w, http.StatusServiceUnavailable, "auth_unavailable", "Oturum servisi geçici olarak kullanılamıyor.")
			return
		}
		if retryAfter > 0 {
			s.logRateLimitedLogin(rateKeys, retryAfter)
			writeRateLimited(w, retryAfter)
			return
		}
		writeError(w, http.StatusUnauthorized, "invalid_credentials", "E-posta veya parola geçersiz.")
		return
	}

	if err := s.loginLimiter.RecordSuccess(r.Context(), rateKeys); err != nil {
		s.logger.Error("reset login rate limit failed", "error", err)
		writeError(w, http.StatusServiceUnavailable, "auth_unavailable", "Oturum servisi geçici olarak kullanılamıyor.")
		return
	}
	jwtID, err := auth.NewSessionID()
	if err != nil {
		s.logger.Error("generate session identity failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Oturum açılamadı.")
		return
	}
	token, expiresAt, err := s.tokens.Issue(userID, email, roles, jwtID, authVersion)
	if err != nil {
		s.logger.Error("issue token failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Oturum açılamadı.")
		return
	}
	if err := s.sessions.Create(r.Context(), jwtID, userID, authVersion, expiresAt); err != nil {
		s.logger.Error("create server session failed", "error", err)
		writeError(w, http.StatusInternalServerError, "session_failed", "Oturum kaydı oluşturulamadı.")
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"access_token": token,
		"token_type":   "Bearer",
		"expires_at":   expiresAt,
		"user": map[string]any{
			"id":    userID,
			"email": email,
			"roles": roles,
		},
	})
}

func (s *Server) logRateLimitedLogin(keys auth.LoginRateKeys, retryAfter time.Duration) {
	s.logger.Warn(
		"login blocked by rate limit",
		"account_key", keys.Account,
		"ip_key", keys.IP,
		"retry_after_seconds", max(1, int(math.Ceil(retryAfter.Seconds()))),
	)
}

func (s *Server) logout(w http.ResponseWriter, r *http.Request) {
	principal, _ := principalFrom(r.Context())
	if err := s.sessions.Revoke(r.Context(), principal, "user_logout"); err != nil {
		s.logger.Error("logout revoke failed", "error", err)
		writeError(w, http.StatusInternalServerError, "logout_failed", "Oturum kapatılamadı.")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "revoked"})
}

func (s *Server) logoutAll(w http.ResponseWriter, r *http.Request) {
	principal, _ := principalFrom(r.Context())
	revokedCount, err := s.sessions.RevokeAll(r.Context(), principal, "user_logout_all")
	if err != nil {
		s.logger.Error("all-session revoke failed", "error", err)
		writeError(w, http.StatusInternalServerError, "logout_failed", "Oturumlar kapatılamadı.")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "revoked", "revoked_count": revokedCount})
}

func (s *Server) me(w http.ResponseWriter, r *http.Request) {
	principal, _ := principalFrom(r.Context())
	writeJSON(w, http.StatusOK, map[string]any{
		"id":    principal.Subject,
		"email": principal.Email,
		"roles": principal.Roles,
	})
}

func clientIP(r *http.Request) string {
	host, _, err := net.SplitHostPort(strings.TrimSpace(r.RemoteAddr))
	if err != nil {
		host = strings.TrimSpace(r.RemoteAddr)
	}
	remoteIP := net.ParseIP(host)
	if remoteIP != nil && remoteIP.IsLoopback() {
		if forwarded := net.ParseIP(strings.TrimSpace(r.Header.Get("X-Real-IP"))); forwarded != nil {
			return forwarded.String()
		}
	}
	if remoteIP == nil {
		return "unknown"
	}
	return remoteIP.String()
}

func writeRateLimited(w http.ResponseWriter, retryAfter time.Duration) {
	seconds := max(1, int(math.Ceil(retryAfter.Seconds())))
	w.Header().Set("Retry-After", fmt.Sprintf("%d", seconds))
	writeError(w, http.StatusTooManyRequests, "login_rate_limited", "Çok fazla başarısız giriş denemesi. Daha sonra yeniden deneyin.")
}
