package httpapi

import (
	"errors"
	"net/http"
	"slices"

	"github.com/celikbros/derlem/internal/auth"
	"github.com/celikbros/derlem/internal/domain"
	"github.com/celikbros/derlem/internal/repository"
)

func (s *Server) listSimilarityCalibrationRuns(w http.ResponseWriter, r *http.Request) {
	runs, err := s.similarities.ListRuns(r.Context())
	if err != nil {
		s.logger.Error("list similarity calibration runs failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Benzerlik kalibrasyonlari getirilemedi.")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": runs})
}

func (s *Server) listSimilarityReviewPairs(w http.ResponseWriter, r *http.Request) {
	limit, err := auth.ParsePositiveInt(r.URL.Query().Get("limit"), 100, 200)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid_limit", "Limit pozitif bir sayi olmalidir.")
		return
	}
	principal, _ := principalFrom(r.Context())
	pairs, err := s.similarities.ListPairs(r.Context(), r.PathValue("id"), principal.Subject, limit)
	if err != nil {
		s.logger.Error("list similarity review pairs failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Benzerlik ciftleri getirilemedi.")
		return
	}
	if len(pairs) == 0 {
		writeError(w, http.StatusNotFound, "similarity_run_not_found", "Benzerlik kalibrasyonu bulunamadi.")
		return
	}
	for index := range pairs {
		pairs[index] = blindSimilarityPair(pairs[index], principal.Roles)
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": pairs})
}

func (s *Server) getSimilarityReviewPair(w http.ResponseWriter, r *http.Request) {
	principal, _ := principalFrom(r.Context())
	pair, err := s.similarities.GetPair(r.Context(), r.PathValue("id"), principal.Subject)
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "similarity_pair_not_found", "Benzerlik cifti bulunamadi.")
		return
	}
	if err != nil {
		s.logger.Error("get similarity review pair failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Benzerlik cifti getirilemedi.")
		return
	}
	leftContent, err := s.readDocumentObject(r, pair.LeftObjectSHA256)
	if err != nil {
		s.logger.Error("read left similarity object failed", "pair_id", pair.ID, "error", err)
		writeError(w, http.StatusInternalServerError, "similarity_object_unavailable", "Sol belge okunamadi.")
		return
	}
	rightContent, err := s.readDocumentObject(r, pair.RightObjectSHA256)
	if err != nil {
		s.logger.Error("read right similarity object failed", "pair_id", pair.ID, "error", err)
		writeError(w, http.StatusInternalServerError, "similarity_object_unavailable", "Sag belge okunamadi.")
		return
	}
	reviews := []domain.SimilarityPairReview{}
	if !similarityEvidenceIsBlinded(pair, principal.Roles) {
		reviews, err = s.similarities.ListPairReviews(r.Context(), pair.ID)
		if err != nil {
			s.logger.Error("list similarity pair reviews failed", "pair_id", pair.ID, "error", err)
			writeError(w, http.StatusInternalServerError, "internal_error", "Benzerlik incelemeleri getirilemedi.")
			return
		}
	}
	pair = blindSimilarityPair(pair, principal.Roles)
	writeJSON(w, http.StatusOK, domain.SimilarityPairDetail{
		Pair: pair, LeftContent: leftContent, RightContent: rightContent, Reviews: reviews,
	})
}

func similarityEvidenceIsBlinded(pair domain.SimilarityReviewPair, roles []string) bool {
	return pair.CurrentReviewerLabel == nil && similarityReviewerEligible(roles)
}

func similarityReviewerEligible(roles []string) bool {
	return slices.Contains(roles, "admin") ||
		slices.Contains(roles, "moderator") ||
		slices.Contains(roles, "expert_reviewer")
}

func blindSimilarityPair(pair domain.SimilarityReviewPair, roles []string) domain.SimilarityReviewPair {
	if !similarityEvidenceIsBlinded(pair, roles) {
		return pair
	}
	pair.ReviewCount = 0
	pair.ConsensusLabel = nil
	pair.HasDisagreement = false
	return pair
}

func (s *Server) reviewSimilarityPair(w http.ResponseWriter, r *http.Request) {
	var input domain.ReviewSimilarityPairInput
	if !decodeJSON(w, r, &input) {
		return
	}
	principal, _ := principalFrom(r.Context())
	review, err := s.similarities.ReviewPair(r.Context(), r.PathValue("id"), principal.Subject, input)
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "similarity_pair_not_found", "Benzerlik cifti bulunamadi.")
		return
	}
	if errors.Is(err, repository.ErrConflict) {
		writeError(w, http.StatusConflict, "similarity_review_conflict", "Bu cifti daha once incelediniz.")
		return
	}
	var gateError *repository.GateError
	if errors.As(err, &gateError) {
		writeJSON(w, http.StatusUnprocessableEntity, map[string]any{
			"error": map[string]any{
				"code":    "similarity_review_validation_failed",
				"message": "Benzerlik inceleme girdisi gecersiz.",
				"reasons": gateError.Reasons,
			},
		})
		return
	}
	if err != nil {
		s.logger.Error("review similarity pair failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Benzerlik incelemesi kaydedilemedi.")
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{"review": review})
}
