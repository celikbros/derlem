package httpapi

import (
	"errors"
	"fmt"
	"net/http"
	"sort"
	"strings"
	"unicode/utf8"

	"github.com/celikbros/derlem/internal/domain"
	"github.com/celikbros/derlem/internal/repository"
)

const (
	maxContributionPromptChars  = 10000
	maxContributionBodyChars    = 100000
	maxContributionDomainChars  = 100
	maxContributionModelIDChars = 200
)

// contributionTaskTypeNames, hata mesajı için kayıt defterindeki tipleri sıralı
// verir; mesaj yeni tip eklendiğinde kendiliğinden güncel kalır.
func contributionTaskTypeNames() string {
	names := make([]string, 0, len(domain.ContributionTaskTypes))
	for name := range domain.ContributionTaskTypes {
		names = append(names, name)
	}
	sort.Strings(names)
	return strings.Join(names, ", ")
}

// normalizeAndValidateContribution, katkı girdisini kırpar ve neden listesi
// döndürür (normalizeAndValidateSource ile aynı desen). Tipe özel kurallar
// domain.ContributionTaskTypes'tan okunur.
func normalizeAndValidateContribution(input *domain.SubmitContributionInput) []string {
	input.TaskType = strings.TrimSpace(input.TaskType)
	input.Domain = strings.TrimSpace(input.Domain)
	input.Prompt = strings.TrimSpace(input.Prompt)
	input.Body = strings.TrimSpace(input.Body)
	input.DataOrigin = strings.TrimSpace(input.DataOrigin)
	input.ModelID = strings.TrimSpace(input.ModelID)
	if input.DataOrigin == "" {
		input.DataOrigin = "human"
	}

	reasons := make([]string, 0)
	taskType, known := domain.ContributionTaskTypes[input.TaskType]
	if !known {
		reasons = append(reasons, "Görev tipi şunlardan biri olmalıdır: "+contributionTaskTypeNames()+".")
	}
	if known && taskType.PromptRequired && input.Prompt == "" {
		reasons = append(reasons, "Bu görev tipinde soru boş olamaz.")
	}
	// Soru alanı kullanılmayan tipte gönderilen soru demete girmez; kabul edip
	// sessizce düşürmek yerine gönderim anında reddedilir (katkıcının tepki
	// verebildiği tek yer).
	if known && taskType.PromptForbidden && input.Prompt != "" {
		reasons = append(reasons, "Bu görev tipinde soru alanı kullanılmaz; tüm metni tek alana yazın.")
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
	if known {
		reasons = append(reasons, validateContributionPayload(input, taskType)...)
	}
	reasons = append(reasons, validateContributionOrigin(input)...)
	return reasons
}

// validateContributionPayload, payload'ı tipin anahtar şemasına göre doğrular,
// değerleri kırpar ve boş isteğe bağlı anahtarları atar. Bilinmeyen anahtar
// adıyla reddedilir.
func validateContributionPayload(input *domain.SubmitContributionInput, taskType domain.ContributionTaskType) []string {
	reasons := make([]string, 0)
	normalized := make(map[string]string, len(input.Payload))

	submittedKeys := make([]string, 0, len(input.Payload))
	for key := range input.Payload {
		submittedKeys = append(submittedKeys, key)
	}
	sort.Strings(submittedKeys)
	for _, key := range submittedKeys {
		field, allowed := taskType.Payload[key]
		if !allowed {
			reasons = append(reasons, fmt.Sprintf("payload.%s bu görev tipinde kullanılmaz.", key))
			continue
		}
		value := strings.TrimSpace(input.Payload[key])
		if utf8.RuneCountInString(value) > field.MaxChars {
			reasons = append(reasons, fmt.Sprintf("payload.%s %d karakteri aşamaz.", key, field.MaxChars))
		}
		if value != "" {
			normalized[key] = value
		}
	}

	declaredKeys := make([]string, 0, len(taskType.Payload))
	for key := range taskType.Payload {
		declaredKeys = append(declaredKeys, key)
	}
	sort.Strings(declaredKeys)
	for _, key := range declaredKeys {
		if taskType.Payload[key].Required && normalized[key] == "" {
			reasons = append(reasons, fmt.Sprintf("payload.%s zorunludur.", key))
		}
	}

	if key := taskType.DistinctFromBody; key != "" && normalized[key] != "" &&
		collapseWhitespace(normalized[key]) == collapseWhitespace(input.Body) {
		reasons = append(reasons, fmt.Sprintf(
			"payload.%s metinle aynı; değişiklik yoksa bu katkı gönderilmez.", key,
		))
	}

	input.Payload = normalized
	return reasons
}

// validateContributionOrigin, kökeni sources.data_origin sözlüğüyle doğrular.
// Model ya da karma kökenli katkı model adını taşır; insan kökenli katkıda model
// adı anlamsızdır ve reddedilir.
func validateContributionOrigin(input *domain.SubmitContributionInput) []string {
	if _, ok := domain.ContributionDataOrigins[input.DataOrigin]; !ok {
		return []string{"Köken unknown, human, model veya hybrid olmalıdır."}
	}
	reasons := make([]string, 0)
	modelOrigin := input.DataOrigin == "model" || input.DataOrigin == "hybrid"
	if modelOrigin && input.ModelID == "" {
		reasons = append(reasons, "Model ya da karma kökenli katkıda model adı zorunludur.")
	}
	if !modelOrigin && input.ModelID != "" {
		reasons = append(reasons, "Model adı yalnız model ya da karma kökenli katkıda verilir.")
	}
	if utf8.RuneCountInString(input.ModelID) > maxContributionModelIDChars {
		reasons = append(reasons, "Model adı 200 karakteri aşamaz.")
	}
	return reasons
}

func collapseWhitespace(value string) string {
	return strings.Join(strings.Fields(value), " ")
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
		reasons = append(reasons, "Görev tipi şunlardan biri olmalıdır: "+contributionTaskTypeNames()+".")
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
