CREATE TABLE release_exports (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    release_id uuid NOT NULL REFERENCES releases(id) ON DELETE RESTRICT,
    format text NOT NULL CHECK (format IN ('jsonl', 'txt')),
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'building', 'ready', 'failed')),
    object_sha256 char(64) REFERENCES storage_objects(sha256) ON DELETE RESTRICT,
    manifest_object_sha256 char(64) REFERENCES storage_objects(sha256) ON DELETE RESTRICT,
    record_count bigint,
    byte_size bigint,
    last_error text,
    created_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    UNIQUE (release_id, format),
    CONSTRAINT release_exports_ready_fields CHECK (
        status <> 'ready' OR (
            object_sha256 IS NOT NULL AND
            manifest_object_sha256 IS NOT NULL AND
            record_count IS NOT NULL AND record_count >= 0 AND
            byte_size IS NOT NULL AND byte_size >= 0 AND
            completed_at IS NOT NULL
        )
    )
);

CREATE INDEX release_exports_release_idx
ON release_exports (release_id, format);

CREATE OR REPLACE FUNCTION protect_ready_release_export()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' AND OLD.status = 'ready' THEN
        RAISE EXCEPTION 'ready release exports are immutable';
    END IF;
    IF TG_OP = 'UPDATE' AND OLD.status = 'ready' THEN
        RAISE EXCEPTION 'ready release exports are immutable';
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE TRIGGER release_exports_protect_ready
BEFORE UPDATE OR DELETE ON release_exports
FOR EACH ROW EXECUTE FUNCTION protect_ready_release_export();
