ALTER TABLE documents
    ADD COLUMN risk_score smallint NOT NULL DEFAULT 0
        CHECK (risk_score BETWEEN 0 AND 10),
    ADD COLUMN risk_reasons text[] NOT NULL DEFAULT '{}'::text[]
        CHECK (cardinality(risk_reasons) <= 16);

CREATE INDEX documents_source_risk_idx
ON documents (source_id, risk_score DESC, source_ordinal)
WHERE risk_score > 0;
