CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TABLE users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text NOT NULL,
    password_hash text NOT NULL,
    display_name text NOT NULL,
    status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT users_email_normalized CHECK (email = lower(btrim(email)))
);

CREATE UNIQUE INDEX users_email_unique_idx ON users (lower(email));

CREATE TRIGGER users_set_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE roles (
    name text PRIMARY KEY,
    description text NOT NULL
);

INSERT INTO roles(name, description) VALUES
    ('admin', 'System administration and release freeze'),
    ('data_manager', 'Source registration and dataset management'),
    ('editor', 'Content and metadata editing'),
    ('moderator', 'Approval and rejection decisions'),
    ('expert_reviewer', 'Sensitive domain review'),
    ('contributor', 'Data contribution'),
    ('consumer_team', 'Approved release access');

CREATE TABLE user_roles (
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_name text NOT NULL REFERENCES roles(name) ON DELETE RESTRICT,
    assigned_at timestamptz NOT NULL DEFAULT now(),
    assigned_by uuid REFERENCES users(id) ON DELETE SET NULL,
    PRIMARY KEY (user_id, role_name)
);

CREATE TABLE storage_objects (
    sha256 char(64) PRIMARY KEY,
    storage_key text NOT NULL UNIQUE,
    byte_size bigint NOT NULL CHECK (byte_size >= 0),
    media_type text,
    immutable boolean NOT NULL DEFAULT true CHECK (immutable),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT storage_objects_sha256_format CHECK (sha256 ~ '^[0-9a-f]{64}$')
);

CREATE TABLE sources (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 240),
    source_type text NOT NULL CHECK (length(btrim(source_type)) BETWEEN 1 AND 80),
    content_purpose text NOT NULL
        CHECK (content_purpose IN ('pretrain', 'instruction', 'preference', 'eval', 'holdout', 'post_training')),
    license text NOT NULL CHECK (length(btrim(license)) > 0),
    rights_status text NOT NULL DEFAULT 'unknown'
        CHECK (rights_status IN ('unknown', 'cleared', 'restricted', 'blocked')),
    language text NOT NULL CHECK (length(btrim(language)) BETWEEN 2 AND 64),
    domain text NOT NULL CHECK (length(btrim(domain)) BETWEEN 1 AND 120),
    source_url text,
    license_evidence_ref text,
    lineage_ref text NOT NULL CHECK (length(btrim(lineage_ref)) > 0),
    object_sha256 char(64) REFERENCES storage_objects(sha256) ON DELETE RESTRICT,
    byte_size bigint CHECK (byte_size >= 0),
    line_count bigint CHECK (line_count >= 0),
    document_count bigint CHECK (document_count >= 0),
    detected_encoding text,
    pii_status text NOT NULL DEFAULT 'not_scanned'
        CHECK (pii_status IN ('not_scanned', 'clear', 'flagged', 'quarantined')),
    risk_level text NOT NULL DEFAULT 'unknown'
        CHECK (risk_level IN ('unknown', 'low', 'medium', 'high', 'critical')),
    approval_status text NOT NULL DEFAULT 'source_registered'
        CHECK (approval_status IN (
            'source_registered', 'license_review', 'raw_ingested', 'normalized',
            'auto_checked', 'sampled_for_review', 'approved_source',
            'release_candidate', 'rejected', 'quarantined'
        )),
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
    created_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX sources_status_purpose_idx ON sources (approval_status, content_purpose, created_at DESC);
CREATE INDEX sources_object_sha256_idx ON sources (object_sha256) WHERE object_sha256 IS NOT NULL;
CREATE INDEX sources_created_by_idx ON sources (created_by, created_at DESC);

CREATE OR REPLACE FUNCTION protect_source_content_purpose()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.content_purpose IS DISTINCT FROM OLD.content_purpose THEN
        RAISE EXCEPTION 'content_purpose is immutable';
    END IF;
    NEW.version = OLD.version + 1;
    RETURN NEW;
END;
$$;

CREATE TRIGGER sources_protect_content_purpose
BEFORE UPDATE ON sources
FOR EACH ROW EXECUTE FUNCTION protect_source_content_purpose();

CREATE TRIGGER sources_set_updated_at
BEFORE UPDATE ON sources
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE background_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type text NOT NULL CHECK (length(btrim(job_type)) BETWEEN 1 AND 80),
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
    priority smallint NOT NULL DEFAULT 100 CHECK (priority BETWEEN 0 AND 1000),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    result jsonb,
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts integer NOT NULL DEFAULT 3 CHECK (max_attempts > 0),
    available_at timestamptz NOT NULL DEFAULT now(),
    locked_at timestamptz,
    locked_by text,
    last_error text,
    created_by uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE INDEX background_jobs_claim_idx
ON background_jobs (priority, available_at, created_at)
WHERE status = 'queued';

CREATE TRIGGER background_jobs_set_updated_at
BEFORE UPDATE ON background_jobs
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE reviews (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id uuid NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    reviewer_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    decision text NOT NULL CHECK (decision IN ('approved', 'rejected', 'sensitive_review')),
    reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT reviews_rejection_reason CHECK (decision <> 'rejected' OR length(btrim(reason)) > 0)
);

CREATE INDEX reviews_source_idx ON reviews (source_id, created_at DESC);
CREATE INDEX reviews_reviewer_idx ON reviews (reviewer_id, created_at DESC);

CREATE TABLE releases (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    version text NOT NULL,
    content_purpose text NOT NULL
        CHECK (content_purpose IN ('pretrain', 'instruction', 'preference', 'eval', 'holdout', 'post_training')),
    status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'frozen', 'superseded')),
    manifest_object_sha256 char(64) REFERENCES storage_objects(sha256) ON DELETE RESTRICT,
    manifest_sha256 char(64),
    gate_results jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    frozen_by uuid REFERENCES users(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    frozen_at timestamptz,
    UNIQUE (name, version),
    CONSTRAINT releases_freeze_fields CHECK (
        status <> 'frozen' OR
        (frozen_by IS NOT NULL AND frozen_at IS NOT NULL AND manifest_sha256 IS NOT NULL)
    )
);

CREATE TABLE release_sources (
    release_id uuid NOT NULL REFERENCES releases(id) ON DELETE RESTRICT,
    source_id uuid NOT NULL REFERENCES sources(id) ON DELETE RESTRICT,
    source_sha256 char(64) NOT NULL,
    added_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (release_id, source_id)
);

CREATE TABLE audit_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id uuid NOT NULL DEFAULT gen_random_uuid(),
    actor_id uuid REFERENCES users(id) ON DELETE SET NULL,
    actor_type text NOT NULL DEFAULT 'human' CHECK (actor_type IN ('human', 'agent', 'system')),
    action text NOT NULL CHECK (length(btrim(action)) > 0),
    entity_type text NOT NULL CHECK (length(btrim(entity_type)) > 0),
    entity_id uuid,
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX audit_events_entity_idx ON audit_events (entity_type, entity_id, created_at DESC);
CREATE INDEX audit_events_actor_idx ON audit_events (actor_id, created_at DESC);

CREATE OR REPLACE FUNCTION reject_audit_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'audit_events are append-only';
END;
$$;

CREATE TRIGGER audit_events_no_update
BEFORE UPDATE ON audit_events
FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation();

CREATE TRIGGER audit_events_no_delete
BEFORE DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation();
