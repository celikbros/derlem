ALTER TABLE release_exports
ADD COLUMN estimated_token_count bigint,
ADD COLUMN token_estimate_lower_bound bigint,
ADD COLUMN token_estimate_upper_bound bigint,
ADD COLUMN token_estimate_method text,
ADD COLUMN record_type_counts jsonb;

ALTER TABLE release_exports
ADD CONSTRAINT release_exports_token_estimate_consistent CHECK (
    (
        estimated_token_count IS NULL AND
        token_estimate_lower_bound IS NULL AND
        token_estimate_upper_bound IS NULL AND
        token_estimate_method IS NULL
    ) OR (
        estimated_token_count IS NOT NULL AND estimated_token_count >= 0 AND
        token_estimate_lower_bound IS NOT NULL AND token_estimate_lower_bound >= 0 AND
        token_estimate_upper_bound IS NOT NULL AND token_estimate_upper_bound >= estimated_token_count AND
        token_estimate_lower_bound <= estimated_token_count AND
        token_estimate_method IS NOT NULL AND length(btrim(token_estimate_method)) > 0
    )
),
ADD CONSTRAINT release_exports_record_type_counts_object CHECK (
    record_type_counts IS NULL OR jsonb_typeof(record_type_counts) = 'object'
);
