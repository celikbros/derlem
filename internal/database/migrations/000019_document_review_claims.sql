CREATE TABLE document_review_claims (
    document_id uuid PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    reviewer_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    claim_token uuid NOT NULL,
    document_version bigint NOT NULL CHECK (document_version > 0),
    claimed_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    CHECK (expires_at > claimed_at)
);

CREATE INDEX document_review_claims_reviewer_token_idx
ON document_review_claims (reviewer_id, claim_token);

CREATE INDEX document_review_claims_expiry_idx
ON document_review_claims (expires_at);

CREATE OR REPLACE FUNCTION clear_invalid_document_review_claim()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM document_review_claims WHERE document_id = NEW.id;
    RETURN NULL;
END;
$$;

CREATE TRIGGER documents_clear_invalid_review_claim
AFTER UPDATE OF current_version, is_active, status ON documents
FOR EACH ROW
WHEN (
    OLD.current_version IS DISTINCT FROM NEW.current_version
    OR OLD.is_active IS DISTINCT FROM NEW.is_active
    OR (
        OLD.status IS DISTINCT FROM NEW.status
        AND NEW.status NOT IN ('sampled', 'edited')
    )
)
EXECUTE FUNCTION clear_invalid_document_review_claim();
