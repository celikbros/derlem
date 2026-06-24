CREATE TABLE pii_scans (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id uuid NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    job_id uuid REFERENCES background_jobs(id) ON DELETE SET NULL,
    object_sha256 char(64) NOT NULL REFERENCES storage_objects(sha256) ON DELETE RESTRICT,
    scanner_version text NOT NULL,
    status text NOT NULL CHECK (status IN ('clear', 'flagged', 'failed')),
    findings jsonb NOT NULL DEFAULT '{}'::jsonb,
    scanned_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_id, object_sha256, scanner_version)
);

CREATE INDEX pii_scans_source_idx ON pii_scans (source_id, scanned_at DESC);

ALTER TABLE reviews
    ADD COLUMN source_version bigint NOT NULL DEFAULT 1 CHECK (source_version > 0),
    ADD COLUMN review_context jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE UNIQUE INDEX background_jobs_active_source_type_uidx
ON background_jobs (job_type, (payload->>'source_id'))
WHERE status IN ('queued', 'running') AND payload ? 'source_id';

CREATE INDEX background_jobs_source_idx
ON background_jobs ((payload->>'source_id'), created_at DESC)
WHERE payload ? 'source_id';

INSERT INTO background_jobs(job_type, payload, created_by)
SELECT
    'scan_pii',
    jsonb_build_object('source_id', source.id::text, 'object_sha256', source.object_sha256::text),
    source.created_by
FROM sources AS source
WHERE source.object_sha256 IS NOT NULL
  AND source.pii_status = 'not_scanned'
  AND NOT EXISTS (
      SELECT 1
      FROM background_jobs AS job
      WHERE job.job_type = 'scan_pii'
        AND job.payload->>'source_id' = source.id::text
        AND job.status IN ('queued', 'running')
  );
