package httpapi

import (
	"errors"
	"net/http"
	"strings"

	"github.com/celikbros/derlem/internal/auth"
	"github.com/jackc/pgx/v5"
)

type loginRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

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

	var userID, email, passwordHash, status string
	var roles []string
	err := s.pool.QueryRow(r.Context(), `
		SELECT u.id::text, u.email, u.password_hash, u.status,
			COALESCE(
				array_agg(ur.role_name ORDER BY ur.role_name)
				FILTER (WHERE ur.role_name IS NOT NULL),
				ARRAY[]::text[]
			)
		FROM users u
		LEFT JOIN user_roles ur ON ur.user_id = u.id
		WHERE u.email = $1
		GROUP BY u.id
	`, request.Email).Scan(&userID, &email, &passwordHash, &status, &roles)
	if errors.Is(err, pgx.ErrNoRows) || err == nil && !auth.CheckPassword(passwordHash, request.Password) {
		writeError(w, http.StatusUnauthorized, "invalid_credentials", "E-posta veya parola geçersiz.")
		return
	}
	if err != nil {
		s.logger.Error("login query failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Oturum açılamadı.")
		return
	}
	if status != "active" {
		writeError(w, http.StatusForbidden, "user_disabled", "Kullanıcı hesabı etkin değil.")
		return
	}

	token, expiresAt, err := s.tokens.Issue(userID, email, roles)
	if err != nil {
		s.logger.Error("issue token failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Oturum açılamadı.")
		return
	}
	if _, err := s.pool.Exec(r.Context(), `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id)
		VALUES ($1, 'auth.login', 'user', $1)
	`, userID); err != nil {
		s.logger.Error("audit login failed", "error", err)
		writeError(w, http.StatusInternalServerError, "audit_failed", "Oturum denetim kaydı oluşturulamadı.")
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

func (s *Server) me(w http.ResponseWriter, r *http.Request) {
	principal, _ := principalFrom(r.Context())
	writeJSON(w, http.StatusOK, map[string]any{
		"id":    principal.Subject,
		"email": principal.Email,
		"roles": principal.Roles,
	})
}
