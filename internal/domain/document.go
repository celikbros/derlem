package domain

import "time"

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
