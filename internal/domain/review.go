package domain

import (
	"encoding/json"
	"time"
)

type UpdateSourceInput struct {
	Name               string  `json:"name"`
	SourceType         string  `json:"source_type"`
	License            string  `json:"license"`
	RightsStatus       string  `json:"rights_status"`
	Language           string  `json:"language"`
	Domain             string  `json:"domain"`
	SourceURL          *string `json:"source_url"`
	LicenseEvidenceRef *string `json:"license_evidence_ref"`
	LineageRef         string  `json:"lineage_ref"`
	Version            int64   `json:"version"`
}

type ReviewInput struct {
	Decision string  `json:"decision"`
	Reason   *string `json:"reason"`
}

type Review struct {
	ID            string          `json:"id"`
	SourceID      string          `json:"source_id"`
	ReviewerID    string          `json:"reviewer_id"`
	Decision      string          `json:"decision"`
	Reason        *string         `json:"reason,omitempty"`
	SourceVersion int64           `json:"source_version"`
	Context       json.RawMessage `json:"context"`
	CreatedAt     time.Time       `json:"created_at"`
}

type PIIScan struct {
	ID             string          `json:"id"`
	SourceID       string          `json:"source_id"`
	ObjectSHA256   string          `json:"object_sha256"`
	ScannerVersion string          `json:"scanner_version"`
	Status         string          `json:"status"`
	Findings       json.RawMessage `json:"findings"`
	ScannedAt      time.Time       `json:"scanned_at"`
}

type BackgroundJob struct {
	ID          string          `json:"id"`
	JobType     string          `json:"job_type"`
	Status      string          `json:"status"`
	Priority    int16           `json:"priority"`
	Result      json.RawMessage `json:"result,omitempty"`
	Attempts    int             `json:"attempts"`
	MaxAttempts int             `json:"max_attempts"`
	LastError   *string         `json:"last_error,omitempty"`
	CreatedAt   time.Time       `json:"created_at"`
	UpdatedAt   time.Time       `json:"updated_at"`
	CompletedAt *time.Time      `json:"completed_at,omitempty"`
}
