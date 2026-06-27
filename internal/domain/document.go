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
	CreatedAt           time.Time `json:"created_at"`
	UpdatedAt           time.Time `json:"updated_at"`
}

type UpdateDocumentInput struct {
	Content string  `json:"content"`
	Version int64   `json:"version"`
	Reason  *string `json:"reason"`
}

type ReviewDocumentInput struct {
	Decision        string  `json:"decision"`
	Reason          *string `json:"reason"`
	QualityScore    int16   `json:"quality_score"`
	DocumentVersion int64   `json:"document_version"`
}

type BulkReviewDocumentItem struct {
	DocumentID      string `json:"document_id"`
	DocumentVersion int64  `json:"document_version"`
}

type BulkReviewDocumentsInput struct {
	Documents    []BulkReviewDocumentItem `json:"documents"`
	Decision     string                   `json:"decision"`
	Reason       *string                  `json:"reason"`
	QualityScore int16                    `json:"quality_score"`
}

type BulkDocumentReviewResult struct {
	Source    Source           `json:"source"`
	Documents []Document       `json:"documents"`
	Reviews   []DocumentReview `json:"reviews"`
}

type DocumentReview struct {
	ID              string          `json:"id"`
	DocumentID      string          `json:"document_id"`
	ReviewerID      string          `json:"reviewer_id"`
	Decision        string          `json:"decision"`
	Reason          *string         `json:"reason,omitempty"`
	QualityScore    int16           `json:"quality_score"`
	DocumentVersion int64           `json:"document_version"`
	ObjectSHA256    string          `json:"object_sha256"`
	Context         json.RawMessage `json:"context"`
	CreatedAt       time.Time       `json:"created_at"`
}
