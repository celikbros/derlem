package repository

import (
	"context"

	"github.com/celikbros/derlem/internal/domain"
)

func (r *Sources) ListJobs(ctx context.Context, sourceID string, limit int) ([]domain.BackgroundJob, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT id::text, job_type, status, priority, result, attempts, max_attempts,
			last_error, created_at, updated_at, completed_at
		FROM background_jobs
		WHERE ($1::text = '' OR payload->>'source_id' = $1)
		ORDER BY created_at DESC, id DESC
		LIMIT $2
	`, sourceID, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	jobs := []domain.BackgroundJob{}
	for rows.Next() {
		var job domain.BackgroundJob
		if err := rows.Scan(
			&job.ID, &job.JobType, &job.Status, &job.Priority, &job.Result,
			&job.Attempts, &job.MaxAttempts, &job.LastError,
			&job.CreatedAt, &job.UpdatedAt, &job.CompletedAt,
		); err != nil {
			return nil, err
		}
		jobs = append(jobs, job)
	}
	return jobs, rows.Err()
}
