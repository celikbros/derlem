package domain

import (
	"encoding/json"
	"time"
)

type Release struct {
	ID                   string          `json:"id"`
	Name                 string          `json:"name"`
	Version              string          `json:"version"`
	ContentPurpose       string          `json:"content_purpose"`
	Status               string          `json:"status"`
	ManifestObjectSHA256 *string         `json:"manifest_object_sha256,omitempty"`
	ManifestSHA256       *string         `json:"manifest_sha256,omitempty"`
	GateResults          json.RawMessage `json:"gate_results"`
	CreatedBy            string          `json:"created_by"`
	FrozenBy             *string         `json:"frozen_by,omitempty"`
	CreatedAt            time.Time       `json:"created_at"`
	FrozenAt             *time.Time      `json:"frozen_at,omitempty"`
	Sources              []ReleaseSource `json:"sources"`
}

type ReleaseSource struct {
	SourceID      string    `json:"source_id"`
	SourceSHA256  string    `json:"source_sha256"`
	SourceVersion int64     `json:"source_version"`
	SourceName    string    `json:"source_name"`
	SourceType    string    `json:"source_type"`
	License       string    `json:"license"`
	RightsStatus  string    `json:"rights_status"`
	Language      string    `json:"language"`
	Domain        string    `json:"domain"`
	LineageRef    string    `json:"lineage_ref"`
	ByteSize      *int64    `json:"byte_size,omitempty"`
	LineCount     *int64    `json:"line_count,omitempty"`
	MediaType     *string   `json:"media_type,omitempty"`
	AddedAt       time.Time `json:"added_at"`
}

type CreateReleaseInput struct {
	Name           string   `json:"name"`
	Version        string   `json:"version"`
	ContentPurpose string   `json:"content_purpose"`
	SourceIDs      []string `json:"source_ids"`
}
