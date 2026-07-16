package httpapi

import (
	"errors"
	"net/http"
	"strings"
	"unicode/utf8"

	"github.com/celikbros/derlem/internal/domain"
	"github.com/celikbros/derlem/internal/repository"
)

const (
	maxContributionPromptChars = 10000
	maxContributionBodyChars   = 100000
	maxContributionDomainChars = 100
)

// normalizeAndValidateContribution, katkı girdisini kırpar ve neden listesi
// döndürür (normalizeAndValidateSource ile aynı desen).
func normalizeAndValidateContribution(input *domain.SubmitContributionInput) []string {
	input.TaskType = strings.TrimSpace(input.TaskType)
	input.Domain = strings.TrimSpace(input.Domain)
	input.Prompt = strings.TrimSpace(input.Prompt)
	input.Body = strings.TrimSpace(input.Body)

	reasons := make([]string, 0)
	if _, ok := domain.ContributionTaskTypes[input.TaskType]; !ok {
		reasons = append(reasons, "Görev tipi qa_pair veya free_text olmalıdır.")
	}
	if input.TaskType == "qa_pair" && input.Prompt == "" {
		reasons = append(reasons, "Soru-cevap katkısında soru boş olamaz.")
	}
	if utf8.RuneCountInString(input.Prompt) > maxContributionPromptChars {
		reasons = append(reasons, "Soru 10.000 karakteri aşamaz.")
	}
	if input.Body == "" {
		reasons = append(reasons, "Metin boş olamaz.")
	}
	if utf8.RuneCountInString(input.Body) > maxContributionBodyChars {
		reasons = append(reasons, "Metin 100.000 karakteri aşamaz.")
	}
	if utf8.RuneCountInString(input.Domain) > maxContributionDomainChars {
		reasons = append(reasons, "Alan etiketi 100 karakteri aşamaz.")
	}
	if !input.AcceptTerms {
		reasons = append(reasons, "Kullanım şartı onaylanmadan katkı gönderilemez.")
	}
	return reasons
}

func (s *Server) submitContribution(w http.ResponseWriter, r *http.Request) {
	var input domain.SubmitContributionInput
	if !decodeJSON(w, r, &input) {
		return
	}
	if reasons := normalizeAndValidateContribution(&input); len(reasons) > 0 {
		writeJSON(w, http.StatusUnprocessableEntity, map[string]any{
			"error": map[string]any{
				"code": "contribution_validation_failed", "message": "Katkı girdileri geçerli değil.", "reasons": reasons,
			},
		})
		return
	}
	principal, _ := principalFrom(r.Context())
	contribution, err := s.contributions.Submit(r.Context(), principal.Subject, input)
	if err != nil {
		s.logger.Error("submit contribution failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Katkı kaydedilemedi.")
		return
	}
	writeJSON(w, http.StatusCreated, contribution)
}

func (s *Server) listMyContributions(w http.ResponseWriter, r *http.Request) {
	principal, _ := principalFrom(r.Context())
	contributions, err := s.contributions.ListMine(r.Context(), principal.Subject)
	if err != nil {
		s.logger.Error("list my contributions failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Katkılar listelenemedi.")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": contributions})
}

func (s *Server) listPendingContributions(w http.ResponseWriter, r *http.Request) {
	pending, err := s.contributions.ListPending(r.Context())
	if err != nil {
		s.logger.Error("list pending contributions failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Katkı havuzu listelenemedi.")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": pending})
}

func (s *Server) withdrawContribution(w http.ResponseWriter, r *http.Request) {
	principal, _ := principalFrom(r.Context())
	err := s.contributions.Withdraw(r.Context(), r.PathValue("id"), principal.Subject)
	if errors.Is(err, repository.ErrNotFound) {
		writeError(w, http.StatusNotFound, "contribution_not_found", "Katkı bulunamadı.")
		return
	}
	if errors.Is(err, repository.ErrConflict) {
		writeError(w, http.StatusConflict, "contribution_not_pending", "Katkı demetlenmiş veya zaten geri çekilmiş; geri çekilemez.")
		return
	}
	if err != nil {
		s.logger.Error("withdraw contribution failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Katkı geri çekilemedi.")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// normalizeAndValidateBundle, demetleme girdisini kırpar ve neden listesi
// döndürür. Dil boşsa tr varsayılır (ofis ölçeği varsayımı).
func normalizeAndValidateBundle(input *domain.BundleContributionsInput) []string {
	input.TaskType = strings.TrimSpace(input.TaskType)
	input.Name = strings.TrimSpace(input.Name)
	input.Language = strings.TrimSpace(input.Language)
	input.Domain = strings.TrimSpace(input.Domain)
	if input.Language == "" {
		input.Language = "tr"
	}

	reasons := make([]string, 0)
	if _, ok := domain.ContributionTaskTypes[input.TaskType]; !ok {
		reasons = append(reasons, "Görev tipi qa_pair veya free_text olmalıdır.")
	}
	if input.Name == "" {
		reasons = append(reasons, "Kaynak adı zorunludur.")
	}
	if input.Domain == "" {
		reasons = append(reasons, "Alan (domain) etiketi zorunludur.")
	}
	return reasons
}

func (s *Server) bundleContributions(w http.ResponseWriter, r *http.Request) {
	var input domain.BundleContributionsInput
	if !decodeJSON(w, r, &input) {
		return
	}
	if reasons := normalizeAndValidateBundle(&input); len(reasons) > 0 {
		writeJSON(w, http.StatusUnprocessableEntity, map[string]any{
			"error": map[string]any{
				"code": "bundle_validation_failed", "message": "Demetleme girdileri geçerli değil.", "reasons": reasons,
			},
		})
		return
	}
	principal, _ := principalFrom(r.Context())
	result, err := s.contributions.Bundle(r.Context(), input, s.stagingRoot, principal.Subject)
	var gateError *repository.GateError
	if errors.As(err, &gateError) {
		writeJSON(w, http.StatusUnprocessableEntity, map[string]any{
			"error": map[string]any{
				"code": "bundle_blocked", "message": "Katkı havuzu demetlenemedi.", "reasons": gateError.Reasons,
			},
		})
		return
	}
	if err != nil {
		s.logger.Error("bundle contributions failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Katkı havuzu demetlenemedi.")
		return
	}
	writeJSON(w, http.StatusCreated, result)
}
