ALTER TABLE sources
    DROP CONSTRAINT sources_document_sampling_status_check;

ALTER TABLE sources
    ADD CONSTRAINT sources_document_sampling_status_check
        CHECK (document_sampling_status IN ('not_sampled', 'resampling', 'sampled', 'failed')),
    ADD COLUMN document_sample_generation integer NOT NULL DEFAULT 0
        CHECK (document_sample_generation >= 0),
    ADD COLUMN document_sampling_method text NOT NULL DEFAULT 'not_sampled';

ALTER TABLE documents
    ADD COLUMN is_active boolean NOT NULL DEFAULT true,
    ADD COLUMN sample_generation integer NOT NULL DEFAULT 1
        CHECK (sample_generation > 0);

UPDATE sources AS source
SET document_sample_generation = 1,
    document_sampling_method = COALESCE((
        SELECT document.sampling_method
        FROM documents AS document
        WHERE document.source_id = source.id
        ORDER BY document.source_ordinal
        LIMIT 1
    ), 'reservoir-sha256-v1')
WHERE source.sampled_document_count > 0;

CREATE INDEX documents_source_active_idx
ON documents (source_id, source_ordinal)
WHERE is_active;

CREATE INDEX documents_source_generation_idx
ON documents (source_id, sample_generation, source_ordinal);
