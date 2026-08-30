package repository

import (
	"context"
	"crypto/rand"
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"strings"
	"time"

	"github.com/celikbros/derlem/internal/domain"
	"github.com/celikbros/derlem/internal/storage"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

const documentReviewClaimLease = 15 * time.Minute

const (
	reviewCampaignArtifactKind         = "contract_bundle"
	trustedEmptyProfileConfigSHA256    = "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"
	trustedProfileConfigSchemaSHA256   = "cd1a463c46d6264134447db17a8c3c7abe5b9a2488c6d759fea66da1f96b133e"
	trustedProfileImplementationDigest = "8a2093eafc5bca99285f51dbc2fb2e08c4463d2e64cc3e565640c5d1aa6912a5"
)

var uuidPattern = regexp.MustCompile(`(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`)

type Documents struct {
	pool *pgxpool.Pool
}

func NewDocuments(pool *pgxpool.Pool) *Documents {
	return &Documents{pool: pool}
}

type reviewCampaignBinding struct {
	ID            string
	RubricVersion string
}

type reviewCampaignPins struct {
	DataProfileKey              string
	DataProfileVersion          string
	ContentPurpose              string
	ProfileConfigArtifactKind   string
	ProfileConfigSHA256         string
	ProfileConfigSchemaKind     string
	ProfileConfigSchemaSHA256   string
	ProfileImplementationKey    string
	ProfileImplementationDigest string
	RubricKey                   string
	RubricVersion               string
	PurposeContractVersion      string
	ProtocolKey                 string
	ProtocolVersion             string
	PIIPolicyKind               string
	PIIPolicyKey                string
	PIIPolicyVersion            string
	DedupPolicyKind             string
	DedupPolicyKey              string
	DedupPolicyVersion          string
	LeakagePolicyKind           string
	LeakagePolicyKey            string
	LeakagePolicyVersion        string
	PurposeContractArtifactKind string
	PurposeContractSHA256       string
	ImplementationBundleSHA256  string
}

func trustedPurposeContractVersion(
	profileKey, profileVersion, contentPurpose string,
) (string, bool) {
	if profileVersion != "1" ||
		(profileKey != "legacy-auto" && profileKey != "text-document") {
		return "", false
	}
	switch contentPurpose {
	case "pretrain", "instruction", "preference", "eval", "holdout", "post_training":
		return "1", true
	default:
		return "", false
	}
}

func trustedProfileImplementationKey(profileKey string) (string, bool) {
	switch profileKey {
	case "legacy-auto":
		return "legacy-current-v1", true
	case "text-document":
		return "text-document-v1", true
	default:
		return "", false
	}
}

func loadReviewCampaignPins(
	ctx context.Context,
	tx pgx.Tx,
	sourceID string,
	sampleGeneration int64,
) (reviewCampaignPins, error) {
	var pins reviewCampaignPins
	if err := tx.QueryRow(ctx, `
		SELECT source.data_profile_key, source.data_profile_version,
			source.content_purpose, source.profile_config_artifact_kind,
			source.profile_config_sha256
		FROM sources AS source
		JOIN document_sample_generations AS generation
		  ON generation.source_id = source.id
		 AND generation.generation = source.document_sample_generation
		 AND generation.status = 'active'
		WHERE source.id = $1::uuid
		  AND source.document_sample_generation = $2
	`, sourceID, sampleGeneration).Scan(
		&pins.DataProfileKey, &pins.DataProfileVersion,
		&pins.ContentPurpose, &pins.ProfileConfigArtifactKind,
		&pins.ProfileConfigSHA256,
	); errors.Is(err, pgx.ErrNoRows) {
		return reviewCampaignPins{}, &GateError{Reasons: []string{"active_sample_generation_missing"}}
	} else if err != nil {
		return reviewCampaignPins{}, err
	}

	contractVersion, trusted := trustedPurposeContractVersion(
		pins.DataProfileKey, pins.DataProfileVersion, pins.ContentPurpose,
	)
	if !trusted {
		return reviewCampaignPins{}, &GateError{Reasons: []string{"review_contract_not_trusted"}}
	}
	if pins.ProfileConfigArtifactKind != "profile_config" ||
		pins.ProfileConfigSHA256 != trustedEmptyProfileConfigSHA256 {
		return reviewCampaignPins{}, &GateError{Reasons: []string{"profile_config_not_trusted"}}
	}
	trustedImplementationKey, trusted := trustedProfileImplementationKey(
		pins.DataProfileKey,
	)
	if !trusted {
		return reviewCampaignPins{}, &GateError{Reasons: []string{"data_profile_not_trusted"}}
	}
	pins.PurposeContractVersion = contractVersion
	if err := tx.QueryRow(ctx, `
		SELECT profile.profile_config_schema_artifact_kind,
			profile.profile_config_schema_sha256,
			profile.implementation_key, profile.implementation_digest,
			profile.rubric_key, profile.rubric_version,
			contract.protocol_key, contract.protocol_version,
			contract.pii_policy_kind, contract.pii_policy_key,
			contract.pii_policy_version,
			contract.dedup_policy_kind, contract.dedup_policy_key,
			contract.dedup_policy_version,
			contract.leakage_policy_kind, contract.leakage_policy_key,
			contract.leakage_policy_version,
			contract.spec_artifact_kind, contract.spec_sha256,
			contract.implementation_bundle_sha256
		FROM data_profile_versions AS profile
		JOIN profile_purpose_contract_versions AS contract
		  ON contract.data_profile_key = profile.data_profile_key
		 AND contract.data_profile_version = profile.data_profile_version
		WHERE profile.data_profile_key = $1
		  AND profile.data_profile_version = $2
		  AND contract.content_purpose = $3
		  AND contract.purpose_contract_version = $4
	`, pins.DataProfileKey, pins.DataProfileVersion, pins.ContentPurpose,
		pins.PurposeContractVersion).Scan(
		&pins.ProfileConfigSchemaKind, &pins.ProfileConfigSchemaSHA256,
		&pins.ProfileImplementationKey, &pins.ProfileImplementationDigest,
		&pins.RubricKey, &pins.RubricVersion,
		&pins.ProtocolKey, &pins.ProtocolVersion,
		&pins.PIIPolicyKind, &pins.PIIPolicyKey, &pins.PIIPolicyVersion,
		&pins.DedupPolicyKind, &pins.DedupPolicyKey, &pins.DedupPolicyVersion,
		&pins.LeakagePolicyKind, &pins.LeakagePolicyKey,
		&pins.LeakagePolicyVersion, &pins.PurposeContractArtifactKind,
		&pins.PurposeContractSHA256, &pins.ImplementationBundleSHA256,
	); errors.Is(err, pgx.ErrNoRows) {
		return reviewCampaignPins{}, &GateError{Reasons: []string{"review_contract_not_found"}}
	} else if err != nil {
		return reviewCampaignPins{}, err
	}
	if pins.ProfileConfigSchemaKind != "profile_config_schema" ||
		pins.ProfileConfigSchemaSHA256 != trustedProfileConfigSchemaSHA256 ||
		pins.ProfileImplementationKey != trustedImplementationKey ||
		pins.ProfileImplementationDigest != trustedProfileImplementationDigest {
		return reviewCampaignPins{}, &GateError{Reasons: []string{"data_profile_not_trusted"}}
	}
	if pins.RubricVersion != domain.MultidimensionalQualityRubric {
		return reviewCampaignPins{}, &GateError{Reasons: []string{"unsupported_review_rubric"}}
	}
	return pins, nil
}

func ensureReviewCampaign(
	ctx context.Context,
	tx pgx.Tx,
	sourceID, actorID string,
	sampleGeneration int64,
) (reviewCampaignBinding, error) {
	if _, err := tx.Exec(ctx, `
		SELECT pg_advisory_xact_lock(
			hashtextextended(
				'review-campaign:' || $1::text || ':' || $2::bigint::text, 0
			)
		)
	`, sourceID, sampleGeneration); err != nil {
		return reviewCampaignBinding{}, err
	}
	pins, err := loadReviewCampaignPins(
		ctx, tx, sourceID, sampleGeneration,
	)
	if err != nil {
		return reviewCampaignBinding{}, err
	}

	var campaignID string
	var campaignContractSHA256 string
	created := true
	err = tx.QueryRow(ctx, `
		INSERT INTO review_campaigns(
			source_id, sample_generation,
			data_profile_key, data_profile_version, content_purpose,
			profile_config_artifact_kind, profile_config_sha256,
			rubric_key, rubric_version, purpose_contract_version,
			protocol_key, protocol_version,
			pii_policy_kind, pii_policy_key, pii_policy_version,
			dedup_policy_kind, dedup_policy_key, dedup_policy_version,
			leakage_policy_kind, leakage_policy_key, leakage_policy_version,
			purpose_contract_artifact_kind, purpose_contract_sha256,
			campaign_contract_artifact_kind, campaign_contract_sha256,
			implementation_bundle_sha256, created_by
		)
		VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
			$21, $22, $23, $24, $25, $26, $27
		)
		ON CONFLICT ON CONSTRAINT review_campaigns_contract_identity_unique
		DO NOTHING
		RETURNING id::text, campaign_contract_sha256
	`, sourceID, sampleGeneration,
		pins.DataProfileKey, pins.DataProfileVersion, pins.ContentPurpose,
		pins.ProfileConfigArtifactKind, pins.ProfileConfigSHA256,
		pins.RubricKey, pins.RubricVersion, pins.PurposeContractVersion,
		pins.ProtocolKey, pins.ProtocolVersion,
		pins.PIIPolicyKind, pins.PIIPolicyKey, pins.PIIPolicyVersion,
		pins.DedupPolicyKind, pins.DedupPolicyKey, pins.DedupPolicyVersion,
		pins.LeakagePolicyKind, pins.LeakagePolicyKey, pins.LeakagePolicyVersion,
		pins.PurposeContractArtifactKind, pins.PurposeContractSHA256,
		reviewCampaignArtifactKind, nil,
		pins.ImplementationBundleSHA256, actorID,
	).Scan(&campaignID, &campaignContractSHA256)
	if errors.Is(err, pgx.ErrNoRows) {
		created = false
		err = tx.QueryRow(ctx, `
			SELECT id::text, campaign_contract_sha256
			FROM review_campaigns
			WHERE source_id = $1::uuid
			  AND sample_generation = $2
			  AND data_profile_key = $3
			  AND data_profile_version = $4
			  AND content_purpose = $5
			  AND purpose_contract_version = $6
		`, sourceID, sampleGeneration, pins.DataProfileKey,
			pins.DataProfileVersion, pins.ContentPurpose,
			pins.PurposeContractVersion,
		).Scan(&campaignID, &campaignContractSHA256)
	}
	if err != nil {
		return reviewCampaignBinding{}, fmt.Errorf("get or create review campaign: %w", err)
	}
	if created {
		details, _ := json.Marshal(map[string]any{
			"review_campaign_id":       campaignID,
			"sample_generation":        sampleGeneration,
			"data_profile_key":         pins.DataProfileKey,
			"data_profile_version":     pins.DataProfileVersion,
			"content_purpose":          pins.ContentPurpose,
			"purpose_contract_version": pins.PurposeContractVersion,
			"rubric_key":               pins.RubricKey,
			"rubric_version":           pins.RubricVersion,
			"protocol_key":             pins.ProtocolKey,
			"protocol_version":         pins.ProtocolVersion,
		})
		if _, err := tx.Exec(ctx, `
			INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
			VALUES ($1, 'review_campaign.opened', 'review_campaign', $2, $3::jsonb)
		`, actorID, campaignID, details); err != nil {
			return reviewCampaignBinding{}, fmt.Errorf("audit review campaign open: %w", err)
		}
	}
	return reviewCampaignBinding{
		ID: campaignID, RubricVersion: pins.RubricVersion,
	}, nil
}

func (r *Documents) ListBySource(ctx context.Context, sourceID string, limit int) ([]domain.Document, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT `+documentColumns+`
		FROM documents
		WHERE source_id = $1 AND is_active
		ORDER BY source_ordinal ASC
		LIMIT $2
	`, sourceID, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	documents := make([]domain.Document, 0, limit)
	for rows.Next() {
		document, err := scanDocument(rows)
		if err != nil {
			return nil, err
		}
		documents = append(documents, document)
	}
	return documents, rows.Err()
}

func (r *Documents) ListSampleGenerations(ctx context.Context, sourceID string) ([]domain.DocumentSampleGeneration, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT source_id::text, generation, source_sha256, sampling_method,
			status, sample_count, job_id::text, created_at
		FROM document_sample_generations
		WHERE source_id = $1
		ORDER BY generation DESC
	`, sourceID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	generations := []domain.DocumentSampleGeneration{}
	for rows.Next() {
		var generation domain.DocumentSampleGeneration
		if err := rows.Scan(
			&generation.SourceID, &generation.Generation, &generation.SourceSHA256,
			&generation.SamplingMethod, &generation.Status, &generation.SampleCount,
			&generation.JobID, &generation.CreatedAt,
		); err != nil {
			return nil, err
		}
		generations = append(generations, generation)
	}
	return generations, rows.Err()
}

func (r *Documents) QueueResample(ctx context.Context, sourceID, actorID string) (string, error) {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return "", err
	}
	defer tx.Rollback(ctx)

	var objectSHA256 *string
	var samplingStatus, samplingMethod, approvalStatus string
	var generation, reviewedCount int64
	if err := tx.QueryRow(ctx, `
		SELECT object_sha256, document_sampling_status, document_sample_generation,
			document_sampling_method, reviewed_document_count, approval_status
		FROM sources
		WHERE id = $1
		FOR UPDATE
	`, sourceID).Scan(
		&objectSHA256, &samplingStatus, &generation, &samplingMethod,
		&reviewedCount, &approvalStatus,
	); errors.Is(err, pgx.ErrNoRows) {
		return "", ErrNotFound
	} else if err != nil {
		return "", err
	}

	reasons := []string{}
	if objectSHA256 == nil || samplingStatus != "sampled" {
		reasons = append(reasons, "source_not_sampled")
	}
	sourceReviewStarted := reviewedCount > 0 || approvalStatus == "approved_source" ||
		approvalStatus == "release_candidate" || approvalStatus == "rejected" ||
		approvalStatus == "quarantined"

	var activeCount, unsafeCount, documentReviewCount, sourceReviewCount int64
	if err := tx.QueryRow(ctx, `
		SELECT
			count(*) FILTER (WHERE document.is_active),
			count(*) FILTER (WHERE document.is_active AND (
				document.current_version <> 1 OR document.status <> 'sampled'
			)),
			(SELECT count(*)
			 FROM document_reviews AS review
			 JOIN documents AS reviewed_document ON reviewed_document.id = review.document_id
			 WHERE reviewed_document.source_id = $1),
			(SELECT count(*) FROM reviews AS review WHERE review.source_id = $1)
		FROM documents AS document
		WHERE document.source_id = $1
	`, sourceID).Scan(
		&activeCount, &unsafeCount, &documentReviewCount, &sourceReviewCount,
	); err != nil {
		return "", err
	}
	if sourceReviewStarted || sourceReviewCount > 0 {
		reasons = append(reasons, "source_review_already_started")
	}
	if activeCount == 0 {
		reasons = append(reasons, "active_sample_missing")
	}
	if unsafeCount > 0 {
		reasons = append(reasons, "sample_documents_changed")
	}
	if documentReviewCount > 0 {
		reasons = append(reasons, "sample_reviews_exist")
	}
	var activeClaimCount int64
	if err := tx.QueryRow(ctx, `
		SELECT count(*)
		FROM document_review_claims AS claim
		JOIN documents AS document ON document.id = claim.document_id
		WHERE document.source_id = $1 AND claim.expires_at > now()
	`, sourceID).Scan(&activeClaimCount); err != nil {
		return "", err
	}
	if activeClaimCount > 0 {
		reasons = append(reasons, "sample_review_claims_active")
	}
	if len(reasons) > 0 {
		return "", &GateError{Reasons: reasons}
	}

	var jobID string
	err = tx.QueryRow(ctx, `
		INSERT INTO background_jobs(job_type, priority, payload, created_by)
		VALUES (
			'resample_documents', 55,
			jsonb_build_object(
				'source_id', $1::text,
				'object_sha256', $2::text,
				'previous_generation', $3::bigint,
				'previous_sampling_method', $4::text,
				'requested_by', $5::text
			),
			$5::uuid
		)
		ON CONFLICT DO NOTHING
		RETURNING id::text
	`, sourceID, *objectSHA256, generation, samplingMethod, actorID).Scan(&jobID)
	if errors.Is(err, pgx.ErrNoRows) {
		return "", ErrConflict
	}
	if err != nil {
		return "", err
	}

	updated, err := tx.Exec(ctx, `
		UPDATE sources
		SET document_sampling_status = 'resampling'
		WHERE id = $1 AND document_sampling_status = 'sampled'
	`, sourceID)
	if err != nil {
		return "", err
	}
	if updated.RowsAffected() != 1 {
		return "", ErrConflict
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES (
			$1, 'source.document_resample_queued', 'source', $2,
			jsonb_build_object(
				'job_id', $3::text, 'object_sha256', $4::text,
				'previous_generation', $5::bigint,
				'previous_sampling_method', $6::text,
				'active_sample_count', $7::bigint
			)
		)
	`, actorID, sourceID, jobID, *objectSHA256, generation, samplingMethod, activeCount); err != nil {
		return "", fmt.Errorf("audit document resample queue: %w", err)
	}
	if err := tx.Commit(ctx); err != nil {
		return "", err
	}
	return jobID, nil
}

func (r *Documents) Get(ctx context.Context, id string) (domain.Document, error) {
	document, err := scanDocument(r.pool.QueryRow(ctx,
		"SELECT "+documentColumns+" FROM documents WHERE id = $1", id,
	))
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.Document{}, ErrNotFound
	}
	return document, err
}

func (r *Documents) ClaimForReview(
	ctx context.Context,
	sourceID, actorID string,
	limit int,
	allowSelfReview bool,
) (domain.DocumentReviewClaim, error) {
	if limit < 1 || limit > 200 {
		return domain.DocumentReviewClaim{}, &GateError{Reasons: []string{"invalid_claim_limit"}}
	}
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return domain.DocumentReviewClaim{}, err
	}
	defer tx.Rollback(ctx)

	var sourceCreator, samplingStatus string
	var sampleGeneration int64
	// Take the source row before either claim advisory lock.  Creating a review
	// campaign validates its pins in a trigger that also locks this source FOR
	// UPDATE.  A weaker lock here lets concurrent callers each retain FOR SHARE
	// while one waits on the reviewer/campaign advisory lock and the other waits
	// to upgrade the source lock, forming a deadlock.  This establishes the
	// global claim order as source -> reviewer -> campaign -> documents/claims;
	// the trigger's source lock is then re-entrant for this transaction.
	if err := tx.QueryRow(ctx,
		`SELECT created_by::text, document_sampling_status,
			document_sample_generation
		FROM sources WHERE id = $1 FOR UPDATE`, sourceID,
	).Scan(&sourceCreator, &samplingStatus, &sampleGeneration); errors.Is(err, pgx.ErrNoRows) {
		return domain.DocumentReviewClaim{}, ErrNotFound
	} else if err != nil {
		return domain.DocumentReviewClaim{}, err
	}
	if sourceCreator == actorID && !allowSelfReview {
		return domain.DocumentReviewClaim{}, ErrSelfReview
	}
	if samplingStatus != "sampled" || sampleGeneration < 1 {
		return domain.DocumentReviewClaim{}, &GateError{Reasons: []string{"source_not_sampled"}}
	}
	// A reviewer can have only one active package per source. Serializing only
	// this reviewer/source pair prevents two concurrent acquire requests (for
	// example a double click after refresh) from allocating disjoint packages.
	if _, err := tx.Exec(ctx, `
		SELECT pg_advisory_xact_lock(hashtextextended($1::text || ':' || $2::text, 0))
	`, sourceID, actorID); err != nil {
		return domain.DocumentReviewClaim{}, err
	}

	var expiresAt time.Time
	if err := tx.QueryRow(ctx, `
		SELECT now() + make_interval(secs => $1)
	`, int(documentReviewClaimLease.Seconds())).Scan(&expiresAt); err != nil {
		return domain.DocumentReviewClaim{}, err
	}
	resumedClaim, duplicateClaimCount, resumed, err := resumeActiveReviewClaim(
		ctx, tx, sourceID, actorID, sampleGeneration, expiresAt,
	)
	if err != nil {
		return domain.DocumentReviewClaim{}, err
	}
	if resumed {
		details, _ := json.Marshal(map[string]any{
			"document_count":                 len(resumedClaim.Documents),
			"expires_at":                     resumedClaim.ExpiresAt,
			"released_duplicate_claim_count": duplicateClaimCount,
			"review_campaign_id":             resumedClaim.ReviewCampaignID,
		})
		if _, err := tx.Exec(ctx, `
			INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
			VALUES ($1, 'documents.review_claim_resumed', 'source', $2, $3::jsonb)
		`, actorID, sourceID, details); err != nil {
			return domain.DocumentReviewClaim{}, fmt.Errorf("audit document review claim resume: %w", err)
		}
		if err := tx.Commit(ctx); err != nil {
			return domain.DocumentReviewClaim{}, err
		}
		return resumedClaim, nil
	}

	campaign, err := ensureReviewCampaign(
		ctx, tx, sourceID, actorID, sampleGeneration,
	)
	if err != nil {
		return domain.DocumentReviewClaim{}, err
	}

	claimToken, err := newUUID()
	if err != nil {
		return domain.DocumentReviewClaim{}, fmt.Errorf("generate document review claim token: %w", err)
	}
	rows, err := tx.Query(ctx, `
		WITH candidates AS (
			SELECT document.id
			FROM documents AS document
			LEFT JOIN document_review_claims AS active_claim
			  ON active_claim.document_id = document.id
			 AND active_claim.expires_at > now()
			WHERE document.source_id = $1
			  AND document.is_active
			  AND document.sample_generation = $6
			  AND document.status IN ('sampled', 'edited')
			  AND active_claim.document_id IS NULL
			ORDER BY document.risk_score DESC, document.source_ordinal ASC
			FOR UPDATE OF document SKIP LOCKED
			LIMIT $4
		)
		INSERT INTO document_review_claims(
			document_id, reviewer_id, claim_token, document_version,
			claimed_at, expires_at, review_campaign_id
		)
		SELECT document.id, $2::uuid, $3::uuid, document.current_version,
			now(), $5, $7::uuid
		FROM candidates
		JOIN documents AS document ON document.id = candidates.id
		ON CONFLICT (document_id) DO UPDATE
		SET reviewer_id = EXCLUDED.reviewer_id,
			claim_token = EXCLUDED.claim_token,
			document_version = EXCLUDED.document_version,
			claimed_at = EXCLUDED.claimed_at,
			expires_at = EXCLUDED.expires_at,
			review_campaign_id = EXCLUDED.review_campaign_id
		WHERE document_review_claims.expires_at <= now()
		RETURNING document_id::text
	`, sourceID, actorID, claimToken, limit, expiresAt,
		sampleGeneration, campaign.ID)
	if err != nil {
		return domain.DocumentReviewClaim{}, err
	}
	documentIDs := make([]string, 0, limit)
	for rows.Next() {
		var documentID string
		if err := rows.Scan(&documentID); err != nil {
			rows.Close()
			return domain.DocumentReviewClaim{}, err
		}
		documentIDs = append(documentIDs, documentID)
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		return domain.DocumentReviewClaim{}, err
	}
	rows.Close()

	documents := make([]domain.Document, 0, len(documentIDs))
	if len(documentIDs) > 0 {
		rows, err = tx.Query(ctx, `
			SELECT `+documentColumns+`
			FROM documents
			WHERE id = ANY($1::uuid[])
			ORDER BY risk_score DESC, source_ordinal ASC
		`, documentIDs)
		if err != nil {
			return domain.DocumentReviewClaim{}, err
		}
		for rows.Next() {
			document, err := scanDocument(rows)
			if err != nil {
				rows.Close()
				return domain.DocumentReviewClaim{}, err
			}
			documents = append(documents, document)
		}
		if err := rows.Err(); err != nil {
			rows.Close()
			return domain.DocumentReviewClaim{}, err
		}
		rows.Close()

		details, _ := json.Marshal(map[string]any{
			"document_count":     len(documents),
			"expires_at":         expiresAt,
			"review_campaign_id": campaign.ID,
		})
		if _, err := tx.Exec(ctx, `
			INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
			VALUES ($1, 'documents.review_claimed', 'source', $2, $3::jsonb)
		`, actorID, sourceID, details); err != nil {
			return domain.DocumentReviewClaim{}, fmt.Errorf("audit document review claim: %w", err)
		}
	}

	if err := tx.Commit(ctx); err != nil {
		return domain.DocumentReviewClaim{}, err
	}
	return domain.DocumentReviewClaim{
		ClaimToken:       claimToken,
		ReviewCampaignID: campaign.ID,
		ExpiresAt:        expiresAt,
		Documents:        documents,
		Resumed:          false,
	}, nil
}

// resumeActiveReviewClaim renews the most recently acquired, still-valid
// package for this reviewer/source. Older active tokens may exist from clients
// that reacquired after a refresh; those claims are released so they cannot
// remain stranded until lease expiry. The advisory lock in ClaimForReview
// serializes this operation with other acquire calls for the same pair.
func resumeActiveReviewClaim(
	ctx context.Context,
	tx pgx.Tx,
	sourceID, actorID string,
	sampleGeneration int64,
	expiresAt time.Time,
) (domain.DocumentReviewClaim, int64, bool, error) {
	var claimToken string
	var campaignID *string
	var campaignIsValid bool
	err := tx.QueryRow(ctx, `
		SELECT claim.claim_token::text,
			bool_and(claim.review_campaign_id IS NOT NULL)
				AND bool_and(campaign.id IS NOT NULL)
				AND bool_and(campaign.source_id = document.source_id)
				AND bool_and(campaign.sample_generation = document.sample_generation)
				AND bool_and(campaign.rubric_version = $4)
				AND count(DISTINCT claim.review_campaign_id) = 1,
			min(claim.review_campaign_id::text)
		FROM document_review_claims AS claim
		JOIN documents AS document ON document.id = claim.document_id
		LEFT JOIN review_campaigns AS campaign
		  ON campaign.id = claim.review_campaign_id
		WHERE claim.reviewer_id = $2::uuid
		  AND claim.expires_at > now()
		  AND document.source_id = $1::uuid
		  AND document.is_active
		  AND document.sample_generation = $3
		  AND document.status IN ('sampled', 'edited')
		  AND document.current_version = claim.document_version
		GROUP BY claim.claim_token
		ORDER BY max(claim.claimed_at) DESC, claim.claim_token ASC
		LIMIT 1
	`, sourceID, actorID, sampleGeneration,
		domain.MultidimensionalQualityRubric).Scan(
		&claimToken, &campaignIsValid, &campaignID,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.DocumentReviewClaim{}, 0, false, nil
	}
	if err != nil {
		return domain.DocumentReviewClaim{}, 0, false, err
	}
	if !campaignIsValid || campaignID == nil {
		var releasedCount int64
		if err := tx.QueryRow(ctx, `
			WITH released AS (
				DELETE FROM document_review_claims AS claim
				USING documents AS document
				WHERE document.id = claim.document_id
				  AND document.source_id = $1::uuid
				  AND claim.reviewer_id = $2::uuid
				  AND claim.expires_at > now()
				RETURNING claim.document_id
			)
			SELECT count(*) FROM released
		`, sourceID, actorID).Scan(&releasedCount); err != nil {
			return domain.DocumentReviewClaim{}, 0, false, err
		}
		return domain.DocumentReviewClaim{}, releasedCount, false, nil
	}

	var duplicateClaimCount int64
	if err := tx.QueryRow(ctx, `
		WITH released AS (
			DELETE FROM document_review_claims AS claim
			USING documents AS document
			WHERE document.id = claim.document_id
			  AND document.source_id = $1::uuid
			  AND claim.reviewer_id = $2::uuid
			  AND claim.expires_at > now()
			  AND claim.claim_token <> $3::uuid
			RETURNING claim.document_id
		)
		SELECT count(*) FROM released
	`, sourceID, actorID, claimToken).Scan(&duplicateClaimCount); err != nil {
		return domain.DocumentReviewClaim{}, 0, false, err
	}

	rows, err := tx.Query(ctx, `
		UPDATE document_review_claims AS claim
		SET expires_at = $3
		FROM documents AS document
		WHERE document.id = claim.document_id
		  AND document.source_id = $1::uuid
		  AND claim.reviewer_id = $2::uuid
		  AND claim.claim_token = $4::uuid
		  AND claim.expires_at > now()
		  AND claim.review_campaign_id IS NOT NULL
		  AND document.is_active
		  AND document.status IN ('sampled', 'edited')
		  AND document.current_version = claim.document_version
		RETURNING claim.document_id::text
	`, sourceID, actorID, expiresAt, claimToken)
	if err != nil {
		return domain.DocumentReviewClaim{}, 0, false, err
	}
	documentIDs := make([]string, 0)
	for rows.Next() {
		var documentID string
		if err := rows.Scan(&documentID); err != nil {
			rows.Close()
			return domain.DocumentReviewClaim{}, 0, false, err
		}
		documentIDs = append(documentIDs, documentID)
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		return domain.DocumentReviewClaim{}, 0, false, err
	}
	rows.Close()
	if len(documentIDs) == 0 {
		return domain.DocumentReviewClaim{}, duplicateClaimCount, false, nil
	}

	documents, err := listClaimDocuments(ctx, tx, documentIDs)
	if err != nil {
		return domain.DocumentReviewClaim{}, 0, false, err
	}
	return domain.DocumentReviewClaim{
		ClaimToken:       claimToken,
		ReviewCampaignID: *campaignID,
		ExpiresAt:        expiresAt,
		Documents:        documents,
		Resumed:          true,
	}, duplicateClaimCount, true, nil
}

func listClaimDocuments(ctx context.Context, tx pgx.Tx, documentIDs []string) ([]domain.Document, error) {
	documents := make([]domain.Document, 0, len(documentIDs))
	if len(documentIDs) == 0 {
		return documents, nil
	}
	rows, err := tx.Query(ctx, `
		SELECT `+documentColumns+`
		FROM documents
		WHERE id = ANY($1::uuid[])
		ORDER BY risk_score DESC, source_ordinal ASC
	`, documentIDs)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		document, err := scanDocument(rows)
		if err != nil {
			return nil, err
		}
		documents = append(documents, document)
	}
	return documents, rows.Err()
}

func (r *Documents) RenewReviewClaim(
	ctx context.Context,
	claimToken, actorID string,
) (domain.DocumentReviewClaimRenewal, error) {
	claimToken = strings.TrimSpace(claimToken)
	if !uuidPattern.MatchString(claimToken) {
		return domain.DocumentReviewClaimRenewal{}, ErrClaimLost
	}
	rows, err := r.pool.Query(ctx, `
		UPDATE document_review_claims AS claim
		SET expires_at = now() + make_interval(secs => $3)
		FROM documents AS document
		WHERE claim.claim_token = $1::uuid
		  AND claim.reviewer_id = $2::uuid
		  AND claim.expires_at > now()
		  AND claim.review_campaign_id IS NOT NULL
		  AND document.id = claim.document_id
		  AND document.is_active
		  AND document.status IN ('sampled', 'edited')
		  AND document.current_version = claim.document_version
		RETURNING claim.expires_at
	`, claimToken, actorID, int(documentReviewClaimLease.Seconds()))
	if err != nil {
		return domain.DocumentReviewClaimRenewal{}, err
	}
	defer rows.Close()
	var count int64
	var expiresAt time.Time
	for rows.Next() {
		if err := rows.Scan(&expiresAt); err != nil {
			return domain.DocumentReviewClaimRenewal{}, err
		}
		count++
	}
	if err := rows.Err(); err != nil {
		return domain.DocumentReviewClaimRenewal{}, err
	}
	if count == 0 {
		return domain.DocumentReviewClaimRenewal{}, ErrClaimLost
	}
	return domain.DocumentReviewClaimRenewal{ExpiresAt: expiresAt, DocumentCount: count}, nil
}

func (r *Documents) ReleaseReviewClaim(ctx context.Context, claimToken, actorID string) error {
	claimToken = strings.TrimSpace(claimToken)
	if !uuidPattern.MatchString(claimToken) {
		return ErrClaimLost
	}
	_, err := r.pool.Exec(ctx, `
		DELETE FROM document_review_claims
		WHERE claim_token = $1::uuid AND reviewer_id = $2::uuid
	`, claimToken, actorID)
	return err
}

func (r *Documents) UpdateContent(
	ctx context.Context,
	id string,
	expectedVersion int64,
	object storage.Object,
	textPreview string,
	charCount int64,
	reason *string,
	actorID string,
) (domain.Document, error) {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return domain.Document{}, err
	}
	defer tx.Rollback(ctx)

	// Release creation locks the source before it validates and locks the
	// source's sampled documents. Discover the parent without trusting that
	// read as state, then take the same source -> document lock order here. The
	// locked document lookup revalidates the relationship and prevents an edit
	// from retaining a document lock while waiting on a release-held source.
	var sourceID string
	if err := tx.QueryRow(ctx, `
		SELECT source_id::text FROM documents WHERE id = $1
	`, id).Scan(&sourceID); errors.Is(err, pgx.ErrNoRows) {
		return domain.Document{}, ErrNotFound
	} else if err != nil {
		return domain.Document{}, err
	}

	var lockedSourceID string
	if err := tx.QueryRow(ctx, `
		SELECT id::text FROM sources WHERE id = $1::uuid FOR UPDATE
	`, sourceID).Scan(&lockedSourceID); errors.Is(err, pgx.ErrNoRows) {
		return domain.Document{}, ErrConflict
	} else if err != nil {
		return domain.Document{}, err
	}

	before, err := scanDocument(tx.QueryRow(ctx,
		"SELECT "+documentColumns+" FROM documents WHERE id = $1 AND source_id = $2::uuid FOR UPDATE",
		id, lockedSourceID,
	))
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.Document{}, ErrConflict
	}
	if err != nil {
		return domain.Document{}, err
	}
	if !before.IsActive {
		return domain.Document{}, ErrConflict
	}
	if before.CurrentVersion != expectedVersion {
		return domain.Document{}, ErrConflict
	}

	if _, err := tx.Exec(ctx, `
		INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
		VALUES ($1, $2, $3, 'text/plain; charset=utf-8')
		ON CONFLICT (sha256) DO NOTHING
	`, object.SHA256, object.StorageKey, object.ByteSize); err != nil {
		return domain.Document{}, fmt.Errorf("register document object: %w", err)
	}

	nextVersion := before.CurrentVersion + 1
	updated, err := scanDocument(tx.QueryRow(ctx, `
		UPDATE documents
		SET current_object_sha256 = $1,
			text_preview = $2,
			byte_size = $3,
			char_count = $4,
			status = 'edited',
			current_version = $5,
			risk_score = 0,
			risk_reasons = '{}'::text[]
		WHERE id = $6 AND current_version = $7
		RETURNING `+documentColumns,
		object.SHA256, textPreview, object.ByteSize, charCount, nextVersion, id, expectedVersion,
	))
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.Document{}, ErrConflict
	}
	if err != nil {
		return domain.Document{}, fmt.Errorf("update document: %w", err)
	}

	reason = trimReason(reason)
	if _, err := tx.Exec(ctx, `
		INSERT INTO document_versions(
			document_id, version, object_sha256, byte_size, char_count,
			actor_type, created_by, reason
		)
		VALUES ($1, $2, $3, $4, $5, 'human', $6, $7)
	`, id, nextVersion, object.SHA256, object.ByteSize, charCount, actorID, reason); err != nil {
		return domain.Document{}, fmt.Errorf("insert document version: %w", err)
	}

	details, _ := json.Marshal(map[string]any{
		"source_id":     before.SourceID,
		"from_version":  before.CurrentVersion,
		"to_version":    nextVersion,
		"before_sha256": before.CurrentObjectSHA256,
		"after_sha256":  object.SHA256,
		"reason":        reason,
	})
	if _, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES ($1, 'document.edited', 'document', $2, $3::jsonb)
	`, actorID, id, details); err != nil {
		return domain.Document{}, fmt.Errorf("audit document edit: %w", err)
	}
	if err := refreshSourceDocumentReviewCounts(ctx, tx, before.SourceID, true); err != nil {
		return domain.Document{}, err
	}

	if err := tx.Commit(ctx); err != nil {
		return domain.Document{}, err
	}
	return updated, nil
}

func (r *Documents) Review(
	ctx context.Context,
	id string,
	input domain.ReviewDocumentInput,
	actorID string,
	allowSelfReview bool,
) (domain.Source, domain.Document, domain.DocumentReview, error) {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return domain.Source{}, domain.Document{}, domain.DocumentReview{}, err
	}
	defer tx.Rollback(ctx)

	// Release contract validation serializes evidence at the source boundary
	// before it locks sampled documents. Discovering the parent without a row
	// lock, then taking source -> document locks in that same order prevents a
	// concurrent review from forming a source/document deadlock with release
	// creation or freeze. The locked document query below revalidates the
	// relationship so the unlocked lookup is never trusted as state.
	var sourceID string
	if err := tx.QueryRow(ctx, `
		SELECT source_id::text FROM documents WHERE id = $1
	`, id).Scan(&sourceID); errors.Is(err, pgx.ErrNoRows) {
		return domain.Source{}, domain.Document{}, domain.DocumentReview{}, ErrNotFound
	} else if err != nil {
		return domain.Source{}, domain.Document{}, domain.DocumentReview{}, err
	}

	var sourceCreator string
	if err := tx.QueryRow(ctx, `
		SELECT created_by::text FROM sources WHERE id = $1 FOR UPDATE
	`, sourceID).Scan(&sourceCreator); errors.Is(err, pgx.ErrNoRows) {
		return domain.Source{}, domain.Document{}, domain.DocumentReview{}, ErrConflict
	} else if err != nil {
		return domain.Source{}, domain.Document{}, domain.DocumentReview{}, err
	}

	document, err := scanDocument(tx.QueryRow(ctx,
		"SELECT "+documentColumns+" FROM documents WHERE id = $1 AND source_id = $2 FOR UPDATE",
		id, sourceID,
	))
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.Source{}, domain.Document{}, domain.DocumentReview{}, ErrConflict
	}
	if err != nil {
		return domain.Source{}, domain.Document{}, domain.DocumentReview{}, err
	}
	if !document.IsActive {
		return domain.Source{}, domain.Document{}, domain.DocumentReview{}, ErrConflict
	}
	if document.Status != "sampled" && document.Status != "edited" {
		return domain.Source{}, domain.Document{}, domain.DocumentReview{}, ErrConflict
	}
	if document.CurrentVersion != input.DocumentVersion {
		return domain.Source{}, domain.Document{}, domain.DocumentReview{}, ErrConflict
	}

	if sourceCreator == actorID && !allowSelfReview {
		return domain.Source{}, domain.Document{}, domain.DocumentReview{}, ErrSelfReview
	}
	campaign, err := validateReviewClaim(
		ctx, tx, document, input.ClaimToken, actorID,
	)
	if err != nil {
		return domain.Source{}, domain.Document{}, domain.DocumentReview{}, err
	}

	nextStatus, reason, err := normalizeDocumentReview(
		input.Decision, input.Reason, input.DocumentQualityScores,
	)
	if err != nil {
		return domain.Source{}, domain.Document{}, domain.DocumentReview{}, err
	}
	updated, review, err := reviewDocumentTx(
		ctx, tx, document, input, nextStatus, reason, actorID, campaign,
	)
	if err != nil {
		return domain.Source{}, domain.Document{}, domain.DocumentReview{}, err
	}

	if err := refreshSourceDocumentReviewCounts(ctx, tx, document.SourceID, true); err != nil {
		return domain.Source{}, domain.Document{}, domain.DocumentReview{}, err
	}
	source, err := scanSource(tx.QueryRow(ctx,
		"SELECT "+sourceColumns+" FROM sources WHERE id = $1", document.SourceID,
	))
	if err != nil {
		return domain.Source{}, domain.Document{}, domain.DocumentReview{}, err
	}

	if err := tx.Commit(ctx); err != nil {
		return domain.Source{}, domain.Document{}, domain.DocumentReview{}, err
	}
	return source, updated, review, nil
}

func (r *Documents) BulkReview(
	ctx context.Context,
	sourceID string,
	input domain.BulkReviewDocumentsInput,
	actorID string,
	allowSelfReview bool,
) (domain.BulkDocumentReviewResult, error) {
	if len(input.Documents) == 0 || len(input.Documents) > 200 {
		return domain.BulkDocumentReviewResult{}, &GateError{Reasons: []string{"invalid_document_count"}}
	}
	input.ClaimToken = strings.TrimSpace(input.ClaimToken)
	if !uuidPattern.MatchString(input.ClaimToken) {
		return domain.BulkDocumentReviewResult{}, ErrClaimLost
	}
	nextStatus, reason, err := normalizeDocumentReview(
		input.Decision, input.Reason, input.DocumentQualityScores,
	)
	if err != nil {
		return domain.BulkDocumentReviewResult{}, err
	}

	versions := make(map[string]int64, len(input.Documents))
	documentIDs := make([]string, 0, len(input.Documents))
	for _, item := range input.Documents {
		id := strings.TrimSpace(item.DocumentID)
		if id == "" || item.DocumentVersion <= 0 {
			return domain.BulkDocumentReviewResult{}, &GateError{Reasons: []string{"invalid_document_reference"}}
		}
		if _, exists := versions[id]; exists {
			return domain.BulkDocumentReviewResult{}, &GateError{Reasons: []string{"duplicate_document_reference"}}
		}
		versions[id] = item.DocumentVersion
		documentIDs = append(documentIDs, id)
	}

	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return domain.BulkDocumentReviewResult{}, err
	}
	defer tx.Rollback(ctx)

	var sourceCreator string
	if err := tx.QueryRow(ctx,
		"SELECT created_by::text FROM sources WHERE id = $1 FOR UPDATE", sourceID,
	).Scan(&sourceCreator); errors.Is(err, pgx.ErrNoRows) {
		return domain.BulkDocumentReviewResult{}, ErrNotFound
	} else if err != nil {
		return domain.BulkDocumentReviewResult{}, err
	}
	if sourceCreator == actorID && !allowSelfReview {
		return domain.BulkDocumentReviewResult{}, ErrSelfReview
	}

	rows, err := tx.Query(ctx, `
		SELECT `+documentColumns+`
		FROM documents
		WHERE source_id = $1 AND is_active AND id = ANY($2::uuid[])
		ORDER BY source_ordinal
		FOR UPDATE
	`, sourceID, documentIDs)
	if err != nil {
		return domain.BulkDocumentReviewResult{}, err
	}
	documents := make([]domain.Document, 0, len(documentIDs))
	for rows.Next() {
		document, err := scanDocument(rows)
		if err != nil {
			rows.Close()
			return domain.BulkDocumentReviewResult{}, err
		}
		documents = append(documents, document)
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		return domain.BulkDocumentReviewResult{}, err
	}
	rows.Close()
	if len(documents) != len(documentIDs) {
		return domain.BulkDocumentReviewResult{}, ErrNotFound
	}
	claimRows, err := tx.Query(ctx, `
		SELECT claim.document_id, campaign.id::text, campaign.rubric_version
		FROM document_review_claims AS claim
		JOIN documents AS document ON document.id = claim.document_id
		JOIN review_campaigns AS campaign ON campaign.id = claim.review_campaign_id
		WHERE claim.document_id = ANY($1::uuid[])
		  AND claim.reviewer_id = $2::uuid
		  AND claim.claim_token = $3::uuid
		  AND claim.expires_at > now()
		  AND claim.document_version = document.current_version
		  AND campaign.source_id = document.source_id
		  AND campaign.sample_generation = document.sample_generation
		ORDER BY claim.document_id
		FOR UPDATE OF claim
	`, documentIDs, actorID, input.ClaimToken)
	if err != nil {
		return domain.BulkDocumentReviewResult{}, err
	}
	claimedCount := 0
	var campaign reviewCampaignBinding
	for claimRows.Next() {
		var documentID, campaignID, rubricVersion string
		if err := claimRows.Scan(&documentID, &campaignID, &rubricVersion); err != nil {
			claimRows.Close()
			return domain.BulkDocumentReviewResult{}, err
		}
		if claimedCount == 0 {
			campaign = reviewCampaignBinding{
				ID: campaignID, RubricVersion: rubricVersion,
			}
		} else if campaign.ID != campaignID ||
			campaign.RubricVersion != rubricVersion {
			claimRows.Close()
			return domain.BulkDocumentReviewResult{}, ErrClaimLost
		}
		claimedCount++
	}
	if err := claimRows.Err(); err != nil {
		claimRows.Close()
		return domain.BulkDocumentReviewResult{}, err
	}
	claimRows.Close()
	if claimedCount != len(documentIDs) {
		return domain.BulkDocumentReviewResult{}, ErrClaimLost
	}
	updatedDocuments := make([]domain.Document, 0, len(documents))
	reviews := make([]domain.DocumentReview, 0, len(documents))
	for _, document := range documents {
		if document.CurrentVersion != versions[document.ID] {
			return domain.BulkDocumentReviewResult{}, ErrConflict
		}
		if document.Status != "sampled" && document.Status != "edited" {
			return domain.BulkDocumentReviewResult{}, &GateError{Reasons: []string{"document_not_pending"}}
		}
		reviewInput := domain.ReviewDocumentInput{
			DocumentQualityScores: input.DocumentQualityScores,
			Decision:              input.Decision,
			Reason:                reason,
			DocumentVersion:       document.CurrentVersion,
			ClaimToken:            input.ClaimToken,
		}
		updated, review, err := reviewDocumentTx(
			ctx, tx, document, reviewInput, nextStatus, reason, actorID, campaign,
		)
		if err != nil {
			return domain.BulkDocumentReviewResult{}, err
		}
		updatedDocuments = append(updatedDocuments, updated)
		reviews = append(reviews, review)
	}

	if err := refreshSourceDocumentReviewCounts(ctx, tx, sourceID, true); err != nil {
		return domain.BulkDocumentReviewResult{}, err
	}
	source, err := scanSource(tx.QueryRow(ctx,
		"SELECT "+sourceColumns+" FROM sources WHERE id = $1", sourceID,
	))
	if err != nil {
		return domain.BulkDocumentReviewResult{}, err
	}
	bulkAuditDetails, _ := json.Marshal(map[string]any{
		"decision":                  input.Decision,
		"rubric_version":            campaign.RubricVersion,
		"quality_score":             input.QualityScore,
		"language_quality_score":    input.LanguageQualityScore,
		"coherence_score":           input.CoherenceScore,
		"information_density_score": input.InformationDensityScore,
		"cleanliness_score":         input.CleanlinessScore,
		"document_count":            len(updatedDocuments),
		"document_ids":              documentIDs,
		"reason":                    reason,
		"review_campaign_id":        campaign.ID,
	})
	if _, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES ($1, 'documents.bulk_reviewed', 'source', $2, $3::jsonb)
	`, actorID, sourceID, bulkAuditDetails); err != nil {
		return domain.BulkDocumentReviewResult{}, fmt.Errorf("audit bulk document review: %w", err)
	}

	if err := tx.Commit(ctx); err != nil {
		return domain.BulkDocumentReviewResult{}, err
	}
	return domain.BulkDocumentReviewResult{
		Source: source, Documents: updatedDocuments, Reviews: reviews,
	}, nil
}

func validateReviewClaim(
	ctx context.Context,
	tx pgx.Tx,
	document domain.Document,
	claimToken, actorID string,
) (reviewCampaignBinding, error) {
	claimToken = strings.TrimSpace(claimToken)
	if !uuidPattern.MatchString(claimToken) {
		return reviewCampaignBinding{}, ErrClaimLost
	}
	var campaign reviewCampaignBinding
	if err := tx.QueryRow(ctx, `
		SELECT campaign.id::text, campaign.rubric_version
		FROM document_review_claims AS claim
		JOIN review_campaigns AS campaign ON campaign.id = claim.review_campaign_id
		WHERE claim.document_id = $1::uuid
		  AND claim.reviewer_id = $2::uuid
		  AND claim.claim_token = $3::uuid
		  AND claim.document_version = $4
		  AND claim.expires_at > now()
		  AND campaign.source_id = $5::uuid
		  AND campaign.sample_generation = $6
		FOR UPDATE OF claim
	`, document.ID, actorID, claimToken, document.CurrentVersion,
		document.SourceID, document.SampleGeneration).Scan(
		&campaign.ID, &campaign.RubricVersion,
	); errors.Is(err, pgx.ErrNoRows) {
		return reviewCampaignBinding{}, ErrClaimLost
	} else if err != nil {
		return reviewCampaignBinding{}, err
	}
	if campaign.RubricVersion != domain.MultidimensionalQualityRubric {
		return reviewCampaignBinding{}, ErrClaimLost
	}
	return campaign, nil
}

func newUUID() (string, error) {
	value := make([]byte, 16)
	if _, err := rand.Read(value); err != nil {
		return "", err
	}
	value[6] = (value[6] & 0x0f) | 0x40
	value[8] = (value[8] & 0x3f) | 0x80
	return fmt.Sprintf(
		"%08x-%04x-%04x-%04x-%012x",
		value[0:4], value[4:6], value[6:8], value[8:10], value[10:16],
	), nil
}

func normalizeDocumentReview(
	decision string,
	inputReason *string,
	scores domain.DocumentQualityScores,
) (string, *string, error) {
	reason := trimReason(inputReason)
	invalidScores := []string{}
	for _, score := range []struct {
		value  int16
		reason string
	}{
		{scores.QualityScore, "quality_score_required"},
		{scores.LanguageQualityScore, "language_quality_score_required"},
		{scores.CoherenceScore, "coherence_score_required"},
		{scores.InformationDensityScore, "information_density_score_required"},
		{scores.CleanlinessScore, "cleanliness_score_required"},
	} {
		if score.value < 1 || score.value > 5 {
			invalidScores = append(invalidScores, score.reason)
		}
	}
	if len(invalidScores) > 0 {
		return "", nil, &GateError{Reasons: invalidScores}
	}
	if decision != "approved" && reason == nil {
		return "", nil, &GateError{Reasons: []string{"reason_required"}}
	}
	nextStatus, valid := map[string]string{
		"approved":         "approved",
		"rejected":         "rejected",
		"sensitive_review": "sensitive_review",
	}[decision]
	if !valid {
		return "", nil, &GateError{Reasons: []string{"invalid_decision"}}
	}
	return nextStatus, reason, nil
}

func reviewDocumentTx(
	ctx context.Context,
	tx pgx.Tx,
	document domain.Document,
	input domain.ReviewDocumentInput,
	nextStatus string,
	reason *string,
	actorID string,
	campaign reviewCampaignBinding,
) (domain.Document, domain.DocumentReview, error) {
	var alreadyReviewed bool
	if err := tx.QueryRow(ctx, `
		SELECT EXISTS (
			SELECT 1
			FROM document_reviews AS review
			LEFT JOIN document_review_reversals AS reversal
			  ON reversal.review_id = review.id
			WHERE review.document_id = $1
			  AND review.document_version = $2
			  AND review.reviewer_id = $3
			  AND reversal.review_id IS NULL
		)
	`, document.ID, input.DocumentVersion, actorID).Scan(&alreadyReviewed); err != nil {
		return domain.Document{}, domain.DocumentReview{}, err
	}
	if alreadyReviewed {
		return domain.Document{}, domain.DocumentReview{}, ErrConflict
	}

	updated, err := scanDocument(tx.QueryRow(ctx, `
		UPDATE documents
		SET status = $1
		WHERE id = $2 AND current_version = $3
		RETURNING `+documentColumns,
		nextStatus, document.ID, input.DocumentVersion,
	))
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.Document{}, domain.DocumentReview{}, ErrConflict
	}
	if err != nil {
		return domain.Document{}, domain.DocumentReview{}, err
	}

	contextJSON, _ := json.Marshal(map[string]any{
		"source_id":          document.SourceID,
		"previous_status":    document.Status,
		"sampling_method":    document.SamplingMethod,
		"sample_generation":  document.SampleGeneration,
		"risk_score":         document.RiskScore,
		"risk_reasons":       document.RiskReasons,
		"review_campaign_id": campaign.ID,
	})
	var review domain.DocumentReview
	if err := tx.QueryRow(ctx, `
		INSERT INTO document_reviews(
			document_id, reviewer_id, review_campaign_id,
			decision, reason, rubric_version,
			quality_score, language_quality_score, coherence_score,
			information_density_score, cleanliness_score,
			document_version, object_sha256, review_context
		)
		VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, $12, $13, $14::jsonb
		)
		RETURNING id::text, document_id::text, reviewer_id::text,
			review_campaign_id::text, decision, reason,
			rubric_version, quality_score, language_quality_score, coherence_score,
			information_density_score, cleanliness_score,
			document_version, object_sha256, review_context, created_at
	`, document.ID, actorID, campaign.ID, input.Decision, reason,
		campaign.RubricVersion, input.QualityScore,
		input.LanguageQualityScore, input.CoherenceScore,
		input.InformationDensityScore, input.CleanlinessScore,
		input.DocumentVersion, document.CurrentObjectSHA256, contextJSON,
	).Scan(
		&review.ID, &review.DocumentID, &review.ReviewerID,
		&review.ReviewCampaignID, &review.Decision, &review.Reason,
		&review.RubricVersion,
		&review.QualityScore,
		&review.LanguageQualityScore, &review.CoherenceScore,
		&review.InformationDensityScore, &review.CleanlinessScore,
		&review.DocumentVersion, &review.ObjectSHA256, &review.Context, &review.CreatedAt,
	); err != nil {
		return domain.Document{}, domain.DocumentReview{}, fmt.Errorf("insert document review: %w", err)
	}

	reviewAuditDetails, _ := json.Marshal(map[string]any{
		"review_id":                 review.ID,
		"decision":                  input.Decision,
		"rubric_version":            campaign.RubricVersion,
		"quality_score":             input.QualityScore,
		"language_quality_score":    input.LanguageQualityScore,
		"coherence_score":           input.CoherenceScore,
		"information_density_score": input.InformationDensityScore,
		"cleanliness_score":         input.CleanlinessScore,
		"document_version":          input.DocumentVersion,
		"object_sha256":             document.CurrentObjectSHA256,
		"sample_generation":         document.SampleGeneration,
		"reason":                    reason,
		"review_campaign_id":        campaign.ID,
	})
	if _, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES ($1, 'document.reviewed', 'document', $2, $3::jsonb)
	`, actorID, document.ID, reviewAuditDetails); err != nil {
		return domain.Document{}, domain.DocumentReview{}, fmt.Errorf("audit document review: %w", err)
	}
	return updated, review, nil
}

func (r *Documents) ListReviews(ctx context.Context, documentID string) ([]domain.DocumentReview, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT review.id::text, review.document_id::text, review.reviewer_id::text,
			review.review_campaign_id::text,
			review.decision, review.reason, review.rubric_version,
			review.quality_score, review.language_quality_score,
			review.coherence_score, review.information_density_score,
			review.cleanliness_score, review.document_version,
			review.object_sha256, review.review_context, review.created_at,
			reversal.id::text, reversal.review_id::text,
			reversal.reversed_by::text, reversal.reason,
			reversal.restored_document_status, reversal.created_at
		FROM document_reviews AS review
		LEFT JOIN document_review_reversals AS reversal
		  ON reversal.review_id = review.id
		WHERE review.document_id = $1
		ORDER BY review.created_at DESC, review.id DESC
	`, documentID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	reviews := []domain.DocumentReview{}
	for rows.Next() {
		var review domain.DocumentReview
		var reversalID, reversalReviewID, reversedBy, reversalReason, restoredStatus *string
		var reversedAt *time.Time
		if err := rows.Scan(
			&review.ID, &review.DocumentID, &review.ReviewerID,
			&review.ReviewCampaignID, &review.Decision,
			&review.Reason, &review.RubricVersion, &review.QualityScore,
			&review.LanguageQualityScore, &review.CoherenceScore,
			&review.InformationDensityScore, &review.CleanlinessScore,
			&review.DocumentVersion, &review.ObjectSHA256, &review.Context, &review.CreatedAt,
			&reversalID, &reversalReviewID, &reversedBy, &reversalReason,
			&restoredStatus, &reversedAt,
		); err != nil {
			return nil, err
		}
		if reversalID != nil && reversalReviewID != nil && reversedBy != nil &&
			reversalReason != nil && restoredStatus != nil && reversedAt != nil {
			review.Reversal = &domain.DocumentReviewReversal{
				ID: *reversalID, ReviewID: *reversalReviewID, ReversedBy: *reversedBy,
				Reason: *reversalReason, RestoredDocumentStatus: *restoredStatus,
				CreatedAt: *reversedAt,
			}
		}
		reviews = append(reviews, review)
	}
	return reviews, rows.Err()
}

// ListReviewHistory returns only reviews authored by reviewerID for documents
// belonging to sourceID. Reversed reviews remain in the result so the
// append-only decision chain stays discoverable after a document returns to
// the pending queue.
func (r *Documents) ListReviewHistory(
	ctx context.Context,
	sourceID string,
	reviewerID string,
) ([]domain.DocumentReviewHistoryItem, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT
			document.id::text, document.source_id::text, document.source_ordinal,
			document.external_id, document.current_object_sha256,
			document.text_preview, document.byte_size, document.char_count,
			document.status, document.current_version, document.sampling_method,
			document.risk_score, document.risk_reasons, document.is_active,
			document.sample_generation, document.created_at, document.updated_at,
			review.id::text, review.document_id::text, review.reviewer_id::text,
			review.review_campaign_id::text,
			review.decision, review.reason, review.rubric_version,
			review.quality_score, review.language_quality_score,
			review.coherence_score, review.information_density_score,
			review.cleanliness_score, review.document_version,
			review.object_sha256, review.review_context, review.created_at,
			reversal.id::text, reversal.review_id::text,
			reversal.reversed_by::text, reversal.reason,
			reversal.restored_document_status, reversal.created_at
		FROM document_reviews AS review
		JOIN documents AS document ON document.id = review.document_id
		LEFT JOIN document_review_reversals AS reversal
		  ON reversal.review_id = review.id
		WHERE document.source_id = $1::uuid
		  AND review.reviewer_id = $2::uuid
		ORDER BY COALESCE(reversal.created_at, review.created_at) DESC,
			document.source_ordinal ASC, review.created_at DESC, review.id DESC
	`, sourceID, reviewerID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	items := []domain.DocumentReviewHistoryItem{}
	itemIndexes := map[string]int{}
	for rows.Next() {
		var document domain.Document
		var review domain.DocumentReview
		var reversalID, reversalReviewID, reversedBy, reversalReason, restoredStatus *string
		var reversedAt *time.Time
		if err := rows.Scan(
			&document.ID, &document.SourceID, &document.SourceOrdinal, &document.ExternalID,
			&document.CurrentObjectSHA256, &document.TextPreview, &document.ByteSize,
			&document.CharCount, &document.Status, &document.CurrentVersion,
			&document.SamplingMethod, &document.RiskScore, &document.RiskReasons,
			&document.IsActive, &document.SampleGeneration,
			&document.CreatedAt, &document.UpdatedAt,
			&review.ID, &review.DocumentID, &review.ReviewerID,
			&review.ReviewCampaignID, &review.Decision,
			&review.Reason, &review.RubricVersion, &review.QualityScore,
			&review.LanguageQualityScore, &review.CoherenceScore,
			&review.InformationDensityScore, &review.CleanlinessScore,
			&review.DocumentVersion, &review.ObjectSHA256, &review.Context, &review.CreatedAt,
			&reversalID, &reversalReviewID, &reversedBy, &reversalReason,
			&restoredStatus, &reversedAt,
		); err != nil {
			return nil, err
		}
		if reversalID != nil && reversalReviewID != nil && reversedBy != nil &&
			reversalReason != nil && restoredStatus != nil && reversedAt != nil {
			review.Reversal = &domain.DocumentReviewReversal{
				ID: *reversalID, ReviewID: *reversalReviewID, ReversedBy: *reversedBy,
				Reason: *reversalReason, RestoredDocumentStatus: *restoredStatus,
				CreatedAt: *reversedAt,
			}
		}

		index, exists := itemIndexes[document.ID]
		if !exists {
			index = len(items)
			itemIndexes[document.ID] = index
			items = append(items, domain.DocumentReviewHistoryItem{
				Document: document,
				Reviews:  []domain.DocumentReview{},
			})
		}
		items[index].Reviews = append(items[index].Reviews, review)
	}
	return items, rows.Err()
}

func (r *Documents) QualitySummary(ctx context.Context, sourceID string) (domain.DocumentQualitySummary, error) {
	var summary domain.DocumentQualitySummary
	err := r.pool.QueryRow(ctx, `
		SELECT
			$1::text,
			$2::text,
			count(review.id) FILTER (
				WHERE review.rubric_version = $2
			)::bigint,
			count(DISTINCT review.document_id) FILTER (
				WHERE review.rubric_version = $2
			)::bigint,
			count(review.id) FILTER (
				WHERE review.rubric_version = 'overall-v1'
			)::bigint,
			avg(review.quality_score) FILTER (
				WHERE review.rubric_version = $2
			)::float8,
			avg(review.language_quality_score) FILTER (
				WHERE review.rubric_version = $2
			)::float8,
			avg(review.coherence_score) FILTER (
				WHERE review.rubric_version = $2
			)::float8,
			avg(review.information_density_score) FILTER (
				WHERE review.rubric_version = $2
			)::float8,
			avg(review.cleanliness_score) FILTER (
				WHERE review.rubric_version = $2
			)::float8
		FROM documents AS document
		LEFT JOIN document_reviews AS review
		  ON review.document_id = document.id
		 AND review.document_version = document.current_version
		 AND review.object_sha256 = document.current_object_sha256
		 AND NOT EXISTS (
			SELECT 1 FROM document_review_reversals AS reversal
			WHERE reversal.review_id = review.id
		 )
		WHERE document.source_id = $1::uuid AND document.is_active
	`, sourceID, domain.MultidimensionalQualityRubric).Scan(
		&summary.SourceID, &summary.RubricVersion,
		&summary.ReviewCount, &summary.DocumentCount, &summary.LegacyReviewCount,
		&summary.AverageQualityScore, &summary.AverageLanguageQualityScore,
		&summary.AverageCoherenceScore, &summary.AverageInformationDensityScore,
		&summary.AverageCleanlinessScore,
	)
	return summary, err
}

func refreshSourceDocumentReviewCounts(ctx context.Context, tx pgx.Tx, sourceID string, demote bool) error {
	_, err := tx.Exec(ctx, `
		UPDATE sources
		SET reviewed_document_count = (
				SELECT count(*) FROM documents
				WHERE source_id = $1 AND is_active
				  AND status IN ('approved', 'rejected', 'sensitive_review')
			),
			approved_document_count = (
				SELECT count(*) FROM documents
				WHERE source_id = $1 AND is_active AND status = 'approved'
			),
			flagged_document_count = (
				SELECT count(*) FROM documents
				WHERE source_id = $1 AND is_active
				  AND status IN ('rejected', 'sensitive_review')
			),
			approval_status = CASE
				WHEN $2 AND approval_status IN ('approved_source', 'release_candidate')
					THEN 'sampled_for_review'
				ELSE approval_status
			END
		WHERE id = $1
	`, sourceID, demote)
	if err != nil {
		return fmt.Errorf("refresh source document review counts: %w", err)
	}
	return nil
}

const documentColumns = `
	id::text, source_id::text, source_ordinal, external_id,
	current_object_sha256, text_preview, byte_size, char_count,
	status, current_version, sampling_method, risk_score, risk_reasons,
	is_active, sample_generation,
	created_at, updated_at`

func scanDocument(row scanner) (domain.Document, error) {
	var document domain.Document
	err := row.Scan(
		&document.ID, &document.SourceID, &document.SourceOrdinal, &document.ExternalID,
		&document.CurrentObjectSHA256, &document.TextPreview, &document.ByteSize,
		&document.CharCount, &document.Status, &document.CurrentVersion,
		&document.SamplingMethod, &document.RiskScore, &document.RiskReasons,
		&document.IsActive, &document.SampleGeneration,
		&document.CreatedAt, &document.UpdatedAt,
	)
	return document, err
}

func DocumentPreview(content string) string {
	preview := strings.Join(strings.Fields(content), " ")
	if len([]rune(preview)) <= 240 {
		return preview
	}
	return string([]rune(preview)[:240]) + "…"
}
