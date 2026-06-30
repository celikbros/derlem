CREATE TABLE similarity_calibration_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    report_object_sha256 char(64) NOT NULL REFERENCES storage_objects(sha256) ON DELETE RESTRICT,
    schema_version text NOT NULL CHECK (length(btrim(schema_version)) > 0),
    method text NOT NULL CHECK (length(btrim(method)) > 0),
    content_purpose text NOT NULL
        CHECK (content_purpose IN ('pretrain', 'instruction', 'preference', 'eval', 'holdout', 'post_training')),
    source_snapshot jsonb NOT NULL CHECK (jsonb_typeof(source_snapshot) = 'array'),
    sampled_document_count bigint NOT NULL CHECK (sampled_document_count > 1),
    eligible_document_count bigint NOT NULL CHECK (eligible_document_count >= sampled_document_count),
    simhash_version text NOT NULL CHECK (length(btrim(simhash_version)) > 0),
    threshold_max smallint NOT NULL CHECK (threshold_max BETWEEN 0 AND 64),
    pair_count integer NOT NULL CHECK (pair_count > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (report_object_sha256)
);

CREATE INDEX similarity_calibration_runs_purpose_idx
ON similarity_calibration_runs (content_purpose, created_at DESC);

CREATE TABLE similarity_review_pairs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES similarity_calibration_runs(id) ON DELETE RESTRICT,
    pair_rank integer NOT NULL CHECK (pair_rank > 0),
    hamming_distance smallint NOT NULL CHECK (hamming_distance BETWEEN 0 AND 64),
    left_source_id uuid NOT NULL REFERENCES sources(id) ON DELETE RESTRICT,
    left_source_sha256 char(64) NOT NULL,
    left_source_ordinal bigint NOT NULL CHECK (left_source_ordinal > 0),
    left_object_sha256 char(64) NOT NULL REFERENCES storage_objects(sha256) ON DELETE RESTRICT,
    left_text_preview text NOT NULL CHECK (length(left_text_preview) <= 500),
    left_token_count integer NOT NULL CHECK (left_token_count > 0),
    right_source_id uuid NOT NULL REFERENCES sources(id) ON DELETE RESTRICT,
    right_source_sha256 char(64) NOT NULL,
    right_source_ordinal bigint NOT NULL CHECK (right_source_ordinal > 0),
    right_object_sha256 char(64) NOT NULL REFERENCES storage_objects(sha256) ON DELETE RESTRICT,
    right_text_preview text NOT NULL CHECK (length(right_text_preview) <= 500),
    right_token_count integer NOT NULL CHECK (right_token_count > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, pair_rank),
    UNIQUE (
        run_id,
        left_source_sha256,
        left_source_ordinal,
        right_source_sha256,
        right_source_ordinal
    ),
    CHECK (
        left_source_sha256 <> right_source_sha256 OR
        left_source_ordinal <> right_source_ordinal
    )
);

CREATE INDEX similarity_review_pairs_run_distance_idx
ON similarity_review_pairs (run_id, hamming_distance, pair_rank);

CREATE TABLE similarity_pair_reviews (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    pair_id uuid NOT NULL REFERENCES similarity_review_pairs(id) ON DELETE RESTRICT,
    reviewer_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    label text NOT NULL
        CHECK (label IN ('exact_duplicate', 'near_duplicate', 'related', 'different', 'uncertain')),
    reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (pair_id, reviewer_id),
    CHECK (label NOT IN ('uncertain') OR length(btrim(reason)) > 0)
);

CREATE INDEX similarity_pair_reviews_pair_idx
ON similarity_pair_reviews (pair_id, created_at, id);

CREATE INDEX similarity_pair_reviews_reviewer_idx
ON similarity_pair_reviews (reviewer_id, created_at DESC);

CREATE OR REPLACE FUNCTION reject_similarity_review_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'similarity calibration evidence is append-only';
END;
$$;

CREATE TRIGGER similarity_calibration_runs_no_update
BEFORE UPDATE ON similarity_calibration_runs
FOR EACH ROW EXECUTE FUNCTION reject_similarity_review_mutation();

CREATE TRIGGER similarity_calibration_runs_no_delete
BEFORE DELETE ON similarity_calibration_runs
FOR EACH ROW EXECUTE FUNCTION reject_similarity_review_mutation();

CREATE TRIGGER similarity_review_pairs_no_update
BEFORE UPDATE ON similarity_review_pairs
FOR EACH ROW EXECUTE FUNCTION reject_similarity_review_mutation();

CREATE TRIGGER similarity_review_pairs_no_delete
BEFORE DELETE ON similarity_review_pairs
FOR EACH ROW EXECUTE FUNCTION reject_similarity_review_mutation();

CREATE TRIGGER similarity_pair_reviews_no_update
BEFORE UPDATE ON similarity_pair_reviews
FOR EACH ROW EXECUTE FUNCTION reject_similarity_review_mutation();

CREATE TRIGGER similarity_pair_reviews_no_delete
BEFORE DELETE ON similarity_pair_reviews
FOR EACH ROW EXECUTE FUNCTION reject_similarity_review_mutation();

CREATE TRIGGER similarity_calibration_runs_no_truncate
BEFORE TRUNCATE ON similarity_calibration_runs
FOR EACH STATEMENT EXECUTE FUNCTION reject_similarity_review_mutation();

CREATE TRIGGER similarity_review_pairs_no_truncate
BEFORE TRUNCATE ON similarity_review_pairs
FOR EACH STATEMENT EXECUTE FUNCTION reject_similarity_review_mutation();

CREATE TRIGGER similarity_pair_reviews_no_truncate
BEFORE TRUNCATE ON similarity_pair_reviews
FOR EACH STATEMENT EXECUTE FUNCTION reject_similarity_review_mutation();
