-- Phase-1 database audit safety net.
--
-- The ledger records structural change metadata and a table-specific safe
-- projection. It never stores complete rows or hashes complete rows: free-form
-- content, credentials, URLs, paths, review reasons, PII findings, previews and
-- arbitrary JSON are intentionally absent from both summaries and hashes.

CREATE TABLE row_change_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    transaction_id bigint NOT NULL DEFAULT txid_current(),
    database_role text NOT NULL DEFAULT session_user,
    table_schema text NOT NULL CHECK (length(btrim(table_schema)) > 0),
    table_name text NOT NULL CHECK (length(btrim(table_name)) > 0),
    operation text NOT NULL CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE')),
    row_key jsonb NOT NULL CHECK (jsonb_typeof(row_key) = 'object'),
    changed_columns text[] NOT NULL,
    before_summary jsonb CHECK (
        before_summary IS NULL OR jsonb_typeof(before_summary) = 'object'
    ),
    after_summary jsonb CHECK (
        after_summary IS NULL OR jsonb_typeof(after_summary) = 'object'
    ),
    before_hash char(64) CHECK (
        before_hash IS NULL OR before_hash ~ '^[0-9a-f]{64}$'
    ),
    after_hash char(64) CHECK (
        after_hash IS NULL OR after_hash ~ '^[0-9a-f]{64}$'
    ),
    CHECK (operation <> 'INSERT' OR before_summary IS NULL),
    CHECK (operation <> 'DELETE' OR after_summary IS NULL)
);

CREATE INDEX row_change_events_row_idx
ON row_change_events (
    table_schema, table_name, row_key, occurred_at DESC, id DESC
);

CREATE INDEX row_change_events_transaction_idx
ON row_change_events (transaction_id, occurred_at, id);

CREATE OR REPLACE FUNCTION reject_row_change_event_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'row_change_events are append-only';
END;
$$;

CREATE TRIGGER row_change_events_no_update
BEFORE UPDATE ON row_change_events
FOR EACH ROW EXECUTE FUNCTION reject_row_change_event_mutation();

CREATE TRIGGER row_change_events_no_delete
BEFORE DELETE ON row_change_events
FOR EACH ROW EXECUTE FUNCTION reject_row_change_event_mutation();

CREATE TRIGGER row_change_events_no_truncate
BEFORE TRUNCATE ON row_change_events
FOR EACH STATEMENT EXECUTE FUNCTION reject_row_change_event_mutation();

-- Positive allowlists are used rather than subtracting known-sensitive fields.
-- A column added by a future migration therefore remains absent until a later
-- reviewed migration explicitly opts it into this projection.
CREATE OR REPLACE FUNCTION row_change_safe_summary(
    target_table text,
    row_data jsonb
)
RETURNS jsonb
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    IF row_data IS NULL THEN
        RETURN NULL;
    END IF;

    RETURN CASE target_table
        WHEN 'users' THEN jsonb_build_object(
            'id', row_data->'id',
            'status', row_data->'status',
            'auth_version', row_data->'auth_version'
        )
        WHEN 'roles' THEN jsonb_build_object(
            'name', row_data->'name'
        )
        WHEN 'user_roles' THEN jsonb_build_object(
            'user_id', row_data->'user_id',
            'role_name', row_data->'role_name',
            'assigned_by', row_data->'assigned_by'
        )
        WHEN 'storage_objects' THEN jsonb_build_object(
            'sha256', row_data->'sha256',
            'byte_size', row_data->'byte_size',
            'immutable', row_data->'immutable'
        )
        WHEN 'sources' THEN jsonb_build_object(
            'id', row_data->'id',
            'content_purpose', row_data->'content_purpose',
            'rights_status', row_data->'rights_status',
            'object_sha256', row_data->'object_sha256',
            'pii_status', row_data->'pii_status',
            'risk_level', row_data->'risk_level',
            'approval_status', row_data->'approval_status',
            'version', row_data->'version',
            'duplicate_status', row_data->'duplicate_status',
            'duplicate_of_source_id', row_data->'duplicate_of_source_id',
            'document_sampling_status', row_data->'document_sampling_status',
            'sampled_document_count', row_data->'sampled_document_count',
            'reviewed_document_count', row_data->'reviewed_document_count',
            'approved_document_count', row_data->'approved_document_count',
            'flagged_document_count', row_data->'flagged_document_count',
            'normalized_dedup_status', row_data->'normalized_dedup_status',
            'normalized_duplicate_count', row_data->'normalized_duplicate_count',
            'normalized_duplicate_source_count', row_data->'normalized_duplicate_source_count',
            'document_sample_generation', row_data->'document_sample_generation',
            'derived_from_source_id', row_data->'derived_from_source_id'
        )
        WHEN 'reviews' THEN jsonb_build_object(
            'id', row_data->'id',
            'source_id', row_data->'source_id',
            'reviewer_id', row_data->'reviewer_id',
            'decision', row_data->'decision',
            'source_version', row_data->'source_version'
        )
        WHEN 'pii_scans' THEN jsonb_build_object(
            'id', row_data->'id',
            'source_id', row_data->'source_id',
            'job_id', row_data->'job_id',
            'object_sha256', row_data->'object_sha256',
            'status', row_data->'status'
        )
        WHEN 'documents' THEN jsonb_build_object(
            'id', row_data->'id',
            'source_id', row_data->'source_id',
            'source_ordinal', row_data->'source_ordinal',
            'current_object_sha256', row_data->'current_object_sha256',
            'byte_size', row_data->'byte_size',
            'char_count', row_data->'char_count',
            'status', row_data->'status',
            'current_version', row_data->'current_version',
            'risk_score', row_data->'risk_score',
            'is_active', row_data->'is_active',
            'sample_generation', row_data->'sample_generation'
        )
        WHEN 'document_versions' THEN jsonb_build_object(
            'id', row_data->'id',
            'document_id', row_data->'document_id',
            'version', row_data->'version',
            'object_sha256', row_data->'object_sha256',
            'byte_size', row_data->'byte_size',
            'char_count', row_data->'char_count',
            'actor_type', row_data->'actor_type',
            'created_by', row_data->'created_by'
        )
        WHEN 'document_sample_generations' THEN jsonb_build_object(
            'source_id', row_data->'source_id',
            'generation', row_data->'generation',
            'source_sha256', row_data->'source_sha256',
            'status', row_data->'status',
            'sample_count', row_data->'sample_count',
            'job_id', row_data->'job_id'
        )
        WHEN 'document_sample_memberships' THEN jsonb_build_object(
            'source_id', row_data->'source_id',
            'generation', row_data->'generation',
            'document_id', row_data->'document_id',
            'source_ordinal', row_data->'source_ordinal',
            'object_sha256', row_data->'object_sha256',
            'risk_score', row_data->'risk_score'
        )
        WHEN 'document_reviews' THEN jsonb_build_object(
            'id', row_data->'id',
            'document_id', row_data->'document_id',
            'reviewer_id', row_data->'reviewer_id',
            'decision', row_data->'decision',
            'quality_score', row_data->'quality_score',
            'document_version', row_data->'document_version',
            'object_sha256', row_data->'object_sha256',
            'rubric_version', row_data->'rubric_version',
            'language_quality_score', row_data->'language_quality_score',
            'coherence_score', row_data->'coherence_score',
            'information_density_score', row_data->'information_density_score',
            'cleanliness_score', row_data->'cleanliness_score'
        )
        WHEN 'document_review_reversals' THEN jsonb_build_object(
            'id', row_data->'id',
            'review_id', row_data->'review_id',
            'reversed_by', row_data->'reversed_by',
            'restored_document_status', row_data->'restored_document_status'
        )
        WHEN 'similarity_calibration_runs' THEN jsonb_build_object(
            'id', row_data->'id',
            'report_object_sha256', row_data->'report_object_sha256',
            'content_purpose', row_data->'content_purpose',
            'sampled_document_count', row_data->'sampled_document_count',
            'eligible_document_count', row_data->'eligible_document_count',
            'threshold_max', row_data->'threshold_max',
            'pair_count', row_data->'pair_count'
        )
        WHEN 'similarity_review_pairs' THEN jsonb_build_object(
            'id', row_data->'id',
            'run_id', row_data->'run_id',
            'pair_rank', row_data->'pair_rank',
            'hamming_distance', row_data->'hamming_distance',
            'left_source_id', row_data->'left_source_id',
            'left_source_sha256', row_data->'left_source_sha256',
            'left_source_ordinal', row_data->'left_source_ordinal',
            'left_object_sha256', row_data->'left_object_sha256',
            'left_token_count', row_data->'left_token_count',
            'right_source_id', row_data->'right_source_id',
            'right_source_sha256', row_data->'right_source_sha256',
            'right_source_ordinal', row_data->'right_source_ordinal',
            'right_object_sha256', row_data->'right_object_sha256',
            'right_token_count', row_data->'right_token_count'
        )
        WHEN 'similarity_pair_reviews' THEN jsonb_build_object(
            'id', row_data->'id',
            'pair_id', row_data->'pair_id',
            'reviewer_id', row_data->'reviewer_id',
            'label', row_data->'label'
        )
        WHEN 'releases' THEN jsonb_build_object(
            'id', row_data->'id',
            'content_purpose', row_data->'content_purpose',
            'status', row_data->'status',
            'manifest_object_sha256', row_data->'manifest_object_sha256',
            'manifest_sha256', row_data->'manifest_sha256',
            'created_by', row_data->'created_by',
            'frozen_by', row_data->'frozen_by'
        )
        WHEN 'release_sources' THEN jsonb_build_object(
            'release_id', row_data->'release_id',
            'source_id', row_data->'source_id',
            'source_sha256', row_data->'source_sha256',
            'source_version', row_data->'source_version',
            'rights_status', row_data->'rights_status',
            'byte_size', row_data->'byte_size',
            'line_count', row_data->'line_count'
        )
        WHEN 'release_exports' THEN jsonb_build_object(
            'id', row_data->'id',
            'release_id', row_data->'release_id',
            'format', row_data->'format',
            'status', row_data->'status',
            'object_sha256', row_data->'object_sha256',
            'manifest_object_sha256', row_data->'manifest_object_sha256',
            'record_count', row_data->'record_count',
            'byte_size', row_data->'byte_size',
            'estimated_token_count', row_data->'estimated_token_count',
            'token_estimate_lower_bound', row_data->'token_estimate_lower_bound',
            'token_estimate_upper_bound', row_data->'token_estimate_upper_bound'
        )
        ELSE NULL
    END;
END;
$$;

CREATE OR REPLACE FUNCTION capture_row_change_event()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    old_data jsonb;
    new_data jsonb;
    source_data jsonb;
    key_data jsonb := '{}'::jsonb;
    before_data jsonb;
    after_data jsonb;
    changed text[];
    key_column text;
    before_digest text;
    after_digest text;
    digest_schema text;
    audit_schema text;
BEGIN
    SELECT namespace.nspname
    INTO audit_schema
    FROM pg_catalog.pg_trigger AS trigger_def
    JOIN pg_catalog.pg_proc AS function_def
      ON function_def.oid = trigger_def.tgfoid
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.oid = function_def.pronamespace
    WHERE trigger_def.tgrelid = TG_RELID
      AND trigger_def.tgname = TG_NAME
      AND NOT trigger_def.tgisinternal;

    IF audit_schema IS NULL
       OR audit_schema IS DISTINCT FROM TG_TABLE_SCHEMA THEN
        RAISE EXCEPTION 'row-change audit schema mismatch for %.%',
            TG_TABLE_SCHEMA, TG_TABLE_NAME;
    END IF;

    IF TG_OP = 'INSERT' THEN
        new_data := to_jsonb(NEW);
        source_data := new_data;
    ELSIF TG_OP = 'UPDATE' THEN
        old_data := to_jsonb(OLD);
        new_data := to_jsonb(NEW);
        source_data := new_data;
    ELSIF TG_OP = 'DELETE' THEN
        old_data := to_jsonb(OLD);
        source_data := old_data;
    ELSE
        RAISE EXCEPTION 'unsupported row change operation: %', TG_OP;
    END IF;

    FOREACH key_column IN ARRAY TG_ARGV LOOP
        IF NOT source_data ? key_column THEN
            RAISE EXCEPTION 'audit key column % is absent on %.%',
                key_column, TG_TABLE_SCHEMA, TG_TABLE_NAME;
        END IF;
        key_data := key_data || jsonb_build_object(
            key_column, source_data->key_column
        );
    END LOOP;

    IF key_data = '{}'::jsonb THEN
        RAISE EXCEPTION 'row change trigger on %.% requires a safe row key',
            TG_TABLE_SCHEMA, TG_TABLE_NAME;
    END IF;

    SELECT COALESCE(array_agg(column_name ORDER BY column_name), '{}'::text[])
    INTO changed
    FROM (
        SELECT column_name
        FROM jsonb_object_keys(
            COALESCE(old_data, '{}'::jsonb) || COALESCE(new_data, '{}'::jsonb)
        ) AS columns(column_name)
        WHERE old_data->column_name IS DISTINCT FROM new_data->column_name
    ) AS differences;

    -- Dynamic schema qualification keeps the migration compatible with the
    -- isolated search_path schemas used by database integration tests.
    EXECUTE format('SELECT %I.row_change_safe_summary($1, $2)', audit_schema)
    INTO before_data
    USING TG_TABLE_NAME, old_data;
    EXECUTE format('SELECT %I.row_change_safe_summary($1, $2)', audit_schema)
    INTO after_data
    USING TG_TABLE_NAME, new_data;

    IF (old_data IS NOT NULL AND before_data IS NULL)
       OR (new_data IS NOT NULL AND after_data IS NULL) THEN
        RAISE EXCEPTION 'safe row-change summary is not configured for %.%',
            TG_TABLE_SCHEMA, TG_TABLE_NAME;
    END IF;

    SELECT namespace.nspname
    INTO digest_schema
    FROM pg_catalog.pg_extension AS extension
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.oid = extension.extnamespace
    WHERE extension.extname = 'pgcrypto';
    IF digest_schema IS NULL THEN
        RAISE EXCEPTION 'pgcrypto extension is required for row-change auditing';
    END IF;

    IF before_data IS NOT NULL THEN
        EXECUTE format(
            'SELECT pg_catalog.encode(%I.digest('
            'pg_catalog.convert_to($1::text, ''UTF8''), ''sha256'''
            '), ''hex'')',
            digest_schema
        )
        INTO before_digest
        USING before_data;
    END IF;
    IF after_data IS NOT NULL THEN
        EXECUTE format(
            'SELECT pg_catalog.encode(%I.digest('
            'pg_catalog.convert_to($1::text, ''UTF8''), ''sha256'''
            '), ''hex'')',
            digest_schema
        )
        INTO after_digest
        USING after_data;
    END IF;

    EXECUTE format(
        'INSERT INTO %I.row_change_events('
        'table_schema, table_name, operation, row_key, changed_columns, '
        'before_summary, after_summary, before_hash, after_hash'
        ') VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)',
        audit_schema
    )
    USING TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP, key_data, changed,
        before_data, after_data, before_digest, after_digest;

    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

-- Critical durable business state. Trigger arguments are safe, non-PII keys.
CREATE TRIGGER roles_capture_row_change
AFTER INSERT OR UPDATE OR DELETE ON roles
FOR EACH ROW EXECUTE FUNCTION capture_row_change_event('name');

CREATE TRIGGER users_capture_row_change
AFTER INSERT OR UPDATE OR DELETE ON users
FOR EACH ROW EXECUTE FUNCTION capture_row_change_event('id');

CREATE TRIGGER user_roles_capture_row_change
AFTER INSERT OR UPDATE OR DELETE ON user_roles
FOR EACH ROW EXECUTE FUNCTION capture_row_change_event('user_id', 'role_name');

CREATE TRIGGER storage_objects_capture_row_change
AFTER INSERT OR UPDATE OR DELETE ON storage_objects
FOR EACH ROW EXECUTE FUNCTION capture_row_change_event('sha256');

CREATE TRIGGER sources_capture_row_change
AFTER INSERT OR UPDATE OR DELETE ON sources
FOR EACH ROW EXECUTE FUNCTION capture_row_change_event('id');

CREATE TRIGGER reviews_capture_row_change
AFTER INSERT OR UPDATE OR DELETE ON reviews
FOR EACH ROW EXECUTE FUNCTION capture_row_change_event('id');

CREATE TRIGGER pii_scans_capture_row_change
AFTER INSERT OR UPDATE OR DELETE ON pii_scans
FOR EACH ROW EXECUTE FUNCTION capture_row_change_event('id');

CREATE TRIGGER documents_capture_row_change
AFTER INSERT OR UPDATE OR DELETE ON documents
FOR EACH ROW EXECUTE FUNCTION capture_row_change_event('id');

CREATE TRIGGER document_versions_capture_row_change
AFTER INSERT OR UPDATE OR DELETE ON document_versions
FOR EACH ROW EXECUTE FUNCTION capture_row_change_event('id');

CREATE TRIGGER document_sample_generations_capture_row_change
AFTER INSERT OR UPDATE OR DELETE ON document_sample_generations
FOR EACH ROW EXECUTE FUNCTION capture_row_change_event('source_id', 'generation');

CREATE TRIGGER document_sample_memberships_capture_row_change
AFTER INSERT OR UPDATE OR DELETE ON document_sample_memberships
FOR EACH ROW EXECUTE FUNCTION capture_row_change_event(
    'source_id', 'generation', 'document_id'
);

CREATE TRIGGER document_reviews_capture_row_change
AFTER INSERT OR UPDATE OR DELETE ON document_reviews
FOR EACH ROW EXECUTE FUNCTION capture_row_change_event('id');

CREATE TRIGGER document_review_reversals_capture_row_change
AFTER INSERT OR UPDATE OR DELETE ON document_review_reversals
FOR EACH ROW EXECUTE FUNCTION capture_row_change_event('id');

CREATE TRIGGER similarity_calibration_runs_capture_row_change
AFTER INSERT OR UPDATE OR DELETE ON similarity_calibration_runs
FOR EACH ROW EXECUTE FUNCTION capture_row_change_event('id');

CREATE TRIGGER similarity_review_pairs_capture_row_change
AFTER INSERT OR UPDATE OR DELETE ON similarity_review_pairs
FOR EACH ROW EXECUTE FUNCTION capture_row_change_event('id');

CREATE TRIGGER similarity_pair_reviews_capture_row_change
AFTER INSERT OR UPDATE OR DELETE ON similarity_pair_reviews
FOR EACH ROW EXECUTE FUNCTION capture_row_change_event('id');

CREATE TRIGGER releases_capture_row_change
AFTER INSERT OR UPDATE OR DELETE ON releases
FOR EACH ROW EXECUTE FUNCTION capture_row_change_event('id');

CREATE TRIGGER release_sources_capture_row_change
AFTER INSERT OR UPDATE OR DELETE ON release_sources
FOR EACH ROW EXECUTE FUNCTION capture_row_change_event('release_id', 'source_id');

CREATE TRIGGER release_exports_capture_row_change
AFTER INSERT OR UPDATE OR DELETE ON release_exports
FOR EACH ROW EXECUTE FUNCTION capture_row_change_event('id');

REVOKE ALL ON FUNCTION capture_row_change_event() FROM PUBLIC;
REVOKE ALL ON FUNCTION row_change_safe_summary(text, jsonb) FROM PUBLIC;

-- Intentionally excluded from this generic row trigger:
--   audit_events, row_change_events
--     Audit ledgers; triggering them would recurse or double-log.
--   schema_migrations
--     Migration bookkeeping, not durable business state.
--   background_jobs
--     Payload/result/error may contain secrets or paths, while lock and
--     heartbeat updates are high-churn. Semantic job events remain explicit.
--   auth_sessions, login_rate_limits
--     Session/token-derived and rate-limit state is sensitive and high-churn.
--   document_review_claims
--     Lease acquisition and renewal is ephemeral coordination state.
--   document_fingerprints
--     Bulk, reproducible derived fingerprints are extremely high-volume.
--   contributions
--     Prompt/body is raw user content. Its lifecycle requires explicit,
--     redacted semantic audit events rather than a generic row copier.
--   active_document_reviews
--     Mutable projection derived from append-only reviews and reversals.
