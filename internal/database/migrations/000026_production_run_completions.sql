-- A production_runs row is immutable run intent: it pins the implementation,
-- configuration and input identity before execution.  Successful execution is
-- separate append-only evidence because the intent row must never be updated.
-- The legacy output/completed columns therefore cannot be used as an alternate
-- completion channel.

ALTER TABLE production_runs
    ADD CONSTRAINT production_runs_are_intent_only CHECK (
        output_manifest_sha256 IS NULL AND completed_at IS NULL
    );

COMMENT ON TABLE production_runs IS
    'Immutable production intent; successful output is recorded only in production_run_completions.';
COMMENT ON COLUMN production_runs.output_manifest_sha256 IS
    'Reserved legacy column; constrained NULL. See production_run_completions.';
COMMENT ON COLUMN production_runs.completed_at IS
    'Reserved legacy column; constrained NULL. See production_run_completions.';

CREATE TABLE production_run_completions (
    production_run_id uuid PRIMARY KEY
        REFERENCES production_runs(id) ON DELETE RESTRICT,
    job_id uuid NOT NULL UNIQUE
        REFERENCES background_jobs(id) ON DELETE RESTRICT,
    output_manifest_sha256 char(64) NOT NULL
        REFERENCES storage_objects(sha256) ON DELETE RESTRICT,
    output_sha256 char(64) NOT NULL
        REFERENCES storage_objects(sha256) ON DELETE RESTRICT
        CHECK (output_sha256 ~ '^[0-9a-f]{64}$'),
    output_byte_size bigint NOT NULL CHECK (output_byte_size > 0),
    output_record_count bigint NOT NULL CHECK (output_record_count > 0),
    completed_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT production_run_completions_manifest_sha256_format CHECK (
        output_manifest_sha256 ~ '^[0-9a-f]{64}$'
    ),
    UNIQUE (production_run_id, job_id)
);

COMMENT ON TABLE production_run_completions IS
    'Append-only, one-to-one proof that a model or hybrid production intent completed with exact output bytes.';

-- Resolve all evidence tables from the trigger relation's own schema.  The
-- function runs with pg_catalog-only search_path so pg_temp or attacker-owned
-- lookalike tables cannot satisfy completion validation.
CREATE OR REPLACE FUNCTION validate_production_run_completion()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    evidence_schema text;
    function_schema text;
    run_row record;
    job_row record;
    manifest_is_immutable boolean;
    output_is_immutable boolean;
    output_storage_byte_size bigint;
    result_manifest_sha text;
    result_manifest_alias_sha text;
    result_output_sha text;
    result_output_byte_size bigint;
    result_output_record_count bigint;
    result_output_record_alias_count bigint;
    matched_rows bigint;
BEGIN
    SELECT namespace.nspname
    INTO evidence_schema
    FROM pg_catalog.pg_class AS relation
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.oid = relation.relnamespace
    WHERE relation.oid = TG_RELID;

    SELECT function_namespace.nspname
    INTO function_schema
    FROM pg_catalog.pg_trigger AS trigger_def
    JOIN pg_catalog.pg_proc AS function_def
      ON function_def.oid = trigger_def.tgfoid
    JOIN pg_catalog.pg_namespace AS function_namespace
      ON function_namespace.oid = function_def.pronamespace
    WHERE trigger_def.tgrelid = TG_RELID
      AND trigger_def.tgname = TG_NAME
      AND NOT trigger_def.tgisinternal;

    IF evidence_schema IS NULL
       OR function_schema IS NULL
       OR function_schema IS DISTINCT FROM evidence_schema THEN
        RAISE EXCEPTION 'production completion validator schema mismatch';
    END IF;

    EXECUTE pg_catalog.format(
        'SELECT run_kind, origin_kind, recorded_at '
        'FROM %I.production_runs WHERE id = $1 FOR SHARE',
        evidence_schema
    )
    INTO run_row
    USING NEW.production_run_id;
    -- EXECUTE does not update PL/pgSQL FOUND, so use ROW_COUNT explicitly.
    GET DIAGNOSTICS matched_rows = ROW_COUNT;
    IF matched_rows <> 1 THEN
        RAISE EXCEPTION 'production completion run intent does not exist';
    END IF;
    IF (run_row.run_kind, run_row.origin_kind) NOT IN (
        ('model_generation', 'model'),
        ('hybrid_generation', 'hybrid')
    ) THEN
        RAISE EXCEPTION 'production completion requires model or hybrid generation intent';
    END IF;

    EXECUTE pg_catalog.format(
        'SELECT job_type, status, payload, result, completed_at '
        'FROM %I.background_jobs WHERE id = $1 FOR SHARE',
        evidence_schema
    )
    INTO job_row
    USING NEW.job_id;
    GET DIAGNOSTICS matched_rows = ROW_COUNT;
    IF matched_rows <> 1 THEN
        RAISE EXCEPTION 'production completion background job does not exist';
    END IF;
    IF job_row.job_type IS DISTINCT FROM 'distill_source'
       OR job_row.status IS DISTINCT FROM 'succeeded'
       OR job_row.completed_at IS NULL
       OR pg_catalog.jsonb_typeof(job_row.payload) IS DISTINCT FROM 'object'
       OR pg_catalog.jsonb_typeof(job_row.result) IS DISTINCT FROM 'object'
       OR job_row.payload->>'production_run_id' IS DISTINCT FROM
          NEW.production_run_id::text
       OR job_row.result->>'production_run_id' IS DISTINCT FROM
          NEW.production_run_id::text THEN
        RAISE EXCEPTION 'production completion job is not successful generation evidence';
    END IF;

    result_manifest_sha := job_row.result->>'output_manifest_sha256';
    result_manifest_alias_sha := job_row.result->>'manifest_sha256';
    IF result_manifest_sha IS NULL THEN
        result_manifest_sha := result_manifest_alias_sha;
    ELSIF result_manifest_alias_sha IS NOT NULL
          AND result_manifest_alias_sha IS DISTINCT FROM result_manifest_sha THEN
        RAISE EXCEPTION 'production completion job has ambiguous manifest evidence';
    END IF;
    result_output_sha := job_row.result->>'output_sha256';

    BEGIN
        result_output_byte_size := (job_row.result->>'output_byte_size')::bigint;
        result_output_record_count :=
            (job_row.result->>'output_record_count')::bigint;
        result_output_record_alias_count :=
            (job_row.result->>'document_count')::bigint;
    EXCEPTION
        WHEN invalid_text_representation OR numeric_value_out_of_range THEN
            RAISE EXCEPTION 'production completion job has invalid numeric evidence';
    END;
    IF result_output_record_count IS NULL THEN
        result_output_record_count := result_output_record_alias_count;
    ELSIF result_output_record_alias_count IS NOT NULL
          AND result_output_record_alias_count IS DISTINCT FROM
              result_output_record_count THEN
        RAISE EXCEPTION 'production completion job has ambiguous record-count evidence';
    END IF;

    IF result_manifest_sha IS DISTINCT FROM
          pg_catalog.btrim(NEW.output_manifest_sha256::text)
       OR result_output_sha IS DISTINCT FROM
          pg_catalog.btrim(NEW.output_sha256::text)
       OR result_output_byte_size IS DISTINCT FROM NEW.output_byte_size
       OR result_output_record_count IS DISTINCT FROM NEW.output_record_count THEN
        RAISE EXCEPTION 'production completion output does not match job result';
    END IF;

    IF NEW.completed_at IS NOT NULL
       AND NEW.completed_at IS DISTINCT FROM job_row.completed_at THEN
        RAISE EXCEPTION 'production completion timestamp does not match job result';
    END IF;
    IF job_row.completed_at < run_row.recorded_at THEN
        RAISE EXCEPTION 'production completion predates its run intent';
    END IF;
    NEW.completed_at := job_row.completed_at;

    EXECUTE pg_catalog.format(
        'SELECT immutable FROM %I.storage_objects WHERE sha256 = $1',
        evidence_schema
    )
    INTO manifest_is_immutable
    USING NEW.output_manifest_sha256;
    IF manifest_is_immutable IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'production completion manifest is not immutable';
    END IF;

    EXECUTE pg_catalog.format(
        'SELECT immutable, byte_size FROM %I.storage_objects WHERE sha256 = $1',
        evidence_schema
    )
    INTO output_is_immutable, output_storage_byte_size
    USING NEW.output_sha256;
    GET DIAGNOSTICS matched_rows = ROW_COUNT;
    -- Let the declarative FK report a missing CAS object.  When it exists,
    -- require its immutable metadata to agree with the claimed output size.
    IF matched_rows = 1 AND (
        output_is_immutable IS DISTINCT FROM true
        OR output_storage_byte_size IS DISTINCT FROM NEW.output_byte_size
    ) THEN
        RAISE EXCEPTION 'production completion output storage evidence does not match';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER production_run_completions_validate
BEFORE INSERT ON production_run_completions
FOR EACH ROW EXECUTE FUNCTION validate_production_run_completion();

CREATE OR REPLACE FUNCTION reject_production_run_completion_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'production_run_completions are append-only';
END;
$$;

CREATE TRIGGER production_run_completions_no_update
BEFORE UPDATE ON production_run_completions FOR EACH ROW
EXECUTE FUNCTION reject_production_run_completion_mutation();
CREATE TRIGGER production_run_completions_no_delete
BEFORE DELETE ON production_run_completions FOR EACH ROW
EXECUTE FUNCTION reject_production_run_completion_mutation();
CREATE TRIGGER production_run_completions_no_truncate
BEFORE TRUNCATE ON production_run_completions FOR EACH STATEMENT
EXECUTE FUNCTION reject_production_run_completion_mutation();

-- Once a job is referenced as canonical completion evidence, its semantic
-- identity and result cannot be rewritten behind the append-only completion.
CREATE OR REPLACE FUNCTION protect_completed_production_job()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    evidence_schema text;
    function_schema text;
    completion_exists boolean;
BEGIN
    SELECT namespace.nspname
    INTO evidence_schema
    FROM pg_catalog.pg_class AS relation
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.oid = relation.relnamespace
    WHERE relation.oid = TG_RELID;

    SELECT function_namespace.nspname
    INTO function_schema
    FROM pg_catalog.pg_trigger AS trigger_def
    JOIN pg_catalog.pg_proc AS function_def
      ON function_def.oid = trigger_def.tgfoid
    JOIN pg_catalog.pg_namespace AS function_namespace
      ON function_namespace.oid = function_def.pronamespace
    WHERE trigger_def.tgrelid = TG_RELID
      AND trigger_def.tgname = TG_NAME
      AND NOT trigger_def.tgisinternal;

    IF evidence_schema IS NULL
       OR function_schema IS NULL
       OR function_schema IS DISTINCT FROM evidence_schema THEN
        RAISE EXCEPTION 'completed production job protector schema mismatch';
    END IF;

    EXECUTE pg_catalog.format(
        'SELECT EXISTS ('
        'SELECT 1 FROM %I.production_run_completions WHERE job_id = $1)',
        evidence_schema
    )
    INTO completion_exists
    USING OLD.id;

    IF completion_exists AND (
        NEW.id IS DISTINCT FROM OLD.id
        OR NEW.job_type IS DISTINCT FROM OLD.job_type
        OR NEW.status IS DISTINCT FROM OLD.status
        OR NEW.payload IS DISTINCT FROM OLD.payload
        OR NEW.result IS DISTINCT FROM OLD.result
        OR NEW.created_by IS DISTINCT FROM OLD.created_by
        OR NEW.created_at IS DISTINCT FROM OLD.created_at
        OR NEW.completed_at IS DISTINCT FROM OLD.completed_at
    ) THEN
        RAISE EXCEPTION 'completed production job evidence is immutable';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER background_jobs_protect_completed_production_evidence
BEFORE UPDATE ON background_jobs FOR EACH ROW
EXECUTE FUNCTION protect_completed_production_job();

-- A release child must carry the exact successful-output evidence for every
-- model or hybrid source.  Human/imported sources carry no synthetic
-- completion fields.  The UTC timestamp is stored as canonical text so child
-- and top hashes cannot vary with a session TimeZone setting.
ALTER TABLE release_source_contract_snapshots
    ADD COLUMN production_run_completion_job_id uuid,
    ADD COLUMN production_run_output_manifest_sha256 char(64),
    ADD COLUMN production_run_output_sha256 char(64),
    ADD COLUMN production_run_output_byte_size bigint,
    ADD COLUMN production_run_output_record_count bigint,
    ADD COLUMN production_run_completed_at_utc text,
    ADD CONSTRAINT release_source_snapshots_completion_shape CHECK (
        (
            data_origin IN ('model', 'hybrid')
            AND production_run_id IS NOT NULL
            AND production_run_completion_job_id IS NOT NULL
            AND production_run_output_manifest_sha256 ~ '^[0-9a-f]{64}$'
            AND production_run_output_sha256 ~ '^[0-9a-f]{64}$'
            AND production_run_output_byte_size > 0
            AND production_run_output_record_count > 0
            AND production_run_completed_at_utc ~
                '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}[.][0-9]{6}Z$'
        ) OR (
            data_origin NOT IN ('model', 'hybrid')
            AND production_run_completion_job_id IS NULL
            AND production_run_output_manifest_sha256 IS NULL
            AND production_run_output_sha256 IS NULL
            AND production_run_output_byte_size IS NULL
            AND production_run_output_record_count IS NULL
            AND production_run_completed_at_utc IS NULL
        )
    ),
    ADD CONSTRAINT release_source_snapshots_completion_fkey
        FOREIGN KEY (
            production_run_id, production_run_completion_job_id
        ) REFERENCES production_run_completions(production_run_id, job_id)
        ON DELETE RESTRICT,
    ADD CONSTRAINT release_source_snapshots_completion_manifest_fkey
        FOREIGN KEY (production_run_output_manifest_sha256)
        REFERENCES storage_objects(sha256) ON DELETE RESTRICT,
    ADD CONSTRAINT release_source_snapshots_completion_output_fkey
        FOREIGN KEY (production_run_output_sha256)
        REFERENCES storage_objects(sha256) ON DELETE RESTRICT;

CREATE OR REPLACE FUNCTION pin_release_source_production_completion()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    evidence_schema text;
    function_schema text;
    source_row record;
    completion_row record;
    expected_completed_at_utc text;
    matched_rows bigint;
BEGIN
    SELECT namespace.nspname
    INTO evidence_schema
    FROM pg_catalog.pg_class AS relation
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.oid = relation.relnamespace
    WHERE relation.oid = TG_RELID;

    SELECT function_namespace.nspname
    INTO function_schema
    FROM pg_catalog.pg_trigger AS trigger_def
    JOIN pg_catalog.pg_proc AS function_def
      ON function_def.oid = trigger_def.tgfoid
    JOIN pg_catalog.pg_namespace AS function_namespace
      ON function_namespace.oid = function_def.pronamespace
    WHERE trigger_def.tgrelid = TG_RELID
      AND trigger_def.tgname = TG_NAME
      AND NOT trigger_def.tgisinternal;

    IF evidence_schema IS NULL
       OR function_schema IS NULL
       OR function_schema IS DISTINCT FROM evidence_schema THEN
        RAISE EXCEPTION 'release completion pin validator schema mismatch';
    END IF;

    EXECUTE pg_catalog.format(
        'SELECT data_origin, production_run_id, object_sha256, byte_size, line_count '
        'FROM %I.sources WHERE id = $1 FOR SHARE',
        evidence_schema
    )
    INTO source_row
    USING NEW.source_id;
    GET DIAGNOSTICS matched_rows = ROW_COUNT;
    IF matched_rows <> 1 THEN
        RAISE EXCEPTION 'release completion pin source does not exist';
    END IF;

    IF source_row.data_origin IN ('model', 'hybrid') THEN
        IF NEW.data_origin IS DISTINCT FROM source_row.data_origin
           OR NEW.production_run_id IS DISTINCT FROM source_row.production_run_id THEN
            RAISE EXCEPTION 'release completion pin source provenance mismatch';
        END IF;

        EXECUTE pg_catalog.format(
            'SELECT job_id, output_manifest_sha256, output_sha256, '
            'output_byte_size, output_record_count, completed_at '
            'FROM %I.production_run_completions '
            'WHERE production_run_id = $1 FOR SHARE',
            evidence_schema
        )
        INTO completion_row
        USING source_row.production_run_id;
        GET DIAGNOSTICS matched_rows = ROW_COUNT;
        IF matched_rows <> 1 THEN
            RAISE EXCEPTION 'model or hybrid release source requires production completion evidence';
        END IF;

        IF source_row.object_sha256 IS DISTINCT FROM completion_row.output_sha256
           OR source_row.byte_size IS DISTINCT FROM completion_row.output_byte_size
           OR source_row.line_count IS DISTINCT FROM
               completion_row.output_record_count THEN
            RAISE EXCEPTION 'release source identity does not match production completion output';
        END IF;

        expected_completed_at_utc := pg_catalog.to_char(
            completion_row.completed_at AT TIME ZONE 'UTC',
            'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
        );
        IF (NEW.production_run_completion_job_id IS NOT NULL
            AND NEW.production_run_completion_job_id IS DISTINCT FROM
                completion_row.job_id)
           OR (NEW.production_run_output_manifest_sha256 IS NOT NULL
               AND NEW.production_run_output_manifest_sha256 IS DISTINCT FROM
                   completion_row.output_manifest_sha256)
           OR (NEW.production_run_output_sha256 IS NOT NULL
               AND NEW.production_run_output_sha256 IS DISTINCT FROM
                   completion_row.output_sha256)
           OR (NEW.production_run_output_byte_size IS NOT NULL
               AND NEW.production_run_output_byte_size IS DISTINCT FROM
                   completion_row.output_byte_size)
           OR (NEW.production_run_output_record_count IS NOT NULL
               AND NEW.production_run_output_record_count IS DISTINCT FROM
                   completion_row.output_record_count)
           OR (NEW.production_run_completed_at_utc IS NOT NULL
               AND NEW.production_run_completed_at_utc IS DISTINCT FROM
                   expected_completed_at_utc) THEN
            RAISE EXCEPTION 'release production completion pins do not match evidence';
        END IF;

        NEW.production_run_completion_job_id := completion_row.job_id;
        NEW.production_run_output_manifest_sha256 :=
            completion_row.output_manifest_sha256;
        NEW.production_run_output_sha256 := completion_row.output_sha256;
        NEW.production_run_output_byte_size := completion_row.output_byte_size;
        NEW.production_run_output_record_count := completion_row.output_record_count;
        NEW.production_run_completed_at_utc := expected_completed_at_utc;
    ELSE
        IF NEW.production_run_completion_job_id IS NOT NULL
           OR NEW.production_run_output_manifest_sha256 IS NOT NULL
           OR NEW.production_run_output_sha256 IS NOT NULL
           OR NEW.production_run_output_byte_size IS NOT NULL
           OR NEW.production_run_output_record_count IS NOT NULL
           OR NEW.production_run_completed_at_utc IS NOT NULL THEN
            RAISE EXCEPTION 'non-generated release source cannot carry production completion evidence';
        END IF;
        NEW.production_run_completion_job_id := NULL;
        NEW.production_run_output_manifest_sha256 := NULL;
        NEW.production_run_output_sha256 := NULL;
        NEW.production_run_output_byte_size := NULL;
        NEW.production_run_output_record_count := NULL;
        NEW.production_run_completed_at_utc := NULL;
    END IF;
    RETURN NEW;
END;
$$;

-- PostgreSQL runs same-kind triggers by name.  The zz prefix deliberately
-- places this after 024's validator, which first derives source/run identity.
CREATE TRIGGER zz_release_source_contract_snapshots_pin_completion
BEFORE INSERT ON release_source_contract_snapshots
FOR EACH ROW EXECUTE FUNCTION pin_release_source_production_completion();

-- Re-check the child pins at both authority boundaries.  The 024 trigger runs
-- first and derives the bounded top artifact from the entire child row; this
-- follow-up trigger proves those hashed completion fields are still exact.
CREATE OR REPLACE FUNCTION validate_release_completion_snapshot_transition()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    evidence_schema text;
    function_schema text;
    evidence_row record;
    completion_row record;
    expected_completed_at_utc text;
    matched_rows bigint;
    requires_full_revalidation boolean;
BEGIN
    requires_full_revalidation := (
        OLD.contract_snapshot_status = 'pending'
        AND NEW.contract_snapshot_status = 'present'
    ) OR (
        OLD.status = 'draft'
        AND NEW.status = 'frozen'
    );
    IF NOT requires_full_revalidation THEN
        RETURN NEW;
    END IF;

    SELECT namespace.nspname
    INTO evidence_schema
    FROM pg_catalog.pg_class AS relation
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.oid = relation.relnamespace
    WHERE relation.oid = TG_RELID;

    SELECT function_namespace.nspname
    INTO function_schema
    FROM pg_catalog.pg_trigger AS trigger_def
    JOIN pg_catalog.pg_proc AS function_def
      ON function_def.oid = trigger_def.tgfoid
    JOIN pg_catalog.pg_namespace AS function_namespace
      ON function_namespace.oid = function_def.pronamespace
    WHERE trigger_def.tgrelid = TG_RELID
      AND trigger_def.tgname = TG_NAME
      AND NOT trigger_def.tgisinternal;

    IF evidence_schema IS NULL
       OR function_schema IS NULL
       OR function_schema IS DISTINCT FROM evidence_schema THEN
        RAISE EXCEPTION 'release completion transition validator schema mismatch';
    END IF;

    FOR evidence_row IN EXECUTE pg_catalog.format(
        'SELECT snapshot.source_id, snapshot.data_origin, '
        'snapshot.production_run_id, '
        'snapshot.production_run_completion_job_id, '
        'snapshot.production_run_output_manifest_sha256, '
        'snapshot.production_run_output_sha256, '
        'snapshot.production_run_output_byte_size, '
        'snapshot.production_run_output_record_count, '
        'snapshot.production_run_completed_at_utc, '
        'source.data_origin AS source_data_origin, '
        'source.production_run_id AS source_production_run_id, '
        'source.object_sha256 AS source_object_sha256, '
        'source.byte_size AS source_byte_size, '
        'source.line_count AS source_line_count '
        'FROM %I.release_source_contract_snapshots AS snapshot '
        'JOIN %I.sources AS source ON source.id = snapshot.source_id '
        'WHERE snapshot.release_id = $1 ORDER BY snapshot.source_id '
        'FOR SHARE OF source',
        evidence_schema, evidence_schema
    ) USING NEW.id
    LOOP
        IF evidence_row.source_data_origin IN ('model', 'hybrid') THEN
            IF evidence_row.data_origin IS DISTINCT FROM
                   evidence_row.source_data_origin
               OR evidence_row.production_run_id IS DISTINCT FROM
                   evidence_row.source_production_run_id THEN
                RAISE EXCEPTION 'release completion snapshot provenance is stale';
            END IF;

            EXECUTE pg_catalog.format(
                'SELECT job_id, output_manifest_sha256, output_sha256, '
                'output_byte_size, output_record_count, completed_at '
                'FROM %I.production_run_completions '
                'WHERE production_run_id = $1 FOR SHARE',
                evidence_schema
            )
            INTO completion_row
            USING evidence_row.source_production_run_id;
            GET DIAGNOSTICS matched_rows = ROW_COUNT;
            IF matched_rows <> 1 THEN
                RAISE EXCEPTION 'model or hybrid release source requires production completion evidence';
            END IF;

            expected_completed_at_utc := pg_catalog.to_char(
                completion_row.completed_at AT TIME ZONE 'UTC',
                'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
            );
            IF evidence_row.source_object_sha256 IS DISTINCT FROM
                   completion_row.output_sha256
               OR evidence_row.source_byte_size IS DISTINCT FROM
                   completion_row.output_byte_size
               OR evidence_row.source_line_count IS DISTINCT FROM
                   completion_row.output_record_count
               OR evidence_row.production_run_completion_job_id IS DISTINCT FROM
                   completion_row.job_id
               OR evidence_row.production_run_output_manifest_sha256 IS DISTINCT FROM
                   completion_row.output_manifest_sha256
               OR evidence_row.production_run_output_sha256 IS DISTINCT FROM
                   completion_row.output_sha256
               OR evidence_row.production_run_output_byte_size IS DISTINCT FROM
                   completion_row.output_byte_size
               OR evidence_row.production_run_output_record_count IS DISTINCT FROM
                   completion_row.output_record_count
               OR evidence_row.production_run_completed_at_utc IS DISTINCT FROM
                   expected_completed_at_utc THEN
                RAISE EXCEPTION 'release production completion snapshot is stale';
            END IF;
        ELSIF evidence_row.production_run_completion_job_id IS NOT NULL
           OR evidence_row.production_run_output_manifest_sha256 IS NOT NULL
           OR evidence_row.production_run_output_sha256 IS NOT NULL
           OR evidence_row.production_run_output_byte_size IS NOT NULL
           OR evidence_row.production_run_output_record_count IS NOT NULL
           OR evidence_row.production_run_completed_at_utc IS NOT NULL THEN
            RAISE EXCEPTION 'non-generated release source has production completion evidence';
        END IF;
    END LOOP;
    RETURN NEW;
END;
$$;

CREATE TRIGGER zz_releases_validate_completion_snapshot_transition
BEFORE UPDATE ON releases
FOR EACH ROW EXECUTE FUNCTION validate_release_completion_snapshot_transition();

-- Extend the positive safe-summary allowlist.  Neither job payload/result nor
-- prompts, provider URLs, filesystem paths or free-form text are copied.
ALTER FUNCTION row_change_safe_summary(text, jsonb)
    RENAME TO row_change_safe_summary_v25;

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
    IF target_table = 'production_run_completions' THEN
        RETURN jsonb_build_object(
            'production_run_id', row_data->'production_run_id',
            'job_id', row_data->'job_id',
            'output_manifest_sha256', row_data->'output_manifest_sha256',
            'output_sha256', row_data->'output_sha256',
            'output_byte_size', row_data->'output_byte_size',
            'output_record_count', row_data->'output_record_count',
            'completed_at', row_data->'completed_at'
        );
    END IF;
    prior_summary := row_change_safe_summary_v25(target_table, row_data);
    IF target_table = 'release_source_contract_snapshots' THEN
        RETURN prior_summary || jsonb_build_object(
            'production_run_completion_job_id',
                row_data->'production_run_completion_job_id',
            'production_run_output_manifest_sha256',
                row_data->'production_run_output_manifest_sha256',
            'production_run_output_sha256',
                row_data->'production_run_output_sha256',
            'production_run_output_byte_size',
                row_data->'production_run_output_byte_size',
            'production_run_output_record_count',
                row_data->'production_run_output_record_count',
            'production_run_completed_at_utc',
                row_data->'production_run_completed_at_utc'
        );
    END IF;
    RETURN prior_summary;
END;
$$;

CREATE TRIGGER production_run_completions_capture_row_change
AFTER INSERT OR UPDATE OR DELETE ON production_run_completions
FOR EACH ROW EXECUTE FUNCTION capture_row_change_event('production_run_id');

REVOKE ALL ON FUNCTION validate_production_run_completion() FROM PUBLIC;
REVOKE ALL ON FUNCTION reject_production_run_completion_mutation() FROM PUBLIC;
REVOKE ALL ON FUNCTION protect_completed_production_job() FROM PUBLIC;
REVOKE ALL ON FUNCTION pin_release_source_production_completion() FROM PUBLIC;
REVOKE ALL ON FUNCTION validate_release_completion_snapshot_transition() FROM PUBLIC;
REVOKE ALL ON FUNCTION row_change_safe_summary(text, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION row_change_safe_summary_v25(text, jsonb) FROM PUBLIC;
