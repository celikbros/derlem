export type User = {
  id: string;
  email: string;
  roles: string[];
};

export type Source = {
  id: string;
  name: string;
  source_type: string;
  content_purpose: string;
  license: string;
  rights_status: string;
  language: string;
  domain: string;
  source_url?: string;
  license_evidence_ref?: string;
  lineage_ref: string;
  declared_sha256?: string;
  declared_byte_size?: number;
  declared_line_count?: number;
  source_metadata: Record<string, unknown>;
  object_sha256?: string;
  byte_size?: number;
  line_count?: number;
  document_count?: number;
  detected_encoding?: string;
  pii_status: string;
  risk_level: string;
  approval_status: string;
  version: number;
  created_by: string;
  created_at: string;
  updated_at: string;
};

export type Review = {
  id: string;
  source_id: string;
  reviewer_id: string;
  decision: "approved" | "rejected" | "sensitive_review";
  reason?: string;
  source_version: number;
  context: Record<string, unknown>;
  created_at: string;
};

export type PIIScan = {
  id: string;
  source_id: string;
  object_sha256: string;
  scanner_version: string;
  status: "clear" | "flagged" | "failed";
  findings: Record<string, number>;
  scanned_at: string;
};

export type BackgroundJob = {
  id: string;
  job_type: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  priority: number;
  result?: Record<string, unknown>;
  attempts: number;
  max_attempts: number;
  last_error?: string;
  created_at: string;
  updated_at: string;
  completed_at?: string;
};
