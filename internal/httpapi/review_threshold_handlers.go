package httpapi

// TASK-048: pretrain inceleme eşiğinin yazıldığı uç. Ayrı dosyada ve ayrı
// rota listesinde durur (authorization.go'daki protectedRoutes'a eklenmedi);
// server.go iki listeyi aynı fail-closed rol politikasıyla kaydeder.

import (
	"bytes"
	"encoding/json"
	"errors"
	"net/http"

	"github.com/celikbros/derlem/internal/repository"
)

// reviewThresholdRoutes: eşiği yalnız admin (kurucu) koyar; çubuğu ölçümden
// önce koymak bir yönetim kararıdır, veri yöneticisi ya da inceleyici işi değil.
func reviewThresholdRoutes(s *Server) []protectedRoute {
	return []protectedRoute{
		{"PUT /api/v1/sources/{id}/pretrain-review-threshold", []string{roleAdmin}, s.setPretrainReviewThreshold},
	}
}

type pretrainReviewThresholdRequest struct {
	// json.RawMessage: anahtar zorunlu; null açıkça "eşiği kaldır" demektir.
	Threshold json.RawMessage `json:"pretrain_review_reject_threshold"`
}

// parsePretrainReviewThreshold, istek gövdesindeki eşiği ayrıştırır. ok=false
// ise anahtar yok ya da değer sayı/null değil.
func parsePretrainReviewThreshold(raw json.RawMessage) (*float64, bool) {
	trimmed := bytes.TrimSpace(raw)
	if len(trimmed) == 0 {
		return nil, false
	}
	if bytes.Equal(trimmed, []byte("null")) {
		return nil, true
	}
	var value float64
	if err := json.Unmarshal(trimmed, &value); err != nil {
		return nil, false
	}
	return &value, true
}

func (s *Server) setPretrainReviewThreshold(w http.ResponseWriter, r *http.Request) {
	var input pretrainReviewThresholdRequest
	if !decodeJSON(w, r, &input) {
		return
	}
	value, ok := parsePretrainReviewThreshold(input.Threshold)
	if !ok {
		writeError(w, http.StatusUnprocessableEntity, "validation_failed",
			"pretrain_review_reject_threshold zorunludur: 0-100 arası yüzde (en çok iki ondalık) ya da null.")
		return
	}
	principal, _ := principalFrom(r.Context())
	source, err := s.sources.SetPretrainReviewThreshold(r.Context(), r.PathValue("id"), value, principal.Subject)
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "source_not_found", "Kaynak bulunamadı.")
		return
	}
	var gateError *repository.GateError
	if errors.As(err, &gateError) {
		writeJSON(w, http.StatusUnprocessableEntity, map[string]any{
			"error": map[string]any{
				"code":    "pretrain_review_threshold_blocked",
				"message": "İnceleme eşiği yazılamadı: eşik yalnız pretrain kaynakta ve inceleme başlamadan önce konur.",
				"reasons": gateError.Reasons,
			},
		})
		return
	}
	if err != nil {
		s.logger.Error("set pretrain review threshold failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "İnceleme eşiği kaydedilemedi.")
		return
	}
	writeJSON(w, http.StatusOK, source)
}
