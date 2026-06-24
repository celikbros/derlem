package domain

import "time"

var ContentPurposes = map[string]struct{}{
	"pretrain":      {},
	"instruction":   {},
	"preference":    {},
	"eval":          {},
	"holdout":       {},
	"post_training": {},
}

var RightsStatuses = map[string]struct{}{
	"unknown":    {},
	"cleared":    {},
	"restricted": {},
	"blocked":    {},
}

type Source struct {
	ID                     string    `json:"id"`
	Name                   string    `json:"name"`
	SourceType             string    `json:"source_type"`
	ContentPurpose         string    `json:"content_purpose"`
	License                string    `json:"license"`
	RightsStatus           string    `json:"rights_status"`
	Language               string    `json:"language"`
	Domain                 string    `json:"domain"`
	SourceURL              *string   `json:"source_url,omitempty"`
	LicenseEvidenceRef     *string   `json:"license_evidence_ref,omitempty"`
	LineageRef             string    `json:"lineage_ref"`
	DeclaredSHA256         *string   `json:"declared_sha256,omitempty"`
	DeclaredByteSize       *int64    `json:"declared_byte_size,omitempty"`
	DeclaredLineCount      *int64    `json:"declared_line_count,omitempty"`
	SourceMetadata         any       `json:"source_metadata"`
	ObjectSHA256           *string   `json:"object_sha256,omitempty"`
	ByteSize               *int64    `json:"byte_size,omitempty"`
	LineCount              *int64    `json:"line_count,omitempty"`
	DocumentCount          *int64    `json:"document_count,omitempty"`
	DocumentSamplingStatus string    `json:"document_sampling_status"`
	SampledDocumentCount   int64     `json:"sampled_document_count"`
	DetectedEncoding       *string   `json:"detected_encoding,omitempty"`
	PIIStatus              string    `json:"pii_status"`
	DuplicateStatus        string    `json:"duplicate_status"`
	DuplicateOfSourceID    *string   `json:"duplicate_of_source_id,omitempty"`
	RiskLevel              string    `json:"risk_level"`
	ApprovalStatus         string    `json:"approval_status"`
	Version                int64     `json:"version"`
	CreatedBy              string    `json:"created_by"`
	CreatedAt              time.Time `json:"created_at"`
	UpdatedAt              time.Time `json:"updated_at"`
}

type CreateSourceInput struct {
	Name               string  `json:"name"`
	SourceType         string  `json:"source_type"`
	ContentPurpose     string  `json:"content_purpose"`
	License            string  `json:"license"`
	RightsStatus       string  `json:"rights_status"`
	Language           string  `json:"language"`
	Domain             string  `json:"domain"`
	SourceURL          *string `json:"source_url"`
	LicenseEvidenceRef *string `json:"license_evidence_ref"`
	LineageRef         string  `json:"lineage_ref"`
}
