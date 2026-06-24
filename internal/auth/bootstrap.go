package auth

import (
	"context"
	"fmt"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

func BootstrapAdmin(ctx context.Context, pool *pgxpool.Pool, email, password string) error {
	if email == "" {
		return nil
	}
	email = strings.ToLower(strings.TrimSpace(email))

	tx, err := pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)

	var userID string
	created := false
	err = tx.QueryRow(ctx, "SELECT id::text FROM users WHERE email = $1", email).Scan(&userID)
	if err != nil && err != pgx.ErrNoRows {
		return fmt.Errorf("find bootstrap admin: %w", err)
	}
	if err == pgx.ErrNoRows {
		hash, err := HashPassword(password)
		if err != nil {
			return fmt.Errorf("hash bootstrap password: %w", err)
		}
		if err := tx.QueryRow(ctx, `
			INSERT INTO users(email, password_hash, display_name)
			VALUES ($1, $2, $3)
			RETURNING id::text
		`, email, hash, "Derlem Admin").Scan(&userID); err != nil {
			return fmt.Errorf("create bootstrap admin: %w", err)
		}
		created = true
	}

	roleResult, err := tx.Exec(ctx, `
		INSERT INTO user_roles(user_id, role_name)
		VALUES ($1, 'admin')
		ON CONFLICT DO NOTHING
	`, userID)
	if err != nil {
		return fmt.Errorf("assign bootstrap admin role: %w", err)
	}

	if created || roleResult.RowsAffected() > 0 {
		if _, err := tx.Exec(ctx, `
			INSERT INTO audit_events(actor_id, actor_type, action, entity_type, entity_id, details)
			VALUES (
				$1, 'system', 'user.bootstrap_admin', 'user', $1,
				jsonb_build_object('email', $2::text, 'created', $3::boolean)
			)
		`, userID, email, created); err != nil {
			return fmt.Errorf("audit bootstrap admin: %w", err)
		}
	}

	return tx.Commit(ctx)
}
