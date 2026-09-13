package domain

import (
	"sort"
	"time"
)

// ContributionPayloadField, bir görev tipinin payload anahtarı. DB yalnız
// payload'ın bir JSON nesnesi olduğunu bilir (000028); hangi anahtarın izinli,
// zorunlu ve en fazla kaç karakter olduğu burada bildirilir ve her gönderimde
// doğrulanır. Listede olmayan anahtar reddedilir: payload bir çöplük değildir.
type ContributionPayloadField struct {
	Required bool
	MaxChars int
	// Label ve Order, web formundaki alan etiketi ve sırası (katalog).
	Label string
	Order int
}

// Demetin bir görev tipini yazma biçimleri.
const (
	// BundleEmissionPlainText: {"id","text"} satırı. Yapısı olmayan tip içindir.
	BundleEmissionPlainText = "plain_text"
	// BundleEmissionConversation: kanonik konuşma kaydı (user = prompt,
	// assistant = body).
	BundleEmissionConversation = "canonical_conversation"
	// BundleEmissionPreference: kanonik tercih kaydı (bağlam = prompt,
	// chosen = body, rejected = payload[DistinctFromBody]).
	BundleEmissionPreference = "canonical_preference"
)

// ContributionTaskType, bir katkı görev tipinin kayıt defteri satırı. Doğrulama,
// demetleme ve web formu tipe özel dal yazmaz, buradan okur; yeni tip = yeni
// satır.
type ContributionTaskType struct {
	// ContentPurpose, demet kaynağının içerik amacı. Eşlemesi olmayan tip
	// demetlenemez (sources.content_purpose trigger'la değişmez; yanlış amaçla
	// yaratılan kaynak kalıcıdır).
	ContentPurpose string
	// PromptRequired: soru boş olamaz. PromptForbidden: soru alanı kullanılmaz
	// (gönderilirse demette sessizce düşerdi, bu yüzden reddedilir).
	PromptRequired  bool
	PromptForbidden bool
	// Payload, tipin izin verdiği anahtarlar.
	Payload map[string]ContributionPayloadField
	// DistinctFromBody, değeri body'den (boşluk farkı yok sayılarak) farklı olmak
	// zorunda olan payload anahtarı; boşsa kapı yok. Tercih yayınında bu anahtar
	// rejected dalıdır: gönderim kapısı, ihracatta özdeş dal reddinin
	// (preference_branches_identical) hiç tetiklenmemesini garanti eder.
	DistinctFromBody string
	// BundleEmission, demetin bu tipi nasıl yazdığı. Boşsa tip demetlenemez:
	// yazılamayan alanlar sessizce kaybolurdu (TASK-004 sınıfı).
	BundleEmission string
	// Web formu: tip etiketi, soru ve metin alanlarının etiketi, seçim sırası.
	Label        string
	PromptLabel  string
	BodyLabel    string
	DisplayOrder int
}

// ContributionTaskTypes, katkı kuyruğunun görev tipleri. Çeviri ve tercih
// karşılaştırması Faz B'dir, ayrı kart ve onay ister
// (docs/katki_gorev_tipleri_karar_notu.md). Her satırın içerik amacı ve yayın
// biçimi TestContentPurposeForTaskType ile, web kataloğu
// TestContributionCatalogMatchesWebFixture ile zorlanır.
var ContributionTaskTypes = map[string]ContributionTaskType{
	"qa_pair": {
		ContentPurpose: "instruction",
		PromptRequired: true,
		BundleEmission: BundleEmissionConversation,
		Label:          "Soru-cevap çifti",
		PromptLabel:    "Soru",
		BodyLabel:      "Cevap",
		DisplayOrder:   1,
	},
	"free_text": {
		ContentPurpose:  "pretrain",
		PromptForbidden: true,
		BundleEmission:  BundleEmissionPlainText,
		Label:           "Serbest metin",
		BodyLabel:       "Metin",
		DisplayOrder:    2,
	},
	// Cevap düzeltme: prompt = soru, body = düzeltilmiş cevap (katkının ürettiği
	// metin), payload.original_response = orijinal cevap (000028).
	"response_edit_pair": {
		ContentPurpose: "preference",
		PromptRequired: true,
		Payload: map[string]ContributionPayloadField{
			"original_response": {Required: true, MaxChars: 100000, Label: "Orijinal cevap", Order: 1},
			"edit_note":         {MaxChars: 2000, Label: "Ne düzeltildi? (opsiyonel)", Order: 2},
		},
		DistinctFromBody: "original_response",
		BundleEmission:   BundleEmissionPreference,
		Label:            "Cevap düzeltme (öncesi / sonrası)",
		PromptLabel:      "Soru",
		BodyLabel:        "Düzeltilmiş cevap",
		DisplayOrder:     3,
	},
}

// ContributionDataOrigins, katkının kökeni; sources.data_origin ile aynı sözlük
// (000024). model ve hybrid, model_id ister.
var ContributionDataOrigins = map[string]struct{}{
	"unknown": {},
	"human":   {},
	"model":   {},
	"hybrid":  {},
}

// ContributionDataOriginOption, web formundaki köken seçeneği.
type ContributionDataOriginOption struct {
	Value string `json:"value"`
	Label string `json:"label"`
	// RequiresModelID: bu kökende model adı zorunludur (doğrulamayla aynı kural).
	RequiresModelID bool `json:"requires_model_id"`
}

// ContributionDataOriginOptions, köken seçeneklerinin form sırası. Üyeleri
// ContributionDataOrigins ile aynı olmak zorundadır (katalog testi zorlar).
var ContributionDataOriginOptions = []ContributionDataOriginOption{
	{Value: "human", Label: "Kendim yazdım"},
	{Value: "hybrid", Label: "Model çıktısını düzenledim", RequiresModelID: true},
	{Value: "model", Label: "Model çıktısı", RequiresModelID: true},
	{Value: "unknown", Label: "Bilinmiyor"},
}

// ContributionCatalog, kayıt defterinin web'e verilen görünümü. Web formu tip
// listesini elle kopyalamaz; bu yapı web/lib/contribution-task-types.json olarak
// yazılır ve TestContributionCatalogMatchesWebFixture onu bayt bayt karşılaştırır.
type ContributionCatalog struct {
	TaskTypes   []ContributionCatalogTaskType  `json:"task_types"`
	DataOrigins []ContributionDataOriginOption `json:"data_origins"`
}

type ContributionCatalogTaskType struct {
	Name             string                     `json:"name"`
	Label            string                     `json:"label"`
	ContentPurpose   string                     `json:"content_purpose"`
	PromptRequired   bool                       `json:"prompt_required"`
	PromptForbidden  bool                       `json:"prompt_forbidden"`
	PromptLabel      string                     `json:"prompt_label"`
	BodyLabel        string                     `json:"body_label"`
	Payload          []ContributionCatalogField `json:"payload"`
	DistinctFromBody string                     `json:"distinct_from_body"`
}

type ContributionCatalogField struct {
	Key      string `json:"key"`
	Label    string `json:"label"`
	Required bool   `json:"required"`
	MaxChars int    `json:"max_chars"`
}

// ContributionTaskTypeCatalog, kayıt defterini sıralı ve belirlenimci biçimde
// döndürür: tipler DisplayOrder'a, payload alanları Order'a göre (eşitlikte ada
// göre).
func ContributionTaskTypeCatalog() ContributionCatalog {
	catalog := ContributionCatalog{
		TaskTypes:   make([]ContributionCatalogTaskType, 0, len(ContributionTaskTypes)),
		DataOrigins: append([]ContributionDataOriginOption(nil), ContributionDataOriginOptions...),
	}
	for name, entry := range ContributionTaskTypes {
		fields := make([]ContributionCatalogField, 0, len(entry.Payload))
		for key, field := range entry.Payload {
			fields = append(fields, ContributionCatalogField{
				Key: key, Label: field.Label, Required: field.Required, MaxChars: field.MaxChars,
			})
		}
		sort.Slice(fields, func(i, j int) bool {
			left, right := entry.Payload[fields[i].Key], entry.Payload[fields[j].Key]
			if left.Order != right.Order {
				return left.Order < right.Order
			}
			return fields[i].Key < fields[j].Key
		})
		catalog.TaskTypes = append(catalog.TaskTypes, ContributionCatalogTaskType{
			Name:             name,
			Label:            entry.Label,
			ContentPurpose:   entry.ContentPurpose,
			PromptRequired:   entry.PromptRequired,
			PromptForbidden:  entry.PromptForbidden,
			PromptLabel:      entry.PromptLabel,
			BodyLabel:        entry.BodyLabel,
			Payload:          fields,
			DistinctFromBody: entry.DistinctFromBody,
		})
	}
	sort.Slice(catalog.TaskTypes, func(i, j int) bool {
		left := ContributionTaskTypes[catalog.TaskTypes[i].Name]
		right := ContributionTaskTypes[catalog.TaskTypes[j].Name]
		if left.DisplayOrder != right.DisplayOrder {
			return left.DisplayOrder < right.DisplayOrder
		}
		return catalog.TaskTypes[i].Name < catalog.TaskTypes[j].Name
	})
	return catalog
}

// ContributionTermsVersion, katkı gönderilirken onaylanan kullanım şartının
// sürümüdür; her katkıya lineage olarak işlenir.
const ContributionTermsVersion = "office-v1"

type Contribution struct {
	ID            string            `json:"id"`
	ContributorID string            `json:"contributor_id"`
	TaskType      string            `json:"task_type"`
	Domain        string            `json:"domain"`
	Prompt        string            `json:"prompt"`
	Body          string            `json:"body"`
	Payload       map[string]string `json:"payload"`
	DataOrigin    string            `json:"data_origin"`
	ModelID       *string           `json:"model_id"`
	TermsVersion  string            `json:"terms_ack_version"`
	Status        string            `json:"status"`
	SourceID      *string           `json:"source_id"`
	CreatedAt     time.Time         `json:"created_at"`
	UpdatedAt     time.Time         `json:"updated_at"`
}

// PendingContribution, demetleme havuzunda görünen satır; katkıcı kimliği
// yalnız görünen adla verilir (e-posta havuz listesine sızmaz).
type PendingContribution struct {
	ID              string            `json:"id"`
	TaskType        string            `json:"task_type"`
	Domain          string            `json:"domain"`
	Prompt          string            `json:"prompt"`
	Body            string            `json:"body"`
	Payload         map[string]string `json:"payload"`
	DataOrigin      string            `json:"data_origin"`
	ModelID         *string           `json:"model_id"`
	ContributorName string            `json:"contributor_name"`
	CreatedAt       time.Time         `json:"created_at"`
}

type SubmitContributionInput struct {
	TaskType    string            `json:"task_type"`
	Domain      string            `json:"domain"`
	Prompt      string            `json:"prompt"`
	Body        string            `json:"body"`
	Payload     map[string]string `json:"payload"`
	DataOrigin  string            `json:"data_origin"`
	ModelID     string            `json:"model_id"`
	AcceptTerms bool              `json:"accept_terms"`
}

// BundleContributionsInput, bekleyen havuzu tek kaynağa demetler. İçerik amacı
// görev tipinin kayıt defteri satırından türetilir.
type BundleContributionsInput struct {
	TaskType string `json:"task_type"`
	Name     string `json:"name"`
	Language string `json:"language"`
	Domain   string `json:"domain"`
}

type ContributionBundleResult struct {
	SourceID string `json:"source_id"`
	JobID    string `json:"job_id"`
	Count    int64  `json:"count"`
}
