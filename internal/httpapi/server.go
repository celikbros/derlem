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
	objectStore    storage.Store
	tokens         *auth.TokenManager
	logger         *slog.Logger
	webOrigin      string
	stagingRoot    string
	maxUploadBytes int64
}

func NewServer(pool *pgxpool.Pool, objectStore storage.Store, tokens *auth.TokenManager, logger *slog.Logger, webOrigin, stagingRoot string, maxUploadBytes int64) *Server {
	return &Server{
		pool:           pool,
		sources:        repository.NewSources(pool),
		documents:      repository.NewDocuments(pool),
		objectStore:    objectStore,
		tokens:         tokens,
		logger:         logger,
		webOrigin:      webOrigin,
		stagingRoot:    stagingRoot,
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
	mux.Handle("GET /api/v1/sources", s.authenticate(http.HandlerFunc(s.listSources)))
	mux.Handle("POST /api/v1/sources", s.authenticate(requireRoles("admin", "data_manager")(http.HandlerFunc(s.createSource))))
	mux.Handle("GET /api/v1/sources/{id}", s.authenticate(http.HandlerFunc(s.getSource)))
	mux.Handle("PATCH /api/v1/sources/{id}", s.authenticate(requireRoles("admin", "data_manager", "editor")(http.HandlerFunc(s.updateSource))))
	mux.Handle("POST /api/v1/sources/{id}/ingest", s.authenticate(requireRoles("admin", "data_manager")(http.HandlerFunc(s.queueSourceIngest))))
	mux.Handle("POST /api/v1/sources/{id}/upload", s.authenticate(requireRoles("admin", "data_manager")(http.HandlerFunc(s.uploadSourceFile))))
	mux.Handle("GET /api/v1/sources/{id}/reviews", s.authenticate(http.HandlerFunc(s.listSourceReviews)))
	mux.Handle("POST /api/v1/sources/{id}/reviews", s.authenticate(requireRoles("admin", "moderator", "expert_reviewer")(http.HandlerFunc(s.reviewSource))))
	mux.Handle("GET /api/v1/sources/{id}/pii-scans", s.authenticate(http.HandlerFunc(s.listSourcePIIScans)))
	mux.Handle("GET /api/v1/sources/{id}/documents", s.authenticate(http.HandlerFunc(s.listSourceDocuments)))
	mux.Handle("GET /api/v1/documents/{id}", s.authenticate(http.HandlerFunc(s.getDocument)))
	mux.Handle("PATCH /api/v1/documents/{id}", s.authenticate(requireRoles("admin", "editor")(http.HandlerFunc(s.updateDocument))))
	mux.Handle("GET /api/v1/documents/{id}/reviews", s.authenticate(http.HandlerFunc(s.listDocumentReviews)))
	mux.Handle("POST /api/v1/documents/{id}/reviews", s.authenticate(requireRoles("admin", "moderator", "expert_reviewer")(http.HandlerFunc(s.reviewDocument))))
	mux.Handle("GET /api/v1/jobs", s.authenticate(http.HandlerFunc(s.listJobs)))
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
