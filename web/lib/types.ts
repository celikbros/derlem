export type User = {
  id: string;
  email: string;
  roles: string[];
};

export type UserAccount = {
  id: string;
  email: string;
  display_name: string;
  status: string;
  roles: string[];
  created_at: string;
  updated_at: string;
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
  document_sampling_status: "not_sampled" | "resampling" | "sampled" | "failed";
  document_sample_generation: number;
  document_sampling_method: string;
  sampled_document_count: number;
  reviewed_document_count: number;
  approved_document_count: number;
  flagged_document_count: number;
  detected_encoding?: string;
  pii_status: string;
  duplicate_status: "not_checked" | "unique" | "duplicate";
  duplicate_of_source_id?: string;
  normalized_dedup_status: "not_checked" | "unique" | "duplicates_found" | "failed";
  normalized_duplicate_count: number;
  normalized_duplicate_source_count: number;
  risk_level: string;
  approval_status: string;
  version: number;
  created_by: string;
  created_at: string;
  updated_at: string;
};

export type Document = {
  id: string;
  source_id: string;
  source_ordinal: number;
  external_id?: string;
  current_object_sha256: string;
  text_preview: string;
  byte_size: number;
  char_count: number;
  status: "sampled" | "edited" | "approved" | "rejected" | "sensitive_review";
  current_version: number;
  sampling_method: string;
  risk_score: number;
  risk_reasons: string[];
  is_active: boolean;
  sample_generation: number;
  created_at: string;
  updated_at: string;
};

export type DocumentReview = {
  id: string;
  document_id: string;
  reviewer_id: string;
  decision: "approved" | "rejected" | "sensitive_review";
  reason?: string;
  rubric_version: "overall-v1" | "multidimensional-v1";
  quality_score: number;
  language_quality_score?: number;
  coherence_score?: number;
  information_density_score?: number;
  cleanliness_score?: number;
  document_version: number;
  object_sha256: string;
  context: Record<string, unknown>;
  created_at: string;
};

export type DocumentQualitySummary = {
  source_id: string;
  rubric_version: "multidimensional-v1";
  review_count: number;
  document_count: number;
  legacy_review_count: number;
  average_quality_score?: number;
  average_language_quality_score?: number;
  average_coherence_score?: number;
  average_information_density_score?: number;
  average_cleanliness_score?: number;
};

export type DocumentSampleGeneration = {
  source_id: string;
  generation: number;
  source_sha256: string;
  sampling_method: string;
  status: "active" | "superseded";
  sample_count: number;
  job_id?: string;
  created_at: string;
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

export type SimilarityCalibrationSource = {
  source_id: string;
  name: string;
  sha256: string;
};

export type SimilarityCalibrationRun = {
  id: string;
  report_object_sha256: string;
  schema_version: string;
  method: string;
  content_purpose: Source["content_purpose"];
  source_snapshot: SimilarityCalibrationSource[];
  sampled_document_count: number;
  eligible_document_count: number;
  simhash_version: string;
  threshold_max: number;
  pair_count: number;
  reviewed_pair_count: number;
  independent_review_count: number;
  consensus_pair_count: number;
  disagreement_pair_count: number;
  created_at: string;
};

export type SimilarityReviewLabel =
  | "exact_duplicate"
  | "near_duplicate"
  | "related"
  | "different"
  | "uncertain";

export type SimilarityReviewPair = {
  id: string;
  run_id: string;
  pair_rank: number;
  hamming_distance: number;
  left_source_id: string;
  left_source_sha256: string;
  left_source_ordinal: number;
  left_object_sha256: string;
  left_text_preview: string;
  left_token_count: number;
  right_source_id: string;
  right_source_sha256: string;
  right_source_ordinal: number;
  right_object_sha256: string;
  right_text_preview: string;
  right_token_count: number;
  review_count: number;
  consensus_label?: SimilarityReviewLabel;
  has_disagreement: boolean;
  current_reviewer_label?: SimilarityReviewLabel;
  created_at: string;
};

export type SimilarityPairReview = {
  id: string;
  pair_id: string;
  reviewer_id: string;
  reviewer: string;
  label: SimilarityReviewLabel;
  reason?: string;
  created_at: string;
};

export type SimilarityPairDetail = {
  pair: SimilarityReviewPair;
  left_content: string;
  right_content: string;
  reviews: SimilarityPairReview[];
};

export type ReleaseSource = {
  source_id: string;
  source_sha256: string;
  source_version: number;
  source_name: string;
  source_type: string;
  license: string;
  rights_status: string;
  language: string;
  domain: string;
  lineage_ref: string;
  byte_size?: number;
  line_count?: number;
  media_type?: string;
  added_at: string;
};

export type Release = {
  id: string;
  name: string;
  version: string;
  content_purpose: Source["content_purpose"];
  status: "draft" | "frozen" | "superseded";
  manifest_object_sha256?: string;
  manifest_sha256?: string;
  gate_results: Record<string, unknown>;
  created_by: string;
  frozen_by?: string;
  created_at: string;
  frozen_at?: string;
  sources: ReleaseSource[];
  exports: ReleaseExport[];
};

export type ReleaseExport = {
  id: string;
  release_id: string;
  format: "jsonl" | "txt";
  status: "queued" | "building" | "ready" | "failed";
  object_sha256?: string;
  manifest_object_sha256?: string;
  record_count?: number;
  byte_size?: number;
  estimated_token_count?: number;
  token_estimate_lower_bound?: number;
  token_estimate_upper_bound?: number;
  token_estimate_method?: string;
  record_type_counts?: Record<string, number>;
  last_error?: string;
  created_by: string;
  created_at: string;
  completed_at?: string;
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
