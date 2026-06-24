ALTER TABLE sources
    ADD COLUMN document_sampling_status text NOT NULL DEFAULT 'not_sampled'
        CHECK (document_sampling_status IN ('not_sampled', 'sampled', 'failed')),
    ADD COLUMN sampled_document_count bigint NOT NULL DEFAULT 0
        CHECK (sampled_document_count >= 0);

CREATE TABLE documents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id uuid NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    source_ordinal bigint NOT NULL CHECK (source_ordinal > 0),
    external_id text,
    current_object_sha256 char(64) NOT NULL REFERENCES storage_objects(sha256) ON DELETE RESTRICT,
    text_preview text NOT NULL CHECK (length(text_preview) <= 500),
    byte_size bigint NOT NULL CHECK (byte_size >= 0),
    char_count bigint NOT NULL CHECK (char_count >= 0),
    status text NOT NULL DEFAULT 'sampled'
        CHECK (status IN ('sampled', 'edited', 'approved', 'rejected', 'sensitive_review')),
    current_version bigint NOT NULL DEFAULT 1 CHECK (current_version > 0),
    sampling_method text NOT NULL DEFAULT 'reservoir-sha256-v1',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_id, source_ordinal)
);

CREATE INDEX documents_source_idx
ON documents (source_id, source_ordinal);

CREATE INDEX documents_status_idx
ON documents (status, updated_at DESC);

CREATE TABLE document_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE RESTRICT,
    version bigint NOT NULL CHECK (version > 0),
    object_sha256 char(64) NOT NULL REFERENCES storage_objects(sha256) ON DELETE RESTRICT,
    byte_size bigint NOT NULL CHECK (byte_size >= 0),
    char_count bigint NOT NULL CHECK (char_count >= 0),
    actor_type text NOT NULL CHECK (actor_type IN ('human', 'agent', 'system')),
    created_by uuid REFERENCES users(id) ON DELETE SET NULL,
    reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, version)
);

CREATE INDEX document_versions_document_idx
ON document_versions (document_id, version DESC);

CREATE TRIGGER documents_set_updated_at
BEFORE UPDATE ON documents
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
