package repository

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/celikbros/derlem/internal/domain"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

type SimilarityReviews struct {
	pool *pgxpool.Pool
}

func NewSimilarityReviews(pool *pgxpool.Pool) *SimilarityReviews {
	return &SimilarityReviews{pool: pool}
}

func (r *SimilarityReviews) ListRuns(ctx context.Context) ([]domain.SimilarityCalibrationRun, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT run.id::text, run.report_object_sha256, run.schema_version, run.method,
			run.content_purpose, run.source_snapshot, run.sampled_document_count,
			run.eligible_document_count, run.simhash_version, run.threshold_max,
			run.pair_count,
			COALESCE(stats.reviewed_pair_count, 0),
			COALESCE(stats.independent_review_count, 0),
			COALESCE(stats.consensus_pair_count, 0),
			COALESCE(stats.disagreement_pair_count, 0),
			run.created_at
		FROM similarity_calibration_runs AS run
		LEFT JOIN LATERAL (
			SELECT
				count(*) FILTER (WHERE pair_stats.review_count > 0) AS reviewed_pair_count,
				COALESCE(sum(pair_stats.review_count), 0) AS independent_review_count,
				count(*) FILTER (
					WHERE pair_stats.review_count >= 2 AND pair_stats.distinct_label_count = 1
				) AS consensus_pair_count,
				count(*) FILTER (
					WHERE pair_stats.review_count >= 2 AND pair_stats.distinct_label_count > 1
				) AS disagreement_pair_count
			FROM (
				SELECT pair.id, count(review.id) AS review_count,
					count(DISTINCT review.label) AS distinct_label_count
				FROM similarity_review_pairs AS pair
				LEFT JOIN similarity_pair_reviews AS review ON review.pair_id = pair.id
				WHERE pair.run_id = run.id
				GROUP BY pair.id
			) AS pair_stats
		) AS stats ON true
		ORDER BY run.created_at DESC, run.id DESC
	`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	runs := []domain.SimilarityCalibrationRun{}
	for rows.Next() {
		var run domain.SimilarityCalibrationRun
		if err := rows.Scan(
			&run.ID, &run.ReportObjectSHA256, &run.SchemaVersion, &run.Method,
			&run.ContentPurpose, &run.SourceSnapshot, &run.SampledDocumentCount,
			&run.EligibleDocumentCount, &run.SimHashVersion, &run.ThresholdMax,
			&run.PairCount, &run.ReviewedPairCount, &run.IndependentReviewCount,
			&run.ConsensusPairCount, &run.DisagreementPairCount, &run.CreatedAt,
		); err != nil {
			return nil, err
		}
		runs = append(runs, run)
	}
	return runs, rows.Err()
}

func (r *SimilarityReviews) ListPairs(
	ctx context.Context,
	runID string,
	reviewerID string,
	limit int,
) ([]domain.SimilarityReviewPair, error) {
	rows, err := r.pool.Query(ctx, similarityPairQuery+`
		WHERE pair.run_id = $1
		GROUP BY pair.id
		ORDER BY pair.hamming_distance, pair.pair_rank
		LIMIT $3
	`, runID, reviewerID, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	pairs := make([]domain.SimilarityReviewPair, 0, limit)
	for rows.Next() {
		pair, err := scanSimilarityPair(rows)
		if err != nil {
			return nil, err
		}
		pairs = append(pairs, pair)
	}
	return pairs, rows.Err()
}

func (r *SimilarityReviews) GetPair(
	ctx context.Context,
	pairID string,
	reviewerID string,
) (domain.SimilarityReviewPair, error) {
	pair, err := scanSimilarityPair(r.pool.QueryRow(ctx, similarityPairQuery+`
		WHERE pair.id = $1
		GROUP BY pair.id
	`, pairID, reviewerID))
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.SimilarityReviewPair{}, ErrNotFound
	}
	return pair, err
}

func (r *SimilarityReviews) ListPairReviews(
	ctx context.Context,
	pairID string,
) ([]domain.SimilarityPairReview, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT review.id::text, review.pair_id::text, review.reviewer_id::text,
			user_account.display_name, review.label, review.reason, review.created_at
		FROM similarity_pair_reviews AS review
		JOIN users AS user_account ON user_account.id = review.reviewer_id
		WHERE review.pair_id = $1
		ORDER BY review.created_at, review.id
	`, pairID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	reviews := []domain.SimilarityPairReview{}
	for rows.Next() {
		var review domain.SimilarityPairReview
		if err := rows.Scan(
			&review.ID, &review.PairID, &review.ReviewerID, &review.Reviewer,
			&review.Label, &review.Reason, &review.CreatedAt,
		); err != nil {
			return nil, err
		}
		reviews = append(reviews, review)
	}
	return reviews, rows.Err()
}

func (r *SimilarityReviews) ReviewPair(
	ctx context.Context,
	pairID string,
	actorID string,
	input domain.ReviewSimilarityPairInput,
) (domain.SimilarityPairReview, error) {
	input.Label = strings.TrimSpace(input.Label)
	input.Reason = trimReason(input.Reason)
	if message := ValidateSimilarityPairReview(input); message != "" {
		return domain.SimilarityPairReview{}, &GateError{Reasons: []string{message}}
	}

	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return domain.SimilarityPairReview{}, err
	}
	defer tx.Rollback(ctx)

	var runID string
	if err := tx.QueryRow(ctx,
		"SELECT run_id::text FROM similarity_review_pairs WHERE id = $1",
		pairID,
	).Scan(&runID); errors.Is(err, pgx.ErrNoRows) {
		return domain.SimilarityPairReview{}, ErrNotFound
	} else if err != nil {
		return domain.SimilarityPairReview{}, err
	}

	var review domain.SimilarityPairReview
	err = tx.QueryRow(ctx, `
		INSERT INTO similarity_pair_reviews(pair_id, reviewer_id, label, reason)
		VALUES ($1, $2, $3, $4)
		RETURNING id::text, pair_id::text, reviewer_id::text,
			(SELECT display_name FROM users WHERE id = $2), label, reason, created_at
	`, pairID, actorID, input.Label, input.Reason).Scan(
		&review.ID, &review.PairID, &review.ReviewerID, &review.Reviewer,
		&review.Label, &review.Reason, &review.CreatedAt,
	)
	if err != nil {
		var pgError *pgconn.PgError
		if errors.As(err, &pgError) && pgError.Code == "23505" {
			return domain.SimilarityPairReview{}, ErrConflict
		}
		return domain.SimilarityPairReview{}, fmt.Errorf("insert similarity pair review: %w", err)
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES (
			$1, 'similarity.pair_reviewed', 'similarity_review_pair', $2,
			jsonb_build_object(
				'run_id', $3::text, 'review_id', $4::text,
				'label', $5::text, 'reason', $6::text
			)
		)
	`, actorID, pairID, runID, review.ID, input.Label, input.Reason); err != nil {
		return domain.SimilarityPairReview{}, fmt.Errorf("audit similarity review: %w", err)
	}
	if err := tx.Commit(ctx); err != nil {
		return domain.SimilarityPairReview{}, err
	}
	return review, nil
}

func ValidateSimilarityPairReview(input domain.ReviewSimilarityPairInput) string {
	valid := map[string]bool{
		"exact_duplicate": true,
		"near_duplicate":  true,
		"related":         true,
		"different":       true,
		"uncertain":       true,
	}
	if !valid[strings.TrimSpace(input.Label)] {
		return "invalid_similarity_label"
	}
	reason := trimReason(input.Reason)
	if input.Label == "uncertain" && reason == nil {
		return "reason_required"
	}
	if reason != nil && len([]rune(*reason)) > 2000 {
		return "reason_too_long"
	}
	return ""
}

const similarityPairQuery = `
	SELECT pair.id::text, pair.run_id::text, pair.pair_rank, pair.hamming_distance,
		pair.left_source_id::text, pair.left_source_sha256, pair.left_source_ordinal,
		pair.left_object_sha256, pair.left_text_preview, pair.left_token_count,
		pair.right_source_id::text, pair.right_source_sha256, pair.right_source_ordinal,
		pair.right_object_sha256, pair.right_text_preview, pair.right_token_count,
		count(review.id)::integer,
		CASE WHEN count(review.id) >= 2 AND count(DISTINCT review.label) = 1
			THEN min(review.label) END,
		(count(review.id) >= 2 AND count(DISTINCT review.label) > 1),
		max(review.label) FILTER (WHERE review.reviewer_id = $2),
		pair.created_at
	FROM similarity_review_pairs AS pair
	LEFT JOIN similarity_pair_reviews AS review ON review.pair_id = pair.id
`

func scanSimilarityPair(row pgx.Row) (domain.SimilarityReviewPair, error) {
	var pair domain.SimilarityReviewPair
	err := row.Scan(
		&pair.ID, &pair.RunID, &pair.PairRank, &pair.HammingDistance,
		&pair.LeftSourceID, &pair.LeftSourceSHA256, &pair.LeftSourceOrdinal,
		&pair.LeftObjectSHA256, &pair.LeftTextPreview, &pair.LeftTokenCount,
		&pair.RightSourceID, &pair.RightSourceSHA256, &pair.RightSourceOrdinal,
		&pair.RightObjectSHA256, &pair.RightTextPreview, &pair.RightTokenCount,
		&pair.ReviewCount, &pair.ConsensusLabel, &pair.HasDisagreement,
		&pair.CurrentReviewerLabel, &pair.CreatedAt,
	)
	return pair, err
}
