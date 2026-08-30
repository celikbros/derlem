CREATE TABLE document_review_reversals (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id uuid NOT NULL UNIQUE
        REFERENCES document_reviews(id) ON DELETE RESTRICT,
    reversed_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    reason text NOT NULL CHECK (length(btrim(reason)) > 0),
    restored_document_status text NOT NULL
        CHECK (restored_document_status IN ('sampled', 'edited')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX document_review_reversals_actor_idx
ON document_review_reversals (reversed_by, created_at DESC);

-- Mutable projection used only to preserve the former database-level
-- uniqueness guarantee while document_reviews and their reversals stay
-- append-only. A reversed review is removed from this projection by trigger.
CREATE TABLE active_document_reviews (
    review_id uuid PRIMARY KEY REFERENCES document_reviews(id) ON DELETE RESTRICT,
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE RESTRICT,
    document_version bigint NOT NULL CHECK (document_version > 0),
    reviewer_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    UNIQUE (document_id, document_version, reviewer_id)
);

INSERT INTO active_document_reviews(
    review_id, document_id, document_version, reviewer_id
)
SELECT id, document_id, document_version, reviewer_id
FROM document_reviews;

CREATE OR REPLACE FUNCTION reject_document_review_reversal_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'document_review_reversals are append-only';
END;
$$;

CREATE TRIGGER document_review_reversals_no_update
BEFORE UPDATE ON document_review_reversals
FOR EACH ROW EXECUTE FUNCTION reject_document_review_reversal_mutation();

CREATE TRIGGER document_review_reversals_no_delete
BEFORE DELETE ON document_review_reversals
FOR EACH ROW EXECUTE FUNCTION reject_document_review_reversal_mutation();

CREATE TRIGGER document_review_reversals_no_truncate
BEFORE TRUNCATE ON document_review_reversals
FOR EACH STATEMENT EXECUTE FUNCTION reject_document_review_reversal_mutation();

-- A reversed review remains immutable history, but the same reviewer must be
-- able to review the restored document version again. Effective uniqueness is
-- enforced while the document row is locked by the repository transaction.
ALTER TABLE document_reviews
    DROP CONSTRAINT IF EXISTS document_reviews_document_id_document_version_reviewer_id_key;

CREATE INDEX document_reviews_effective_lookup_idx
ON document_reviews (document_id, document_version, reviewer_id, created_at DESC);

CREATE OR REPLACE FUNCTION register_active_document_review()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO active_document_reviews(
        review_id, document_id, document_version, reviewer_id
    )
    VALUES (NEW.id, NEW.document_id, NEW.document_version, NEW.reviewer_id);
    RETURN NULL;
END;
$$;

CREATE TRIGGER document_reviews_register_active
AFTER INSERT ON document_reviews
FOR EACH ROW EXECUTE FUNCTION register_active_document_review();

CREATE OR REPLACE FUNCTION unregister_reversed_document_review()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM active_document_reviews WHERE review_id = NEW.review_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'document review is not active';
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER document_review_reversals_unregister_active
AFTER INSERT ON document_review_reversals
FOR EACH ROW EXECUTE FUNCTION unregister_reversed_document_review();
