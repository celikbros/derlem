-- Katkı kuyruğu (ofis ölçeği, 2026-07-16): katkıcılar uygulama içinden
-- soru-cevap çifti veya serbest metin gönderir; havuz admin/data_manager
-- tarafından tek bir kaynağa demetlenir ve normal kapılardan geçer.
-- Güven kademeleri / N-onay / altın görevler açık kayıt fazına aittir
-- (docs/katki_platformu_tasarimi.md).

CREATE TABLE contributions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contributor_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    task_type text NOT NULL CHECK (task_type IN ('qa_pair', 'free_text')),
    domain text NOT NULL DEFAULT '' CHECK (char_length(domain) <= 100),
    prompt text NOT NULL DEFAULT '' CHECK (char_length(prompt) <= 10000),
    body text NOT NULL CHECK (char_length(body) BETWEEN 1 AND 100000),
    -- Katkı gönderilirken onaylanan kullanım şartı sürümü; lineage'a işlenir.
    terms_ack_version text NOT NULL CHECK (terms_ack_version <> ''),
    status text NOT NULL DEFAULT 'submitted'
        CHECK (status IN ('submitted', 'withdrawn', 'bundled')),
    source_id uuid REFERENCES sources(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    -- Soru-cevap çiftinde soru boş olamaz.
    CHECK (task_type <> 'qa_pair' OR char_length(btrim(prompt)) > 0),
    -- Demetlenen katkı mutlaka bir kaynağa bağlıdır.
    CHECK (status <> 'bundled' OR source_id IS NOT NULL)
);

CREATE TRIGGER contributions_set_updated_at
BEFORE UPDATE ON contributions
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX contributions_contributor_idx
ON contributions (contributor_id, created_at DESC);

CREATE INDEX contributions_pending_idx
ON contributions (task_type, created_at) WHERE status = 'submitted';
