ALTER TABLE sources
    ADD COLUMN declared_sha256 char(64),
    ADD COLUMN declared_byte_size bigint CHECK (declared_byte_size >= 0),
    ADD COLUMN declared_line_count bigint CHECK (declared_line_count >= 0),
    ADD COLUMN source_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD CONSTRAINT sources_declared_sha256_format
        CHECK (declared_sha256 IS NULL OR declared_sha256 ~ '^[0-9a-f]{64}$');

CREATE UNIQUE INDEX sources_seed_key_unique_idx
ON sources ((source_metadata->>'seed_key'))
WHERE source_metadata ? 'seed_key';
