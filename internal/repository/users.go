package repository

import (
	"context"
	"errors"
	"fmt"

	"github.com/celikbros/derlem/internal/domain"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

var (
	ErrEmailTaken  = errors.New("email already registered")
	ErrUnknownRole = errors.New("unknown role")
	ErrSelfLockout = errors.New("cannot disable or demote own account")
	ErrLastAdmin   = errors.New("cannot remove the last active admin")
)

type Users struct {
	pool *pgxpool.Pool
}

func NewUsers(pool *pgxpool.Pool) *Users {
	return &Users{pool: pool}
}

type UpdateUserInput struct {
	DisplayName  *string
	Status       *string
	Roles        []string
	PasswordHash *string
}

const userSelect = `
	SELECT u.id::text, u.email, u.display_name, u.status, u.created_at, u.updated_at,
		COALESCE(
			array_agg(ur.role_name ORDER BY ur.role_name)
			FILTER (WHERE ur.role_name IS NOT NULL),
			ARRAY[]::text[]
		)
	FROM users u
	LEFT JOIN user_roles ur ON ur.user_id = u.id
`

func scanUser(row pgx.Row) (domain.UserAccount, error) {
	var user domain.UserAccount
	err := row.Scan(&user.ID, &user.Email, &user.DisplayName, &user.Status,
		&user.CreatedAt, &user.UpdatedAt, &user.Roles)
	return user, err
}

func (r *Users) List(ctx context.Context) ([]domain.UserAccount, error) {
	rows, err := r.pool.Query(ctx, userSelect+` GROUP BY u.id ORDER BY u.created_at, u.id`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	users := []domain.UserAccount{}
	for rows.Next() {
		user, err := scanUser(rows)
		if err != nil {
			return nil, err
		}
		users = append(users, user)
	}
	return users, rows.Err()
}

func (r *Users) Get(ctx context.Context, userID string) (domain.UserAccount, error) {
	user, err := scanUser(r.pool.QueryRow(ctx, userSelect+` WHERE u.id = $1 GROUP BY u.id`, userID))
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.UserAccount{}, ErrNotFound
	}
	return user, err
}

func (r *Users) Create(ctx context.Context, actorID, email, displayName, passwordHash string, roles []string) (domain.UserAccount, error) {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return domain.UserAccount{}, err
	}
	defer tx.Rollback(ctx)

	var userID string
	err = tx.QueryRow(ctx, `
		INSERT INTO users(email, password_hash, display_name)
		VALUES ($1, $2, $3)
		RETURNING id::text
	`, email, passwordHash, displayName).Scan(&userID)
	if err != nil {
		if isUniqueViolation(err) {
			return domain.UserAccount{}, ErrEmailTaken
		}
		return domain.UserAccount{}, fmt.Errorf("create user: %w", err)
	}
	if err := assignRoles(ctx, tx, userID, actorID, roles); err != nil {
		return domain.UserAccount{}, err
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES (
			$1, 'user.created', 'user', $2,
			jsonb_build_object('email', $3::text, 'roles', $4::text[])
		)
	`, actorID, userID, email, roles); err != nil {
		return domain.UserAccount{}, fmt.Errorf("audit user create: %w", err)
	}
	if err := tx.Commit(ctx); err != nil {
		return domain.UserAccount{}, err
	}
	return r.Get(ctx, userID)
}

func (r *Users) Update(ctx context.Context, actorID, userID string, input UpdateUserInput) (domain.UserAccount, error) {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return domain.UserAccount{}, err
	}
	defer tx.Rollback(ctx)

	var currentStatus string
	err = tx.QueryRow(ctx, `
		SELECT status FROM users WHERE id = $1 FOR UPDATE
	`, userID).Scan(&currentStatus)
	if errors.Is(err, pgx.ErrNoRows) {
		return domain.UserAccount{}, ErrNotFound
	}
	if err != nil {
		return domain.UserAccount{}, err
	}
	var currentRoles []string
	if err := tx.QueryRow(ctx, `
		SELECT COALESCE(
			array_agg(role_name ORDER BY role_name),
			ARRAY[]::text[]
		)
		FROM user_roles
		WHERE user_id = $1
	`, userID).Scan(&currentRoles); err != nil {
		return domain.UserAccount{}, err
	}

	nextStatus := currentStatus
	if input.Status != nil {
		nextStatus = *input.Status
	}
	nextRoles := currentRoles
	if input.Roles != nil {
		nextRoles = input.Roles
	}

	disabling := nextStatus != "active"
	losingAdmin := contains(currentRoles, "admin") && !contains(nextRoles, "admin")
	if userID == actorID && (disabling || losingAdmin) {
		return domain.UserAccount{}, ErrSelfLockout
	}
	if contains(currentRoles, "admin") && currentStatus == "active" && (disabling || losingAdmin) {
		var otherAdmins int
		if err := tx.QueryRow(ctx, `
			SELECT count(*)
			FROM users u
			JOIN user_roles ur ON ur.user_id = u.id AND ur.role_name = 'admin'
			WHERE u.status = 'active' AND u.id <> $1
		`, userID).Scan(&otherAdmins); err != nil {
			return domain.UserAccount{}, err
		}
		if otherAdmins == 0 {
			return domain.UserAccount{}, ErrLastAdmin
		}
	}

	if input.DisplayName != nil || input.Status != nil || input.PasswordHash != nil {
		if _, err := tx.Exec(ctx, `
			UPDATE users SET
				display_name = COALESCE($2, display_name),
				status = COALESCE($3, status),
				password_hash = COALESCE($4, password_hash),
				updated_at = now()
			WHERE id = $1
		`, userID, input.DisplayName, input.Status, input.PasswordHash); err != nil {
			return domain.UserAccount{}, fmt.Errorf("update user: %w", err)
		}
	}
	if input.Roles != nil {
		if _, err := tx.Exec(ctx, `DELETE FROM user_roles WHERE user_id = $1`, userID); err != nil {
			return domain.UserAccount{}, fmt.Errorf("clear roles: %w", err)
		}
		if err := assignRoles(ctx, tx, userID, actorID, input.Roles); err != nil {
			return domain.UserAccount{}, err
		}
	}

	if _, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES (
			$1, 'user.updated', 'user', $2,
			jsonb_build_object(
				'display_name_changed', $3::boolean,
				'status', $4::text,
				'roles', $5::text[],
				'password_reset', $6::boolean
			)
		)
	`, actorID, userID,
		input.DisplayName != nil,
		nextStatus,
		nextRoles,
		input.PasswordHash != nil,
	); err != nil {
		return domain.UserAccount{}, fmt.Errorf("audit user update: %w", err)
	}
	if err := tx.Commit(ctx); err != nil {
		return domain.UserAccount{}, err
	}
	return r.Get(ctx, userID)
}

func assignRoles(ctx context.Context, tx pgx.Tx, userID, actorID string, roles []string) error {
	for _, role := range roles {
		if _, err := tx.Exec(ctx, `
			INSERT INTO user_roles(user_id, role_name, assigned_by)
			VALUES ($1, $2, $3)
			ON CONFLICT DO NOTHING
		`, userID, role, actorID); err != nil {
			if isForeignKeyViolation(err) {
				return fmt.Errorf("%w: %s", ErrUnknownRole, role)
			}
			return fmt.Errorf("assign role %s: %w", role, err)
		}
	}
	return nil
}

func contains(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}

func isForeignKeyViolation(err error) bool {
	var pgError *pgconn.PgError
	return errors.As(err, &pgError) && pgError.Code == "23503"
}
