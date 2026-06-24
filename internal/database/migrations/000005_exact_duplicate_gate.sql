ALTER TABLE sources
    ADD COLUMN duplicate_status text NOT NULL DEFAULT 'not_checked'
        CHECK (duplicate_status IN ('not_checked', 'unique', 'duplicate')),
    ADD COLUMN duplicate_of_source_id uuid REFERENCES sources(id) ON DELETE RESTRICT,
    ADD CONSTRAINT sources_duplicate_reference_consistency CHECK (
        (duplicate_status = 'duplicate' AND duplicate_of_source_id IS NOT NULL)
        OR (duplicate_status <> 'duplicate' AND duplicate_of_source_id IS NULL)
    );

CREATE INDEX sources_duplicate_status_idx
ON sources (duplicate_status, created_at DESC);

CREATE INDEX sources_duplicate_of_idx
ON sources (duplicate_of_source_id)
WHERE duplicate_of_source_id IS NOT NULL;
