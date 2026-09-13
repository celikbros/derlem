package repository

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"

	"github.com/celikbros/derlem/internal/domain"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// Contributions, ofis ölçeğindeki katkı kuyruğunu yönetir: katkıcılar tekil
// kayıt gönderir, bekleyen havuz tek kaynağa demetlenir ve normal ingest
// kapılarından geçer. Güven kademeleri / N-onay açık kayıt fazına aittir.
type Contributions struct {
	pool *pgxpool.Pool
}

func NewContributions(pool *pgxpool.Pool) *Contributions {
	return &Contributions{pool: pool}
}

const contributionColumns = `
	id::text, contributor_id::text, task_type, domain, prompt, body,
	payload, data_origin, model_id,
	terms_ack_version, status, source_id::text, created_at, updated_at
`

func scanContribution(row pgx.Row) (domain.Contribution, error) {
	var contribution domain.Contribution
	err := row.Scan(
		&contribution.ID, &contribution.ContributorID, &contribution.TaskType,
		&contribution.Domain, &contribution.Prompt, &contribution.Body,
		&contribution.Payload, &contribution.DataOrigin, &contribution.ModelID,
		&contribution.TermsVersion, &contribution.Status, &contribution.SourceID,
		&contribution.CreatedAt, &contribution.UpdatedAt,
	)
	return contribution, err
}

// Submit yeni bir katkı kaydeder ve audit olayını aynı transaction'da yazar.
// Audit ayrıntısı içerik taşımaz: prompt, body ve payload değerleri ham
// kullanıcı içeriğidir (000023), yalnız tip, alan, şart ve köken yazılır.
func (r *Contributions) Submit(ctx context.Context, contributorID string, input domain.SubmitContributionInput) (domain.Contribution, error) {
	payload := input.Payload
	if payload == nil {
		// Boş map "null" olarak serileşir ve contributions_payload_object
		// kısıtını ihlal ederdi.
		payload = map[string]string{}
	}
	payloadJSON, err := json.Marshal(payload)
	if err != nil {
		return domain.Contribution{}, err
	}
	dataOrigin := input.DataOrigin
	if dataOrigin == "" {
		dataOrigin = "human"
	}
	var modelID any
	if input.ModelID != "" {
		modelID = input.ModelID
	}

	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return domain.Contribution{}, err
	}
	defer tx.Rollback(ctx)

	contribution, err := scanContribution(tx.QueryRow(ctx, `
		INSERT INTO contributions(
			contributor_id, task_type, domain, prompt, body,
			payload, data_origin, model_id, terms_ack_version
		)
		VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9)
		RETURNING `+contributionColumns,
		contributorID, input.TaskType, input.Domain, input.Prompt, input.Body,
		string(payloadJSON), dataOrigin, modelID, domain.ContributionTermsVersion,
	))
	if err != nil {
		return domain.Contribution{}, err
	}

	details, err := json.Marshal(map[string]any{
		"task_type":   contribution.TaskType,
		"domain":      contribution.Domain,
		"terms_ack":   contribution.TermsVersion,
		"data_origin": contribution.DataOrigin,
		"model_id":    contribution.ModelID,
	})
	if err != nil {
		return domain.Contribution{}, err
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES ($1, 'contribution.submitted', 'contribution', $2, $3::jsonb)
	`, contributorID, contribution.ID, details); err != nil {
		return domain.Contribution{}, err
	}
	return contribution, tx.Commit(ctx)
}

// ListMine, katkıcının kendi kayıtlarını en yeniden eskiye listeler.
func (r *Contributions) ListMine(ctx context.Context, contributorID string) ([]domain.Contribution, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT `+contributionColumns+`
		FROM contributions
		WHERE contributor_id = $1
		ORDER BY created_at DESC
		LIMIT 500
	`, contributorID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	contributions := make([]domain.Contribution, 0)
	for rows.Next() {
		contribution, err := scanContribution(rows)
		if err != nil {
			return nil, err
		}
		contributions = append(contributions, contribution)
	}
	return contributions, rows.Err()
}

// ListPending, demetleme havuzunu listeler (yalnız admin/data_manager uçları
// çağırır). Katkıcının e-postası değil görünen adı verilir.
func (r *Contributions) ListPending(ctx context.Context) ([]domain.PendingContribution, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT c.id::text, c.task_type, c.domain, c.prompt, c.body,
		       c.payload, c.data_origin, c.model_id,
		       u.display_name, c.created_at
		FROM contributions c
		JOIN users u ON u.id = c.contributor_id
		WHERE c.status = 'submitted'
		ORDER BY c.created_at
		LIMIT 2000
	`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	pending := make([]domain.PendingContribution, 0)
	for rows.Next() {
		var item domain.PendingContribution
		if err := rows.Scan(
			&item.ID, &item.TaskType, &item.Domain, &item.Prompt, &item.Body,
			&item.Payload, &item.DataOrigin, &item.ModelID,
			&item.ContributorName, &item.CreatedAt,
		); err != nil {
			return nil, err
		}
		pending = append(pending, item)
	}
	return pending, rows.Err()
}

// Withdraw, katkıcının kendi bekleyen kaydını geri çeker. Kayıt başka
// kullanıcıya aitse yokmuş gibi davranılır; demetlenmiş kayıt geri çekilemez.
func (r *Contributions) Withdraw(ctx context.Context, contributionID, contributorID string) error {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)

	var status string
	err = tx.QueryRow(ctx, `
		SELECT status FROM contributions
		WHERE id = $1 AND contributor_id = $2
		FOR UPDATE
	`, contributionID, contributorID).Scan(&status)
	if errors.Is(err, pgx.ErrNoRows) {
		return ErrNotFound
	}
	if err != nil {
		return err
	}
	if status != "submitted" {
		return ErrConflict
	}

	if _, err := tx.Exec(ctx, `
		UPDATE contributions SET status = 'withdrawn' WHERE id = $1
	`, contributionID); err != nil {
		return err
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES ($1, 'contribution.withdrawn', 'contribution', $2, '{}'::jsonb)
	`, contributorID, contributionID); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

type bundleItem struct {
	ID         string
	Domain     string
	Prompt     string
	Body       string
	Payload    map[string]string
	DataOrigin string
	ModelID    *string
}

// canonicalSchemaVersion, worker/src/derlem_worker/canonical.py
// CANONICAL_SCHEMA_VERSION ile aynı olmalıdır; sözleşme
// data_samples/example_contribution_bundles.jsonl ile iki dilde de sınanır.
const canonicalSchemaVersion = "derlem.canonical-sample.v1"

type canonicalMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type canonicalPreference struct {
	Chosen   []canonicalMessage `json:"chosen"`
	Rejected []canonicalMessage `json:"rejected"`
}

// canonicalRecord, demetin yazdığı kanonik satır. Boş isteğe bağlı alanlar
// yazılmaz: ayrıştırıcı boş dizeyi reddeder ve tek geçersiz kayıt ihracatta tüm
// release'i bloke eder. Katkıcı kimliği (created_by) bilerek yoktur.
type canonicalRecord struct {
	SchemaVersion  string               `json:"schema_version"`
	RecordType     string               `json:"record_type"`
	SampleID       string               `json:"sample_id"`
	ContentPurpose string               `json:"content_purpose"`
	TaskType       string               `json:"task_type"`
	Language       string               `json:"language,omitempty"`
	Domain         string               `json:"domain,omitempty"`
	TrainPolicy    string               `json:"train_policy"`
	Messages       []canonicalMessage   `json:"messages"`
	Preference     *canonicalPreference `json:"preference,omitempty"`
	Metadata       map[string]string    `json:"metadata"`
}

// buildContributionJSONL, demet dosyasının satırlarını kayıt defterindeki
// yayın biçimine göre üretir. Yapısı olmayan tip düz {"id","text"} satırı;
// yapılı tipler kanonik kayıt (derlem.canonical-sample.v1) olur ve soru, cevap,
// orijinal cevap, köken, model adı ile kalan payload anahtarları kaybolmaz.
// Katkıcı kimliği dosyaya asla yazılmaz (kimlik-içerik ayrımı).
func buildContributionJSONL(taskType, contentPurpose, language string, items []bundleItem) ([]byte, error) {
	entry, ok := domain.ContributionTaskTypes[taskType]
	if !ok || entry.BundleEmission == "" {
		return nil, fmt.Errorf("contribution task type %q has no bundle emission", taskType)
	}

	var buffer bytes.Buffer
	encoder := json.NewEncoder(&buffer)
	encoder.SetEscapeHTML(false)
	for _, item := range items {
		var line any
		switch entry.BundleEmission {
		case domain.BundleEmissionPlainText:
			line = map[string]string{"id": item.ID, "text": item.Body}
		case domain.BundleEmissionConversation:
			record := newCanonicalRecord(item, taskType, contentPurpose, language, "conversation", "")
			record.Messages = []canonicalMessage{
				{Role: "user", Content: item.Prompt},
				{Role: "assistant", Content: item.Body},
			}
			line = record
		case domain.BundleEmissionPreference:
			rejected := item.Payload[entry.DistinctFromBody]
			if entry.DistinctFromBody == "" || rejected == "" {
				return nil, fmt.Errorf("contribution %s has no rejected branch in payload.%s", item.ID, entry.DistinctFromBody)
			}
			record := newCanonicalRecord(item, taskType, contentPurpose, language, "preference", entry.DistinctFromBody)
			record.Messages = []canonicalMessage{{Role: "user", Content: item.Prompt}}
			record.Preference = &canonicalPreference{
				Chosen:   []canonicalMessage{{Role: "assistant", Content: item.Body}},
				Rejected: []canonicalMessage{{Role: "assistant", Content: rejected}},
			}
			line = record
		default:
			return nil, fmt.Errorf("contribution task type %q has unknown bundle emission %q", taskType, entry.BundleEmission)
		}
		if err := encoder.Encode(line); err != nil {
			return nil, err
		}
	}
	return buffer.Bytes(), nil
}

// newCanonicalRecord, kaydın ortak alanlarını ve metadata'sını kurar. metadata:
// köken, varsa model adı ve kayda başka yerde yazılmayan payload anahtarları
// (consumedKey, tercih dalına yazılan anahtardır).
func newCanonicalRecord(item bundleItem, taskType, contentPurpose, language, recordType, consumedKey string) canonicalRecord {
	metadata := map[string]string{"data_origin": item.DataOrigin}
	if item.ModelID != nil && *item.ModelID != "" {
		metadata["model_id"] = *item.ModelID
	}
	keys := make([]string, 0, len(item.Payload))
	for key := range item.Payload {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	for _, key := range keys {
		if key != consumedKey && item.Payload[key] != "" {
			metadata[key] = item.Payload[key]
		}
	}
	return canonicalRecord{
		SchemaVersion:  canonicalSchemaVersion,
		RecordType:     recordType,
		SampleID:       item.ID,
		ContentPurpose: contentPurpose,
		TaskType:       taskType,
		Language:       language,
		Domain:         item.Domain,
		TrainPolicy:    "assistant_only",
		Metadata:       metadata,
	}
}

// contentPurposeForTaskType, demet kaynağının içerik amacını kayıt defterinden
// okur. Eşlemesi olmayan tip hata döndürür: eski sessiz "pretrain" varsayılanı,
// yeni bir tip eklenip burası unutulduğunda kaynağı kalıcı olarak yanlış amaçla
// yaratıyordu (tercih kayıtları ihracatta reddedilir, release bloke olur).
func contentPurposeForTaskType(taskType string) (string, error) {
	entry, ok := domain.ContributionTaskTypes[taskType]
	if !ok || entry.ContentPurpose == "" {
		return "", fmt.Errorf("contribution task type %q has no content_purpose mapping", taskType)
	}
	return entry.ContentPurpose, nil
}

// Bundle, bekleyen havuzu tek transaction içinde kaynağa demetler: katkılar
// FOR UPDATE ile kilitlenir, JSONL staging'e yazılır, kaynak + ingest job'u
// + audit olayları eklenir ve katkılar kaynağa bağlanır. Dosya yazımı
// transaction dışı tek yan etkidir; commit başarısız olursa dosya silinir.
func (r *Contributions) Bundle(ctx context.Context, input domain.BundleContributionsInput, stagingRoot, actorID string) (domain.ContributionBundleResult, error) {
	contentPurpose, err := contentPurposeForTaskType(input.TaskType)
	if err != nil {
		return domain.ContributionBundleResult{}, err
	}
	if domain.ContributionTaskTypes[input.TaskType].BundleEmission == "" {
		return domain.ContributionBundleResult{}, &GateError{Reasons: []string{
			"Bu görev tipinin demet yayın biçimi tanımlı değil; alanları sessizce kaybolacağı için demetlenemez.",
		}}
	}

	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return domain.ContributionBundleResult{}, err
	}
	defer tx.Rollback(ctx)

	// Kaynağa demet düzeyinde tek alan yazılır; kaynak etiketi yanlış olmasın
	// diye demet yalnız o alanla eşleşen (veya alanı boş) katkıları alır, kalanlar
	// havuzda görünür kalır. Köken ve model adı kanonik kaydın metadata'sında
	// yolculuk eder; kaynak düzeyinde data_origin 'unknown' kalır (TASK-002 D2a).
	rows, err := tx.Query(ctx, `
		SELECT id::text, domain, prompt, body, payload, data_origin, model_id
		FROM contributions
		WHERE status = 'submitted' AND task_type = $1
		  AND (domain = '' OR lower(domain) = lower($2))
		ORDER BY created_at
		FOR UPDATE
	`, input.TaskType, input.Domain)
	if err != nil {
		return domain.ContributionBundleResult{}, err
	}
	items := make([]bundleItem, 0)
	ids := make([]string, 0)
	for rows.Next() {
		var item bundleItem
		if err := rows.Scan(
			&item.ID, &item.Domain, &item.Prompt, &item.Body,
			&item.Payload, &item.DataOrigin, &item.ModelID,
		); err != nil {
			rows.Close()
			return domain.ContributionBundleResult{}, err
		}
		items = append(items, item)
		ids = append(ids, item.ID)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return domain.ContributionBundleResult{}, err
	}
	if len(items) == 0 {
		return domain.ContributionBundleResult{}, &GateError{Reasons: []string{
			"Bu görev tipinde ve alanda bekleyen katkı yok (farklı alan etiketli katkılar kendi alanlarıyla demetlenir).",
		}}
	}

	payloadBytes, err := buildContributionJSONL(input.TaskType, contentPurpose, input.Language, items)
	if err != nil {
		return domain.ContributionBundleResult{}, err
	}
	stagedPath, err := writeStagedContributionFile(stagingRoot, payloadBytes)
	if err != nil {
		return domain.ContributionBundleResult{}, err
	}
	cleanupStaged := true
	defer func() {
		if cleanupStaged {
			os.Remove(stagedPath)
		}
	}()

	evidence := fmt.Sprintf(
		"contributions.terms_ack=%s; katkı kayıtları ve şart onayları contributions tablosu + audit'tedir",
		domain.ContributionTermsVersion,
	)
	lineage := fmt.Sprintf(
		"katkı kuyruğu demeti: %d katkı, görev tipi %s, şart %s",
		len(items), input.TaskType, domain.ContributionTermsVersion,
	)
	var sourceID string
	err = tx.QueryRow(ctx, `
		INSERT INTO sources(
			name, source_type, content_purpose, license, rights_status,
			language, domain, license_evidence_ref, lineage_ref, created_by
		)
		VALUES ($1, 'community_contribution', $2, 'topluluk-katkisi-ic-sozlesme-v1', 'cleared', $3, $4, $5, $6, $7)
		RETURNING id::text
	`, input.Name, contentPurpose, input.Language,
		input.Domain, evidence, lineage, actorID).Scan(&sourceID)
	if err != nil {
		return domain.ContributionBundleResult{}, err
	}

	var jobID string
	if err := tx.QueryRow(ctx, `
		INSERT INTO background_jobs(job_type, payload, created_by)
		VALUES ('ingest_staged_file', $1::jsonb, $2)
		RETURNING id::text
	`, mustJSON(map[string]any{
		"source_id":         sourceID,
		"staged_path":       stagedPath,
		"original_filename": "katki-demeti.jsonl",
		"uploaded_bytes":    len(payloadBytes),
	}), actorID).Scan(&jobID); err != nil {
		return domain.ContributionBundleResult{}, err
	}

	if _, err := tx.Exec(ctx, `
		UPDATE contributions SET status = 'bundled', source_id = $1
		WHERE id = ANY($2::uuid[])
	`, sourceID, ids); err != nil {
		return domain.ContributionBundleResult{}, err
	}

	sourceDetails, err := json.Marshal(map[string]any{
		"name": input.Name, "content_purpose": contentPurpose, "rights_status": "cleared",
	})
	if err != nil {
		return domain.ContributionBundleResult{}, err
	}
	bundleDetails, err := json.Marshal(map[string]any{
		"count": len(items), "task_type": input.TaskType, "job_id": jobID,
	})
	if err != nil {
		return domain.ContributionBundleResult{}, err
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES ($1, 'source.created', 'source', $2, $3::jsonb),
		       ($1, 'contributions.bundled', 'source', $2, $4::jsonb)
	`, actorID, sourceID, sourceDetails, bundleDetails); err != nil {
		return domain.ContributionBundleResult{}, err
	}

	if err := tx.Commit(ctx); err != nil {
		return domain.ContributionBundleResult{}, err
	}
	cleanupStaged = false
	return domain.ContributionBundleResult{
		SourceID: sourceID,
		JobID:    jobID,
		Count:    int64(len(items)),
	}, nil
}

// writeStagedContributionFile, demet dosyasını worker'ın staged-ingest
// kökünde oluşturur ve diske fsync eder (upload handler'ıyla aynı desen).
func writeStagedContributionFile(stagingRoot string, payload []byte) (string, error) {
	if err := os.MkdirAll(stagingRoot, 0o700); err != nil {
		return "", fmt.Errorf("create staging root: %w", err)
	}
	file, err := os.CreateTemp(stagingRoot, "contrib-*.jsonl")
	if err != nil {
		return "", fmt.Errorf("create staged contribution file: %w", err)
	}
	name := file.Name()
	if _, err := file.Write(payload); err != nil {
		file.Close()
		os.Remove(name)
		return "", fmt.Errorf("write staged contribution file: %w", err)
	}
	if err := file.Sync(); err != nil {
		file.Close()
		os.Remove(name)
		return "", fmt.Errorf("sync staged contribution file: %w", err)
	}
	if err := file.Close(); err != nil {
		os.Remove(name)
		return "", fmt.Errorf("close staged contribution file: %w", err)
	}
	absolute, err := filepath.Abs(name)
	if err != nil {
		os.Remove(name)
		return "", fmt.Errorf("resolve staged contribution file: %w", err)
	}
	return absolute, nil
}

func mustJSON(value map[string]any) []byte {
	payload, err := json.Marshal(value)
	if err != nil {
		panic(fmt.Sprintf("marshal static payload: %v", err))
	}
	return payload
}
