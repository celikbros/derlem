package domain

import (
	"encoding/json"
	"time"
)

type SimilarityCalibrationRun struct {
	ID                     string          `json:"id"`
	ReportObjectSHA256     string          `json:"report_object_sha256"`
	SchemaVersion          string          `json:"schema_version"`
	Method                 string          `json:"method"`
	ContentPurpose         string          `json:"content_purpose"`
	SourceSnapshot         json.RawMessage `json:"source_snapshot"`
	SampledDocumentCount   int64           `json:"sampled_document_count"`
	EligibleDocumentCount  int64           `json:"eligible_document_count"`
	SimHashVersion         string          `json:"simhash_version"`
	ThresholdMax           int16           `json:"threshold_max"`
	PairCount              int             `json:"pair_count"`
	ReviewedPairCount      int             `json:"reviewed_pair_count"`
	IndependentReviewCount int             `json:"independent_review_count"`
	ConsensusPairCount     int             `json:"consensus_pair_count"`
	DisagreementPairCount  int             `json:"disagreement_pair_count"`
	CreatedAt              time.Time       `json:"created_at"`
}

type SimilarityReviewPair struct {
	ID                   string    `json:"id"`
	RunID                string    `json:"run_id"`
	PairRank             int       `json:"pair_rank"`
	HammingDistance      int16     `json:"hamming_distance"`
	LeftSourceID         string    `json:"left_source_id"`
	LeftSourceSHA256     string    `json:"left_source_sha256"`
	LeftSourceOrdinal    int64     `json:"left_source_ordinal"`
	LeftObjectSHA256     string    `json:"left_object_sha256"`
	LeftTextPreview      string    `json:"left_text_preview"`
	LeftTokenCount       int       `json:"left_token_count"`
	RightSourceID        string    `json:"right_source_id"`
	RightSourceSHA256    string    `json:"right_source_sha256"`
	RightSourceOrdinal   int64     `json:"right_source_ordinal"`
	RightObjectSHA256    string    `json:"right_object_sha256"`
	RightTextPreview     string    `json:"right_text_preview"`
	RightTokenCount      int       `json:"right_token_count"`
	ReviewCount          int       `json:"review_count"`
	ConsensusLabel       *string   `json:"consensus_label,omitempty"`
	HasDisagreement      bool      `json:"has_disagreement"`
	CurrentReviewerLabel *string   `json:"current_reviewer_label,omitempty"`
	CreatedAt            time.Time `json:"created_at"`
}

type SimilarityPairReview struct {
	ID         string    `json:"id"`
	PairID     string    `json:"pair_id"`
	ReviewerID string    `json:"reviewer_id"`
	Reviewer   string    `json:"reviewer"`
	Label      string    `json:"label"`
	Reason     *string   `json:"reason,omitempty"`
	CreatedAt  time.Time `json:"created_at"`
}

type SimilarityPairDetail struct {
	Pair         SimilarityReviewPair   `json:"pair"`
	LeftContent  string                 `json:"left_content"`
	RightContent string                 `json:"right_content"`
	Reviews      []SimilarityPairReview `json:"reviews"`
}

type ReviewSimilarityPairInput struct {
	Label  string  `json:"label"`
	Reason *string `json:"reason"`
}
