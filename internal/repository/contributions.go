package repository

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"

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
	terms_ack_version, status, source_id::text, created_at, updated_at
`

func scanContribution(row pgx.Row) (domain.Contribution, error) {
	var contribution domain.Contribution
	err := row.Scan(
		&contribution.ID, &contribution.ContributorID, &contribution.TaskType,
		&contribution.Domain, &contribution.Prompt, &contribution.Body,
		&contribution.TermsVersion, &contribution.Status, &contribution.SourceID,
		&contribution.CreatedAt, &contribution.UpdatedAt,
	)
	return contribution, err
}

// Submit yeni bir katkı kaydeder ve audit olayını aynı transaction'da yazar.
func (r *Contributions) Submit(ctx context.Context, contributorID string, input domain.SubmitContributionInput) (domain.Contribution, error) {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return domain.Contribution{}, err
	}
	defer tx.Rollback(ctx)

	contribution, err := scanContribution(tx.QueryRow(ctx, `
		INSERT INTO contributions(contributor_id, task_type, domain, prompt, body, terms_ack_version)
		VALUES ($1, $2, $3, $4, $5, $6)
		RETURNING `+contributionColumns,
		contributorID, input.TaskType, input.Domain, input.Prompt, input.Body,
		domain.ContributionTermsVersion,
	))
	if err != nil {
		return domain.Contribution{}, err
	}

	details, err := json.Marshal(map[string]any{
		"task_type": contribution.TaskType,
		"domain":    contribution.Domain,
		"terms_ack": contribution.TermsVersion,
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
	ID     string
	Prompt string
	Body   string
}

// buildContributionJSONL, demet dosyasının satırlarını üretir. Sampler her
// satırda "text" alanını belge metni, "id" alanını external id olarak okur;
// katkıcı kimliği dosyaya asla yazılmaz (kimlik-içerik ayrımı).
func buildContributionJSONL(taskType string, items []bundleItem) ([]byte, error) {
	var buffer bytes.Buffer
	encoder := json.NewEncoder(&buffer)
	encoder.SetEscapeHTML(false)
	for _, item := range items {
		text := item.Body
		if taskType == "qa_pair" {
			// Şablonsuz, insan-okur düz metin: canonical conversation
			// kaydına terfi, pipeline conversation'ı uçtan uca
			// işlediğinde yapılacak (katkı_platformu_tasarimi.md).
			text = "Soru: " + item.Prompt + "\n\nCevap: " + item.Body
		}
		if err := encoder.Encode(map[string]string{"id": item.ID, "text": text}); err != nil {
			return nil, err
		}
	}
	return buffer.Bytes(), nil
}

func contentPurposeForTaskType(taskType string) string {
	if taskType == "qa_pair" {
		return "instruction"
	}
	return "pretrain"
}

// Bundle, bekleyen havuzu tek transaction içinde kaynağa demetler: katkılar
// FOR UPDATE ile kilitlenir, JSONL staging'e yazılır, kaynak + ingest job'u
// + audit olayları eklenir ve katkılar kaynağa bağlanır. Dosya yazımı
// transaction dışı tek yan etkidir; commit başarısız olursa dosya silinir.
func (r *Contributions) Bundle(ctx context.Context, input domain.BundleContributionsInput, stagingRoot, actorID string) (domain.ContributionBundleResult, error) {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return domain.ContributionBundleResult{}, err
	}
	defer tx.Rollback(ctx)

	rows, err := tx.Query(ctx, `
		SELECT id::text, prompt, body FROM contributions
		WHERE status = 'submitted' AND task_type = $1
		ORDER BY created_at
		FOR UPDATE
	`, input.TaskType)
	if err != nil {
		return domain.ContributionBundleResult{}, err
	}
	items := make([]bundleItem, 0)
	ids := make([]string, 0)
	for rows.Next() {
		var item bundleItem
		if err := rows.Scan(&item.ID, &item.Prompt, &item.Body); err != nil {
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
			"Bu görev tipinde bekleyen katkı yok.",
		}}
	}

	payloadBytes, err := buildContributionJSONL(input.TaskType, items)
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
	`, input.Name, contentPurposeForTaskType(input.TaskType), input.Language,
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
		"name": input.Name, "content_purpose": contentPurposeForTaskType(input.TaskType), "rights_status": "cleared",
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
