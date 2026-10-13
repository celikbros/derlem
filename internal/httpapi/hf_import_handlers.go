package httpapi

import (
	"errors"
	"fmt"
	"net/http"
	"path/filepath"
	"strings"

	"github.com/celikbros/derlem/internal/domain"
	"github.com/celikbros/derlem/internal/repository"
)

// hfImportRequest, POST /api/v1/sources/import-hf govdesi (TASK-032). Veri seti,
// sabit surum, config/split ve sutunlar uyarlayici yaml'indadir; isci onu
// dogrular. Bilinmeyen alan decodeJSON'da reddedilir.
type hfImportRequest struct {
	AdapterPath        string  `json:"adapter_path"`
	ContentPurpose     string  `json:"content_purpose"`
	RightsStatus       string  `json:"rights_status"`
	LicenseEvidenceRef *string `json:"license_evidence_ref"`
	LineageNote        *string `json:"lineage_note"`
	Name               *string `json:"name"`
	Language           *string `json:"language"`
	Domain             *string `json:"domain"`
}

const (
	hfSourceType          = "hf_dataset"
	hfPendingLicense      = "hf-card:pending"
	hfLicenseEvidenceRoot = "docs/haklar/"
	hfMaxLineageNote      = 2000
)

func (s *Server) importHFDataset(w http.ResponseWriter, r *http.Request) {
	var request hfImportRequest
	if !decodeJSON(w, r, &request) {
		return
	}
	adapterPath, err := resolveAdapterPath(s.importRoot, s.adaptersRoot, strings.TrimSpace(request.AdapterPath))
	if err != nil {
		writeError(w, http.StatusUnprocessableEntity, "invalid_adapter_path",
			"Uyarlayıcı IMPORT_ROOT ya da ADAPTERS_ROOT altında, sembolik bağ içermeyen bir .yaml dosyası olmalıdır.")
		return
	}
	input, lineageNote, message := hfImportSourceInput(request, adapterPath)
	if message != "" {
		writeError(w, http.StatusUnprocessableEntity, "validation_failed", message)
		return
	}
	principal, _ := principalFrom(r.Context())
	source, jobID, err := s.sources.QueueHFImport(r.Context(), input, adapterPath, lineageNote, principal.Subject)
	if errors.Is(err, repository.ErrConflict) {
		writeError(w, http.StatusConflict, "import_conflict", "Bu uyarlayıcıyla çalışan bir alım işi zaten var.")
		return
	}
	if err != nil {
		s.logger.Error("queue hf import failed", "error", err)
		writeError(w, http.StatusInternalServerError, "internal_error", "Alım işi oluşturulamadı.")
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]any{"job_id": jobID, "status": "queued", "source": source})
}

// resolveAdapterPath: mutlak yol IMPORT_ROOT ya da ADAPTERS_ROOT altinda olmali;
// goreli yol ADAPTERS_ROOT'a goredir. Yol kokten cikamaz, sembolik bag icermez.
func resolveAdapterPath(importRoot, adaptersRoot, candidate string) (string, error) {
	if candidate == "" {
		return "", errInvalidImportPath
	}
	lower := strings.ToLower(candidate)
	if !strings.HasSuffix(lower, ".yaml") && !strings.HasSuffix(lower, ".yml") {
		return "", fmt.Errorf("%w: adapter must be a yaml file", errInvalidImportPath)
	}
	if !filepath.IsAbs(candidate) {
		if strings.TrimSpace(adaptersRoot) == "" {
			return "", errInvalidImportPath
		}
		root, err := filepath.Abs(adaptersRoot)
		if err != nil {
			return "", fmt.Errorf("%w: %v", errInvalidImportPath, err)
		}
		return resolveImportFile(root, filepath.Join(root, candidate))
	}
	for _, root := range []string{importRoot, adaptersRoot} {
		if strings.TrimSpace(root) == "" {
			continue
		}
		absolute, err := filepath.Abs(root)
		if err != nil {
			continue
		}
		if resolved, err := resolveImportFile(absolute, candidate); err == nil {
			return resolved, nil
		}
	}
	return "", fmt.Errorf("%w: adapter is outside IMPORT_ROOT and ADAPTERS_ROOT", errInvalidImportPath)
}

func hfImportSourceInput(request hfImportRequest, adapterPath string) (domain.CreateSourceInput, *string, string) {
	lineageNote := trimOptional(request.LineageNote)
	if lineageNote != nil && len(*lineageNote) > hfMaxLineageNote {
		return domain.CreateSourceInput{}, nil, "Köken notu en fazla 2000 karakter olabilir."
	}
	evidence := trimOptional(request.LicenseEvidenceRef)
	if evidence != nil {
		ref := filepath.ToSlash(*evidence)
		if !strings.HasPrefix(ref, hfLicenseEvidenceRoot) || strings.Contains(ref, "..") || len(ref) <= len(hfLicenseEvidenceRoot) {
			return domain.CreateSourceInput{}, nil, "Lisans kanıtı docs/haklar/ altındaki kaynak notunun yolu olmalıdır."
		}
		evidence = &ref
	}
	stem := strings.TrimSuffix(filepath.Base(adapterPath), filepath.Ext(adapterPath))
	name := "HF: " + stem
	if value := trimOptional(request.Name); value != nil {
		name = *value
	}
	language := "tr"
	if value := trimOptional(request.Language); value != nil {
		language = *value
	}
	domainValue := "general"
	if value := trimOptional(request.Domain); value != nil {
		domainValue = *value
	}
	lineage := "hf-import pending: adapter=" + filepath.Base(adapterPath)
	input := domain.CreateSourceInput{
		Name:               name,
		SourceType:         hfSourceType,
		ContentPurpose:     request.ContentPurpose,
		License:            hfPendingLicense,
		RightsStatus:       request.RightsStatus,
		Language:           language,
		Domain:             domainValue,
		LicenseEvidenceRef: evidence,
		LineageRef:         lineage,
	}
	if message := normalizeAndValidateSource(&input); message != "" {
		return domain.CreateSourceInput{}, nil, message
	}
	return input, lineageNote, ""
}
