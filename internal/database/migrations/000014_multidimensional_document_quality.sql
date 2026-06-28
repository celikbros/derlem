ALTER TABLE document_reviews
    ADD COLUMN rubric_version text NOT NULL DEFAULT 'overall-v1',
    ADD COLUMN language_quality_score smallint,
    ADD COLUMN coherence_score smallint,
    ADD COLUMN information_density_score smallint,
    ADD COLUMN cleanliness_score smallint,
    ADD CONSTRAINT document_reviews_rubric_version_check
        CHECK (rubric_version IN ('overall-v1', 'multidimensional-v1')),
    ADD CONSTRAINT document_reviews_multidimensional_scores_check
        CHECK (
            (
                rubric_version = 'overall-v1'
                AND language_quality_score IS NULL
                AND coherence_score IS NULL
                AND information_density_score IS NULL
                AND cleanliness_score IS NULL
            )
            OR
            (
                rubric_version = 'multidimensional-v1'
                AND language_quality_score BETWEEN 1 AND 5
                AND coherence_score BETWEEN 1 AND 5
                AND information_density_score BETWEEN 1 AND 5
                AND cleanliness_score BETWEEN 1 AND 5
            )
        );

ALTER TABLE document_reviews
    ALTER COLUMN rubric_version SET DEFAULT 'multidimensional-v1';

CREATE INDEX document_reviews_rubric_idx
ON document_reviews (rubric_version, created_at DESC);
