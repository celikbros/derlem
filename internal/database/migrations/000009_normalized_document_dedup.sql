ALTER TABLE sources
    ADD COLUMN normalized_dedup_status text NOT NULL DEFAULT 'not_checked'
        CHECK (normalized_dedup_status IN ('not_checked', 'unique', 'duplicates_found', 'failed')),
    ADD COLUMN normalized_duplicate_count bigint NOT NULL DEFAULT 0
        CHECK (normalized_duplicate_count >= 0),
    ADD COLUMN normalized_duplicate_source_count bigint NOT NULL DEFAULT 0
        CHECK (normalized_duplicate_source_count >= 0);

CREATE INDEX sources_normalized_dedup_status_idx
ON sources (normalized_dedup_status, created_at DESC);

CREATE TABLE document_fingerprints (
    source_id uuid NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    source_sha256 char(64) NOT NULL REFERENCES storage_objects(sha256) ON DELETE RESTRICT,
    source_ordinal bigint NOT NULL CHECK (source_ordinal > 0),
    normalized_sha256 char(64) NOT NULL,
    normalized_char_count bigint NOT NULL CHECK (normalized_char_count > 0),
    fingerprint_version text NOT NULL DEFAULT 'normalized-document-sha256-v1',
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_id, source_sha256, source_ordinal, fingerprint_version),
    CONSTRAINT document_fingerprints_sha256_format
        CHECK (normalized_sha256 ~ '^[0-9a-f]{64}$')
);

CREATE INDEX document_fingerprints_hash_idx
ON document_fingerprints (fingerprint_version, normalized_sha256, source_id);

CREATE INDEX document_fingerprints_source_idx
ON document_fingerprints (source_id, source_sha256);

CREATE UNIQUE INDEX background_jobs_active_normalized_dedup_idx
ON background_jobs (job_type, (payload->>'source_id'))
WHERE job_type = 'index_document_fingerprints'
  AND status IN ('queued', 'running');
