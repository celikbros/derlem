ALTER TABLE sources
    ADD COLUMN reviewed_document_count bigint NOT NULL DEFAULT 0
        CHECK (reviewed_document_count >= 0),
    ADD COLUMN approved_document_count bigint NOT NULL DEFAULT 0
        CHECK (approved_document_count >= 0),
    ADD COLUMN flagged_document_count bigint NOT NULL DEFAULT 0
        CHECK (flagged_document_count >= 0);

CREATE TABLE document_reviews (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE RESTRICT,
    reviewer_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    decision text NOT NULL CHECK (decision IN ('approved', 'rejected', 'sensitive_review')),
    reason text,
    quality_score smallint NOT NULL CHECK (quality_score BETWEEN 1 AND 5),
    document_version bigint NOT NULL CHECK (document_version > 0),
    object_sha256 char(64) NOT NULL REFERENCES storage_objects(sha256) ON DELETE RESTRICT,
    review_context jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT document_reviews_reason CHECK (
        decision = 'approved' OR COALESCE(length(btrim(reason)), 0) > 0
    ),
    UNIQUE (document_id, document_version, reviewer_id)
);

CREATE INDEX document_reviews_document_idx
ON document_reviews (document_id, created_at DESC);

CREATE INDEX document_reviews_reviewer_idx
ON document_reviews (reviewer_id, created_at DESC);

CREATE OR REPLACE FUNCTION reject_document_review_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'document_reviews are append-only';
END;
$$;

CREATE TRIGGER document_reviews_no_update
BEFORE UPDATE ON document_reviews
FOR EACH ROW EXECUTE FUNCTION reject_document_review_mutation();

CREATE TRIGGER document_reviews_no_delete
BEFORE DELETE ON document_reviews
FOR EACH ROW EXECUTE FUNCTION reject_document_review_mutation();

CREATE TRIGGER document_reviews_no_truncate
BEFORE TRUNCATE ON document_reviews
FOR EACH STATEMENT EXECUTE FUNCTION reject_document_review_mutation();

UPDATE sources
SET approval_status = 'sampled_for_review'
WHERE approval_status = 'approved_source'
  AND sampled_document_count > 0;
