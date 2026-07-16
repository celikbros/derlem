package httpapi

import (
	"context"
	"log/slog"
	"net/http"
	"time"

	"github.com/celikbros/derlem/internal/auth"
	"github.com/celikbros/derlem/internal/repository"
	"github.com/celikbros/derlem/internal/storage"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Server struct {
	pool           *pgxpool.Pool
	sources        *repository.Sources
	documents      *repository.Documents
	releases       *repository.Releases
	similarities   *repository.SimilarityReviews
	users          *repository.Users
	contributions  *repository.Contributions
	objectStore    storage.Store
	tokens         *auth.TokenManager
	sessions       *auth.SessionStore
	loginLimiter   *auth.LoginLimiter
	logger         *slog.Logger
	webOrigin      string
	stagingRoot    string
	importRoot     string
	maxUploadBytes int64
}

func NewServer(pool *pgxpool.Pool, objectStore storage.Store, tokens *auth.TokenManager, sessions *auth.SessionStore, loginLimiter *auth.LoginLimiter, logger *slog.Logger, webOrigin, stagingRoot, importRoot string, maxUploadBytes int64) *Server {
	return &Server{
		pool:           pool,
		sources:        repository.NewSources(pool),
		documents:      repository.NewDocuments(pool),
		releases:       repository.NewReleases(pool),
		similarities:   repository.NewSimilarityReviews(pool),
		users:          repository.NewUsers(pool),
		contributions:  repository.NewContributions(pool),
		objectStore:    objectStore,
		tokens:         tokens,
		sessions:       sessions,
		loginLimiter:   loginLimiter,
		logger:         logger,
		webOrigin:      webOrigin,
		stagingRoot:    stagingRoot,
		importRoot:     importRoot,
		maxUploadBytes: maxUploadBytes,
	}
}

func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /", s.serviceInfo)
	mux.HandleFunc("GET /health/live", s.live)
	mux.HandleFunc("GET /health/ready", s.ready)
	mux.HandleFunc("POST /api/v1/auth/login", s.login)
	mux.Handle("GET /api/v1/me", s.authenticate(http.HandlerFunc(s.me)))
	for _, route := range protectedRoutes(s) {
		if len(route.roles) == 0 {
			panic("protected API route has no role policy: " + route.pattern)
		}
		mux.Handle(route.pattern, s.authenticate(requireRoles(route.roles...)(route.handler)))
	}
	return s.middleware(mux)
}

func (s *Server) serviceInfo(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{
		"name":    "Derlem API",
		"version": "0.1.0",
		"status":  "ok",
	})
}

func (s *Server) live(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (s *Server) ready(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := contextWithTimeout(r, 2*time.Second)
	defer cancel()
	if err := s.pool.Ping(ctx); err != nil {
		writeError(w, http.StatusServiceUnavailable, "database_unavailable", "Veritabanı bağlantısı hazır değil.")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ready", "database": "ok"})
}

func contextWithTimeout(r *http.Request, duration time.Duration) (context.Context, context.CancelFunc) {
	return context.WithTimeout(r.Context(), duration)
}
