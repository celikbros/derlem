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
	// Label ve Order, web formundaki alan etiketi ve sırası (katalog). Label
	// doğrulama mesajlarında da kullanılır; "(opsiyonel)" eki web'dedir.
	Label string
	Order int
	// Hint, alanın yanındaki yardım düğmesinin açtığı açıklama; Placeholder,
	// boş kutuda görünen örnek.
	Hint        string
	Placeholder string
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
	// Yardım metinleri (katalog): Description tip seçiminin altında hep görünür;
	// *Hint yardım düğmesiyle açılır; *Placeholder boş kutudaki örnektir.
	Description       string
	PromptHint        string
	PromptPlaceholder string
	BodyHint          string
	BodyPlaceholder   string
	// OriginHint, bu tipte kökenin nasıl seçileceği (boşsa genel açıklama yeter);
	// DefaultDataOrigin, formun bu tip seçilince önerdiği köken (boşsa human).
	OriginHint        string
	DefaultDataOrigin string
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
		Payload: map[string]ContributionPayloadField{
			"knowledge_source": knowledgeSourceField(1),
		},
		BundleEmission: BundleEmissionConversation,
		Label:          "Soru-cevap çifti",
		PromptLabel:    "Soru",
		BodyLabel:      "Cevap",
		DisplayOrder:   1,
		Description: "Bir soru ve ona sizin yazdığınız doğru, eksiksiz cevap. " +
			"Modele soruları nasıl cevaplayacağını öğretir.",
		PromptHint: "Bir kullanıcının yapay zekâya soracağı gibi, tek başına anlaşılır bir soru " +
			"ya da istek yazın.",
		PromptPlaceholder: "örn. Fotosentez nedir, kısaca anlatır mısın?",
		BodyHint: "Sorunun ideal cevabı: doğru, açık ve soruyu tam karşılayan. Başka yerden " +
			"kopyalamayın, kendi cümlelerinizle yazın.",
		BodyPlaceholder: "örn. Fotosentez, bitkilerin güneş ışığını kullanarak su ve karbondioksitten " +
			"besin ve oksijen üretmesidir.",
	},
	"free_text": {
		ContentPurpose:  "pretrain",
		PromptForbidden: true,
		BundleEmission:  BundleEmissionPlainText,
		Label:           "Serbest metin",
		BodyLabel:       "Metin",
		DisplayOrder:    2,
		Description: "Soru-cevap biçiminde olmayan, kendi yazdığınız düz metin (açıklama, makale, " +
			"hikâye). Modelin genel Türkçe bilgisini besler.",
		BodyHint: "Birkaç cümle ya da daha uzun, kendi yazdığınız bir metin. Ad-soyad, telefon, " +
			"e-posta, kimlik numarası gibi kişisel bilgi içermesin.",
		BodyPlaceholder: "Metninizi buraya yazın…",
	},
	// Cevap düzeltme: prompt = soru, body = düzeltilmiş cevap (katkının ürettiği
	// metin), payload.original_response = orijinal cevap (000028).
	"response_edit_pair": {
		ContentPurpose: "preference",
		PromptRequired: true,
		Payload: map[string]ContributionPayloadField{
			"original_response": {
				Required: true, MaxChars: 100000, Label: "Orijinal cevap", Order: 1,
				Hint: "Yapay zekânın bu soruya verdiği cevabı olduğu gibi yapıştırın; " +
					"içindeki hataları burada düzeltmeyin.",
				Placeholder: "örn. Evet, ses her yerde yayılır.",
			},
			"edit_note": {
				MaxChars: 2000, Label: "Ne düzeltildi?", Order: 2,
				Hint: "İnceleyene kısa bir not: neyi, neden değiştirdiniz? " +
					"Boş bırakabilirsiniz.",
				Placeholder: "örn. Bilgi yanlıştı; ses boşlukta yayılmaz.",
			},
			"knowledge_source": knowledgeSourceField(3),
		},
		DistinctFromBody: "original_response",
		BundleEmission:   BundleEmissionPreference,
		Label:            "Cevap düzeltme (öncesi / sonrası)",
		PromptLabel:      "Soru",
		BodyLabel:        "Düzeltilmiş cevap",
		DisplayOrder:     3,
		Description: "Bir yapay zekânın verdiği hatalı ya da zayıf cevabı düzeltirsiniz. Model, " +
			"düzeltilmiş cevabı orijinaline tercih etmeyi öğrenir.",
		PromptHint:        "Yapay zekâya sorulan soru. Orijinal cevap bu soruya verilmiş olmalı.",
		PromptPlaceholder: "örn. Ses boşlukta yayılır mı?",
		BodyHint: "Cevabın sizin düzelttiğiniz, doğru hâli. Orijinal cevaptan farklı olmalı; " +
			"aynıysa katkı gönderilmez.",
		BodyPlaceholder: "örn. Hayır; ses yayılmak için hava ya da su gibi bir ortam ister, " +
			"boşlukta yayılmaz.",
		OriginHint: "Orijinal cevabı bir yapay zekâ verdiyse \"Model çıktısını düzenledim\" seçin " +
			"ve o modelin adını yazın. Orijinal cevabı da siz yazdıysanız \"Kendim yazdım\" seçin.",
		DefaultDataOrigin: "hybrid",
	},
}

// knowledgeSourceField, bilginin nereden öğrenildiği (kitap, belgesel, site).
// İnceleyici doğruluğu kontrol ederken kullanır; kanonik kaydın metadata'sında
// taşınır. Düz metin satırı ({"id","text"}) payload taşıyamadığı için düz metin
// tiplerine eklenmez (TestPlainTextTypesDeclareNoPayload).
func knowledgeSourceField(order int) ContributionPayloadField {
	return ContributionPayloadField{
		MaxChars: 500, Label: "Bilgi kaynağı", Order: order,
		Hint: "Bu bilgiyi nereden öğrendiniz? Kitap adı ve sayfası, belgesel, web sitesi gibi. " +
			"İnceleyici doğruluğu kontrol ederken bakar. Kişi adı yazmayın. Kaynaktaki metni " +
			"aynen kopyalamayın; kendi cümlelerinizle yazın.",
		Placeholder: "örn. Fizik 10 ders kitabı, s. 45",
	}
}

// ContributionDataOriginGuide, köken sorusunun ne sorduğu; formda köken
// açıklamasının başında görünür.
const ContributionDataOriginGuide = "Köken, bilgiyi nereden öğrendiğinizi değil, bu kelimeleri kimin yazdığını sorar. " +
	"Bir kitaptan, filmden ya da birinden öğrendiğinizi kendi cümlelerinizle yazdıysanız \"Kendim yazdım\" seçin; " +
	"bilginin nereden geldiğini \"Bilgi kaynağı\" alanına yazın. Bir kitaptan, filmden ya da siteden metin " +
	"aynen kopyalanmaz: onay kutusu metni sizin ürettiğinizi beyan eder."

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
	RequiresModelID bool   `json:"requires_model_id"`
	Hint            string `json:"hint"`
}

// ContributionDataOriginOptions, köken seçeneklerinin form sırası. Üyeleri
// ContributionDataOrigins ile aynı olmak zorundadır (katalog testi zorlar).
var ContributionDataOriginOptions = []ContributionDataOriginOption{
	{Value: "human", Label: "Kendim yazdım",
		Hint: "Kelimeleri siz yazdınız; bilgiyi bir kitaptan ya da birinden öğrenmiş olsanız bile."},
	{Value: "hybrid", Label: "Model çıktısını düzenledim", RequiresModelID: true,
		Hint: "Bir yapay zekânın çıktısını alıp üzerinde değişiklik yaptınız."},
	{Value: "model", Label: "Model çıktısı", RequiresModelID: true,
		Hint: "Metin bir yapay zekânın çıktısı; siz değiştirmediniz."},
	{Value: "unknown", Label: "Bilinmiyor",
		Hint: "Metnin nasıl üretildiğini bilmiyorsunuz."},
}

// ContributionCatalog, kayıt defterinin web'e verilen görünümü. Web formu tip
// listesini elle kopyalamaz; bu yapı web/lib/contribution-task-types.json olarak
// yazılır ve TestContributionCatalogMatchesWebFixture onu bayt bayt karşılaştırır.
type ContributionCatalog struct {
	TaskTypes       []ContributionCatalogTaskType  `json:"task_types"`
	DataOrigins     []ContributionDataOriginOption `json:"data_origins"`
	DataOriginGuide string                         `json:"data_origin_guide"`
}

type ContributionCatalogTaskType struct {
	Name              string                     `json:"name"`
	Label             string                     `json:"label"`
	Description       string                     `json:"description"`
	ContentPurpose    string                     `json:"content_purpose"`
	PromptRequired    bool                       `json:"prompt_required"`
	PromptForbidden   bool                       `json:"prompt_forbidden"`
	PromptLabel       string                     `json:"prompt_label"`
	PromptHint        string                     `json:"prompt_hint"`
	PromptPlaceholder string                     `json:"prompt_placeholder"`
	BodyLabel         string                     `json:"body_label"`
	BodyHint          string                     `json:"body_hint"`
	BodyPlaceholder   string                     `json:"body_placeholder"`
	Payload           []ContributionCatalogField `json:"payload"`
	DistinctFromBody  string                     `json:"distinct_from_body"`
	OriginHint        string                     `json:"origin_hint"`
	DefaultDataOrigin string                     `json:"default_data_origin"`
}

type ContributionCatalogField struct {
	Key         string `json:"key"`
	Label       string `json:"label"`
	Hint        string `json:"hint"`
	Placeholder string `json:"placeholder"`
	Required    bool   `json:"required"`
	MaxChars    int    `json:"max_chars"`
}

// ContributionTaskTypeCatalog, kayıt defterini sıralı ve belirlenimci biçimde
// döndürür: tipler DisplayOrder'a, payload alanları Order'a göre (eşitlikte ada
// göre).
func ContributionTaskTypeCatalog() ContributionCatalog {
	catalog := ContributionCatalog{
		TaskTypes:       make([]ContributionCatalogTaskType, 0, len(ContributionTaskTypes)),
		DataOrigins:     append([]ContributionDataOriginOption(nil), ContributionDataOriginOptions...),
		DataOriginGuide: ContributionDataOriginGuide,
	}
	for name, entry := range ContributionTaskTypes {
		fields := make([]ContributionCatalogField, 0, len(entry.Payload))
		for key, field := range entry.Payload {
			fields = append(fields, ContributionCatalogField{
				Key: key, Label: field.Label, Hint: field.Hint, Placeholder: field.Placeholder,
				Required: field.Required, MaxChars: field.MaxChars,
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
			Name:              name,
			Label:             entry.Label,
			Description:       entry.Description,
			ContentPurpose:    entry.ContentPurpose,
			PromptRequired:    entry.PromptRequired,
			PromptForbidden:   entry.PromptForbidden,
			PromptLabel:       entry.PromptLabel,
			PromptHint:        entry.PromptHint,
			PromptPlaceholder: entry.PromptPlaceholder,
			BodyLabel:         entry.BodyLabel,
			BodyHint:          entry.BodyHint,
			BodyPlaceholder:   entry.BodyPlaceholder,
			Payload:           fields,
			DistinctFromBody:  entry.DistinctFromBody,
			OriginHint:        entry.OriginHint,
			DefaultDataOrigin: entry.DefaultDataOrigin,
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
