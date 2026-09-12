package domain

import "time"

// ContributionTaskType, bir katkı görev tipinin kayıt defteri satırı. Demet
// kaynağının içerik amacı buradan türetilir; eşlemesi olmayan tip demetlenemez
// (sessiz bir "pretrain" varsayılanı yoktur — sources.content_purpose
// trigger'la değişmez, yanlış amaçla yaratılan kaynak kalıcıdır).
type ContributionTaskType struct {
	ContentPurpose string
}

// ContributionTaskTypes, katkı kuyruğunun ofis ölçeğindeki görev tipleri.
// Çeviri/preference gibi tipler açık kayıt fazına aittir
// (docs/katki_platformu_tasarimi.md). Yeni tip = yeni satır; amaç eşlemesi
// TestContentPurposeForTaskType ile her satır için zorlanır.
var ContributionTaskTypes = map[string]ContributionTaskType{
	"qa_pair":   {ContentPurpose: "instruction"},
	"free_text": {ContentPurpose: "pretrain"},
}

// ContributionTermsVersion, katkı gönderilirken onaylanan kullanım şartının
// sürümüdür; her katkıya lineage olarak işlenir.
const ContributionTermsVersion = "office-v1"

type Contribution struct {
	ID            string    `json:"id"`
	ContributorID string    `json:"contributor_id"`
	TaskType      string    `json:"task_type"`
	Domain        string    `json:"domain"`
	Prompt        string    `json:"prompt"`
	Body          string    `json:"body"`
	TermsVersion  string    `json:"terms_ack_version"`
	Status        string    `json:"status"`
	SourceID      *string   `json:"source_id"`
	CreatedAt     time.Time `json:"created_at"`
	UpdatedAt     time.Time `json:"updated_at"`
}

// PendingContribution, demetleme havuzunda görünen satır; katkıcı kimliği
// yalnız görünen adla verilir (e-posta havuz listesine sızmaz).
type PendingContribution struct {
	ID              string    `json:"id"`
	TaskType        string    `json:"task_type"`
	Domain          string    `json:"domain"`
	Prompt          string    `json:"prompt"`
	Body            string    `json:"body"`
	ContributorName string    `json:"contributor_name"`
	CreatedAt       time.Time `json:"created_at"`
}

type SubmitContributionInput struct {
	TaskType   string `json:"task_type"`
	Domain     string `json:"domain"`
	Prompt     string `json:"prompt"`
	Body       string `json:"body"`
	AcceptTerms bool  `json:"accept_terms"`
}

// BundleContributionsInput, bekleyen havuzu tek kaynağa demetler.
// İçerik amacı görev tipinden türetilir: qa_pair -> instruction,
// free_text -> pretrain.
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
