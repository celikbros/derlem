package httpapi

import (
	"errors"
	"io"
	"net/http"
	"slices"
	"strings"
	"unicode/utf8"

	"github.com/celikbros/derlem/internal/auth"
	"github.com/celikbros/derlem/internal/domain"
	"github.com/celikbros/derlem/internal/repository"
)

const maxEditableDocumentBytes = 1024 * 1024

func (s *Server) listSourceDocuments(w http.ResponseWriter, r *http.Request) {
	limit, err := auth.ParsePositiveInt(r.URL.Query().Get("limit"), 50, 200)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid_limit", "Limit pozitif bir sayı olmalıdır.")
		return
	}
	sourceID := r.PathValue("id")
	if _, err := s.sources.Get(r.Context(), sourceID); errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "source_not_found", "Kaynak bulunamadı.")
		return
	} else if err != nil {
		s.logger.Error("get source before document list failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Kaynak doğrulanamadı.")
		return
	}

	documents, err := s.documents.ListBySource(r.Context(), sourceID, limit)
	if err != nil {
		s.logger.Error("list source documents failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Belge örnekleri getirilemedi.")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": documents})
}

func (s *Server) getDocumentQualitySummary(w http.ResponseWriter, r *http.Request) {
	sourceID := r.PathValue("id")
	if _, err := s.sources.Get(r.Context(), sourceID); errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "source_not_found", "Kaynak bulunamadı.")
		return
	} else if err != nil {
		s.logger.Error("get source before quality summary failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Kaynak doğrulanamadı.")
		return
	}

	summary, err := s.documents.QualitySummary(r.Context(), sourceID)
	if err != nil {
		s.logger.Error("get document quality summary failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Kalite özeti getirilemedi.")
		return
	}
	writeJSON(w, http.StatusOK, summary)
}

func (s *Server) queueDocumentResample(w http.ResponseWriter, r *http.Request) {
	principal, _ := principalFrom(r.Context())
	jobID, err := s.documents.QueueResample(r.Context(), r.PathValue("id"), principal.Subject)
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "source_not_found", "Kaynak bulunamadı.")
		return
	}
	if errors.Is(err, repository.ErrConflict) {
		writeError(w, http.StatusConflict, "document_resample_conflict", "Aktif bir yeniden örnekleme işi var veya kaynak durumu değişti.")
		return
	}
	var gateError *repository.GateError
	if errors.As(err, &gateError) {
		writeJSON(w, http.StatusUnprocessableEntity, map[string]any{
			"error": map[string]any{
				"code":    "document_resample_gate_blocked",
				"message": "Kaynak güvenli yeniden örnekleme koşullarını karşılamıyor.",
				"reasons": gateError.Reasons,
			},
		})
		return
	}
	if err != nil {
		s.logger.Error("queue document resample failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Yeniden örnekleme işi başlatılamadı.")
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]string{"job_id": jobID, "status": "queued"})
}

func (s *Server) listDocumentSampleGenerations(w http.ResponseWriter, r *http.Request) {
	sourceID := r.PathValue("id")
	if _, err := s.sources.Get(r.Context(), sourceID); errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "source_not_found", "Kaynak bulunamadı.")
		return
	} else if err != nil {
		s.logger.Error("get source before sample generation list failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Kaynak doğrulanamadı.")
		return
	}
	generations, err := s.documents.ListSampleGenerations(r.Context(), sourceID)
	if err != nil {
		s.logger.Error("list document sample generations failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Örnek nesilleri getirilemedi.")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": generations})
}

func (s *Server) getDocument(w http.ResponseWriter, r *http.Request) {
	document, err := s.documents.Get(r.Context(), r.PathValue("id"))
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "document_not_found", "Belge bulunamadı.")
		return
	}
	if err != nil {
		s.logger.Error("get document failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Belge getirilemedi.")
		return
	}

	content, err := s.readDocumentObject(r, document.CurrentObjectSHA256)
	if err != nil {
		s.logger.Error("read document object failed", "document_id", document.ID, "error", err)
		writeError(w, http.StatusInternalServerError, "document_object_unavailable", "Belge içeriği okunamadı.")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"document": document, "content": content})
}

func (s *Server) updateDocument(w http.ResponseWriter, r *http.Request) {
	var input domain.UpdateDocumentInput
	if !decodeJSON(w, r, &input) {
		return
	}
	if input.Version <= 0 || strings.TrimSpace(input.Content) == "" {
		writeError(w, http.StatusUnprocessableEntity, "validation_failed", "Belge içeriği ve geçerli sürüm zorunludur.")
		return
	}
	if len([]byte(input.Content)) > maxEditableDocumentBytes {
		writeError(w, http.StatusRequestEntityTooLarge, "document_too_large", "Belge içeriği 1 MiB sınırını aşamaz.")
		return
	}
	if !utf8.ValidString(input.Content) {
		writeError(w, http.StatusUnprocessableEntity, "invalid_utf8", "Belge içeriği UTF-8 olmalıdır.")
		return
	}
	existing, err := s.documents.Get(r.Context(), r.PathValue("id"))
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "document_not_found", "Belge bulunamadı.")
		return
	}
	if err != nil {
		s.logger.Error("get document before update failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Belge doğrulanamadı.")
		return
	}
	if existing.CurrentVersion != input.Version {
		writeError(w, http.StatusConflict, "version_conflict", "Belge başka bir kullanıcı tarafından güncellendi. Yeniden açın.")
		return
	}

	object, err := s.objectStore.Put(r.Context(), strings.NewReader(input.Content))
	if err != nil {
		s.logger.Error("store document edit failed", "error", err)
		writeError(w, http.StatusInternalServerError, "storage_error", "Belge sürümü saklanamadı.")
		return
	}
	principal, _ := principalFrom(r.Context())
	document, err := s.documents.UpdateContent(
		r.Context(),
		r.PathValue("id"),
		input.Version,
		object,
		repository.DocumentPreview(input.Content),
		int64(utf8.RuneCountInString(input.Content)),
		input.Reason,
		principal.Subject,
	)
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "document_not_found", "Belge bulunamadı.")
		return
	}
	if errors.Is(err, repository.ErrConflict) {
		writeError(w, http.StatusConflict, "version_conflict", "Belge başka bir kullanıcı tarafından güncellendi. Yeniden açın.")
		return
	}
	if err != nil {
		s.logger.Error("update document failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Belge güncellenemedi.")
		return
	}
	writeJSON(w, http.StatusOK, document)
}

func (s *Server) listDocumentReviews(w http.ResponseWriter, r *http.Request) {
	documentID := r.PathValue("id")
	if _, err := s.documents.Get(r.Context(), documentID); errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "document_not_found", "Belge bulunamadı.")
		return
	} else if err != nil {
		s.logger.Error("get document before review list failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Belge doğrulanamadı.")
		return
	}
	reviews, err := s.documents.ListReviews(r.Context(), documentID)
	if err != nil {
		s.logger.Error("list document reviews failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Belge incelemeleri getirilemedi.")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": reviews})
}

func (s *Server) reviewDocument(w http.ResponseWriter, r *http.Request) {
	var input domain.ReviewDocumentInput
	if !decodeJSON(w, r, &input) {
		return
	}
	principal, _ := principalFrom(r.Context())
	source, document, review, err := s.documents.Review(
		r.Context(),
		r.PathValue("id"),
		input,
		principal.Subject,
		slices.Contains(principal.Roles, "admin"),
	)
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "document_not_found", "Belge bulunamadı.")
		return
	}
	if errors.Is(err, repository.ErrSelfReview) {
		writeError(w, http.StatusForbidden, "self_review_forbidden", "Kendi kaynağınızdaki belge örneğini onaylayamazsınız.")
		return
	}
	if errors.Is(err, repository.ErrConflict) {
		writeError(w, http.StatusConflict, "review_conflict", "Bu belge sürümü değişti veya tarafınızdan daha önce incelendi.")
		return
	}
	var gateError *repository.GateError
	if errors.As(err, &gateError) {
		writeJSON(w, http.StatusUnprocessableEntity, map[string]any{
			"error": map[string]any{
				"code":    "document_review_gate_blocked",
				"message": "Belge inceleme girdileri geçerli değil.",
				"reasons": gateError.Reasons,
			},
		})
		return
	}
	if err != nil {
		s.logger.Error("review document failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Belge incelemesi kaydedilemedi.")
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{
		"source": source, "document": document, "review": review,
	})
}

func (s *Server) bulkReviewDocuments(w http.ResponseWriter, r *http.Request) {
	var input domain.BulkReviewDocumentsInput
	if !decodeJSON(w, r, &input) {
		return
	}
	principal, _ := principalFrom(r.Context())
	result, err := s.documents.BulkReview(
		r.Context(),
		r.PathValue("id"),
		input,
		principal.Subject,
		slices.Contains(principal.Roles, "admin"),
	)
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "bulk_review_document_not_found", "Kaynak veya seçilen belgelerden biri bulunamadı.")
		return
	}
	if errors.Is(err, repository.ErrSelfReview) {
		writeError(w, http.StatusForbidden, "self_review_forbidden", "Kendi kaynağınızdaki belge örneklerini onaylayamazsınız.")
		return
	}
	if errors.Is(err, repository.ErrConflict) {
		writeError(w, http.StatusConflict, "bulk_review_conflict", "Belgelerden biri değişti veya daha önce tarafınızdan incelendi. Listeyi yenileyin.")
		return
	}
	var gateError *repository.GateError
	if errors.As(err, &gateError) {
		writeJSON(w, http.StatusUnprocessableEntity, map[string]any{
			"error": map[string]any{
				"code":    "bulk_document_review_gate_blocked",
				"message": "Toplu belge inceleme girdileri geçerli değil.",
				"reasons": gateError.Reasons,
			},
		})
		return
	}
	if err != nil {
		s.logger.Error("bulk review documents failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Toplu belge incelemesi kaydedilemedi.")
		return
	}
	writeJSON(w, http.StatusCreated, result)
}

func (s *Server) readDocumentObject(r *http.Request, digest string) (string, error) {
	reader, err := s.objectStore.Open(r.Context(), digest)
	if err != nil {
		return "", err
	}
	defer reader.Close()
	content, err := io.ReadAll(io.LimitReader(reader, maxEditableDocumentBytes+1))
	if err != nil {
		return "", err
	}
	if len(content) > maxEditableDocumentBytes || !utf8.Valid(content) {
		return "", errors.New("document object is too large or invalid UTF-8")
	}
	return string(content), nil
}
