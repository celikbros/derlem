package httpapi

import (
	"errors"
	"net/http"
	"net/mail"
	"slices"
	"strings"

	"github.com/celikbros/derlem/internal/auth"
	"github.com/celikbros/derlem/internal/repository"
)

const minPasswordLength = 12

type createUserRequest struct {
	Email       string   `json:"email"`
	DisplayName string   `json:"display_name"`
	Password    string   `json:"password"`
	Roles       []string `json:"roles"`
}

type updateUserRequest struct {
	DisplayName *string  `json:"display_name"`
	Status      *string  `json:"status"`
	Roles       []string `json:"roles"`
	NewPassword *string  `json:"new_password"`
}

func (s *Server) listUsers(w http.ResponseWriter, r *http.Request) {
	users, err := s.users.List(r.Context())
	if err != nil {
		s.logger.Error("list users failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Kullanıcılar listelenemedi.")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": users})
}

func (s *Server) createUser(w http.ResponseWriter, r *http.Request) {
	var request createUserRequest
	if !decodeJSON(w, r, &request) {
		return
	}
	email := strings.ToLower(strings.TrimSpace(request.Email))
	displayName := strings.TrimSpace(request.DisplayName)
	if email == "" || displayName == "" {
		writeError(w, http.StatusBadRequest, "missing_fields", "E-posta ve görünen ad zorunludur.")
		return
	}
	if _, err := mail.ParseAddress(email); err != nil || len(email) > maxLoginEmailBytes {
		writeError(w, http.StatusBadRequest, "invalid_email", "Geçerli bir e-posta adresi girin.")
		return
	}
	if !validRoleSet(request.Roles) {
		writeError(w, http.StatusBadRequest, "invalid_roles", "En az bir geçerli rol seçilmelidir.")
		return
	}
	if len(request.Password) < minPasswordLength || len(request.Password) > maxLoginPasswordBytes {
		writeError(w, http.StatusBadRequest, "weak_password", "Parola en az 12 karakter olmalıdır.")
		return
	}
	passwordHash, err := auth.HashPassword(request.Password)
	if err != nil {
		s.logger.Error("hash password failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Kullanıcı oluşturulamadı.")
		return
	}
	principal, _ := principalFrom(r.Context())
	user, err := s.users.Create(r.Context(), principal.Subject, email, displayName, passwordHash, request.Roles)
	if err != nil {
		if errors.Is(err, repository.ErrEmailTaken) {
			writeError(w, http.StatusConflict, "email_taken", "Bu e-posta ile kayıtlı kullanıcı var.")
			return
		}
		if errors.Is(err, repository.ErrUnknownRole) {
			writeError(w, http.StatusBadRequest, "invalid_roles", "Bilinmeyen rol.")
			return
		}
		s.logger.Error("create user failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Kullanıcı oluşturulamadı.")
		return
	}
	writeJSON(w, http.StatusCreated, user)
}

func (s *Server) updateUser(w http.ResponseWriter, r *http.Request) {
	var request updateUserRequest
	if !decodeJSON(w, r, &request) {
		return
	}
	input := repository.UpdateUserInput{Roles: request.Roles}
	if request.DisplayName != nil {
		trimmed := strings.TrimSpace(*request.DisplayName)
		if trimmed == "" {
			writeError(w, http.StatusBadRequest, "missing_fields", "Görünen ad boş olamaz.")
			return
		}
		input.DisplayName = &trimmed
	}
	if request.Status != nil {
		if *request.Status != "active" && *request.Status != "disabled" {
			writeError(w, http.StatusBadRequest, "invalid_status", "Durum active veya disabled olabilir.")
			return
		}
		input.Status = request.Status
	}
	if request.Roles != nil && !validRoleSet(request.Roles) {
		writeError(w, http.StatusBadRequest, "invalid_roles", "En az bir geçerli rol seçilmelidir.")
		return
	}
	if request.NewPassword != nil {
		if len(*request.NewPassword) < minPasswordLength || len(*request.NewPassword) > maxLoginPasswordBytes {
			writeError(w, http.StatusBadRequest, "weak_password", "Parola en az 12 karakter olmalıdır.")
			return
		}
		passwordHash, err := auth.HashPassword(*request.NewPassword)
		if err != nil {
			s.logger.Error("hash password failed", "error", err)
			writeError(w, http.StatusInternalServerError, "internal_error", "Kullanıcı güncellenemedi.")
			return
		}
		input.PasswordHash = &passwordHash
	}

	principal, _ := principalFrom(r.Context())
	user, err := s.users.Update(r.Context(), principal.Subject, r.PathValue("id"), input)
	if err != nil {
		switch {
		case errors.Is(err, repository.ErrNotFound):
			writeError(w, http.StatusNotFound, "user_not_found", "Kullanıcı bulunamadı.")
		case errors.Is(err, repository.ErrSelfLockout):
			writeError(w, http.StatusConflict, "self_lockout", "Kendi hesabınızı devre dışı bırakamaz veya admin rolünüzü kaldıramazsınız.")
		case errors.Is(err, repository.ErrLastAdmin):
			writeError(w, http.StatusConflict, "last_admin", "Son aktif admin devre dışı bırakılamaz veya rolü kaldırılamaz.")
		case errors.Is(err, repository.ErrUnknownRole):
			writeError(w, http.StatusBadRequest, "invalid_roles", "Bilinmeyen rol.")
		default:
			s.logger.Error("update user failed", "error", err)
			writeError(w, http.StatusInternalServerError, "internal_error", "Kullanıcı güncellenemedi.")
		}
		return
	}
	writeJSON(w, http.StatusOK, user)
}

func validRoleSet(roles []string) bool {
	if len(roles) == 0 {
		return false
	}
	for _, role := range roles {
		if !slices.Contains(applicationRoles, role) {
			return false
		}
	}
	return true
}
