CREATE TABLE document_sample_generations (
    source_id uuid NOT NULL REFERENCES sources(id) ON DELETE RESTRICT,
    generation integer NOT NULL CHECK (generation > 0),
    source_sha256 char(64) NOT NULL REFERENCES storage_objects(sha256) ON DELETE RESTRICT,
    sampling_method text NOT NULL,
    status text NOT NULL CHECK (status IN ('active', 'superseded')),
    sample_count integer NOT NULL CHECK (sample_count >= 0),
    job_id uuid REFERENCES background_jobs(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_id, generation)
);

CREATE UNIQUE INDEX document_sample_generations_active_uidx
ON document_sample_generations (source_id)
WHERE status = 'active';

CREATE TABLE document_sample_memberships (
    source_id uuid NOT NULL,
    generation integer NOT NULL,
    document_id uuid NOT NULL REFERENCES documents(id) ON DELETE RESTRICT,
    source_ordinal bigint NOT NULL CHECK (source_ordinal > 0),
    object_sha256 char(64) NOT NULL REFERENCES storage_objects(sha256) ON DELETE RESTRICT,
    risk_score smallint NOT NULL CHECK (risk_score BETWEEN 0 AND 10),
    risk_reasons text[] NOT NULL DEFAULT '{}'::text[],
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_id, generation, document_id),
    UNIQUE (source_id, generation, source_ordinal),
    FOREIGN KEY (source_id, generation)
        REFERENCES document_sample_generations(source_id, generation) ON DELETE RESTRICT
);

INSERT INTO document_sample_generations(
    source_id, generation, source_sha256, sampling_method, status, sample_count
)
SELECT source.id, source.document_sample_generation, source.object_sha256,
    source.document_sampling_method, 'active',
    count(document.id)::integer
FROM sources AS source
JOIN documents AS document ON document.source_id = source.id AND document.is_active
WHERE source.document_sample_generation > 0
  AND source.object_sha256 IS NOT NULL
GROUP BY source.id, source.document_sample_generation, source.object_sha256,
    source.document_sampling_method;

INSERT INTO document_sample_memberships(
    source_id, generation, document_id, source_ordinal,
    object_sha256, risk_score, risk_reasons
)
SELECT document.source_id, document.sample_generation, document.id,
    document.source_ordinal, document.current_object_sha256,
    document.risk_score, document.risk_reasons
FROM documents AS document
WHERE document.is_active;
