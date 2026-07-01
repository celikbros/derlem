package httpapi

import (
	"errors"
	"fmt"
	"io"
	"mime"
	"net/http"
	"strconv"
	"strings"
	"unicode"

	"github.com/celikbros/derlem/internal/auth"
	"github.com/celikbros/derlem/internal/domain"
	"github.com/celikbros/derlem/internal/repository"
)

func (s *Server) listReleases(w http.ResponseWriter, r *http.Request) {
	limit, err := auth.ParsePositiveInt(r.URL.Query().Get("limit"), 50, 200)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid_limit", "Limit pozitif bir sayı olmalıdır.")
		return
	}
	principal, _ := principalFrom(r.Context())
	status := ""
	if !canReadDraftReleases(principal.Roles) {
		status = "frozen"
	}
	releases, err := s.releases.List(r.Context(), limit, status)
	if err != nil {
		s.logger.Error("list releases failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Sürümler getirilemedi.")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": releases})
}

func (s *Server) getRelease(w http.ResponseWriter, r *http.Request) {
	release, err := s.releases.Get(r.Context(), r.PathValue("id"))
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "release_not_found", "Sürüm bulunamadı.")
		return
	}
	if err != nil {
		s.logger.Error("get release failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Sürüm getirilemedi.")
		return
	}
	principal, _ := principalFrom(r.Context())
	if release.Status != "frozen" && !canReadDraftReleases(principal.Roles) {
		writeError(w, http.StatusNotFound, "release_not_found", "Sürüm bulunamadı.")
		return
	}
	writeJSON(w, http.StatusOK, release)
}

func (s *Server) createRelease(w http.ResponseWriter, r *http.Request) {
	var input domain.CreateReleaseInput
	if !decodeJSON(w, r, &input) {
		return
	}
	repository.NormalizeReleaseInput(&input)
	if reasons := repository.ReleaseInputGateReasons(input); len(reasons) > 0 {
		writeReleaseGateError(w, "release_validation_failed", "Sürüm girdileri geçerli değil.", reasons)
		return
	}
	principal, _ := principalFrom(r.Context())
	release, err := s.releases.Create(r.Context(), input, principal.Subject)
	if errors.Is(err, repository.ErrConflict) {
		writeError(w, http.StatusConflict, "release_exists", "Aynı ad ve sürüm numarası zaten kullanılıyor.")
		return
	}
	var gateError *repository.GateError
	if errors.As(err, &gateError) {
		writeReleaseGateError(w, "release_gate_blocked", "Seçilen kaynaklar release koşullarını karşılamıyor.", gateError.Reasons)
		return
	}
	if err != nil {
		s.logger.Error("create release failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Sürüm oluşturulamadı.")
		return
	}
	writeJSON(w, http.StatusCreated, release)
}

func (s *Server) freezeRelease(w http.ResponseWriter, r *http.Request) {
	principal, _ := principalFrom(r.Context())
	jobID, err := s.releases.QueueFreeze(r.Context(), r.PathValue("id"), principal.Subject)
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "release_not_found", "Sürüm bulunamadı.")
		return
	}
	if errors.Is(err, repository.ErrConflict) {
		writeError(w, http.StatusConflict, "release_freeze_conflict", "Sürüm zaten dondurulmuş veya aktif bir freeze işi var.")
		return
	}
	var gateError *repository.GateError
	if errors.As(err, &gateError) {
		writeReleaseGateError(w, "release_freeze_gate_blocked", "Kaynak snapshot'ları freeze için geçerli değil.", gateError.Reasons)
		return
	}
	if err != nil {
		s.logger.Error("queue release freeze failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Freeze işi başlatılamadı.")
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]string{"job_id": jobID, "status": "queued"})
}

func (s *Server) createReleaseExport(w http.ResponseWriter, r *http.Request) {
	var input domain.CreateReleaseExportInput
	if !decodeJSON(w, r, &input) {
		return
	}
	input.Format = strings.ToLower(strings.TrimSpace(input.Format))
	if input.Format != "jsonl" && input.Format != "txt" {
		writeError(w, http.StatusBadRequest, "invalid_export_format", "Export formatı jsonl veya txt olmalıdır.")
		return
	}
	principal, _ := principalFrom(r.Context())
	export, jobID, err := s.releases.QueueExport(
		r.Context(),
		r.PathValue("id"),
		input.Format,
		principal.Subject,
	)
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "release_not_found", "Sürüm bulunamadı.")
		return
	}
	if errors.Is(err, repository.ErrConflict) {
		writeError(w, http.StatusConflict, "release_export_conflict", "Bu format için hazır veya devam eden bir export var.")
		return
	}
	var gateError *repository.GateError
	if errors.As(err, &gateError) {
		writeReleaseGateError(w, "release_export_gate_blocked", "Yalnız frozen release export edilebilir.", gateError.Reasons)
		return
	}
	if err != nil {
		s.logger.Error("queue release export failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Export işi başlatılamadı.")
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]any{
		"export": export,
		"job_id": jobID,
	})
}

func (s *Server) downloadReleaseManifest(w http.ResponseWriter, r *http.Request) {
	artifact, err := s.releases.ManifestObject(r.Context(), r.PathValue("id"))
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "release_manifest_not_found", "Frozen manifest bulunamadı.")
		return
	}
	if err != nil {
		s.logger.Error("get release manifest failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Manifest getirilemedi.")
		return
	}
	s.streamReleaseArtifact(w, r, artifact)
}

func (s *Server) downloadReleaseSource(w http.ResponseWriter, r *http.Request) {
	artifact, err := s.releases.SourceArtifact(r.Context(), r.PathValue("id"), r.PathValue("source_id"))
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "release_artifact_not_found", "Frozen kaynak artifact'i bulunamadı.")
		return
	}
	if err != nil {
		s.logger.Error("get release source artifact failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Kaynak artifact'i getirilemedi.")
		return
	}
	s.streamReleaseArtifact(w, r, artifact)
}

func (s *Server) downloadReleaseExport(w http.ResponseWriter, r *http.Request) {
	s.downloadExportArtifact(w, r, false)
}

func (s *Server) downloadReleaseExportManifest(w http.ResponseWriter, r *http.Request) {
	s.downloadExportArtifact(w, r, true)
}

func (s *Server) downloadExportArtifact(w http.ResponseWriter, r *http.Request, manifest bool) {
	exportFormat := strings.ToLower(strings.TrimSpace(r.PathValue("format")))
	if exportFormat != "jsonl" && exportFormat != "txt" {
		writeError(w, http.StatusBadRequest, "invalid_export_format", "Export formatı jsonl veya txt olmalıdır.")
		return
	}
	artifact, err := s.releases.ExportArtifact(r.Context(), r.PathValue("id"), exportFormat, manifest)
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "release_export_not_found", "Hazır export artifact'i bulunamadı.")
		return
	}
	if err != nil {
		s.logger.Error("get release export failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Export artifact'i getirilemedi.")
		return
	}
	s.streamReleaseArtifact(w, r, artifact)
}

func (s *Server) streamReleaseArtifact(w http.ResponseWriter, r *http.Request, artifact repository.ReleaseArtifact) {
	reader, err := s.objectStore.Open(r.Context(), artifact.SHA256)
	if err != nil {
		s.logger.Error("open release artifact failed", "error", err, "sha256", artifact.SHA256)
		writeError(w, http.StatusInternalServerError, "artifact_unavailable", "Artifact depoda bulunamadı.")
		return
	}
	defer reader.Close()
	filename := safeDownloadName(artifact.Name)
	disposition := mime.FormatMediaType("attachment", map[string]string{"filename": filename})
	w.Header().Set("Content-Type", artifact.MediaType)
	w.Header().Set("Content-Length", strconv.FormatInt(artifact.ByteSize, 10))
	w.Header().Set("Content-Disposition", disposition)
	w.Header().Set("ETag", fmt.Sprintf("\"%s\"", artifact.SHA256))
	w.WriteHeader(http.StatusOK)
	if _, err := io.Copy(w, reader); err != nil {
		s.logger.Warn("stream release artifact interrupted", "error", err, "sha256", artifact.SHA256)
	}
}

func safeDownloadName(value string) string {
	value = strings.TrimSpace(value)
	var builder strings.Builder
	for _, character := range value {
		if unicode.IsLetter(character) || unicode.IsDigit(character) || strings.ContainsRune("-_.", character) {
			builder.WriteRune(character)
		} else {
			builder.WriteByte('-')
		}
	}
	name := strings.Trim(builder.String(), ".-")
	if name == "" {
		return "derlem-artifact"
	}
	if len([]rune(name)) > 180 {
		return string([]rune(name)[:180])
	}
	return name
}

func writeReleaseGateError(w http.ResponseWriter, code, message string, reasons []string) {
	writeJSON(w, http.StatusUnprocessableEntity, map[string]any{
		"error": map[string]any{"code": code, "message": message, "reasons": reasons},
	})
}
