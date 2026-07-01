package httpapi

import (
	"context"
	"errors"
	"net/http"
	"runtime/debug"
	"time"

	"github.com/celikbros/derlem/internal/auth"
)

type principalKey struct{}

func (s *Server) authenticate(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		token, err := auth.BearerToken(r.Header.Get("Authorization"))
		if err != nil {
			writeError(w, http.StatusUnauthorized, "unauthorized", "Oturum açmanız gerekiyor.")
			return
		}
		claims, err := s.tokens.Parse(token)
		if err != nil {
			writeError(w, http.StatusUnauthorized, "invalid_token", "Oturum süresi dolmuş veya token geçersiz.")
			return
		}
		if err := s.sessions.Validate(r.Context(), claims); err != nil {
			if errors.Is(err, auth.ErrInvalidSession) || errors.Is(err, auth.ErrExpiredSession) || errors.Is(err, auth.ErrRevokedSession) || errors.Is(err, auth.ErrStalePrincipal) {
				writeError(w, http.StatusUnauthorized, "invalid_session", "Oturum sona ermiş veya yetkiler değişmiş. Yeniden giriş yapın.")
				return
			}
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
				writeError(w, http.StatusUnauthorized, "unauthorized", "Oturum açmanız gerekiyor.")
				return
			}
			if hasAnyRole(principal.Roles, roles) {
				next.ServeHTTP(w, r)
				return
			}
			writeError(w, http.StatusForbidden, "forbidden", "Bu işlem için yetkiniz bulunmuyor.")
		})
	}
}

func principalFrom(ctx context.Context) (auth.Claims, bool) {
	principal, ok := ctx.Value(principalKey{}).(auth.Claims)
	return principal, ok
}

func (s *Server) middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		started := time.Now()
		defer func() {
			if recovered := recover(); recovered != nil {
				s.logger.Error("panic recovered", "panic", recovered, "stack", string(debug.Stack()))
				writeError(w, http.StatusInternalServerError, "internal_error", "Beklenmeyen bir hata oluştu.")
			}
			s.logger.Info("request", "method", r.Method, "path", r.URL.Path, "duration", time.Since(started))
		}()

		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("X-Frame-Options", "DENY")
		w.Header().Set("Referrer-Policy", "no-referrer")
		if origin := r.Header.Get("Origin"); origin != "" && origin == s.webOrigin {
			w.Header().Set("Access-Control-Allow-Origin", origin)
			w.Header().Set("Vary", "Origin")
			w.Header().Set("Access-Control-Allow-Headers", "Authorization, Content-Type")
			w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
			if r.Method == http.MethodOptions {
				w.WriteHeader(http.StatusNoContent)
				return
			}
		}
		next.ServeHTTP(w, r)
	})
}
