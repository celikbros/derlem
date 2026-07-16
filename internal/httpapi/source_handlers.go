package httpapi

import (
	"encoding/base64"
	"errors"
	"net/http"
	"slices"
	"strings"
	"time"

	"github.com/celikbros/derlem/internal/auth"
	"github.com/celikbros/derlem/internal/domain"
	"github.com/celikbros/derlem/internal/repository"
)

type sourceListResponse struct {
	Items      []domain.Source `json:"items"`
	NextCursor string          `json:"next_cursor,omitempty"`
}

func (s *Server) listSources(w http.ResponseWriter, r *http.Request) {
	limit, err := auth.ParsePositiveInt(r.URL.Query().Get("limit"), 50, 200)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid_limit", "Limit pozitif bir sayı olmalıdır.")
		return
	}
	beforeTime, beforeID, err := decodeCursor(r.URL.Query().Get("cursor"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid_cursor", "Sayfalama anahtarı geçersiz.")
		return
	}

	items, err := s.sources.List(r.Context(), limit+1, beforeTime, beforeID)
	if err != nil {
		s.logger.Error("list sources failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Kaynaklar getirilemedi.")
		return
	}
	response := sourceListResponse{Items: items}
	if len(items) > limit {
		response.Items = items[:limit]
		last := response.Items[len(response.Items)-1]
		response.NextCursor = encodeCursor(last.CreatedAt, last.ID)
	}
	writeJSON(w, http.StatusOK, response)
}

func (s *Server) getSource(w http.ResponseWriter, r *http.Request) {
	source, err := s.sources.Get(r.Context(), r.PathValue("id"))
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "source_not_found", "Kaynak bulunamadı.")
		return
	}
	if err != nil {
		s.logger.Error("get source failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Kaynak getirilemedi.")
		return
	}
	writeJSON(w, http.StatusOK, source)
}

func (s *Server) createSource(w http.ResponseWriter, r *http.Request) {
	var input domain.CreateSourceInput
	if !decodeJSON(w, r, &input) {
		return
	}
	validationError := normalizeAndValidateSource(&input)
	if validationError != "" {
		writeError(w, http.StatusUnprocessableEntity, "validation_failed", validationError)
		return
	}
	principal, _ := principalFrom(r.Context())
	source, err := s.sources.Create(r.Context(), input, principal.Subject)
	if err != nil {
		s.logger.Error("create source failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Kaynak oluşturulamadı.")
		return
	}
	writeJSON(w, http.StatusCreated, source)
}

func (s *Server) updateSource(w http.ResponseWriter, r *http.Request) {
	var input domain.UpdateSourceInput
	if !decodeJSON(w, r, &input) {
		return
	}
	if message := normalizeAndValidateSourceUpdate(&input); message != "" {
		writeError(w, http.StatusUnprocessableEntity, "validation_failed", message)
		return
	}
	principal, _ := principalFrom(r.Context())
	source, err := s.sources.Update(r.Context(), r.PathValue("id"), input, principal.Subject)
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "source_not_found", "Kaynak bulunamadı.")
		return
	}
	if errors.Is(err, repository.ErrConflict) {
		writeError(w, http.StatusConflict, "version_conflict", "Kaynak başka bir kullanıcı tarafından güncellendi. Sayfayı yenileyin.")
		return
	}
	if err != nil {
		s.logger.Error("update source failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Kaynak güncellenemedi.")
		return
	}
	writeJSON(w, http.StatusOK, source)
}

type ingestRequest struct {
	LocalPath string `json:"local_path"`
}

var distillationProviders = map[string]bool{
	"anthropic": true, "openai": true, "google": true, "xai": true, "alibaba": true, "echo": true,
}

func (s *Server) distillSource(w http.ResponseWriter, r *http.Request) {
	var input repository.DistillationInput
	if !decodeJSON(w, r, &input) {
		return
	}
	input.Provider = strings.TrimSpace(input.Provider)
	if !distillationProviders[input.Provider] {
		writeError(w, http.StatusUnprocessableEntity, "invalid_provider", "Desteklenmeyen LLM sağlayıcısı.")
		return
	}
	if strings.TrimSpace(input.PromptTemplate) == "" {
		writeError(w, http.StatusUnprocessableEntity, "missing_prompt", "Prompt şablonu zorunludur.")
		return
	}
	if len(input.Topics) == 0 && input.Count < 1 {
		writeError(w, http.StatusUnprocessableEntity, "missing_count", "Konu listesi veya en az 1 belge sayısı gerekir.")
		return
	}
	if input.MaxTokens <= 0 {
		input.MaxTokens = 2000
	}
	if input.MaxTokens > 32000 {
		writeError(w, http.StatusUnprocessableEntity, "invalid_max_tokens", "max_tokens en fazla 32000 olabilir.")
		return
	}
	if len(input.Topics) > 500 || input.Count > 500 {
		writeError(w, http.StatusUnprocessableEntity, "count_too_large", "Tek seferde en fazla 500 belge üretilebilir.")
		return
	}
	if input.Temperature <= 0 {
		input.Temperature = 1.0
	}
	principal, _ := principalFrom(r.Context())
	jobID, err := s.sources.QueueDistillation(r.Context(), r.PathValue("id"), input, principal.Subject)
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "source_not_found", "Kaynak bulunamadı.")
		return
	}
	if errors.Is(err, repository.ErrConflict) {
		writeError(w, http.StatusConflict, "distill_conflict", "Kaynağa zaten içerik alınmış veya aktif bir iş var.")
		return
	}
	if err != nil {
		s.logger.Error("queue distillation failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Distilasyon işi oluşturulamadı.")
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]string{"job_id": jobID, "status": "queued"})
}

func (s *Server) queueSourceIngest(w http.ResponseWriter, r *http.Request) {
	var request ingestRequest
	if !decodeJSON(w, r, &request) {
		return
	}
	request.LocalPath = strings.TrimSpace(request.LocalPath)
	resolvedPath, err := resolveImportFile(s.importRoot, request.LocalPath)
	if err != nil {
		writeError(w, http.StatusUnprocessableEntity, "invalid_local_path", "Dosya IMPORT_ROOT altında, sembolik bağ içermeyen normal bir dosya olmalıdır.")
		return
	}
	principal, _ := principalFrom(r.Context())
	jobID, err := s.sources.QueueLocalIngest(r.Context(), r.PathValue("id"), resolvedPath, principal.Subject)
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "source_not_found", "Kaynak bulunamadı veya daha önce içeri alınmış.")
		return
	}
	if errors.Is(err, repository.ErrConflict) {
		writeError(w, http.StatusConflict, "ingest_conflict", "Kaynak daha önce içe alınmış veya aktif bir içe aktarma işi var.")
		return
	}
	if err != nil {
		s.logger.Error("queue ingest failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "İçe aktarma işi oluşturulamadı.")
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]string{"job_id": jobID, "status": "queued"})
}

func normalizeAndValidateSource(input *domain.CreateSourceInput) string {
	input.Name = strings.TrimSpace(input.Name)
	input.SourceType = strings.TrimSpace(input.SourceType)
	input.ContentPurpose = strings.TrimSpace(input.ContentPurpose)
	input.License = strings.TrimSpace(input.License)
	input.RightsStatus = strings.TrimSpace(input.RightsStatus)
	input.Language = strings.TrimSpace(input.Language)
	input.Domain = strings.TrimSpace(input.Domain)
	input.LineageRef = strings.TrimSpace(input.LineageRef)
	input.SourceURL = trimOptional(input.SourceURL)
	input.LicenseEvidenceRef = trimOptional(input.LicenseEvidenceRef)

	if input.Name == "" || input.SourceType == "" || input.License == "" || input.Language == "" || input.Domain == "" || input.LineageRef == "" {
		return "Ad, kaynak tipi, lisans, dil, alan ve köken bilgisi zorunludur."
	}
	if _, ok := domain.ContentPurposes[input.ContentPurpose]; !ok {
		return "Geçerli bir içerik amacı seçilmelidir."
	}
	if input.RightsStatus == "" {
		input.RightsStatus = "unknown"
	}
	if _, ok := domain.RightsStatuses[input.RightsStatus]; !ok {
		return "Geçerli bir hak durumu seçilmelidir."
	}
	if input.RightsStatus == "cleared" && input.LicenseEvidenceRef == nil {
		return "Hak durumu temizlenmiş kaynaklarda lisans kanıtı zorunludur."
	}
	return ""
}

func normalizeAndValidateSourceUpdate(input *domain.UpdateSourceInput) string {
	input.Name = strings.TrimSpace(input.Name)
	input.SourceType = strings.TrimSpace(input.SourceType)
	input.License = strings.TrimSpace(input.License)
	input.RightsStatus = strings.TrimSpace(input.RightsStatus)
	input.Language = strings.TrimSpace(input.Language)
	input.Domain = strings.TrimSpace(input.Domain)
	input.LineageRef = strings.TrimSpace(input.LineageRef)
	input.SourceURL = trimOptional(input.SourceURL)
	input.LicenseEvidenceRef = trimOptional(input.LicenseEvidenceRef)

	if input.Version <= 0 {
		return "Geçerli kaynak sürümü zorunludur."
	}
	if input.Name == "" || input.SourceType == "" || input.License == "" || input.Language == "" || input.Domain == "" || input.LineageRef == "" {
		return "Ad, kaynak tipi, lisans, dil, alan ve köken bilgisi zorunludur."
	}
	if _, ok := domain.RightsStatuses[input.RightsStatus]; !ok {
		return "Geçerli bir hak durumu seçilmelidir."
	}
	if input.RightsStatus == "cleared" && input.LicenseEvidenceRef == nil {
		return "Hak durumu temizlenmiş kaynaklarda lisans kanıtı zorunludur."
	}
	return ""
}

func (s *Server) reviewSource(w http.ResponseWriter, r *http.Request) {
	var input domain.ReviewInput
	if !decodeJSON(w, r, &input) {
		return
	}
	input.Decision = strings.TrimSpace(input.Decision)
	if !slices.Contains([]string{"approved", "rejected", "sensitive_review"}, input.Decision) {
		writeError(w, http.StatusUnprocessableEntity, "invalid_decision", "Geçerli bir inceleme kararı seçilmelidir.")
		return
	}
	input.Reason = trimOptional(input.Reason)
	principal, _ := principalFrom(r.Context())
	allowSelfReview := slices.Contains(principal.Roles, "admin")
	source, review, err := s.sources.Review(r.Context(), r.PathValue("id"), input, principal.Subject, allowSelfReview)
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "source_not_found", "Kaynak bulunamadı.")
		return
	}
	if errors.Is(err, repository.ErrSelfReview) {
		writeError(w, http.StatusForbidden, "self_review_forbidden", "Kendi oluşturduğunuz kaynağı onaylayamazsınız.")
		return
	}
	var gateError *repository.GateError
	if errors.As(err, &gateError) {
		writeJSON(w, http.StatusUnprocessableEntity, map[string]any{
			"error": map[string]any{
				"code": "review_gate_blocked", "message": "Kaynak inceleme kapılarından geçemedi.", "reasons": gateError.Reasons,
			},
		})
		return
	}
	if err != nil {
		s.logger.Error("review source failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "İnceleme kaydedilemedi.")
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{"source": source, "review": review})
}

func (s *Server) listSourceReviews(w http.ResponseWriter, r *http.Request) {
	reviews, err := s.sources.ListReviews(r.Context(), r.PathValue("id"))
	if err != nil {
		s.logger.Error("list reviews failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "İnceleme geçmişi getirilemedi.")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": reviews})
}

func (s *Server) listSourcePIIScans(w http.ResponseWriter, r *http.Request) {
	scans, err := s.sources.ListPIIScans(r.Context(), r.PathValue("id"))
	if err != nil {
		s.logger.Error("list PII scans failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "PII taramaları getirilemedi.")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": scans})
}

func (s *Server) listJobs(w http.ResponseWriter, r *http.Request) {
	limit, err := auth.ParsePositiveInt(r.URL.Query().Get("limit"), 50, 200)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid_limit", "Limit pozitif bir sayı olmalıdır.")
		return
	}
	jobs, err := s.sources.ListJobs(r.Context(), strings.TrimSpace(r.URL.Query().Get("source_id")), limit)
	if err != nil {
		s.logger.Error("list jobs failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "İş kayıtları getirilemedi.")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": jobs})
}

func trimOptional(value *string) *string {
	if value == nil {
		return nil
	}
	trimmed := strings.TrimSpace(*value)
	if trimmed == "" {
		return nil
	}
	return &trimmed
}

func encodeCursor(createdAt time.Time, id string) string {
	value := createdAt.UTC().Format(time.RFC3339Nano) + "|" + id
	return base64.RawURLEncoding.EncodeToString([]byte(value))
}

func decodeCursor(value string) (*time.Time, string, error) {
	if value == "" {
		return nil, "", nil
	}
	decoded, err := base64.RawURLEncoding.DecodeString(value)
	if err != nil {
		return nil, "", err
	}
	timeValue, id, found := strings.Cut(string(decoded), "|")
	if !found || id == "" {
		return nil, "", errors.New("invalid cursor")
	}
	parsed, err := time.Parse(time.RFC3339Nano, timeValue)
	if err != nil {
		return nil, "", err
	}
	return &parsed, id, nil
}
