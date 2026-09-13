package domain

import "time"

// ContributionPayloadField, bir görev tipinin payload anahtarı. DB yalnız
// payload'ın bir JSON nesnesi olduğunu bilir (000028); hangi anahtarın izinli,
// zorunlu ve en fazla kaç karakter olduğu burada bildirilir ve her gönderimde
// doğrulanır. Listede olmayan anahtar reddedilir: payload bir çöplük değildir.
type ContributionPayloadField struct {
	Required bool
	MaxChars int
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

// ContributionTaskType, bir katkı görev tipinin kayıt defteri satırı. Doğrulama
// ve demetleme tipe özel dal yazmaz, buradan okur; yeni tip = yeni satır.
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
}

// ContributionTaskTypes, katkı kuyruğunun görev tipleri. Çeviri ve tercih
// karşılaştırması Faz B'dir, ayrı kart ve onay ister
// (docs/katki_gorev_tipleri_karar_notu.md). Her satırın içerik amacı
// TestContentPurposeForTaskType ile zorlanır.
var ContributionTaskTypes = map[string]ContributionTaskType{
	"qa_pair": {
		ContentPurpose: "instruction",
		PromptRequired: true,
		BundleEmission: BundleEmissionConversation,
	},
	"free_text": {
		ContentPurpose:  "pretrain",
		PromptForbidden: true,
		BundleEmission:  BundleEmissionPlainText,
	},
	// Cevap düzeltme: prompt = soru, body = düzeltilmiş cevap (katkının ürettiği
	// metin), payload.original_response = orijinal cevap (000028).
	"response_edit_pair": {
		ContentPurpose: "preference",
		PromptRequired: true,
		Payload: map[string]ContributionPayloadField{
			"original_response": {Required: true, MaxChars: 100000},
			"edit_note":         {MaxChars: 2000},
		},
		DistinctFromBody: "original_response",
		BundleEmission:   BundleEmissionPreference,
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
