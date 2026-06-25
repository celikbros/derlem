ALTER TABLE release_sources
    ADD COLUMN source_version bigint,
    ADD COLUMN source_name text,
    ADD COLUMN source_type text,
    ADD COLUMN license text,
    ADD COLUMN rights_status text,
    ADD COLUMN language text,
    ADD COLUMN domain text,
    ADD COLUMN lineage_ref text,
    ADD COLUMN byte_size bigint,
    ADD COLUMN line_count bigint;

UPDATE release_sources AS release_source
SET source_version = source.version,
    source_name = source.name,
    source_type = source.source_type,
    license = source.license,
    rights_status = source.rights_status,
    language = source.language,
    domain = source.domain,
    lineage_ref = source.lineage_ref,
    byte_size = source.byte_size,
    line_count = source.line_count
FROM sources AS source
WHERE source.id = release_source.source_id;

ALTER TABLE release_sources
    ALTER COLUMN source_version SET NOT NULL,
    ALTER COLUMN source_name SET NOT NULL,
    ALTER COLUMN source_type SET NOT NULL,
    ALTER COLUMN license SET NOT NULL,
    ALTER COLUMN rights_status SET NOT NULL,
    ALTER COLUMN language SET NOT NULL,
    ALTER COLUMN domain SET NOT NULL,
    ALTER COLUMN lineage_ref SET NOT NULL,
    ADD CONSTRAINT release_sources_source_version CHECK (source_version > 0),
    ADD CONSTRAINT release_sources_source_sha256_fk
        FOREIGN KEY (source_sha256) REFERENCES storage_objects(sha256) ON DELETE RESTRICT;

ALTER TABLE releases
    ADD CONSTRAINT releases_manifest_object_required CHECK (
        status <> 'frozen' OR manifest_object_sha256 IS NOT NULL
    ),
    ADD CONSTRAINT releases_manifest_identity CHECK (
        manifest_object_sha256 IS NULL OR manifest_sha256 = manifest_object_sha256
    );

CREATE INDEX releases_created_idx ON releases (created_at DESC, id DESC);

CREATE UNIQUE INDEX background_jobs_active_release_type_uidx
ON background_jobs (job_type, (payload->>'release_id'))
WHERE status IN ('queued', 'running') AND payload ? 'release_id';

CREATE OR REPLACE FUNCTION protect_frozen_release()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' AND OLD.status = 'frozen' THEN
        RAISE EXCEPTION 'frozen releases are immutable';
    END IF;
    IF TG_OP = 'UPDATE' AND OLD.status = 'frozen' THEN
        RAISE EXCEPTION 'frozen releases are immutable';
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE TRIGGER releases_protect_frozen
BEFORE UPDATE OR DELETE ON releases
FOR EACH ROW EXECUTE FUNCTION protect_frozen_release();

CREATE OR REPLACE FUNCTION protect_release_source_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    release_status text;
    target_release_id uuid;
BEGIN
    IF TG_OP = 'DELETE' THEN
        target_release_id := OLD.release_id;
    ELSE
        target_release_id := NEW.release_id;
    END IF;
    SELECT status INTO release_status
    FROM releases
    WHERE id = target_release_id;

    IF release_status <> 'draft' THEN
        RAISE EXCEPTION 'frozen release sources are immutable';
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE TRIGGER release_sources_protect_frozen
BEFORE INSERT OR UPDATE OR DELETE ON release_sources
FOR EACH ROW EXECUTE FUNCTION protect_release_source_mutation();
