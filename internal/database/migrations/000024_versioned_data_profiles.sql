-- Versioned data-profile control-plane foundation.
--
-- This migration deliberately does not add translation/reasoning payload
-- projections, normalized review scores or multi-reviewer aggregation. It does
-- add immutable profile identities plus fail-closed campaign and release pins
-- used by the same-rollout runtime.
--
-- contract_spec_artifacts stores only small, reviewed, non-secret control-plane
-- specifications. Raw corpus text, prompts, credentials and runtime config
-- bodies do not belong here. The bytes are retained so a SHA256 is recoverable
-- evidence rather than an opaque label. canonicalization_key names the exact
-- serializer contract; no JSON Canonicalization Scheme claim is implied.

CREATE OR REPLACE FUNCTION contract_spec_artifact_sha256(input_bytes bytea)
RETURNS char(64)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    digest_schema text;
    result char(64);
BEGIN
    SELECT namespace.nspname
    INTO digest_schema
    FROM pg_catalog.pg_extension AS extension
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.oid = extension.extnamespace
    WHERE extension.extname = 'pgcrypto';

    IF digest_schema IS NULL THEN
        RAISE EXCEPTION 'pgcrypto extension is required for contract artifacts';
    END IF;

    EXECUTE format(
        'SELECT pg_catalog.encode(%I.digest($1, ''sha256''), ''hex'')',
        digest_schema
    )
    INTO result
    USING input_bytes;
    RETURN result;
END;
$$;

CREATE TABLE contract_spec_artifacts (
    sha256 char(64) PRIMARY KEY,
    artifact_kind text NOT NULL CHECK (artifact_kind IN (
        'payload_schema', 'profile_config_schema', 'profile_config',
        'field_extraction', 'review_rubric', 'review_protocol',
        'pii_policy', 'dedup_policy', 'leakage_policy',
        'export_contract', 'contract_bundle'
    )),
    canonicalization_key text NOT NULL
        CHECK (length(btrim(canonicalization_key)) BETWEEN 1 AND 120),
    media_type text NOT NULL
        CHECK (length(btrim(media_type)) BETWEEN 1 AND 120),
    canonical_bytes bytea NOT NULL,
    byte_size bigint NOT NULL CHECK (byte_size BETWEEN 1 AND 1048576),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT contract_spec_artifacts_sha256_format
        CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT contract_spec_artifacts_byte_size
        CHECK (byte_size = octet_length(canonical_bytes)),
    UNIQUE (artifact_kind, sha256)
);

COMMENT ON TABLE contract_spec_artifacts IS
    'Immutable, content-addressed, <=1MiB non-secret control-plane specs; never raw corpus content or runtime secrets.';
COMMENT ON COLUMN contract_spec_artifacts.canonicalization_key IS
    'Exact serializer/byte contract identifier; not implicitly JCS.';

CREATE OR REPLACE FUNCTION verify_contract_spec_artifact()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    artifact_schema text;
    computed_sha256 char(64);
BEGIN
    SELECT namespace.nspname
    INTO artifact_schema
    FROM pg_catalog.pg_trigger AS trigger_def
    JOIN pg_catalog.pg_proc AS function_def
      ON function_def.oid = trigger_def.tgfoid
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.oid = function_def.pronamespace
    WHERE trigger_def.tgrelid = TG_RELID
      AND trigger_def.tgname = TG_NAME
      AND NOT trigger_def.tgisinternal;

    IF artifact_schema IS NULL
       OR artifact_schema IS DISTINCT FROM TG_TABLE_SCHEMA THEN
        RAISE EXCEPTION 'contract artifact schema mismatch for %.%',
            TG_TABLE_SCHEMA, TG_TABLE_NAME;
    END IF;

    EXECUTE format(
        'SELECT %I.contract_spec_artifact_sha256($1)', artifact_schema
    )
    INTO computed_sha256
    USING NEW.canonical_bytes;

    IF NEW.sha256 IS DISTINCT FROM computed_sha256 THEN
        RAISE EXCEPTION 'contract artifact sha256 does not match canonical bytes';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER contract_spec_artifacts_verify
BEFORE INSERT ON contract_spec_artifacts
FOR EACH ROW EXECUTE FUNCTION verify_contract_spec_artifact();

CREATE OR REPLACE FUNCTION reject_versioned_contract_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
END;
$$;

CREATE TRIGGER contract_spec_artifacts_no_update
BEFORE UPDATE ON contract_spec_artifacts
FOR EACH ROW EXECUTE FUNCTION reject_versioned_contract_mutation();
CREATE TRIGGER contract_spec_artifacts_no_delete
BEFORE DELETE ON contract_spec_artifacts
FOR EACH ROW EXECUTE FUNCTION reject_versioned_contract_mutation();
CREATE TRIGGER contract_spec_artifacts_no_truncate
BEFORE TRUNCATE ON contract_spec_artifacts
FOR EACH STATEMENT EXECUTE FUNCTION reject_versioned_contract_mutation();

CREATE TABLE review_rubric_versions (
    rubric_key text NOT NULL CHECK (length(btrim(rubric_key)) BETWEEN 1 AND 120),
    rubric_version text NOT NULL CHECK (length(btrim(rubric_version)) BETWEEN 1 AND 80),
    spec_artifact_kind text NOT NULL DEFAULT 'review_rubric'
        CHECK (spec_artifact_kind = 'review_rubric'),
    spec_sha256 char(64) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (rubric_key, rubric_version),
    FOREIGN KEY (spec_artifact_kind, spec_sha256)
        REFERENCES contract_spec_artifacts(artifact_kind, sha256) ON DELETE RESTRICT,
    UNIQUE (rubric_key, rubric_version, spec_sha256)
);

CREATE TABLE review_protocol_versions (
    protocol_key text NOT NULL CHECK (length(btrim(protocol_key)) BETWEEN 1 AND 120),
    protocol_version text NOT NULL CHECK (length(btrim(protocol_version)) BETWEEN 1 AND 80),
    spec_artifact_kind text NOT NULL DEFAULT 'review_protocol'
        CHECK (spec_artifact_kind = 'review_protocol'),
    spec_sha256 char(64) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (protocol_key, protocol_version),
    FOREIGN KEY (spec_artifact_kind, spec_sha256)
        REFERENCES contract_spec_artifacts(artifact_kind, sha256) ON DELETE RESTRICT,
    UNIQUE (protocol_key, protocol_version, spec_sha256)
);

CREATE TABLE data_policy_versions (
    policy_kind text NOT NULL CHECK (policy_kind IN ('pii', 'dedup', 'leakage')),
    policy_key text NOT NULL CHECK (length(btrim(policy_key)) BETWEEN 1 AND 120),
    policy_version text NOT NULL CHECK (length(btrim(policy_version)) BETWEEN 1 AND 80),
    spec_artifact_kind text NOT NULL CHECK (
        (policy_kind = 'pii' AND spec_artifact_kind = 'pii_policy') OR
        (policy_kind = 'dedup' AND spec_artifact_kind = 'dedup_policy') OR
        (policy_kind = 'leakage' AND spec_artifact_kind = 'leakage_policy')
    ),
    spec_sha256 char(64) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (policy_kind, policy_key, policy_version),
    FOREIGN KEY (spec_artifact_kind, spec_sha256)
        REFERENCES contract_spec_artifacts(artifact_kind, sha256) ON DELETE RESTRICT,
    UNIQUE (policy_kind, policy_key, policy_version, spec_sha256)
);

CREATE TABLE export_contract_versions (
    export_contract_key text NOT NULL
        CHECK (length(btrim(export_contract_key)) BETWEEN 1 AND 120),
    export_contract_version text NOT NULL
        CHECK (length(btrim(export_contract_version)) BETWEEN 1 AND 80),
    spec_artifact_kind text NOT NULL DEFAULT 'export_contract'
        CHECK (spec_artifact_kind = 'export_contract'),
    spec_sha256 char(64) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (export_contract_key, export_contract_version),
    FOREIGN KEY (spec_artifact_kind, spec_sha256)
        REFERENCES contract_spec_artifacts(artifact_kind, sha256) ON DELETE RESTRICT,
    UNIQUE (export_contract_key, export_contract_version, spec_sha256)
);

CREATE TABLE data_profile_versions (
    data_profile_key text NOT NULL
        CHECK (length(btrim(data_profile_key)) BETWEEN 1 AND 120),
    data_profile_version text NOT NULL
        CHECK (length(btrim(data_profile_version)) BETWEEN 1 AND 80),
    payload_kind text NOT NULL CHECK (length(btrim(payload_kind)) BETWEEN 1 AND 120),
    payload_schema_artifact_kind text NOT NULL DEFAULT 'payload_schema'
        CHECK (payload_schema_artifact_kind = 'payload_schema'),
    payload_schema_sha256 char(64) NOT NULL,
    profile_config_schema_artifact_kind text NOT NULL DEFAULT 'profile_config_schema'
        CHECK (profile_config_schema_artifact_kind = 'profile_config_schema'),
    profile_config_schema_sha256 char(64) NOT NULL,
    field_extraction_artifact_kind text NOT NULL DEFAULT 'field_extraction'
        CHECK (field_extraction_artifact_kind = 'field_extraction'),
    field_extraction_sha256 char(64) NOT NULL,
    rubric_key text NOT NULL,
    rubric_version text NOT NULL,
    export_contract_key text NOT NULL,
    export_contract_version text NOT NULL,
    implementation_key text NOT NULL
        CHECK (length(btrim(implementation_key)) BETWEEN 1 AND 160),
    implementation_digest char(64) NOT NULL
        CHECK (implementation_digest ~ '^[0-9a-f]{64}$'),
    is_terminal_legacy boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (data_profile_key, data_profile_version),
    FOREIGN KEY (payload_schema_artifact_kind, payload_schema_sha256)
        REFERENCES contract_spec_artifacts(artifact_kind, sha256) ON DELETE RESTRICT,
    FOREIGN KEY (
        profile_config_schema_artifact_kind, profile_config_schema_sha256
    ) REFERENCES contract_spec_artifacts(artifact_kind, sha256) ON DELETE RESTRICT,
    FOREIGN KEY (field_extraction_artifact_kind, field_extraction_sha256)
        REFERENCES contract_spec_artifacts(artifact_kind, sha256) ON DELETE RESTRICT,
    FOREIGN KEY (rubric_key, rubric_version)
        REFERENCES review_rubric_versions(rubric_key, rubric_version) ON DELETE RESTRICT,
    FOREIGN KEY (export_contract_key, export_contract_version)
        REFERENCES export_contract_versions(
            export_contract_key, export_contract_version
        ) ON DELETE RESTRICT,
    UNIQUE (data_profile_key, data_profile_version, rubric_key, rubric_version)
);

CREATE TABLE data_profile_purposes (
    data_profile_key text NOT NULL,
    data_profile_version text NOT NULL,
    content_purpose text NOT NULL CHECK (content_purpose IN (
        'pretrain', 'instruction', 'preference', 'eval', 'holdout',
        'post_training'
    )),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (data_profile_key, data_profile_version, content_purpose),
    FOREIGN KEY (data_profile_key, data_profile_version)
        REFERENCES data_profile_versions(data_profile_key, data_profile_version)
        ON DELETE RESTRICT
);

CREATE TABLE profile_purpose_contract_versions (
    data_profile_key text NOT NULL,
    data_profile_version text NOT NULL,
    content_purpose text NOT NULL,
    purpose_contract_version text NOT NULL
        CHECK (length(btrim(purpose_contract_version)) BETWEEN 1 AND 80),
    protocol_key text NOT NULL,
    protocol_version text NOT NULL,
    pii_policy_kind text NOT NULL DEFAULT 'pii' CHECK (pii_policy_kind = 'pii'),
    pii_policy_key text NOT NULL,
    pii_policy_version text NOT NULL,
    dedup_policy_kind text NOT NULL DEFAULT 'dedup'
        CHECK (dedup_policy_kind = 'dedup'),
    dedup_policy_key text NOT NULL,
    dedup_policy_version text NOT NULL,
    leakage_policy_kind text NOT NULL DEFAULT 'leakage'
        CHECK (leakage_policy_kind = 'leakage'),
    leakage_policy_key text NOT NULL,
    leakage_policy_version text NOT NULL,
    spec_artifact_kind text NOT NULL DEFAULT 'contract_bundle'
        CHECK (spec_artifact_kind = 'contract_bundle'),
    spec_sha256 char(64) NOT NULL,
    implementation_bundle_sha256 char(64) NOT NULL
        CHECK (implementation_bundle_sha256 ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (
        data_profile_key, data_profile_version, content_purpose,
        purpose_contract_version
    ),
    FOREIGN KEY (data_profile_key, data_profile_version, content_purpose)
        REFERENCES data_profile_purposes(
            data_profile_key, data_profile_version, content_purpose
        ) ON DELETE RESTRICT,
    FOREIGN KEY (protocol_key, protocol_version)
        REFERENCES review_protocol_versions(protocol_key, protocol_version)
        ON DELETE RESTRICT,
    FOREIGN KEY (pii_policy_kind, pii_policy_key, pii_policy_version)
        REFERENCES data_policy_versions(policy_kind, policy_key, policy_version)
        ON DELETE RESTRICT,
    FOREIGN KEY (dedup_policy_kind, dedup_policy_key, dedup_policy_version)
        REFERENCES data_policy_versions(policy_kind, policy_key, policy_version)
        ON DELETE RESTRICT,
    FOREIGN KEY (leakage_policy_kind, leakage_policy_key, leakage_policy_version)
        REFERENCES data_policy_versions(policy_kind, policy_key, policy_version)
        ON DELETE RESTRICT,
    FOREIGN KEY (spec_artifact_kind, spec_sha256)
        REFERENCES contract_spec_artifacts(artifact_kind, sha256) ON DELETE RESTRICT,
    UNIQUE (
        data_profile_key, data_profile_version, content_purpose,
        purpose_contract_version, spec_sha256
    )
);

CREATE TABLE production_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_kind text NOT NULL CHECK (run_kind IN (
        'import', 'derive', 'human_authored', 'model_generation',
        'hybrid_generation', 'validation'
    )),
    origin_kind text NOT NULL CHECK (origin_kind IN (
        'human', 'model', 'hybrid', 'system'
    )),
    implementation_key text NOT NULL
        CHECK (length(btrim(implementation_key)) BETWEEN 1 AND 160),
    implementation_digest char(64) NOT NULL
        CHECK (implementation_digest ~ '^[0-9a-f]{64}$'),
    config_sha256 char(64) CHECK (
        config_sha256 IS NULL OR config_sha256 ~ '^[0-9a-f]{64}$'
    ),
    input_manifest_sha256 char(64) CHECK (
        input_manifest_sha256 IS NULL OR input_manifest_sha256 ~ '^[0-9a-f]{64}$'
    ),
    output_manifest_sha256 char(64) CHECK (
        output_manifest_sha256 IS NULL OR output_manifest_sha256 ~ '^[0-9a-f]{64}$'
    ),
    parent_run_id uuid REFERENCES production_runs(id) ON DELETE RESTRICT,
    created_by uuid REFERENCES users(id) ON DELETE SET NULL,
    started_at timestamptz,
    completed_at timestamptz,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CHECK (completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at),
    CHECK (parent_run_id IS NULL OR parent_run_id <> id),
    CONSTRAINT production_runs_kind_origin_matrix CHECK (
        (run_kind = 'import' AND origin_kind = 'system')
        OR (run_kind = 'derive' AND origin_kind = 'system')
        OR (run_kind = 'human_authored' AND origin_kind = 'human')
        OR (run_kind = 'model_generation' AND origin_kind = 'model')
        OR (run_kind = 'hybrid_generation' AND origin_kind = 'hybrid')
        OR (run_kind = 'validation' AND origin_kind = 'system')
    )
);

-- All version registries and production provenance records are immutable.
CREATE TRIGGER review_rubric_versions_no_update
BEFORE UPDATE ON review_rubric_versions FOR EACH ROW
EXECUTE FUNCTION reject_versioned_contract_mutation();
CREATE TRIGGER review_rubric_versions_no_delete
BEFORE DELETE ON review_rubric_versions FOR EACH ROW
EXECUTE FUNCTION reject_versioned_contract_mutation();
CREATE TRIGGER review_rubric_versions_no_truncate
BEFORE TRUNCATE ON review_rubric_versions FOR EACH STATEMENT
EXECUTE FUNCTION reject_versioned_contract_mutation();

CREATE TRIGGER review_protocol_versions_no_update
BEFORE UPDATE ON review_protocol_versions FOR EACH ROW
EXECUTE FUNCTION reject_versioned_contract_mutation();
CREATE TRIGGER review_protocol_versions_no_delete
BEFORE DELETE ON review_protocol_versions FOR EACH ROW
EXECUTE FUNCTION reject_versioned_contract_mutation();
CREATE TRIGGER review_protocol_versions_no_truncate
BEFORE TRUNCATE ON review_protocol_versions FOR EACH STATEMENT
EXECUTE FUNCTION reject_versioned_contract_mutation();

CREATE TRIGGER data_policy_versions_no_update
BEFORE UPDATE ON data_policy_versions FOR EACH ROW
EXECUTE FUNCTION reject_versioned_contract_mutation();
CREATE TRIGGER data_policy_versions_no_delete
BEFORE DELETE ON data_policy_versions FOR EACH ROW
EXECUTE FUNCTION reject_versioned_contract_mutation();
CREATE TRIGGER data_policy_versions_no_truncate
BEFORE TRUNCATE ON data_policy_versions FOR EACH STATEMENT
EXECUTE FUNCTION reject_versioned_contract_mutation();

CREATE TRIGGER export_contract_versions_no_update
BEFORE UPDATE ON export_contract_versions FOR EACH ROW
EXECUTE FUNCTION reject_versioned_contract_mutation();
CREATE TRIGGER export_contract_versions_no_delete
BEFORE DELETE ON export_contract_versions FOR EACH ROW
EXECUTE FUNCTION reject_versioned_contract_mutation();
CREATE TRIGGER export_contract_versions_no_truncate
BEFORE TRUNCATE ON export_contract_versions FOR EACH STATEMENT
EXECUTE FUNCTION reject_versioned_contract_mutation();

CREATE TRIGGER data_profile_versions_no_update
BEFORE UPDATE ON data_profile_versions FOR EACH ROW
EXECUTE FUNCTION reject_versioned_contract_mutation();
CREATE TRIGGER data_profile_versions_no_delete
BEFORE DELETE ON data_profile_versions FOR EACH ROW
EXECUTE FUNCTION reject_versioned_contract_mutation();
CREATE TRIGGER data_profile_versions_no_truncate
BEFORE TRUNCATE ON data_profile_versions FOR EACH STATEMENT
EXECUTE FUNCTION reject_versioned_contract_mutation();

CREATE TRIGGER data_profile_purposes_no_update
BEFORE UPDATE ON data_profile_purposes FOR EACH ROW
EXECUTE FUNCTION reject_versioned_contract_mutation();
CREATE TRIGGER data_profile_purposes_no_delete
BEFORE DELETE ON data_profile_purposes FOR EACH ROW
EXECUTE FUNCTION reject_versioned_contract_mutation();
CREATE TRIGGER data_profile_purposes_no_truncate
BEFORE TRUNCATE ON data_profile_purposes FOR EACH STATEMENT
EXECUTE FUNCTION reject_versioned_contract_mutation();

CREATE TRIGGER profile_purpose_contract_versions_no_update
BEFORE UPDATE ON profile_purpose_contract_versions FOR EACH ROW
EXECUTE FUNCTION reject_versioned_contract_mutation();
CREATE TRIGGER profile_purpose_contract_versions_no_delete
BEFORE DELETE ON profile_purpose_contract_versions FOR EACH ROW
EXECUTE FUNCTION reject_versioned_contract_mutation();
CREATE TRIGGER profile_purpose_contract_versions_no_truncate
BEFORE TRUNCATE ON profile_purpose_contract_versions FOR EACH STATEMENT
EXECUTE FUNCTION reject_versioned_contract_mutation();

CREATE TRIGGER production_runs_no_update
BEFORE UPDATE ON production_runs FOR EACH ROW
EXECUTE FUNCTION reject_versioned_contract_mutation();
CREATE TRIGGER production_runs_no_delete
BEFORE DELETE ON production_runs FOR EACH ROW
EXECUTE FUNCTION reject_versioned_contract_mutation();
CREATE TRIGGER production_runs_no_truncate
BEFORE TRUNCATE ON production_runs FOR EACH STATEMENT
EXECUTE FUNCTION reject_versioned_contract_mutation();

-- Extend the positive safe-summary allowlist without copying the v23 body.
-- SET search_path FROM CURRENT pins the migration schema (including isolated
-- test schemas), so the renamed v23 helper cannot be shadowed at runtime.
ALTER FUNCTION row_change_safe_summary(text, jsonb)
    RENAME TO row_change_safe_summary_v23;

CREATE OR REPLACE FUNCTION row_change_safe_summary(
    target_table text,
    row_data jsonb
)
RETURNS jsonb
LANGUAGE plpgsql
IMMUTABLE
SET search_path FROM CURRENT
AS $$
DECLARE
    prior_summary jsonb;
BEGIN
    IF row_data IS NULL THEN
        RETURN NULL;
    END IF;

    IF target_table = 'contract_spec_artifacts' THEN
        RETURN jsonb_build_object(
            'sha256', row_data->'sha256',
            'artifact_kind', row_data->'artifact_kind',
            'canonicalization_key', row_data->'canonicalization_key',
            'media_type', row_data->'media_type',
            'byte_size', row_data->'byte_size'
        );
    ELSIF target_table = 'review_rubric_versions' THEN
        RETURN jsonb_build_object(
            'rubric_key', row_data->'rubric_key',
            'rubric_version', row_data->'rubric_version',
            'spec_sha256', row_data->'spec_sha256'
        );
    ELSIF target_table = 'review_protocol_versions' THEN
        RETURN jsonb_build_object(
            'protocol_key', row_data->'protocol_key',
            'protocol_version', row_data->'protocol_version',
            'spec_sha256', row_data->'spec_sha256'
        );
    ELSIF target_table = 'data_policy_versions' THEN
        RETURN jsonb_build_object(
            'policy_kind', row_data->'policy_kind',
            'policy_key', row_data->'policy_key',
            'policy_version', row_data->'policy_version',
            'spec_sha256', row_data->'spec_sha256'
        );
    ELSIF target_table = 'export_contract_versions' THEN
        RETURN jsonb_build_object(
            'export_contract_key', row_data->'export_contract_key',
            'export_contract_version', row_data->'export_contract_version',
            'spec_sha256', row_data->'spec_sha256'
        );
    ELSIF target_table = 'data_profile_versions' THEN
        RETURN jsonb_build_object(
            'data_profile_key', row_data->'data_profile_key',
            'data_profile_version', row_data->'data_profile_version',
            'payload_kind', row_data->'payload_kind',
            'payload_schema_sha256', row_data->'payload_schema_sha256',
            'profile_config_schema_sha256', row_data->'profile_config_schema_sha256',
            'field_extraction_sha256', row_data->'field_extraction_sha256',
            'rubric_key', row_data->'rubric_key',
            'rubric_version', row_data->'rubric_version',
            'export_contract_key', row_data->'export_contract_key',
            'export_contract_version', row_data->'export_contract_version',
            'implementation_key', row_data->'implementation_key',
            'implementation_digest', row_data->'implementation_digest',
            'is_terminal_legacy', row_data->'is_terminal_legacy'
        );
    ELSIF target_table = 'data_profile_purposes' THEN
        RETURN jsonb_build_object(
            'data_profile_key', row_data->'data_profile_key',
            'data_profile_version', row_data->'data_profile_version',
            'content_purpose', row_data->'content_purpose'
        );
    ELSIF target_table = 'profile_purpose_contract_versions' THEN
        RETURN jsonb_build_object(
            'data_profile_key', row_data->'data_profile_key',
            'data_profile_version', row_data->'data_profile_version',
            'content_purpose', row_data->'content_purpose',
            'purpose_contract_version', row_data->'purpose_contract_version',
            'protocol_key', row_data->'protocol_key',
            'protocol_version', row_data->'protocol_version',
            'pii_policy_key', row_data->'pii_policy_key',
            'pii_policy_version', row_data->'pii_policy_version',
            'dedup_policy_key', row_data->'dedup_policy_key',
            'dedup_policy_version', row_data->'dedup_policy_version',
            'leakage_policy_key', row_data->'leakage_policy_key',
            'leakage_policy_version', row_data->'leakage_policy_version',
            'spec_sha256', row_data->'spec_sha256',
            'implementation_bundle_sha256', row_data->'implementation_bundle_sha256'
        );
    ELSIF target_table = 'production_runs' THEN
        RETURN jsonb_build_object(
            'id', row_data->'id',
            'run_kind', row_data->'run_kind',
            'origin_kind', row_data->'origin_kind',
            'implementation_key', row_data->'implementation_key',
            'implementation_digest', row_data->'implementation_digest',
            'config_sha256', row_data->'config_sha256',
            'input_manifest_sha256', row_data->'input_manifest_sha256',
            'output_manifest_sha256', row_data->'output_manifest_sha256',
            'parent_run_id', row_data->'parent_run_id',
            'created_by', row_data->'created_by'
        );
    ELSIF target_table = 'review_campaigns' THEN
        RETURN jsonb_build_object(
            'id', row_data->'id',
            'source_id', row_data->'source_id',
            'sample_generation', row_data->'sample_generation',
            'sample_source_sha256', row_data->'sample_source_sha256',
            'sample_count', row_data->'sample_count',
            'sample_job_id', row_data->'sample_job_id',
            'sample_membership_count', row_data->'sample_membership_count',
            'sample_membership_root_sha256', row_data->'sample_membership_root_sha256',
            'data_profile_key', row_data->'data_profile_key',
            'data_profile_version', row_data->'data_profile_version',
            'content_purpose', row_data->'content_purpose',
            'profile_config_sha256', row_data->'profile_config_sha256',
            'rubric_key', row_data->'rubric_key',
            'rubric_version', row_data->'rubric_version',
            'purpose_contract_version', row_data->'purpose_contract_version',
            'purpose_contract_sha256', row_data->'purpose_contract_sha256',
            'campaign_contract_sha256', row_data->'campaign_contract_sha256',
            'implementation_bundle_sha256', row_data->'implementation_bundle_sha256',
            'created_by', row_data->'created_by'
        );
    ELSIF target_table = 'release_source_contract_snapshots' THEN
        RETURN jsonb_build_object(
            'release_id', row_data->'release_id',
            'source_id', row_data->'source_id',
            'data_profile_key', row_data->'data_profile_key',
            'data_profile_version', row_data->'data_profile_version',
            'content_purpose', row_data->'content_purpose',
            'data_origin', row_data->'data_origin',
            'production_run_id', row_data->'production_run_id',
            'production_run_implementation_digest', row_data->'production_run_implementation_digest',
            'production_run_config_sha256', row_data->'production_run_config_sha256',
            'production_run_input_manifest_sha256', row_data->'production_run_input_manifest_sha256',
            'derived_from_source_id', row_data->'derived_from_source_id',
            'license_evidence_ref_sha256', row_data->'license_evidence_ref_sha256',
            'lineage_ref_sha256', row_data->'lineage_ref_sha256',
            'sample_generation', row_data->'sample_generation',
            'sample_source_sha256', row_data->'sample_source_sha256',
            'sample_count', row_data->'sample_count',
            'sample_job_id', row_data->'sample_job_id',
            'sample_membership_count', row_data->'sample_membership_count',
            'sample_membership_root_sha256', row_data->'sample_membership_root_sha256',
            'profile_config_schema_artifact_kind', row_data->'profile_config_schema_artifact_kind',
            'profile_config_schema_sha256', row_data->'profile_config_schema_sha256',
            'profile_config_sha256', row_data->'profile_config_sha256',
            'payload_schema_sha256', row_data->'payload_schema_sha256',
            'field_extraction_sha256', row_data->'field_extraction_sha256',
            'profile_implementation_key', row_data->'profile_implementation_key',
            'profile_implementation_digest', row_data->'profile_implementation_digest',
            'rubric_key', row_data->'rubric_key',
            'rubric_version', row_data->'rubric_version',
            'protocol_key', row_data->'protocol_key',
            'protocol_version', row_data->'protocol_version',
            'pii_policy_key', row_data->'pii_policy_key',
            'pii_policy_version', row_data->'pii_policy_version',
            'dedup_policy_key', row_data->'dedup_policy_key',
            'dedup_policy_version', row_data->'dedup_policy_version',
            'leakage_policy_key', row_data->'leakage_policy_key',
            'leakage_policy_version', row_data->'leakage_policy_version',
            'purpose_contract_version', row_data->'purpose_contract_version',
            'purpose_contract_sha256', row_data->'purpose_contract_sha256',
            'export_contract_key', row_data->'export_contract_key',
            'export_contract_version', row_data->'export_contract_version',
            'export_contract_sha256', row_data->'export_contract_sha256',
            'review_campaign_id', row_data->'review_campaign_id',
            'review_evidence_status', row_data->'review_evidence_status',
            'implementation_bundle_sha256', row_data->'implementation_bundle_sha256'
        );
    END IF;

    prior_summary := row_change_safe_summary_v23(target_table, row_data);
    IF target_table = 'sources' THEN
        RETURN prior_summary || jsonb_build_object(
            'data_profile_key', row_data->'data_profile_key',
            'data_profile_version', row_data->'data_profile_version',
            'profile_config_sha256', row_data->'profile_config_sha256',
            'profile_assignment_reason', row_data->'profile_assignment_reason',
            'data_origin', row_data->'data_origin',
            'production_run_id', row_data->'production_run_id'
        );
    ELSIF target_table = 'document_sample_memberships' THEN
        RETURN prior_summary || jsonb_build_object(
            'document_version', row_data->'document_version'
        );
    ELSIF target_table = 'document_reviews' THEN
        RETURN prior_summary || jsonb_build_object(
            'review_campaign_id', row_data->'review_campaign_id'
        );
    ELSIF target_table = 'releases' THEN
        RETURN prior_summary || jsonb_build_object(
            'contract_snapshot_status', row_data->'contract_snapshot_status',
            'contract_snapshot_sha256', row_data->'contract_snapshot_sha256',
            'implementation_bundle_sha256', row_data->'implementation_bundle_sha256'
        );
    END IF;
    RETURN prior_summary;
END;
$$;

-- Audit registry inserts before seeding them. canonical_bytes never enters the
-- safe summaries or their hashes.
CREATE TRIGGER contract_spec_artifacts_capture_row_change
AFTER INSERT OR UPDATE OR DELETE ON contract_spec_artifacts
FOR EACH ROW EXECUTE FUNCTION capture_row_change_event('sha256');
CREATE TRIGGER review_rubric_versions_capture_row_change
AFTER INSERT OR UPDATE OR DELETE ON review_rubric_versions
FOR EACH ROW EXECUTE FUNCTION capture_row_change_event('rubric_key', 'rubric_version');
CREATE TRIGGER review_protocol_versions_capture_row_change
AFTER INSERT OR UPDATE OR DELETE ON review_protocol_versions
FOR EACH ROW EXECUTE FUNCTION capture_row_change_event('protocol_key', 'protocol_version');
CREATE TRIGGER data_policy_versions_capture_row_change
AFTER INSERT OR UPDATE OR DELETE ON data_policy_versions
FOR EACH ROW EXECUTE FUNCTION capture_row_change_event(
    'policy_kind', 'policy_key', 'policy_version'
);
CREATE TRIGGER export_contract_versions_capture_row_change
AFTER INSERT OR UPDATE OR DELETE ON export_contract_versions
FOR EACH ROW EXECUTE FUNCTION capture_row_change_event(
    'export_contract_key', 'export_contract_version'
);
CREATE TRIGGER data_profile_versions_capture_row_change
AFTER INSERT OR UPDATE OR DELETE ON data_profile_versions
FOR EACH ROW EXECUTE FUNCTION capture_row_change_event(
    'data_profile_key', 'data_profile_version'
);
CREATE TRIGGER data_profile_purposes_capture_row_change
AFTER INSERT OR UPDATE OR DELETE ON data_profile_purposes
FOR EACH ROW EXECUTE FUNCTION capture_row_change_event(
    'data_profile_key', 'data_profile_version', 'content_purpose'
);
CREATE TRIGGER profile_purpose_contract_versions_capture_row_change
AFTER INSERT OR UPDATE OR DELETE ON profile_purpose_contract_versions
FOR EACH ROW EXECUTE FUNCTION capture_row_change_event(
    'data_profile_key', 'data_profile_version', 'content_purpose',
    'purpose_contract_version'
);
CREATE TRIGGER production_runs_capture_row_change
AFTER INSERT OR UPDATE OR DELETE ON production_runs
FOR EACH ROW EXECUTE FUNCTION capture_row_change_event('id');

WITH specs(artifact_kind, canonical_text) AS (
    VALUES
        ('payload_schema', '{"kind":"legacy-auto","schema":"opaque-object-v1"}'),
        ('payload_schema', '{"kind":"text-document","schema":"document-object-v1"}'),
        ('profile_config_schema', '{"additionalProperties":false,"type":"object"}'),
        ('profile_config', '{}'),
        ('field_extraction', '{"fields":["document"],"normalizer":"legacy-current-behavior"}'),
        ('field_extraction', '{"fields":["document"],"normalizer":"text-document-current-behavior"}'),
        ('review_rubric', '{"rubric":"multidimensional-v1"}'),
        ('review_protocol', '{"protocol":"legacy-sampled-source-v1"}'),
        ('pii_policy', '{"policy":"legacy-current-pii-v1"}'),
        ('dedup_policy', '{"policy":"legacy-current-dedup-v1"}'),
        ('leakage_policy', '{"policy":"legacy-current-leakage-v1"}'),
        ('export_contract', '{"contract":"legacy-current-export-v1"}'),
        ('contract_bundle', '{"binding":"legacy-current-purpose-contract-v1"}')
), encoded AS (
    SELECT artifact_kind, convert_to(canonical_text, 'UTF8') AS canonical_bytes
    FROM specs
)
INSERT INTO contract_spec_artifacts(
    sha256, artifact_kind, canonicalization_key, media_type,
    canonical_bytes, byte_size
)
SELECT
    contract_spec_artifact_sha256(canonical_bytes), artifact_kind,
    'literal-utf8-v1', 'application/json', canonical_bytes,
    octet_length(canonical_bytes)
FROM encoded;

INSERT INTO review_rubric_versions(
    rubric_key, rubric_version, spec_sha256
)
SELECT 'document-quality', 'multidimensional-v1', sha256
FROM contract_spec_artifacts
WHERE artifact_kind = 'review_rubric';

INSERT INTO review_protocol_versions(
    protocol_key, protocol_version, spec_sha256
)
SELECT 'legacy-source-sampled', '1', sha256
FROM contract_spec_artifacts
WHERE artifact_kind = 'review_protocol';

INSERT INTO data_policy_versions(
    policy_kind, policy_key, policy_version, spec_artifact_kind, spec_sha256
)
SELECT 'pii', 'legacy-current-pii', '1', artifact_kind, sha256
FROM contract_spec_artifacts WHERE artifact_kind = 'pii_policy'
UNION ALL
SELECT 'dedup', 'legacy-current-dedup', '1', artifact_kind, sha256
FROM contract_spec_artifacts WHERE artifact_kind = 'dedup_policy'
UNION ALL
SELECT 'leakage', 'legacy-current-leakage', '1', artifact_kind, sha256
FROM contract_spec_artifacts WHERE artifact_kind = 'leakage_policy';

INSERT INTO export_contract_versions(
    export_contract_key, export_contract_version, spec_sha256
)
SELECT 'legacy-release-export', '1', sha256
FROM contract_spec_artifacts
WHERE artifact_kind = 'export_contract';

INSERT INTO data_profile_versions(
    data_profile_key, data_profile_version, payload_kind,
    payload_schema_sha256, profile_config_schema_sha256,
    field_extraction_sha256, rubric_key, rubric_version,
    export_contract_key, export_contract_version,
    implementation_key, implementation_digest, is_terminal_legacy
)
SELECT
    profile.data_profile_key, '1', profile.payload_kind,
    payload.sha256, config_schema.sha256, extraction.sha256,
    'document-quality', 'multidimensional-v1',
    'legacy-release-export', '1', profile.implementation_key,
    '8a2093eafc5bca99285f51dbc2fb2e08c4463d2e64cc3e565640c5d1aa6912a5',
    profile.is_terminal_legacy
FROM (VALUES
    ('legacy-auto', 'legacy_document', 'legacy-current-v1', true,
        '{"kind":"legacy-auto","schema":"opaque-object-v1"}',
        '{"fields":["document"],"normalizer":"legacy-current-behavior"}'),
    ('text-document', 'text_document', 'text-document-v1', false,
        '{"kind":"text-document","schema":"document-object-v1"}',
        '{"fields":["document"],"normalizer":"text-document-current-behavior"}')
) AS profile(
    data_profile_key, payload_kind, implementation_key, is_terminal_legacy,
    payload_text, extraction_text
)
JOIN contract_spec_artifacts AS payload
  ON payload.artifact_kind = 'payload_schema'
 AND payload.sha256 = contract_spec_artifact_sha256(
     convert_to(profile.payload_text, 'UTF8')
 )
JOIN contract_spec_artifacts AS config_schema
  ON config_schema.artifact_kind = 'profile_config_schema'
JOIN contract_spec_artifacts AS extraction
  ON extraction.artifact_kind = 'field_extraction'
 AND extraction.sha256 = contract_spec_artifact_sha256(
     convert_to(profile.extraction_text, 'UTF8')
 );

INSERT INTO data_profile_purposes(
    data_profile_key, data_profile_version, content_purpose
)
SELECT profile.data_profile_key, profile.data_profile_version, purpose.content_purpose
FROM data_profile_versions AS profile
CROSS JOIN (VALUES
    ('pretrain'), ('instruction'), ('preference'), ('eval'), ('holdout'),
    ('post_training')
) AS purpose(content_purpose)
WHERE profile.data_profile_key IN ('legacy-auto', 'text-document');

INSERT INTO profile_purpose_contract_versions(
    data_profile_key, data_profile_version, content_purpose,
    purpose_contract_version, protocol_key, protocol_version,
    pii_policy_key, pii_policy_version,
    dedup_policy_key, dedup_policy_version,
    leakage_policy_key, leakage_policy_version,
    spec_sha256, implementation_bundle_sha256
)
SELECT
    purpose.data_profile_key, purpose.data_profile_version,
    purpose.content_purpose, '1', 'legacy-source-sampled', '1',
    'legacy-current-pii', '1', 'legacy-current-dedup', '1',
    'legacy-current-leakage', '1', artifact.sha256,
    '8a2093eafc5bca99285f51dbc2fb2e08c4463d2e64cc3e565640c5d1aa6912a5'
FROM data_profile_purposes AS purpose
CROSS JOIN contract_spec_artifacts AS artifact
WHERE purpose.data_profile_key IN ('legacy-auto', 'text-document')
  AND artifact.artifact_kind = 'contract_bundle';

-- Source identity and provenance are create-time facts. Existing sources are
-- not heuristically classified: they receive the terminal legacy profile.
ALTER TABLE sources
    ADD COLUMN data_profile_key text,
    ADD COLUMN data_profile_version text,
    ADD COLUMN profile_config_artifact_kind text,
    ADD COLUMN profile_config_sha256 char(64),
    ADD COLUMN profile_assignment_reason text,
    ADD COLUMN profile_assigned_at timestamptz,
    ADD COLUMN data_origin text,
    ADD COLUMN production_run_id uuid;

-- Preserve existing source version/updated_at while keeping the durable
-- row-change ledger enabled for the backfill itself.
ALTER TABLE sources DISABLE TRIGGER sources_protect_content_purpose;
ALTER TABLE sources DISABLE TRIGGER sources_set_updated_at;

UPDATE sources
SET data_profile_key = 'legacy-auto',
    data_profile_version = '1',
    profile_config_artifact_kind = 'profile_config',
    profile_config_sha256 =
        '44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a',
    profile_assignment_reason = 'backfilled',
    profile_assigned_at = now(),
    data_origin = 'unknown',
    production_run_id = NULL;

ALTER TABLE sources ENABLE TRIGGER sources_set_updated_at;
ALTER TABLE sources ENABLE TRIGGER sources_protect_content_purpose;

INSERT INTO audit_events(actor_type, action, entity_type, entity_id, details)
SELECT
    'system', 'source.data_profile_backfilled', 'source', source.id,
    jsonb_build_object(
        'data_profile_key', source.data_profile_key,
        'data_profile_version', source.data_profile_version,
        'profile_assignment_reason', source.profile_assignment_reason
    )
FROM sources AS source;

ALTER TABLE sources
    ALTER COLUMN data_profile_key SET DEFAULT 'text-document',
    ALTER COLUMN data_profile_key SET NOT NULL,
    ALTER COLUMN data_profile_version SET DEFAULT '1',
    ALTER COLUMN data_profile_version SET NOT NULL,
    ALTER COLUMN profile_config_artifact_kind SET DEFAULT 'profile_config',
    ALTER COLUMN profile_config_artifact_kind SET NOT NULL,
    ALTER COLUMN profile_config_sha256 SET DEFAULT
        '44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a',
    ALTER COLUMN profile_config_sha256 SET NOT NULL,
    ALTER COLUMN profile_assignment_reason SET DEFAULT 'declared_at_ingest',
    ALTER COLUMN profile_assignment_reason SET NOT NULL,
    ALTER COLUMN profile_assigned_at SET DEFAULT now(),
    ALTER COLUMN profile_assigned_at SET NOT NULL,
    ALTER COLUMN data_origin SET DEFAULT 'unknown',
    ALTER COLUMN data_origin SET NOT NULL,
    ADD CONSTRAINT sources_profile_config_artifact_kind
        CHECK (profile_config_artifact_kind = 'profile_config'),
    ADD CONSTRAINT sources_profile_assignment_reason
        CHECK (profile_assignment_reason IN ('declared_at_ingest', 'backfilled')),
    ADD CONSTRAINT sources_data_origin
        CHECK (data_origin IN ('unknown', 'human', 'model', 'hybrid')),
    ADD CONSTRAINT sources_v1_seed_profile_config_identity CHECK (
        data_profile_version <> '1'
        OR data_profile_key NOT IN ('legacy-auto', 'text-document')
        OR (
            profile_config_artifact_kind = 'profile_config'
            AND profile_config_sha256 =
                '44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a'
        )
    ),
    ADD CONSTRAINT sources_data_profile_purpose_fkey
        FOREIGN KEY (data_profile_key, data_profile_version, content_purpose)
        REFERENCES data_profile_purposes(
            data_profile_key, data_profile_version, content_purpose
        ) ON DELETE RESTRICT,
    ADD CONSTRAINT sources_profile_config_fkey
        FOREIGN KEY (profile_config_artifact_kind, profile_config_sha256)
        REFERENCES contract_spec_artifacts(artifact_kind, sha256)
        ON DELETE RESTRICT,
    ADD CONSTRAINT sources_production_run_fkey
        FOREIGN KEY (production_run_id)
        REFERENCES production_runs(id) ON DELETE RESTRICT;

CREATE INDEX sources_data_profile_idx
ON sources (data_profile_key, data_profile_version, content_purpose, created_at DESC);
CREATE INDEX sources_production_run_idx
ON sources (production_run_id) WHERE production_run_id IS NOT NULL;

-- Resolve production provenance only through the migration schema captured at
-- function creation. This avoids caller-controlled search_path shadowing and
-- gives source INSERT/finalization one exact origin/run-kind matrix.
CREATE OR REPLACE FUNCTION validate_source_production_provenance(
    target_schema text,
    target_data_origin text,
    target_production_run_id uuid
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path FROM CURRENT
AS $$
DECLARE
    run_row record;
BEGIN
    IF target_production_run_id IS NULL THEN
        IF target_data_origin <> 'unknown' THEN
            RAISE EXCEPTION '% sources require a production run',
                target_data_origin;
        END IF;
        RETURN;
    END IF;

    IF target_schema IS NULL OR NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_namespace
        WHERE nspname = target_schema
    ) THEN
        RAISE EXCEPTION 'source provenance schema does not exist';
    END IF;
    EXECUTE format(
        'SELECT run_kind, origin_kind, config_sha256
         FROM %I.production_runs WHERE id = $1',
        target_schema
    )
    INTO run_row
    USING target_production_run_id;
    IF run_row.run_kind IS NULL THEN
        RAISE EXCEPTION 'source production run does not exist';
    END IF;

    IF NOT (
        (target_data_origin = 'unknown'
         AND run_row.origin_kind = 'system'
         AND run_row.run_kind = 'import')
        OR (target_data_origin = 'human'
            AND run_row.origin_kind = 'human'
            AND run_row.run_kind = 'human_authored')
        OR (target_data_origin = 'model'
            AND run_row.origin_kind = 'model'
            AND run_row.run_kind = 'model_generation')
        OR (target_data_origin = 'hybrid'
            AND run_row.origin_kind = 'hybrid'
            AND run_row.run_kind = 'hybrid_generation')
    ) THEN
        RAISE EXCEPTION 'source origin does not match production run matrix';
    END IF;

    IF target_data_origin IN ('model', 'hybrid')
       AND run_row.config_sha256 IS NULL THEN
        RAISE EXCEPTION 'model and hybrid production runs require a config digest';
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION protect_source_profile_identity()
RETURNS trigger
LANGUAGE plpgsql
SET search_path FROM CURRENT
AS $$
BEGIN
    IF NEW.data_profile_key IS DISTINCT FROM OLD.data_profile_key
       OR NEW.data_profile_version IS DISTINCT FROM OLD.data_profile_version
       OR NEW.profile_config_artifact_kind IS DISTINCT FROM OLD.profile_config_artifact_kind
       OR NEW.profile_config_sha256 IS DISTINCT FROM OLD.profile_config_sha256
       OR NEW.profile_assignment_reason IS DISTINCT FROM OLD.profile_assignment_reason
       OR NEW.profile_assigned_at IS DISTINCT FROM OLD.profile_assigned_at THEN
        RAISE EXCEPTION 'source data profile and provenance are immutable';
    END IF;
    IF NEW.data_origin IS DISTINCT FROM OLD.data_origin
       OR NEW.production_run_id IS DISTINCT FROM OLD.production_run_id THEN
        IF OLD.data_origin <> 'unknown' OR OLD.production_run_id IS NOT NULL
           OR NEW.data_origin NOT IN ('model', 'hybrid')
           OR NEW.production_run_id IS NULL
           OR OLD.object_sha256 IS NOT NULL OR NEW.object_sha256 IS NOT NULL THEN
            RAISE EXCEPTION 'source data profile and provenance are immutable';
        END IF;
        PERFORM validate_source_production_provenance(
            TG_TABLE_SCHEMA, NEW.data_origin, NEW.production_run_id
        );
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER sources_protect_profile_identity
BEFORE UPDATE ON sources
FOR EACH ROW EXECUTE FUNCTION protect_source_profile_identity();

CREATE OR REPLACE FUNCTION reject_terminal_legacy_source_insert()
RETURNS trigger
LANGUAGE plpgsql
SET search_path FROM CURRENT
AS $$
DECLARE
    terminal_legacy boolean;
BEGIN
    IF NEW.profile_assignment_reason IS DISTINCT FROM 'declared_at_ingest' THEN
        RAISE EXCEPTION 'new sources must use declared_at_ingest profile assignment';
    END IF;

    SELECT profile.is_terminal_legacy
    INTO terminal_legacy
    FROM data_profile_versions AS profile
    WHERE profile.data_profile_key = NEW.data_profile_key
      AND profile.data_profile_version = NEW.data_profile_version;

    IF terminal_legacy THEN
        RAISE EXCEPTION 'terminal legacy data profiles cannot be assigned to new sources';
    END IF;

    PERFORM validate_source_production_provenance(
        TG_TABLE_SCHEMA, NEW.data_origin, NEW.production_run_id
    );
    RETURN NEW;
END;
$$;

CREATE TRIGGER sources_reject_terminal_legacy_insert
BEFORE INSERT ON sources
FOR EACH ROW EXECUTE FUNCTION reject_terminal_legacy_source_insert();

CREATE OR REPLACE FUNCTION protect_document_sample_generation_identity()
RETURNS trigger
LANGUAGE plpgsql
SET search_path FROM CURRENT
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'document sample generations are immutable';
    END IF;
    IF OLD.status <> 'active' OR NEW.status <> 'superseded'
       OR NEW.source_id IS DISTINCT FROM OLD.source_id
       OR NEW.generation IS DISTINCT FROM OLD.generation
       OR NEW.source_sha256 IS DISTINCT FROM OLD.source_sha256
       OR NEW.sampling_method IS DISTINCT FROM OLD.sampling_method
       OR NEW.sample_count IS DISTINCT FROM OLD.sample_count
       OR NEW.job_id IS DISTINCT FROM OLD.job_id
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'document sample generation identity is immutable';
    END IF;
    PERFORM source.id FROM sources AS source
    WHERE source.id = OLD.source_id
    FOR UPDATE;
    RETURN NEW;
END;
$$;

CREATE TRIGGER document_sample_generations_protect_identity
BEFORE UPDATE OR DELETE ON document_sample_generations
FOR EACH ROW EXECUTE FUNCTION protect_document_sample_generation_identity();
CREATE TRIGGER document_sample_generations_no_truncate_v24
BEFORE TRUNCATE ON document_sample_generations
FOR EACH STATEMENT EXECUTE FUNCTION reject_versioned_contract_mutation();

ALTER TABLE document_sample_memberships
    ADD COLUMN document_version bigint;

UPDATE document_sample_memberships AS membership
SET document_version = document.current_version
FROM documents AS document
WHERE document.id = membership.document_id;

ALTER TABLE document_sample_memberships
    ALTER COLUMN document_version SET NOT NULL,
    ADD CONSTRAINT document_sample_memberships_document_version_positive
        CHECK (document_version > 0);

CREATE OR REPLACE FUNCTION prepare_document_sample_membership_identity()
RETURNS trigger
LANGUAGE plpgsql
SET search_path FROM CURRENT
AS $$
DECLARE
    document_row record;
BEGIN
    PERFORM source.id
    FROM sources AS source
    WHERE source.id = NEW.source_id
    FOR UPDATE;
    SELECT source_id, sample_generation, source_ordinal, current_version,
           current_object_sha256, is_active
    INTO document_row
    FROM documents
    WHERE id = NEW.document_id
    FOR SHARE;
    IF NOT FOUND
       OR NOT document_row.is_active
       OR document_row.source_id IS DISTINCT FROM NEW.source_id
       OR document_row.sample_generation IS DISTINCT FROM NEW.generation
       OR document_row.source_ordinal IS DISTINCT FROM NEW.source_ordinal
       OR document_row.current_object_sha256 IS DISTINCT FROM NEW.object_sha256
       OR (NEW.document_version IS NOT NULL
           AND NEW.document_version IS DISTINCT FROM document_row.current_version) THEN
        RAISE EXCEPTION 'sample membership does not match current document identity';
    END IF;
    NEW.document_version := document_row.current_version;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION reject_document_sample_membership_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'document sample memberships are append-only';
END;
$$;

CREATE TRIGGER document_sample_memberships_prepare_identity
BEFORE INSERT ON document_sample_memberships
FOR EACH ROW EXECUTE FUNCTION prepare_document_sample_membership_identity();
CREATE TRIGGER document_sample_memberships_no_update_v24
BEFORE UPDATE ON document_sample_memberships
FOR EACH ROW EXECUTE FUNCTION reject_document_sample_membership_mutation();
CREATE TRIGGER document_sample_memberships_no_delete_v24
BEFORE DELETE ON document_sample_memberships
FOR EACH ROW EXECUTE FUNCTION reject_document_sample_membership_mutation();
CREATE TRIGGER document_sample_memberships_no_truncate_v24
BEFORE TRUNCATE ON document_sample_memberships
FOR EACH STATEMENT EXECUTE FUNCTION reject_document_sample_membership_mutation();

-- The root commits to the ordered immutable sample membership identities.
-- postgres-jsonb-text-v1 is explicit PostgreSQL jsonb text serialization and
-- makes no JSON Canonicalization Scheme claim. Raw document content is absent.
CREATE OR REPLACE FUNCTION derive_document_sample_membership_evidence(
    target_source_id uuid,
    target_generation integer,
    OUT membership_count integer,
    OUT membership_root_sha256 char(64)
)
RETURNS record
LANGUAGE plpgsql
SET search_path FROM CURRENT
AS $$
DECLARE
    digest_material text;
BEGIN
    PERFORM membership.document_id
    FROM document_sample_memberships AS membership
    JOIN documents AS document ON document.id = membership.document_id
    WHERE membership.source_id = target_source_id
      AND membership.generation = target_generation
    ORDER BY membership.source_ordinal, membership.document_id
    FOR SHARE OF membership, document;

    IF EXISTS (
        SELECT 1
        FROM document_sample_memberships AS membership
        JOIN documents AS document ON document.id = membership.document_id
        WHERE membership.source_id = target_source_id
          AND membership.generation = target_generation
          AND (
              NOT document.is_active
              OR document.source_id IS DISTINCT FROM membership.source_id
              OR document.sample_generation IS DISTINCT FROM membership.generation
              OR document.source_ordinal IS DISTINCT FROM membership.source_ordinal
              OR document.current_version IS DISTINCT FROM membership.document_version
              OR document.current_object_sha256 IS DISTINCT FROM membership.object_sha256
          )
    ) THEN
        RAISE EXCEPTION 'sample membership does not match current document identity';
    END IF;
    IF EXISTS (
        SELECT 1
        FROM documents AS document
        WHERE document.source_id = target_source_id
          AND document.sample_generation = target_generation
          AND document.is_active
          AND NOT EXISTS (
              SELECT 1
              FROM document_sample_memberships AS membership
              WHERE membership.source_id = target_source_id
                AND membership.generation = target_generation
                AND membership.document_id = document.id
          )
    ) THEN
        RAISE EXCEPTION 'active sample document is missing immutable membership';
    END IF;

    SELECT count(*)::integer,
           string_agg(
               btrim(contract_spec_artifact_sha256(convert_to(
                   jsonb_build_object(
                       'source_id', membership.source_id,
                       'generation', membership.generation,
                       'document_id', membership.document_id,
                       'source_ordinal', membership.source_ordinal,
                       'object_sha256', membership.object_sha256,
                       'document_version', membership.document_version,
                       'risk_score', membership.risk_score,
                       'risk_reasons', membership.risk_reasons
                   )::text,
                   'UTF8'
               ))::text),
               '' ORDER BY membership.source_ordinal, membership.document_id
           )
    INTO membership_count, digest_material
    FROM document_sample_memberships AS membership
    WHERE membership.source_id = target_source_id
      AND membership.generation = target_generation;

    IF membership_count = 0 THEN
        RAISE EXCEPTION 'sample generation has no immutable memberships';
    END IF;
    membership_root_sha256 := contract_spec_artifact_sha256(
        convert_to(digest_material, 'UTF8')
    );
END;
$$;

-- A review campaign pins the protocol/policies for one source sample
-- generation. It is intentionally distinct from sample generation so a new
-- protocol can review the same deterministic sample without resampling it.
CREATE TABLE review_campaigns (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id uuid NOT NULL REFERENCES sources(id) ON DELETE RESTRICT,
    sample_generation integer NOT NULL CHECK (sample_generation > 0),
    sample_source_sha256 char(64) NOT NULL
        REFERENCES storage_objects(sha256) ON DELETE RESTRICT,
    sample_sampling_method text NOT NULL,
    sample_count integer NOT NULL CHECK (sample_count >= 0),
    sample_job_id uuid REFERENCES background_jobs(id) ON DELETE RESTRICT,
    sample_membership_count integer NOT NULL CHECK (sample_membership_count > 0),
    sample_membership_root_sha256 char(64) NOT NULL
        CHECK (sample_membership_root_sha256 ~ '^[0-9a-f]{64}$'),
    data_profile_key text NOT NULL,
    data_profile_version text NOT NULL,
    content_purpose text NOT NULL,
    profile_config_artifact_kind text NOT NULL DEFAULT 'profile_config'
        CHECK (profile_config_artifact_kind = 'profile_config'),
    profile_config_sha256 char(64) NOT NULL,
    rubric_key text NOT NULL,
    rubric_version text NOT NULL,
    purpose_contract_version text NOT NULL,
    protocol_key text NOT NULL,
    protocol_version text NOT NULL,
    pii_policy_kind text NOT NULL DEFAULT 'pii' CHECK (pii_policy_kind = 'pii'),
    pii_policy_key text NOT NULL,
    pii_policy_version text NOT NULL,
    dedup_policy_kind text NOT NULL DEFAULT 'dedup'
        CHECK (dedup_policy_kind = 'dedup'),
    dedup_policy_key text NOT NULL,
    dedup_policy_version text NOT NULL,
    leakage_policy_kind text NOT NULL DEFAULT 'leakage'
        CHECK (leakage_policy_kind = 'leakage'),
    leakage_policy_key text NOT NULL,
    leakage_policy_version text NOT NULL,
    purpose_contract_artifact_kind text NOT NULL DEFAULT 'contract_bundle'
        CHECK (purpose_contract_artifact_kind = 'contract_bundle'),
    purpose_contract_sha256 char(64) NOT NULL,
    campaign_contract_artifact_kind text NOT NULL DEFAULT 'contract_bundle'
        CHECK (campaign_contract_artifact_kind = 'contract_bundle'),
    campaign_contract_sha256 char(64) NOT NULL,
    implementation_bundle_sha256 char(64) NOT NULL
        CHECK (implementation_bundle_sha256 ~ '^[0-9a-f]{64}$'),
    created_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT review_campaigns_contract_identity_unique UNIQUE (
        source_id, sample_generation, data_profile_key, data_profile_version,
        content_purpose, purpose_contract_version
    ),
    FOREIGN KEY (source_id, sample_generation)
        REFERENCES document_sample_generations(source_id, generation)
        ON DELETE RESTRICT,
    FOREIGN KEY (data_profile_key, data_profile_version, content_purpose)
        REFERENCES data_profile_purposes(
            data_profile_key, data_profile_version, content_purpose
        ) ON DELETE RESTRICT,
    FOREIGN KEY (profile_config_artifact_kind, profile_config_sha256)
        REFERENCES contract_spec_artifacts(artifact_kind, sha256)
        ON DELETE RESTRICT,
    FOREIGN KEY (rubric_key, rubric_version)
        REFERENCES review_rubric_versions(rubric_key, rubric_version)
        ON DELETE RESTRICT,
    FOREIGN KEY (
        data_profile_key, data_profile_version, content_purpose,
        purpose_contract_version, purpose_contract_sha256
    ) REFERENCES profile_purpose_contract_versions(
        data_profile_key, data_profile_version, content_purpose,
        purpose_contract_version, spec_sha256
    ) ON DELETE RESTRICT,
    FOREIGN KEY (protocol_key, protocol_version)
        REFERENCES review_protocol_versions(protocol_key, protocol_version)
        ON DELETE RESTRICT,
    FOREIGN KEY (pii_policy_kind, pii_policy_key, pii_policy_version)
        REFERENCES data_policy_versions(policy_kind, policy_key, policy_version)
        ON DELETE RESTRICT,
    FOREIGN KEY (dedup_policy_kind, dedup_policy_key, dedup_policy_version)
        REFERENCES data_policy_versions(policy_kind, policy_key, policy_version)
        ON DELETE RESTRICT,
    FOREIGN KEY (leakage_policy_kind, leakage_policy_key, leakage_policy_version)
        REFERENCES data_policy_versions(policy_kind, policy_key, policy_version)
        ON DELETE RESTRICT,
    FOREIGN KEY (purpose_contract_artifact_kind, purpose_contract_sha256)
        REFERENCES contract_spec_artifacts(artifact_kind, sha256)
        ON DELETE RESTRICT,
    FOREIGN KEY (campaign_contract_artifact_kind, campaign_contract_sha256)
        REFERENCES contract_spec_artifacts(artifact_kind, sha256)
        ON DELETE RESTRICT
);

CREATE INDEX review_campaigns_source_idx
ON review_campaigns (source_id, sample_generation, created_at DESC);

CREATE OR REPLACE FUNCTION validate_review_campaign_contract()
RETURNS trigger
LANGUAGE plpgsql
SET search_path FROM CURRENT
AS $$
DECLARE
    source_row record;
    generation_row record;
    membership_evidence record;
    profile_row record;
    contract_row record;
    bundle_bytes bytea;
    bundle_sha char(64);
BEGIN
    SELECT data_profile_key, data_profile_version, content_purpose,
           profile_config_sha256, object_sha256,
           document_sample_generation
    INTO source_row
    FROM sources
    WHERE id = NEW.source_id
    FOR UPDATE;

    IF NOT FOUND
       OR source_row.data_profile_key IS DISTINCT FROM NEW.data_profile_key
       OR source_row.data_profile_version IS DISTINCT FROM NEW.data_profile_version
       OR source_row.content_purpose IS DISTINCT FROM NEW.content_purpose
       OR source_row.profile_config_sha256 IS DISTINCT FROM NEW.profile_config_sha256 THEN
        RAISE EXCEPTION 'review campaign does not match immutable source profile';
    END IF;

    SELECT source_sha256, sampling_method, sample_count, job_id, status
    INTO generation_row
    FROM document_sample_generations
    WHERE source_id = NEW.source_id AND generation = NEW.sample_generation
    FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'review campaign sample generation does not exist';
    END IF;
    IF NEW.sample_generation IS DISTINCT FROM source_row.document_sample_generation
       OR generation_row.status <> 'active'
       OR generation_row.source_sha256 IS DISTINCT FROM source_row.object_sha256
       OR (NEW.sample_source_sha256 IS NOT NULL
        AND NEW.sample_source_sha256 IS DISTINCT FROM generation_row.source_sha256)
       OR (NEW.sample_sampling_method IS NOT NULL
           AND NEW.sample_sampling_method IS DISTINCT FROM generation_row.sampling_method)
       OR (NEW.sample_count IS NOT NULL
           AND NEW.sample_count IS DISTINCT FROM generation_row.sample_count)
       OR (NEW.sample_job_id IS NOT NULL
           AND NEW.sample_job_id IS DISTINCT FROM generation_row.job_id) THEN
        RAISE EXCEPTION 'review campaign sample pins do not match generation';
    END IF;
    SELECT * INTO membership_evidence
    FROM derive_document_sample_membership_evidence(
        NEW.source_id, NEW.sample_generation
    );
    IF membership_evidence.membership_count IS DISTINCT FROM
           generation_row.sample_count THEN
        RAISE EXCEPTION 'review campaign membership count does not match generation';
    END IF;
    IF (NEW.sample_membership_count IS NOT NULL
        AND NEW.sample_membership_count IS DISTINCT FROM
            membership_evidence.membership_count)
       OR (NEW.sample_membership_root_sha256 IS NOT NULL
           AND NEW.sample_membership_root_sha256 IS DISTINCT FROM
               membership_evidence.membership_root_sha256) THEN
        RAISE EXCEPTION 'review campaign membership evidence mismatch';
    END IF;
    NEW.sample_source_sha256 := generation_row.source_sha256;
    NEW.sample_sampling_method := generation_row.sampling_method;
    NEW.sample_count := generation_row.sample_count;
    NEW.sample_job_id := generation_row.job_id;
    NEW.sample_membership_count := membership_evidence.membership_count;
    NEW.sample_membership_root_sha256 :=
        membership_evidence.membership_root_sha256;

    SELECT rubric_key, rubric_version
    INTO profile_row
    FROM data_profile_versions
    WHERE data_profile_key = NEW.data_profile_key
      AND data_profile_version = NEW.data_profile_version;

    IF profile_row.rubric_key IS DISTINCT FROM NEW.rubric_key
       OR profile_row.rubric_version IS DISTINCT FROM NEW.rubric_version THEN
        RAISE EXCEPTION 'review campaign rubric does not match data profile';
    END IF;

    SELECT protocol_key, protocol_version,
           pii_policy_key, pii_policy_version,
           dedup_policy_key, dedup_policy_version,
           leakage_policy_key, leakage_policy_version,
           implementation_bundle_sha256
    INTO contract_row
    FROM profile_purpose_contract_versions
    WHERE data_profile_key = NEW.data_profile_key
      AND data_profile_version = NEW.data_profile_version
      AND content_purpose = NEW.content_purpose
      AND purpose_contract_version = NEW.purpose_contract_version;

    IF contract_row.protocol_key IS DISTINCT FROM NEW.protocol_key
       OR contract_row.protocol_version IS DISTINCT FROM NEW.protocol_version
       OR contract_row.pii_policy_key IS DISTINCT FROM NEW.pii_policy_key
       OR contract_row.pii_policy_version IS DISTINCT FROM NEW.pii_policy_version
       OR contract_row.dedup_policy_key IS DISTINCT FROM NEW.dedup_policy_key
       OR contract_row.dedup_policy_version IS DISTINCT FROM NEW.dedup_policy_version
       OR contract_row.leakage_policy_key IS DISTINCT FROM NEW.leakage_policy_key
       OR contract_row.leakage_policy_version IS DISTINCT FROM NEW.leakage_policy_version
       OR contract_row.implementation_bundle_sha256 IS DISTINCT FROM
          NEW.implementation_bundle_sha256 THEN
        RAISE EXCEPTION 'review campaign pins do not match purpose contract';
    END IF;

    bundle_bytes := convert_to(jsonb_build_object(
        'bundle_kind', 'review_campaign_contract',
        'identity', jsonb_build_array(
            NEW.source_id, NEW.sample_generation, NEW.data_profile_key,
            NEW.data_profile_version, NEW.content_purpose
        ),
        'pins', jsonb_build_array(
            NEW.sample_source_sha256, NEW.sample_sampling_method,
            NEW.sample_count, NEW.sample_job_id,
            NEW.sample_membership_count, NEW.sample_membership_root_sha256,
            NEW.profile_config_sha256, NEW.rubric_key, NEW.rubric_version,
            NEW.purpose_contract_version, NEW.purpose_contract_sha256,
            NEW.protocol_key, NEW.protocol_version, NEW.pii_policy_key,
            NEW.pii_policy_version, NEW.dedup_policy_key,
            NEW.dedup_policy_version, NEW.leakage_policy_key,
            NEW.leakage_policy_version, NEW.implementation_bundle_sha256
        )
    )::text, 'UTF8');
    bundle_sha := contract_spec_artifact_sha256(bundle_bytes);
    IF NEW.campaign_contract_sha256 IS NOT NULL
       AND NEW.campaign_contract_sha256 IS DISTINCT FROM bundle_sha THEN
        RAISE EXCEPTION 'review campaign contract sha256 does not match pinned fields';
    END IF;
    NEW.campaign_contract_sha256 := bundle_sha;

    INSERT INTO contract_spec_artifacts(
        sha256, artifact_kind, canonicalization_key, media_type,
        canonical_bytes, byte_size
    ) VALUES (
        bundle_sha, 'contract_bundle', 'postgres-jsonb-text-v1',
        'application/json', bundle_bytes, octet_length(bundle_bytes)
    ) ON CONFLICT (sha256) DO NOTHING;
    RETURN NEW;
END;
$$;

CREATE TRIGGER review_campaigns_validate_contract
BEFORE INSERT ON review_campaigns
FOR EACH ROW EXECUTE FUNCTION validate_review_campaign_contract();
CREATE TRIGGER review_campaigns_no_update
BEFORE UPDATE ON review_campaigns FOR EACH ROW
EXECUTE FUNCTION reject_versioned_contract_mutation();
CREATE TRIGGER review_campaigns_no_delete
BEFORE DELETE ON review_campaigns FOR EACH ROW
EXECUTE FUNCTION reject_versioned_contract_mutation();
CREATE TRIGGER review_campaigns_no_truncate
BEFORE TRUNCATE ON review_campaigns FOR EACH STATEMENT
EXECUTE FUNCTION reject_versioned_contract_mutation();
CREATE TRIGGER review_campaigns_capture_row_change
AFTER INSERT OR UPDATE OR DELETE ON review_campaigns
FOR EACH ROW EXECUTE FUNCTION capture_row_change_event('id');

ALTER TABLE document_reviews
    ADD COLUMN review_campaign_id uuid,
    ADD CONSTRAINT document_reviews_review_campaign_fkey
        FOREIGN KEY (review_campaign_id)
        REFERENCES review_campaigns(id) ON DELETE RESTRICT;

CREATE INDEX document_reviews_campaign_idx
ON document_reviews (review_campaign_id, created_at DESC)
WHERE review_campaign_id IS NOT NULL;

CREATE OR REPLACE FUNCTION validate_document_review_campaign()
RETURNS trigger
LANGUAGE plpgsql
SET search_path FROM CURRENT
AS $$
DECLARE
    campaign_row record;
    document_row record;
BEGIN
    IF NEW.review_campaign_id IS NULL THEN
        RAISE EXCEPTION 'new document reviews require a pinned review campaign';
    END IF;

    SELECT source_id, sample_generation, rubric_version
    INTO campaign_row
    FROM review_campaigns
    WHERE id = NEW.review_campaign_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'review campaign does not exist';
    END IF;

    SELECT source_id, sample_generation, current_version, current_object_sha256
    INTO document_row
    FROM documents
    WHERE id = NEW.document_id;
    IF NOT FOUND
       OR campaign_row.source_id IS DISTINCT FROM document_row.source_id
       OR campaign_row.sample_generation IS DISTINCT FROM document_row.sample_generation
       OR NEW.document_version IS DISTINCT FROM document_row.current_version
       OR NEW.object_sha256 IS DISTINCT FROM document_row.current_object_sha256
       OR campaign_row.rubric_version IS DISTINCT FROM NEW.rubric_version THEN
        RAISE EXCEPTION 'document review does not match pinned review campaign';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER document_reviews_validate_campaign
BEFORE INSERT ON document_reviews
FOR EACH ROW EXECUTE FUNCTION validate_document_review_campaign();

ALTER TABLE document_review_claims
    ADD COLUMN review_campaign_id uuid,
    ADD CONSTRAINT document_review_claims_review_campaign_fkey
        FOREIGN KEY (review_campaign_id)
        REFERENCES review_campaigns(id) ON DELETE RESTRICT;

CREATE INDEX document_review_claims_campaign_idx
ON document_review_claims (review_campaign_id, claimed_at DESC)
WHERE review_campaign_id IS NOT NULL;

CREATE OR REPLACE FUNCTION validate_document_review_claim_campaign()
RETURNS trigger
LANGUAGE plpgsql
SET search_path FROM CURRENT
AS $$
DECLARE
    campaign_row record;
    document_row record;
BEGIN
    IF TG_OP = 'UPDATE'
       AND NEW.review_campaign_id IS DISTINCT FROM OLD.review_campaign_id THEN
        RAISE EXCEPTION 'document review claim campaign is immutable';
    END IF;
    IF NEW.review_campaign_id IS NULL THEN
        RAISE EXCEPTION 'new or renewed document review claims require a pinned campaign';
    END IF;
    SELECT source_id, sample_generation INTO campaign_row
    FROM review_campaigns WHERE id = NEW.review_campaign_id;
    SELECT source_id, sample_generation INTO document_row
    FROM documents WHERE id = NEW.document_id;
    IF campaign_row.source_id IS DISTINCT FROM document_row.source_id
       OR campaign_row.sample_generation IS DISTINCT FROM document_row.sample_generation THEN
        RAISE EXCEPTION 'document review claim does not match pinned campaign';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER document_review_claims_validate_campaign
BEFORE INSERT OR UPDATE ON document_review_claims
FOR EACH ROW EXECUTE FUNCTION validate_document_review_claim_campaign();

-- active_document_reviews is a mutable performance projection maintained only
-- by the canonical append-only review/reversal triggers. Direct writes cannot
-- create evidence or corrupt the effective-review uniqueness projection.
CREATE OR REPLACE FUNCTION protect_active_document_review_projection()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF pg_trigger_depth() < 2 THEN
        RAISE EXCEPTION 'active document review projection is trigger-maintained';
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE TRIGGER active_document_reviews_trigger_writes_only
BEFORE INSERT OR UPDATE OR DELETE ON active_document_reviews
FOR EACH ROW EXECUTE FUNCTION protect_active_document_review_projection();
CREATE TRIGGER active_document_reviews_no_truncate_v24
BEFORE TRUNCATE ON active_document_reviews
FOR EACH STATEMENT EXECUTE FUNCTION protect_active_document_review_projection();

-- Direct SQL reversals use the same source -> document -> review order as
-- review and release transactions. This makes the canonical reversal row
-- serialize with snapshot/freeze validation instead of racing its statement
-- snapshot after only taking an FK key-share lock.
CREATE OR REPLACE FUNCTION lock_document_review_reversal_evidence()
RETURNS trigger
LANGUAGE plpgsql
SET search_path FROM CURRENT
AS $$
DECLARE
    target_source_id uuid;
    target_document_id uuid;
BEGIN
    SELECT document.source_id, review.document_id
    INTO target_source_id, target_document_id
    FROM document_reviews AS review
    JOIN documents AS document ON document.id = review.document_id
    WHERE review.id = NEW.review_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'document review to reverse does not exist';
    END IF;

    PERFORM source.id FROM sources AS source
    WHERE source.id = target_source_id
    FOR UPDATE;
    PERFORM document.id FROM documents AS document
    WHERE document.id = target_document_id
      AND document.source_id = target_source_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'document review source identity changed';
    END IF;
    PERFORM review.id FROM document_reviews AS review
    WHERE review.id = NEW.review_id
      AND review.document_id = target_document_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'document review identity changed';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER document_review_reversals_lock_evidence_v24
BEFORE INSERT ON document_review_reversals
FOR EACH ROW EXECUTE FUNCTION lock_document_review_reversal_evidence();

CREATE OR REPLACE FUNCTION validate_release_review_evidence(
    target_source_id uuid,
    target_evidence_status text,
    target_campaign_id uuid
)
RETURNS void
LANGUAGE plpgsql
SET search_path FROM CURRENT
AS $$
DECLARE
    source_profile text;
    source_assignment text;
    source_object_sha char(64);
    current_generation integer;
    evidence_generation integer;
    generation_source_sha char(64);
    generation_status text;
    generation_sample_count integer;
    membership_evidence record;
BEGIN
    SELECT data_profile_key, profile_assignment_reason,
           object_sha256, document_sample_generation
    INTO source_profile, source_assignment, source_object_sha,
         current_generation
    FROM sources WHERE id = target_source_id
    FOR UPDATE;

    evidence_generation := current_generation;

    IF target_evidence_status = 'campaign_pinned' THEN
        SELECT sample_generation INTO evidence_generation
        FROM review_campaigns
        WHERE id = target_campaign_id AND source_id = target_source_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'release review campaign does not match source';
        END IF;
    ELSIF target_evidence_status = 'absent_pre_registry' THEN
        IF source_profile <> 'legacy-auto' OR source_assignment <> 'backfilled'
           OR target_campaign_id IS NOT NULL THEN
            RAISE EXCEPTION 'absent_pre_registry review evidence is only valid for backfilled legacy sources';
        END IF;
    ELSE
        RAISE EXCEPTION 'invalid release review evidence status';
    END IF;

    IF evidence_generation IS DISTINCT FROM current_generation THEN
        RAISE EXCEPTION 'release review evidence is not for the current sample generation';
    END IF;
    SELECT source_sha256, status, sample_count
    INTO generation_source_sha, generation_status, generation_sample_count
    FROM document_sample_generations
    WHERE source_id = target_source_id
      AND generation = evidence_generation
    FOR SHARE;
    IF NOT FOUND OR generation_status <> 'active'
       OR generation_source_sha IS DISTINCT FROM source_object_sha THEN
        RAISE EXCEPTION 'release review evidence sample generation is not current';
    END IF;
    SELECT * INTO membership_evidence
    FROM derive_document_sample_membership_evidence(
        target_source_id, evidence_generation
    );
    IF membership_evidence.membership_count IS DISTINCT FROM
           generation_sample_count THEN
        RAISE EXCEPTION 'release review evidence membership count does not match generation';
    END IF;

    IF evidence_generation <= 0 OR NOT EXISTS (
        SELECT 1 FROM documents AS document
        WHERE document.source_id = target_source_id
          AND document.sample_generation = evidence_generation
          AND document.is_active
    ) THEN
        RAISE EXCEPTION 'release review evidence has no active sample documents';
    END IF;

    IF target_evidence_status = 'absent_pre_registry' AND EXISTS (
        SELECT 1
        FROM document_reviews AS review
        LEFT JOIN document_review_reversals AS reversal
          ON reversal.review_id = review.id
        JOIN documents AS document ON document.id = review.document_id
        WHERE document.source_id = target_source_id
          AND document.sample_generation = evidence_generation
          AND document.is_active
          AND review.document_version = document.current_version
          AND review.object_sha256 = document.current_object_sha256
          AND reversal.id IS NULL
          AND review.review_campaign_id IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'absent_pre_registry cannot coexist with campaign review evidence';
    END IF;

    PERFORM document.id
    FROM documents AS document
    WHERE document.source_id = target_source_id
      AND document.sample_generation = evidence_generation
      AND document.is_active
    ORDER BY document.id
    FOR SHARE;

    PERFORM review.id
    FROM document_reviews AS review
    LEFT JOIN document_review_reversals AS reversal
      ON reversal.review_id = review.id
    JOIN documents AS document ON document.id = review.document_id
    WHERE document.source_id = target_source_id
      AND document.sample_generation = evidence_generation
      AND document.is_active
      AND review.document_version = document.current_version
      AND review.object_sha256 = document.current_object_sha256
      AND reversal.id IS NULL
      AND review.decision = 'approved'
      AND (
          (target_evidence_status = 'campaign_pinned'
           AND review.review_campaign_id = target_campaign_id)
          OR (target_evidence_status = 'absent_pre_registry'
              AND review.review_campaign_id IS NULL)
      )
    ORDER BY review.id
    FOR UPDATE OF review;

    IF EXISTS (
        SELECT 1
        FROM documents AS document
        WHERE document.source_id = target_source_id
          AND document.sample_generation = evidence_generation
          AND document.is_active
          AND NOT EXISTS (
              SELECT 1
              FROM document_reviews AS review
              LEFT JOIN document_review_reversals AS reversal
                ON reversal.review_id = review.id
              WHERE review.document_id = document.id
                AND review.document_version = document.current_version
                AND review.object_sha256 = document.current_object_sha256
                AND reversal.id IS NULL
                AND review.decision = 'approved'
                AND (
                    (target_evidence_status = 'campaign_pinned'
                     AND review.review_campaign_id = target_campaign_id)
                    OR (target_evidence_status = 'absent_pre_registry'
                        AND review.review_campaign_id IS NULL)
                )
          )
    ) THEN
        RAISE EXCEPTION 'release review evidence does not cover every active sample document';
    END IF;
END;
$$;

-- Existing frozen releases predate the registry. Their missing contract
-- snapshot is recorded honestly; no child rows or hashes are fabricated.
ALTER TABLE releases
    ADD COLUMN contract_snapshot_status text NOT NULL DEFAULT 'pending'
        CHECK (contract_snapshot_status IN (
            'pending', 'absent_pre_registry', 'present'
        )),
    ADD COLUMN contract_snapshot_artifact_kind text,
    ADD COLUMN contract_snapshot_sha256 char(64),
    ADD COLUMN implementation_bundle_sha256 char(64),
    ADD CONSTRAINT releases_contract_snapshot_shape CHECK (
        (
            contract_snapshot_status IN ('pending', 'absent_pre_registry')
            AND contract_snapshot_artifact_kind IS NULL
            AND contract_snapshot_sha256 IS NULL
            AND implementation_bundle_sha256 IS NULL
        ) OR (
            contract_snapshot_status = 'present'
            AND contract_snapshot_artifact_kind = 'contract_bundle'
            AND contract_snapshot_sha256 ~ '^[0-9a-f]{64}$'
            AND implementation_bundle_sha256 ~ '^[0-9a-f]{64}$'
        )
    ),
    ADD CONSTRAINT releases_contract_snapshot_artifact_fkey
        FOREIGN KEY (contract_snapshot_artifact_kind, contract_snapshot_sha256)
        REFERENCES contract_spec_artifacts(artifact_kind, sha256)
        ON DELETE RESTRICT;

CREATE OR REPLACE FUNCTION protect_release_source_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path FROM CURRENT
AS $$
DECLARE
    old_release_status text;
    old_snapshot_status text;
    new_release_status text;
    new_snapshot_status text;
BEGIN
    -- Lock both sides of an UPDATE in deterministic order before inspecting
    -- either status. A row therefore cannot be moved out of a concurrently
    -- frozen, superseded or contract-snapshotted release.
    IF TG_OP = 'UPDATE' THEN
        PERFORM release.id
        FROM releases AS release
        WHERE release.id IN (OLD.release_id, NEW.release_id)
        ORDER BY release.id
        FOR UPDATE;

        SELECT status, contract_snapshot_status
        INTO old_release_status, old_snapshot_status
        FROM releases WHERE id = OLD.release_id;
        SELECT status, contract_snapshot_status
        INTO new_release_status, new_snapshot_status
        FROM releases WHERE id = NEW.release_id;

        IF old_release_status <> 'draft' OR old_snapshot_status = 'present'
           OR new_release_status <> 'draft' OR new_snapshot_status = 'present' THEN
            RAISE EXCEPTION 'frozen, superseded or contract-snapshotted release sources are immutable';
        END IF;
        IF NEW.release_id IS DISTINCT FROM OLD.release_id
           OR NEW.source_id IS DISTINCT FROM OLD.source_id THEN
            RAISE EXCEPTION 'release source identity is immutable';
        END IF;
        RETURN NEW;
    END IF;

    SELECT status, contract_snapshot_status
    INTO old_release_status, old_snapshot_status
    FROM releases
    WHERE id = CASE WHEN TG_OP = 'DELETE' THEN OLD.release_id ELSE NEW.release_id END
    FOR UPDATE;
    IF old_release_status <> 'draft' OR old_snapshot_status = 'present' THEN
        RAISE EXCEPTION 'frozen, superseded or contract-snapshotted release sources are immutable';
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

ALTER TABLE releases DISABLE TRIGGER releases_protect_frozen;
UPDATE releases
SET contract_snapshot_status = 'absent_pre_registry'
WHERE status IN ('frozen', 'superseded');
ALTER TABLE releases ENABLE TRIGGER releases_protect_frozen;

CREATE OR REPLACE FUNCTION protect_frozen_release()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status IN ('frozen', 'superseded') THEN
        RAISE EXCEPTION 'frozen and superseded releases are immutable';
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

INSERT INTO audit_events(actor_type, action, entity_type, entity_id, details)
SELECT
    'system', 'release.contract_snapshot_absence_recorded', 'release',
    release.id,
    jsonb_build_object(
        'contract_snapshot_status', release.contract_snapshot_status,
        'reason', 'release_frozen_before_profile_registry'
    )
FROM releases AS release
WHERE release.contract_snapshot_status = 'absent_pre_registry';

CREATE INDEX releases_contract_snapshot_status_idx
ON releases (contract_snapshot_status, created_at DESC);

CREATE TABLE release_source_contract_snapshots (
    release_id uuid NOT NULL,
    source_id uuid NOT NULL,
    data_profile_key text NOT NULL,
    data_profile_version text NOT NULL,
    content_purpose text NOT NULL,
    data_origin text NOT NULL CHECK (
        data_origin IN ('unknown', 'human', 'model', 'hybrid')
    ),
    production_run_id uuid REFERENCES production_runs(id) ON DELETE RESTRICT,
    production_run_implementation_digest char(64),
    production_run_config_sha256 char(64),
    production_run_input_manifest_sha256 char(64),
    derived_from_source_id uuid REFERENCES sources(id) ON DELETE RESTRICT,
    license_evidence_ref_sha256 char(64),
    lineage_ref_sha256 char(64) NOT NULL,
    sample_generation integer NOT NULL CHECK (sample_generation > 0),
    sample_source_sha256 char(64) NOT NULL
        REFERENCES storage_objects(sha256) ON DELETE RESTRICT,
    sample_sampling_method text NOT NULL,
    sample_count integer NOT NULL CHECK (sample_count >= 0),
    sample_job_id uuid REFERENCES background_jobs(id) ON DELETE RESTRICT,
    sample_membership_count integer NOT NULL CHECK (sample_membership_count > 0),
    sample_membership_root_sha256 char(64) NOT NULL
        CHECK (sample_membership_root_sha256 ~ '^[0-9a-f]{64}$'),
    profile_config_schema_artifact_kind text NOT NULL
        DEFAULT 'profile_config_schema'
        CHECK (profile_config_schema_artifact_kind = 'profile_config_schema'),
    profile_config_schema_sha256 char(64) NOT NULL,
    profile_config_artifact_kind text NOT NULL DEFAULT 'profile_config'
        CHECK (profile_config_artifact_kind = 'profile_config'),
    profile_config_sha256 char(64) NOT NULL,
    payload_schema_artifact_kind text NOT NULL DEFAULT 'payload_schema'
        CHECK (payload_schema_artifact_kind = 'payload_schema'),
    payload_schema_sha256 char(64) NOT NULL,
    field_extraction_artifact_kind text NOT NULL DEFAULT 'field_extraction'
        CHECK (field_extraction_artifact_kind = 'field_extraction'),
    field_extraction_sha256 char(64) NOT NULL,
    profile_implementation_key text NOT NULL
        CHECK (length(btrim(profile_implementation_key)) BETWEEN 1 AND 160),
    profile_implementation_digest char(64) NOT NULL
        CHECK (profile_implementation_digest ~ '^[0-9a-f]{64}$'),
    rubric_key text NOT NULL,
    rubric_version text NOT NULL,
    rubric_sha256 char(64) NOT NULL,
    protocol_key text NOT NULL,
    protocol_version text NOT NULL,
    protocol_sha256 char(64) NOT NULL,
    pii_policy_kind text NOT NULL DEFAULT 'pii' CHECK (pii_policy_kind = 'pii'),
    pii_policy_key text NOT NULL,
    pii_policy_version text NOT NULL,
    pii_policy_sha256 char(64) NOT NULL,
    dedup_policy_kind text NOT NULL DEFAULT 'dedup'
        CHECK (dedup_policy_kind = 'dedup'),
    dedup_policy_key text NOT NULL,
    dedup_policy_version text NOT NULL,
    dedup_policy_sha256 char(64) NOT NULL,
    leakage_policy_kind text NOT NULL DEFAULT 'leakage'
        CHECK (leakage_policy_kind = 'leakage'),
    leakage_policy_key text NOT NULL,
    leakage_policy_version text NOT NULL,
    leakage_policy_sha256 char(64) NOT NULL,
    purpose_contract_version text NOT NULL,
    purpose_contract_artifact_kind text NOT NULL DEFAULT 'contract_bundle'
        CHECK (purpose_contract_artifact_kind = 'contract_bundle'),
    purpose_contract_sha256 char(64) NOT NULL,
    export_contract_key text NOT NULL,
    export_contract_version text NOT NULL,
    export_contract_sha256 char(64) NOT NULL,
    review_campaign_id uuid REFERENCES review_campaigns(id) ON DELETE RESTRICT,
    review_evidence_status text NOT NULL CHECK (
        review_evidence_status IN ('campaign_pinned', 'absent_pre_registry')
    ),
    implementation_bundle_sha256 char(64) NOT NULL
        CHECK (implementation_bundle_sha256 ~ '^[0-9a-f]{64}$'),
    snapshotted_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (release_id, source_id),
    CONSTRAINT release_source_snapshots_provenance_hashes CHECK (
        lineage_ref_sha256 ~ '^[0-9a-f]{64}$'
        AND (license_evidence_ref_sha256 IS NULL
             OR license_evidence_ref_sha256 ~ '^[0-9a-f]{64}$')
        AND (
            (production_run_id IS NULL
             AND production_run_implementation_digest IS NULL
             AND production_run_config_sha256 IS NULL
             AND production_run_input_manifest_sha256 IS NULL)
            OR (production_run_id IS NOT NULL
                AND production_run_implementation_digest ~ '^[0-9a-f]{64}$'
                AND (production_run_config_sha256 IS NULL
                     OR production_run_config_sha256 ~ '^[0-9a-f]{64}$')
                AND (production_run_input_manifest_sha256 IS NULL
                     OR production_run_input_manifest_sha256 ~ '^[0-9a-f]{64}$'))
        )
    ),
    CONSTRAINT release_source_snapshots_review_evidence_shape CHECK (
        (review_evidence_status = 'campaign_pinned' AND review_campaign_id IS NOT NULL)
        OR (review_evidence_status = 'absent_pre_registry' AND review_campaign_id IS NULL)
    ),
    FOREIGN KEY (release_id, source_id)
        REFERENCES release_sources(release_id, source_id) ON DELETE RESTRICT,
    FOREIGN KEY (data_profile_key, data_profile_version, content_purpose)
        REFERENCES data_profile_purposes(
            data_profile_key, data_profile_version, content_purpose
        ) ON DELETE RESTRICT,
    FOREIGN KEY (profile_config_artifact_kind, profile_config_sha256)
        REFERENCES contract_spec_artifacts(artifact_kind, sha256)
        ON DELETE RESTRICT,
    FOREIGN KEY (
        profile_config_schema_artifact_kind, profile_config_schema_sha256
    ) REFERENCES contract_spec_artifacts(artifact_kind, sha256)
        ON DELETE RESTRICT,
    FOREIGN KEY (payload_schema_artifact_kind, payload_schema_sha256)
        REFERENCES contract_spec_artifacts(artifact_kind, sha256)
        ON DELETE RESTRICT,
    FOREIGN KEY (field_extraction_artifact_kind, field_extraction_sha256)
        REFERENCES contract_spec_artifacts(artifact_kind, sha256)
        ON DELETE RESTRICT,
    FOREIGN KEY (rubric_key, rubric_version, rubric_sha256)
        REFERENCES review_rubric_versions(
            rubric_key, rubric_version, spec_sha256
        ) ON DELETE RESTRICT,
    FOREIGN KEY (protocol_key, protocol_version, protocol_sha256)
        REFERENCES review_protocol_versions(
            protocol_key, protocol_version, spec_sha256
        ) ON DELETE RESTRICT,
    FOREIGN KEY (
        pii_policy_kind, pii_policy_key, pii_policy_version, pii_policy_sha256
    ) REFERENCES data_policy_versions(
        policy_kind, policy_key, policy_version, spec_sha256
    ) ON DELETE RESTRICT,
    FOREIGN KEY (
        dedup_policy_kind, dedup_policy_key, dedup_policy_version,
        dedup_policy_sha256
    ) REFERENCES data_policy_versions(
        policy_kind, policy_key, policy_version, spec_sha256
    ) ON DELETE RESTRICT,
    FOREIGN KEY (
        leakage_policy_kind, leakage_policy_key, leakage_policy_version,
        leakage_policy_sha256
    ) REFERENCES data_policy_versions(
        policy_kind, policy_key, policy_version, spec_sha256
    ) ON DELETE RESTRICT,
    FOREIGN KEY (
        data_profile_key, data_profile_version, content_purpose,
        purpose_contract_version, purpose_contract_sha256
    ) REFERENCES profile_purpose_contract_versions(
        data_profile_key, data_profile_version, content_purpose,
        purpose_contract_version, spec_sha256
    ) ON DELETE RESTRICT,
    FOREIGN KEY (purpose_contract_artifact_kind, purpose_contract_sha256)
        REFERENCES contract_spec_artifacts(artifact_kind, sha256)
        ON DELETE RESTRICT,
    FOREIGN KEY (
        export_contract_key, export_contract_version, export_contract_sha256
    ) REFERENCES export_contract_versions(
        export_contract_key, export_contract_version, spec_sha256
    ) ON DELETE RESTRICT
);

CREATE OR REPLACE FUNCTION validate_release_source_snapshot_fresh(
    target_schema text,
    target_release_id uuid,
    target_source_id uuid
)
RETURNS void
LANGUAGE plpgsql
SET search_path FROM CURRENT
AS $$
DECLARE
    source_row record;
    release_source_row record;
    snapshot_row record;
    current_license_sha char(64);
    current_lineage_sha char(64);
BEGIN
    SELECT data_profile_key, data_profile_version, content_purpose,
           profile_config_artifact_kind, profile_config_sha256,
           data_origin, production_run_id, derived_from_source_id,
           license_evidence_ref, lineage_ref, object_sha256, version, name,
           source_type, license, rights_status, language, domain,
           byte_size, line_count, approval_status, pii_status,
           duplicate_status, normalized_dedup_status,
           document_sampling_status, document_sample_generation,
           document_sampling_method, sampled_document_count,
           reviewed_document_count, approved_document_count,
           flagged_document_count
    INTO source_row
    FROM sources
    WHERE id = target_source_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'release snapshot source does not exist';
    END IF;

    SELECT source_sha256, source_version, source_name, source_type, license,
           rights_status, language, domain, lineage_ref, byte_size, line_count
    INTO release_source_row
    FROM release_sources
    WHERE release_id = target_release_id AND source_id = target_source_id
    FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'release snapshot has no release source';
    END IF;

    SELECT data_profile_key, data_profile_version, content_purpose,
           profile_config_artifact_kind, profile_config_sha256,
           data_origin, production_run_id, derived_from_source_id,
           license_evidence_ref_sha256, lineage_ref_sha256,
           sample_generation, sample_source_sha256, sample_sampling_method,
           sample_count
    INTO snapshot_row
    FROM release_source_contract_snapshots
    WHERE release_id = target_release_id AND source_id = target_source_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'release source contract snapshot does not exist';
    END IF;

    IF source_row.object_sha256 IS NULL
       OR source_row.approval_status <> 'approved_source'
       OR source_row.rights_status <> 'cleared'
       OR source_row.license_evidence_ref IS NULL
       OR length(btrim(source_row.license_evidence_ref)) = 0
       OR source_row.pii_status <> 'clear'
       OR source_row.duplicate_status <> 'unique'
       OR source_row.normalized_dedup_status <> 'unique'
       OR source_row.document_sampling_status <> 'sampled'
       OR source_row.sampled_document_count <= 0
       OR source_row.reviewed_document_count IS DISTINCT FROM
          source_row.sampled_document_count
       OR source_row.approved_document_count IS DISTINCT FROM
          source_row.sampled_document_count
       OR source_row.flagged_document_count <> 0
       OR source_row.sampled_document_count IS DISTINCT FROM
          snapshot_row.sample_count::bigint THEN
        RAISE EXCEPTION 'release source is not eligible';
    END IF;

    IF release_source_row.source_sha256 IS DISTINCT FROM source_row.object_sha256
       OR release_source_row.source_version IS DISTINCT FROM source_row.version
       OR release_source_row.source_name IS DISTINCT FROM source_row.name
       OR release_source_row.source_type IS DISTINCT FROM source_row.source_type
       OR release_source_row.license IS DISTINCT FROM source_row.license
       OR release_source_row.rights_status IS DISTINCT FROM source_row.rights_status
       OR release_source_row.language IS DISTINCT FROM source_row.language
       OR release_source_row.domain IS DISTINCT FROM source_row.domain
       OR release_source_row.lineage_ref IS DISTINCT FROM source_row.lineage_ref
       OR release_source_row.byte_size IS DISTINCT FROM source_row.byte_size
       OR release_source_row.line_count IS DISTINCT FROM source_row.line_count THEN
        RAISE EXCEPTION 'release source snapshot does not match current source';
    END IF;

    current_lineage_sha := contract_spec_artifact_sha256(
        convert_to(source_row.lineage_ref, 'UTF8')
    );
    current_license_sha := contract_spec_artifact_sha256(
        convert_to(source_row.license_evidence_ref, 'UTF8')
    );
    IF snapshot_row.data_profile_key IS DISTINCT FROM source_row.data_profile_key
       OR snapshot_row.data_profile_version IS DISTINCT FROM source_row.data_profile_version
       OR snapshot_row.content_purpose IS DISTINCT FROM source_row.content_purpose
       OR snapshot_row.profile_config_artifact_kind IS DISTINCT FROM
          source_row.profile_config_artifact_kind
       OR snapshot_row.profile_config_sha256 IS DISTINCT FROM
          source_row.profile_config_sha256
       OR snapshot_row.data_origin IS DISTINCT FROM source_row.data_origin
       OR snapshot_row.production_run_id IS DISTINCT FROM source_row.production_run_id
       OR snapshot_row.derived_from_source_id IS DISTINCT FROM
          source_row.derived_from_source_id
       OR snapshot_row.license_evidence_ref_sha256 IS DISTINCT FROM current_license_sha
       OR snapshot_row.lineage_ref_sha256 IS DISTINCT FROM current_lineage_sha
       OR snapshot_row.sample_generation IS DISTINCT FROM
          source_row.document_sample_generation
       OR snapshot_row.sample_source_sha256 IS DISTINCT FROM source_row.object_sha256
       OR snapshot_row.sample_sampling_method IS DISTINCT FROM
          source_row.document_sampling_method THEN
        RAISE EXCEPTION 'release contract snapshot source evidence is stale';
    END IF;

    PERFORM validate_source_production_provenance(
        target_schema, source_row.data_origin, source_row.production_run_id
    );
END;
$$;

CREATE OR REPLACE FUNCTION validate_release_source_contract_snapshot()
RETURNS trigger
LANGUAGE plpgsql
SET search_path FROM CURRENT
AS $$
DECLARE
    release_purpose text;
    release_status text;
    source_row record;
    release_source_row record;
    profile_row record;
    contract_row record;
    campaign_row record;
    generation_row record;
    membership_evidence record;
    run_row record;
    derived_license_sha char(64);
    derived_lineage_sha char(64);
    expected_sample_generation integer;
    expected_sample_source_sha char(64);
    expected_sample_sampling_method text;
    expected_sample_count integer;
    expected_sample_job_id uuid;
    expected_membership_count integer;
    expected_membership_root_sha256 char(64);
BEGIN
    SELECT content_purpose, status INTO release_purpose, release_status
    FROM releases WHERE id = NEW.release_id
    FOR UPDATE;
    IF release_status IS DISTINCT FROM 'draft' THEN
        RAISE EXCEPTION 'contract snapshots can only be added to draft releases';
    END IF;
    IF release_purpose IS DISTINCT FROM NEW.content_purpose THEN
        RAISE EXCEPTION 'release contract snapshot purpose mismatch';
    END IF;

    SELECT data_profile_key, data_profile_version, content_purpose,
           profile_config_sha256, data_origin, production_run_id,
           derived_from_source_id, license_evidence_ref, lineage_ref,
           document_sample_generation, object_sha256, version, name,
           source_type, license, rights_status, language, domain,
           byte_size, line_count, approval_status, pii_status,
           duplicate_status, normalized_dedup_status,
           document_sampling_status, document_sampling_method,
           sampled_document_count, reviewed_document_count,
           approved_document_count, flagged_document_count
    INTO source_row
    FROM sources
    WHERE id = NEW.source_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'release contract snapshot source does not exist';
    END IF;
    IF source_row.data_profile_key IS DISTINCT FROM NEW.data_profile_key
       OR source_row.data_profile_version IS DISTINCT FROM NEW.data_profile_version
       OR source_row.content_purpose IS DISTINCT FROM NEW.content_purpose
       OR source_row.profile_config_sha256 IS DISTINCT FROM NEW.profile_config_sha256 THEN
        RAISE EXCEPTION 'release contract snapshot does not match source profile';
    END IF;
    IF source_row.object_sha256 IS NULL
       OR source_row.approval_status <> 'approved_source'
       OR source_row.rights_status <> 'cleared'
       OR source_row.license_evidence_ref IS NULL
       OR length(btrim(source_row.license_evidence_ref)) = 0
       OR source_row.pii_status <> 'clear'
       OR source_row.duplicate_status <> 'unique'
       OR source_row.normalized_dedup_status <> 'unique'
       OR source_row.document_sampling_status <> 'sampled'
       OR source_row.sampled_document_count <= 0
       OR source_row.reviewed_document_count IS DISTINCT FROM
          source_row.sampled_document_count
       OR source_row.approved_document_count IS DISTINCT FROM
          source_row.sampled_document_count
       OR source_row.flagged_document_count <> 0 THEN
        RAISE EXCEPTION 'release source is not eligible';
    END IF;

    SELECT source_sha256, source_version, source_name, source_type, license,
           rights_status, language, domain, lineage_ref, byte_size, line_count
    INTO release_source_row
    FROM release_sources
    WHERE release_id = NEW.release_id AND source_id = NEW.source_id
    FOR SHARE;
    IF NOT FOUND
       OR release_source_row.source_sha256 IS DISTINCT FROM source_row.object_sha256
       OR release_source_row.source_version IS DISTINCT FROM source_row.version
       OR release_source_row.source_name IS DISTINCT FROM source_row.name
       OR release_source_row.source_type IS DISTINCT FROM source_row.source_type
       OR release_source_row.license IS DISTINCT FROM source_row.license
       OR release_source_row.rights_status IS DISTINCT FROM source_row.rights_status
       OR release_source_row.language IS DISTINCT FROM source_row.language
       OR release_source_row.domain IS DISTINCT FROM source_row.domain
       OR release_source_row.lineage_ref IS DISTINCT FROM source_row.lineage_ref
       OR release_source_row.byte_size IS DISTINCT FROM source_row.byte_size
       OR release_source_row.line_count IS DISTINCT FROM source_row.line_count THEN
        RAISE EXCEPTION 'release source snapshot does not match current source';
    END IF;

    derived_lineage_sha := contract_spec_artifact_sha256(
        convert_to(source_row.lineage_ref, 'UTF8')
    );
    IF source_row.license_evidence_ref IS NULL THEN
        derived_license_sha := NULL;
    ELSE
        derived_license_sha := contract_spec_artifact_sha256(
            convert_to(source_row.license_evidence_ref, 'UTF8')
        );
    END IF;

    IF (NEW.data_origin IS NOT NULL
        AND NEW.data_origin IS DISTINCT FROM source_row.data_origin)
       OR (NEW.production_run_id IS NOT NULL
           AND NEW.production_run_id IS DISTINCT FROM source_row.production_run_id)
       OR (NEW.derived_from_source_id IS NOT NULL
           AND NEW.derived_from_source_id IS DISTINCT FROM source_row.derived_from_source_id)
       OR (NEW.license_evidence_ref_sha256 IS NOT NULL
           AND NEW.license_evidence_ref_sha256 IS DISTINCT FROM derived_license_sha)
       OR (NEW.lineage_ref_sha256 IS NOT NULL
           AND NEW.lineage_ref_sha256 IS DISTINCT FROM derived_lineage_sha) THEN
        RAISE EXCEPTION 'release contract snapshot provenance does not match source';
    END IF;
    NEW.data_origin := source_row.data_origin;
    NEW.production_run_id := source_row.production_run_id;
    NEW.derived_from_source_id := source_row.derived_from_source_id;
    NEW.license_evidence_ref_sha256 := derived_license_sha;
    NEW.lineage_ref_sha256 := derived_lineage_sha;

    IF source_row.production_run_id IS NULL THEN
        IF NEW.production_run_implementation_digest IS NOT NULL
           OR NEW.production_run_config_sha256 IS NOT NULL
           OR NEW.production_run_input_manifest_sha256 IS NOT NULL THEN
            RAISE EXCEPTION 'release contract snapshot has production run evidence without a run';
        END IF;
        NEW.production_run_implementation_digest := NULL;
        NEW.production_run_config_sha256 := NULL;
        NEW.production_run_input_manifest_sha256 := NULL;
    ELSE
        SELECT origin_kind, run_kind, implementation_digest,
               config_sha256, input_manifest_sha256
        INTO run_row
        FROM production_runs
        WHERE id = source_row.production_run_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'release contract snapshot production run does not exist';
        END IF;
        IF run_row.origin_kind = 'system' THEN
            IF source_row.data_origin <> 'unknown' OR run_row.run_kind <> 'import' THEN
                RAISE EXCEPTION 'release contract snapshot source/run provenance mismatch';
            END IF;
        ELSIF run_row.origin_kind IS DISTINCT FROM source_row.data_origin
           OR (source_row.data_origin = 'human'
               AND run_row.run_kind <> 'human_authored')
           OR (source_row.data_origin = 'model'
               AND run_row.run_kind <> 'model_generation')
           OR (source_row.data_origin = 'hybrid'
               AND run_row.run_kind <> 'hybrid_generation') THEN
            RAISE EXCEPTION 'release contract snapshot source/run provenance mismatch';
        END IF;
        IF (NEW.production_run_implementation_digest IS NOT NULL
            AND NEW.production_run_implementation_digest IS DISTINCT FROM
                run_row.implementation_digest)
           OR (NEW.production_run_config_sha256 IS NOT NULL
               AND NEW.production_run_config_sha256 IS DISTINCT FROM
                   run_row.config_sha256)
           OR (NEW.production_run_input_manifest_sha256 IS NOT NULL
               AND NEW.production_run_input_manifest_sha256 IS DISTINCT FROM
                   run_row.input_manifest_sha256) THEN
            RAISE EXCEPTION 'release contract snapshot production run evidence mismatch';
        END IF;
        NEW.production_run_implementation_digest := run_row.implementation_digest;
        NEW.production_run_config_sha256 := run_row.config_sha256;
        NEW.production_run_input_manifest_sha256 := run_row.input_manifest_sha256;
    END IF;

    IF NEW.review_campaign_id IS NOT NULL THEN
        SELECT source_id, data_profile_key, data_profile_version,
               content_purpose, purpose_contract_version,
               sample_generation, sample_source_sha256,
               sample_sampling_method, sample_count, sample_job_id,
               sample_membership_count, sample_membership_root_sha256
        INTO campaign_row
        FROM review_campaigns
        WHERE id = NEW.review_campaign_id;
        IF NOT FOUND
           OR campaign_row.source_id IS DISTINCT FROM NEW.source_id
           OR campaign_row.data_profile_key IS DISTINCT FROM NEW.data_profile_key
           OR campaign_row.data_profile_version IS DISTINCT FROM NEW.data_profile_version
           OR campaign_row.content_purpose IS DISTINCT FROM NEW.content_purpose
           OR campaign_row.purpose_contract_version IS DISTINCT FROM
              NEW.purpose_contract_version THEN
            RAISE EXCEPTION 'release contract snapshot campaign mismatch';
        END IF;
        expected_sample_generation := campaign_row.sample_generation;
        expected_sample_source_sha := campaign_row.sample_source_sha256;
        expected_sample_sampling_method := campaign_row.sample_sampling_method;
        expected_sample_count := campaign_row.sample_count;
        expected_sample_job_id := campaign_row.sample_job_id;
        expected_membership_count := campaign_row.sample_membership_count;
        expected_membership_root_sha256 :=
            campaign_row.sample_membership_root_sha256;
        SELECT source_sha256, sampling_method, sample_count, job_id, status
        INTO generation_row
        FROM document_sample_generations
        WHERE source_id = NEW.source_id
          AND generation = expected_sample_generation
        FOR SHARE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'release contract snapshot campaign generation does not exist';
        END IF;
    ELSE
        expected_sample_generation := source_row.document_sample_generation;
        SELECT source_sha256, sampling_method, sample_count, job_id, status
        INTO generation_row
        FROM document_sample_generations
        WHERE source_id = NEW.source_id
          AND generation = expected_sample_generation
        FOR SHARE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'release contract snapshot sample generation does not exist';
        END IF;
        expected_sample_source_sha := generation_row.source_sha256;
        expected_sample_sampling_method := generation_row.sampling_method;
        expected_sample_count := generation_row.sample_count;
        expected_sample_job_id := generation_row.job_id;
    END IF;

    IF expected_sample_generation IS DISTINCT FROM source_row.document_sample_generation
       OR generation_row.status <> 'active'
       OR generation_row.source_sha256 IS DISTINCT FROM source_row.object_sha256
       OR expected_sample_source_sha IS DISTINCT FROM generation_row.source_sha256
       OR expected_sample_sampling_method IS DISTINCT FROM generation_row.sampling_method
       OR expected_sample_count IS DISTINCT FROM generation_row.sample_count
       OR source_row.sampled_document_count IS DISTINCT FROM
          expected_sample_count::bigint
       OR source_row.document_sampling_method IS DISTINCT FROM
          expected_sample_sampling_method
       OR expected_sample_job_id IS DISTINCT FROM generation_row.job_id THEN
        RAISE EXCEPTION 'release contract snapshot sample generation is not current';
    END IF;
    SELECT * INTO membership_evidence
    FROM derive_document_sample_membership_evidence(
        NEW.source_id, expected_sample_generation
    );
    IF membership_evidence.membership_count IS DISTINCT FROM
           generation_row.sample_count THEN
        RAISE EXCEPTION 'release contract snapshot membership count does not match generation';
    END IF;
    IF NEW.review_campaign_id IS NULL THEN
        expected_membership_count := membership_evidence.membership_count;
        expected_membership_root_sha256 :=
            membership_evidence.membership_root_sha256;
    END IF;
    IF expected_membership_count IS DISTINCT FROM membership_evidence.membership_count
       OR expected_membership_root_sha256 IS DISTINCT FROM
           membership_evidence.membership_root_sha256 THEN
        RAISE EXCEPTION 'release contract snapshot campaign membership evidence is stale';
    END IF;
    IF (NEW.sample_membership_count IS NOT NULL
        AND NEW.sample_membership_count IS DISTINCT FROM expected_membership_count)
       OR (NEW.sample_membership_root_sha256 IS NOT NULL
           AND NEW.sample_membership_root_sha256 IS DISTINCT FROM
               expected_membership_root_sha256) THEN
        RAISE EXCEPTION 'release contract snapshot membership evidence mismatch';
    END IF;

    IF (NEW.sample_generation IS NOT NULL
        AND NEW.sample_generation IS DISTINCT FROM expected_sample_generation)
       OR (NEW.sample_source_sha256 IS NOT NULL
           AND NEW.sample_source_sha256 IS DISTINCT FROM expected_sample_source_sha)
       OR (NEW.sample_sampling_method IS NOT NULL
           AND NEW.sample_sampling_method IS DISTINCT FROM expected_sample_sampling_method)
       OR (NEW.sample_count IS NOT NULL
           AND NEW.sample_count IS DISTINCT FROM expected_sample_count)
       OR (NEW.sample_job_id IS NOT NULL
           AND NEW.sample_job_id IS DISTINCT FROM expected_sample_job_id) THEN
        RAISE EXCEPTION 'release contract snapshot sample pins do not match evidence generation';
    END IF;
    NEW.sample_generation := expected_sample_generation;
    NEW.sample_source_sha256 := expected_sample_source_sha;
    NEW.sample_sampling_method := expected_sample_sampling_method;
    NEW.sample_count := expected_sample_count;
    NEW.sample_job_id := expected_sample_job_id;
    NEW.sample_membership_count := expected_membership_count;
    NEW.sample_membership_root_sha256 := expected_membership_root_sha256;

    SELECT profile_config_schema_artifact_kind,
           profile_config_schema_sha256,
           payload_schema_sha256, field_extraction_sha256,
           implementation_key, implementation_digest,
           rubric_key, rubric_version, export_contract_key,
           export_contract_version
    INTO profile_row
    FROM data_profile_versions
    WHERE data_profile_key = NEW.data_profile_key
      AND data_profile_version = NEW.data_profile_version;
    IF (NEW.profile_config_schema_artifact_kind IS NOT NULL
        AND NEW.profile_config_schema_artifact_kind IS DISTINCT FROM
            profile_row.profile_config_schema_artifact_kind)
       OR (NEW.profile_config_schema_sha256 IS NOT NULL
           AND NEW.profile_config_schema_sha256 IS DISTINCT FROM
               profile_row.profile_config_schema_sha256)
       OR profile_row.payload_schema_sha256 IS DISTINCT FROM NEW.payload_schema_sha256
       OR profile_row.field_extraction_sha256 IS DISTINCT FROM NEW.field_extraction_sha256
       OR (NEW.profile_implementation_key IS NOT NULL
           AND NEW.profile_implementation_key IS DISTINCT FROM
               profile_row.implementation_key)
       OR (NEW.profile_implementation_digest IS NOT NULL
           AND NEW.profile_implementation_digest IS DISTINCT FROM
               profile_row.implementation_digest)
       OR profile_row.rubric_key IS DISTINCT FROM NEW.rubric_key
       OR profile_row.rubric_version IS DISTINCT FROM NEW.rubric_version
       OR profile_row.export_contract_key IS DISTINCT FROM NEW.export_contract_key
       OR profile_row.export_contract_version IS DISTINCT FROM NEW.export_contract_version THEN
        RAISE EXCEPTION 'release contract snapshot does not match data profile';
    END IF;
    NEW.profile_config_schema_artifact_kind :=
        profile_row.profile_config_schema_artifact_kind;
    NEW.profile_config_schema_sha256 := profile_row.profile_config_schema_sha256;
    NEW.profile_implementation_key := profile_row.implementation_key;
    NEW.profile_implementation_digest := profile_row.implementation_digest;

    SELECT protocol_key, protocol_version,
           pii_policy_key, pii_policy_version,
           dedup_policy_key, dedup_policy_version,
           leakage_policy_key, leakage_policy_version,
           implementation_bundle_sha256
    INTO contract_row
    FROM profile_purpose_contract_versions
    WHERE data_profile_key = NEW.data_profile_key
      AND data_profile_version = NEW.data_profile_version
      AND content_purpose = NEW.content_purpose
      AND purpose_contract_version = NEW.purpose_contract_version;
    IF contract_row.protocol_key IS DISTINCT FROM NEW.protocol_key
       OR contract_row.protocol_version IS DISTINCT FROM NEW.protocol_version
       OR contract_row.pii_policy_key IS DISTINCT FROM NEW.pii_policy_key
       OR contract_row.pii_policy_version IS DISTINCT FROM NEW.pii_policy_version
       OR contract_row.dedup_policy_key IS DISTINCT FROM NEW.dedup_policy_key
       OR contract_row.dedup_policy_version IS DISTINCT FROM NEW.dedup_policy_version
       OR contract_row.leakage_policy_key IS DISTINCT FROM NEW.leakage_policy_key
       OR contract_row.leakage_policy_version IS DISTINCT FROM NEW.leakage_policy_version
       OR contract_row.implementation_bundle_sha256 IS DISTINCT FROM
          NEW.implementation_bundle_sha256 THEN
        RAISE EXCEPTION 'release contract snapshot does not match purpose contract';
    END IF;

    PERFORM validate_release_review_evidence(
        NEW.source_id, NEW.review_evidence_status, NEW.review_campaign_id
    );
    RETURN NEW;
END;
$$;

CREATE TRIGGER release_source_contract_snapshots_validate
BEFORE INSERT ON release_source_contract_snapshots
FOR EACH ROW EXECUTE FUNCTION validate_release_source_contract_snapshot();
CREATE TRIGGER release_source_contract_snapshots_no_update
BEFORE UPDATE ON release_source_contract_snapshots FOR EACH ROW
EXECUTE FUNCTION reject_versioned_contract_mutation();
CREATE TRIGGER release_source_contract_snapshots_no_delete
BEFORE DELETE ON release_source_contract_snapshots FOR EACH ROW
EXECUTE FUNCTION reject_versioned_contract_mutation();
CREATE TRIGGER release_source_contract_snapshots_no_truncate
BEFORE TRUNCATE ON release_source_contract_snapshots FOR EACH STATEMENT
EXECUTE FUNCTION reject_versioned_contract_mutation();
CREATE TRIGGER release_source_contract_snapshots_capture_row_change
AFTER INSERT OR UPDATE OR DELETE ON release_source_contract_snapshots
FOR EACH ROW EXECUTE FUNCTION capture_row_change_event('release_id', 'source_id');

-- Future migrations may add authoritative timestamptz evidence to a child
-- snapshot. Normalize known timestamp pins under UTC before hashing so the
-- same row produces the same child digest under every session TimeZone.
CREATE OR REPLACE FUNCTION canonical_release_source_snapshot_json(
    row_data jsonb
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog
SET TimeZone = 'UTC'
SET DateStyle = 'ISO, YMD'
AS $$
DECLARE
    normalized jsonb;
BEGIN
    normalized := row_data - 'snapshotted_at';
    IF normalized ? 'production_run_completed_at'
       AND normalized->'production_run_completed_at' <> 'null'::jsonb THEN
        normalized := jsonb_set(
            normalized,
            '{production_run_completed_at}',
            to_jsonb((normalized->>'production_run_completed_at')::timestamptz)
        );
    END IF;
    RETURN normalized;
END;
$$;

CREATE OR REPLACE FUNCTION validate_release_contract_snapshot_transition()
RETURNS trigger
LANGUAGE plpgsql
SET search_path FROM CURRENT
AS $$
DECLARE
    source_count bigint;
    snapshot_count bigint;
    child_digest_material text;
    implementation_digest_material text;
    implementation_bytes bytea;
    bundle_bytes bytea;
    child_root_sha char(64);
    derived_implementation_sha char(64);
    derived_bundle_sha char(64);
    evidence_row record;
    membership_evidence record;
    requires_full_revalidation boolean;
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status IS DISTINCT FROM 'draft'
           OR NEW.contract_snapshot_status IS DISTINCT FROM 'pending'
           OR NEW.contract_snapshot_artifact_kind IS NOT NULL
           OR NEW.contract_snapshot_sha256 IS NOT NULL
           OR NEW.implementation_bundle_sha256 IS NOT NULL THEN
            RAISE EXCEPTION 'new releases must begin as draft with a pending empty contract snapshot';
        END IF;
        RETURN NEW;
    END IF;

    IF OLD.contract_snapshot_status <> 'pending'
       AND (
           NEW.contract_snapshot_status IS DISTINCT FROM OLD.contract_snapshot_status
           OR NEW.content_purpose IS DISTINCT FROM OLD.content_purpose
           OR NEW.contract_snapshot_artifact_kind IS DISTINCT FROM
              OLD.contract_snapshot_artifact_kind
           OR NEW.contract_snapshot_sha256 IS DISTINCT FROM OLD.contract_snapshot_sha256
           OR NEW.implementation_bundle_sha256 IS DISTINCT FROM
              OLD.implementation_bundle_sha256
       ) THEN
        RAISE EXCEPTION 'release contract snapshot identity is immutable';
    END IF;

    IF NEW.contract_snapshot_status = 'absent_pre_registry'
       AND OLD.contract_snapshot_status IS DISTINCT FROM 'absent_pre_registry' THEN
        RAISE EXCEPTION 'absent_pre_registry is reserved for migration evidence';
    END IF;

    IF NEW.status = 'frozen' AND OLD.status IS DISTINCT FROM 'frozen'
       AND NEW.contract_snapshot_status <> 'present' THEN
        RAISE EXCEPTION 'new frozen releases require a present contract snapshot';
    END IF;

    -- A failed freeze worker must be able to persist gate_results while the
    -- release remains draft/present. Re-run the fail-closed evidence walk only
    -- at the two security boundaries that can make evidence authoritative.
    requires_full_revalidation := (
        OLD.contract_snapshot_status = 'pending'
        AND NEW.contract_snapshot_status = 'present'
    ) OR (
        OLD.status = 'draft'
        AND NEW.status = 'frozen'
    );

    IF requires_full_revalidation THEN
        SELECT count(*) INTO source_count
        FROM release_sources WHERE release_id = NEW.id;
        SELECT count(*) INTO snapshot_count
        FROM release_source_contract_snapshots WHERE release_id = NEW.id;
        IF source_count = 0 OR snapshot_count <> source_count THEN
            RAISE EXCEPTION
                'release contract snapshot incomplete: sources %, snapshots %',
                source_count, snapshot_count;
        END IF;
        FOR evidence_row IN
            SELECT source_id, content_purpose, sample_generation,
                   sample_membership_count, sample_membership_root_sha256,
                   review_evidence_status, review_campaign_id
            FROM release_source_contract_snapshots
            WHERE release_id = NEW.id
            ORDER BY source_id
        LOOP
            IF evidence_row.content_purpose IS DISTINCT FROM NEW.content_purpose THEN
                RAISE EXCEPTION 'release contract snapshot child purpose mismatch';
            END IF;
            PERFORM validate_release_source_snapshot_fresh(
                TG_TABLE_SCHEMA, NEW.id, evidence_row.source_id
            );
            SELECT * INTO membership_evidence
            FROM derive_document_sample_membership_evidence(
                evidence_row.source_id, evidence_row.sample_generation
            );
            IF membership_evidence.membership_count IS DISTINCT FROM
                   evidence_row.sample_membership_count
               OR membership_evidence.membership_root_sha256 IS DISTINCT FROM
                   evidence_row.sample_membership_root_sha256 THEN
                RAISE EXCEPTION 'release contract snapshot membership evidence is stale';
            END IF;
            PERFORM validate_release_review_evidence(
                evidence_row.source_id,
                evidence_row.review_evidence_status,
                evidence_row.review_campaign_id
            );
        END LOOP;

        -- postgres-jsonb-text-v1 is an explicit PostgreSQL jsonb text
        -- serialization contract, not a JCS claim. Each child is first reduced
        -- to a fixed-size SHA-256 digest. The top artifact therefore stays
        -- bounded regardless of release source count and never embeds raw
        -- content, configuration bytes, paths, or URLs.
        SELECT
            string_agg(
                btrim(contract_spec_artifact_sha256(convert_to(
                    canonical_release_source_snapshot_json(
                        to_jsonb(snapshot)
                    )::text, 'UTF8'
                ))::text), '' ORDER BY snapshot.source_id
            ),
            string_agg(
                btrim(contract_spec_artifact_sha256(convert_to(
                    jsonb_build_object(
                        'source_id', snapshot.source_id,
                        'profile_implementation_key',
                            snapshot.profile_implementation_key,
                        'profile_implementation_digest',
                            snapshot.profile_implementation_digest,
                        'purpose_implementation_bundle_sha256',
                            snapshot.implementation_bundle_sha256
                    )::text,
                    'UTF8'
                ))::text),
                '' ORDER BY snapshot.source_id
            )
        INTO child_digest_material, implementation_digest_material
        FROM release_source_contract_snapshots AS snapshot
        WHERE snapshot.release_id = NEW.id;

        child_root_sha := contract_spec_artifact_sha256(
            convert_to(child_digest_material, 'UTF8')
        );

        implementation_bytes := convert_to(
            implementation_digest_material, 'UTF8'
        );
        derived_implementation_sha :=
            contract_spec_artifact_sha256(implementation_bytes);
        IF NEW.implementation_bundle_sha256 IS NOT NULL
           AND NEW.implementation_bundle_sha256 IS DISTINCT FROM
               derived_implementation_sha THEN
            RAISE EXCEPTION 'release implementation bundle sha256 does not match child snapshots';
        END IF;
        NEW.implementation_bundle_sha256 := derived_implementation_sha;

        bundle_bytes := convert_to(jsonb_build_object(
            'bundle_kind', 'release_contract_snapshot',
            'release_id', NEW.id,
            'content_purpose', NEW.content_purpose,
            'implementation_bundle_sha256', derived_implementation_sha,
            'source_count', source_count,
            'child_snapshot_root_sha256', child_root_sha
        )::text, 'UTF8');
        derived_bundle_sha := contract_spec_artifact_sha256(bundle_bytes);
        IF NEW.contract_snapshot_sha256 IS NOT NULL
           AND NEW.contract_snapshot_sha256 IS DISTINCT FROM derived_bundle_sha THEN
            RAISE EXCEPTION 'release contract snapshot sha256 does not match child snapshots';
        END IF;
        IF NEW.contract_snapshot_artifact_kind IS NOT NULL
           AND NEW.contract_snapshot_artifact_kind <> 'contract_bundle' THEN
            RAISE EXCEPTION 'release contract snapshot artifact kind must be contract_bundle';
        END IF;
        NEW.contract_snapshot_artifact_kind := 'contract_bundle';
        NEW.contract_snapshot_sha256 := derived_bundle_sha;
        INSERT INTO contract_spec_artifacts(
            sha256, artifact_kind, canonicalization_key, media_type,
            canonical_bytes, byte_size
        ) VALUES (
            derived_bundle_sha, 'contract_bundle', 'postgres-jsonb-text-v1',
            'application/json', bundle_bytes, octet_length(bundle_bytes)
        ) ON CONFLICT (sha256) DO NOTHING;
    END IF;
    RETURN NEW;
END;
$$;

-- Historical frozen releases retain absent_pre_registry evidence. Every new
-- freeze is fail-closed on a DB-derived present bundle and fresh review coverage.
CREATE TRIGGER releases_validate_contract_snapshot_transition
BEFORE INSERT OR UPDATE ON releases
FOR EACH ROW EXECUTE FUNCTION validate_release_contract_snapshot_transition();

REVOKE ALL ON FUNCTION contract_spec_artifact_sha256(bytea) FROM PUBLIC;
REVOKE ALL ON FUNCTION verify_contract_spec_artifact() FROM PUBLIC;
REVOKE ALL ON FUNCTION validate_source_production_provenance(text, text, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION validate_release_source_snapshot_fresh(text, uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION canonical_release_source_snapshot_json(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION row_change_safe_summary(text, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION row_change_safe_summary_v23(text, jsonb) FROM PUBLIC;
