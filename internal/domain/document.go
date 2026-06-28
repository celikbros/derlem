package domain

import (
	"encoding/json"
	"time"
)

type Document struct {
	ID                  string    `json:"id"`
	SourceID            string    `json:"source_id"`
	SourceOrdinal       int64     `json:"source_ordinal"`
	ExternalID          *string   `json:"external_id,omitempty"`
	CurrentObjectSHA256 string    `json:"current_object_sha256"`
	TextPreview         string    `json:"text_preview"`
	ByteSize            int64     `json:"byte_size"`
	CharCount           int64     `json:"char_count"`
	Status              string    `json:"status"`
	CurrentVersion      int64     `json:"current_version"`
	SamplingMethod      string    `json:"sampling_method"`
	RiskScore           int16     `json:"risk_score"`
	RiskReasons         []string  `json:"risk_reasons"`
	IsActive            bool      `json:"is_active"`
	SampleGeneration    int64     `json:"sample_generation"`
	CreatedAt           time.Time `json:"created_at"`
	UpdatedAt           time.Time `json:"updated_at"`
}

type UpdateDocumentInput struct {
	Content string  `json:"content"`
	Version int64   `json:"version"`
	Reason  *string `json:"reason"`
}

const MultidimensionalQualityRubric = "multidimensional-v1"

type DocumentQualityScores struct {
	QualityScore            int16 `json:"quality_score"`
	LanguageQualityScore    int16 `json:"language_quality_score"`
	CoherenceScore          int16 `json:"coherence_score"`
	InformationDensityScore int16 `json:"information_density_score"`
	CleanlinessScore        int16 `json:"cleanliness_score"`
}

type ReviewDocumentInput struct {
	DocumentQualityScores
	Decision        string  `json:"decision"`
	Reason          *string `json:"reason"`
	DocumentVersion int64   `json:"document_version"`
}

type BulkReviewDocumentItem struct {
	DocumentID      string `json:"document_id"`
	DocumentVersion int64  `json:"document_version"`
}

type BulkReviewDocumentsInput struct {
	DocumentQualityScores
	Documents []BulkReviewDocumentItem `json:"documents"`
	Decision  string                   `json:"decision"`
	Reason    *string                  `json:"reason"`
}

type BulkDocumentReviewResult struct {
	Source    Source           `json:"source"`
	Documents []Document       `json:"documents"`
	Reviews   []DocumentReview `json:"reviews"`
}

type DocumentSampleGeneration struct {
	SourceID       string    `json:"source_id"`
	Generation     int64     `json:"generation"`
	SourceSHA256   string    `json:"source_sha256"`
	SamplingMethod string    `json:"sampling_method"`
	Status         string    `json:"status"`
	SampleCount    int64     `json:"sample_count"`
	JobID          *string   `json:"job_id,omitempty"`
	CreatedAt      time.Time `json:"created_at"`
}

type DocumentReview struct {
	ID                      string          `json:"id"`
	DocumentID              string          `json:"document_id"`
	ReviewerID              string          `json:"reviewer_id"`
	Decision                string          `json:"decision"`
	Reason                  *string         `json:"reason,omitempty"`
	RubricVersion           string          `json:"rubric_version"`
	QualityScore            int16           `json:"quality_score"`
	LanguageQualityScore    *int16          `json:"language_quality_score,omitempty"`
	CoherenceScore          *int16          `json:"coherence_score,omitempty"`
	InformationDensityScore *int16          `json:"information_density_score,omitempty"`
	CleanlinessScore        *int16          `json:"cleanliness_score,omitempty"`
	DocumentVersion         int64           `json:"document_version"`
	ObjectSHA256            string          `json:"object_sha256"`
	Context                 json.RawMessage `json:"context"`
	CreatedAt               time.Time       `json:"created_at"`
}

type DocumentQualitySummary struct {
	SourceID                       string   `json:"source_id"`
	RubricVersion                  string   `json:"rubric_version"`
	ReviewCount                    int64    `json:"review_count"`
	DocumentCount                  int64    `json:"document_count"`
	LegacyReviewCount              int64    `json:"legacy_review_count"`
	AverageQualityScore            *float64 `json:"average_quality_score,omitempty"`
	AverageLanguageQualityScore    *float64 `json:"average_language_quality_score,omitempty"`
	AverageCoherenceScore          *float64 `json:"average_coherence_score,omitempty"`
	AverageInformationDensityScore *float64 `json:"average_information_density_score,omitempty"`
	AverageCleanlinessScore        *float64 `json:"average_cleanliness_score,omitempty"`
}
