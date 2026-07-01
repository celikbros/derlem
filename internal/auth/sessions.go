package auth

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

var (
	ErrInvalidSession = errors.New("invalid session")
	ErrExpiredSession = errors.New("expired session")
	ErrRevokedSession = errors.New("revoked session")
	ErrStalePrincipal = errors.New("stale session principal")
)

type SessionStore struct {
	pool          *pgxpool.Pool
	idleTTL       time.Duration
	touchInterval time.Duration
	now           func() time.Time
}

func NewSessionStore(pool *pgxpool.Pool, idleTTL time.Duration) *SessionStore {
	touchInterval := min(idleTTL/4, time.Minute)
	if touchInterval < time.Second {
		touchInterval = time.Second
	}
	return &SessionStore{
		pool:          pool,
		idleTTL:       idleTTL,
		touchInterval: touchInterval,
		now:           time.Now,
	}
}

func NewSessionID() (string, error) {
	random := make([]byte, 32)
	if _, err := rand.Read(random); err != nil {
		return "", fmt.Errorf("generate session id: %w", err)
	}
	return base64.RawURLEncoding.EncodeToString(random), nil
}

func SessionIDHash(value string) string {
	digest := sha256.Sum256([]byte(value))
	return hex.EncodeToString(digest[:])
}

func (s *SessionStore) Create(ctx context.Context, jwtID, userID string, authVersion int64, absoluteExpiresAt time.Time) error {
	now := s.now().UTC()
	absoluteExpiresAt = absoluteExpiresAt.UTC()
	if jwtID == "" || userID == "" || authVersion <= 0 || !absoluteExpiresAt.After(now) {
		return ErrInvalidSession
	}
	idleExpiresAt := now.Add(s.idleTTL)
	if idleExpiresAt.After(absoluteExpiresAt) {
		idleExpiresAt = absoluteExpiresAt
	}

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)

	var sessionID string
	if err := tx.QueryRow(ctx, `
		INSERT INTO auth_sessions(
			jti_hash, user_id, auth_version, created_at, last_seen_at,
			idle_expires_at, absolute_expires_at
		)
		VALUES ($1, $2, $3, $4, $4, $5, $6)
		RETURNING id::text
	`, SessionIDHash(jwtID), userID, authVersion, now, idleExpiresAt, absoluteExpiresAt).Scan(&sessionID); err != nil {
		return fmt.Errorf("create auth session: %w", err)
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES (
			$1, 'auth.login', 'auth_session', $2,
			jsonb_build_object(
				'auth_version', $3::bigint,
				'idle_expires_at', $4::timestamptz,
				'absolute_expires_at', $5::timestamptz
			)
		)
	`, userID, sessionID, authVersion, idleExpiresAt, absoluteExpiresAt); err != nil {
		return fmt.Errorf("audit auth session creation: %w", err)
	}
	return tx.Commit(ctx)
}

func (s *SessionStore) Validate(ctx context.Context, claims Claims) error {
	now := s.now().UTC()
	var (
		userID             string
		sessionAuthVersion int64
		userAuthVersion    int64
		lastSeenAt         time.Time
		idleExpiresAt      time.Time
		absoluteExpiresAt  time.Time
		revokedAt          *time.Time
		userStatus         string
	)
	err := s.pool.QueryRow(ctx, `
		SELECT session.user_id::text, session.auth_version, account.auth_version,
			session.last_seen_at, session.idle_expires_at,
			session.absolute_expires_at, session.revoked_at, account.status
		FROM auth_sessions AS session
		JOIN users AS account ON account.id = session.user_id
		WHERE session.jti_hash = $1
	`, SessionIDHash(claims.JWTID)).Scan(
		&userID, &sessionAuthVersion, &userAuthVersion, &lastSeenAt,
		&idleExpiresAt, &absoluteExpiresAt, &revokedAt, &userStatus,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return ErrInvalidSession
	}
	if err != nil {
		return fmt.Errorf("validate auth session: %w", err)
	}
	if revokedAt != nil {
		return ErrRevokedSession
	}
	if !now.Before(idleExpiresAt) || !now.Before(absoluteExpiresAt) {
		return ErrExpiredSession
	}
	if userStatus != "active" || userID != claims.Subject || sessionAuthVersion != claims.AuthVersion || userAuthVersion != claims.AuthVersion {
		return ErrStalePrincipal
	}
	if now.Sub(lastSeenAt) < s.touchInterval {
		return nil
	}
	nextIdleExpiry := now.Add(s.idleTTL)
	if nextIdleExpiry.After(absoluteExpiresAt) {
		nextIdleExpiry = absoluteExpiresAt
	}
	result, err := s.pool.Exec(ctx, `
		UPDATE auth_sessions
		SET last_seen_at = $2, idle_expires_at = $3
		WHERE jti_hash = $1 AND revoked_at IS NULL
			AND idle_expires_at > $2 AND absolute_expires_at > $2
	`, SessionIDHash(claims.JWTID), now, nextIdleExpiry)
	if err != nil {
		return fmt.Errorf("touch auth session: %w", err)
	}
	if result.RowsAffected() != 1 {
		return ErrInvalidSession
	}
	return nil
}

func (s *SessionStore) Revoke(ctx context.Context, claims Claims, reason string) error {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)

	var sessionID string
	err = tx.QueryRow(ctx, `
		UPDATE auth_sessions
		SET revoked_at = now(), revoked_reason = $3
		WHERE jti_hash = $1 AND user_id = $2 AND revoked_at IS NULL
		RETURNING id::text
	`, SessionIDHash(claims.JWTID), claims.Subject, reason).Scan(&sessionID)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil
	}
	if err != nil {
		return fmt.Errorf("revoke auth session: %w", err)
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES ($1, 'auth.logout', 'auth_session', $2, jsonb_build_object('reason', $3::text))
	`, claims.Subject, sessionID, reason); err != nil {
		return fmt.Errorf("audit auth session revoke: %w", err)
	}
	return tx.Commit(ctx)
}

func (s *SessionStore) RevokeAll(ctx context.Context, claims Claims, reason string) (int64, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return 0, err
	}
	defer tx.Rollback(ctx)

	var revokedCount int64
	if err := tx.QueryRow(ctx, `
		WITH revoked AS (
			UPDATE auth_sessions
			SET revoked_at = now(), revoked_reason = $2
			WHERE user_id = $1 AND revoked_at IS NULL
				AND absolute_expires_at > now()
			RETURNING id
		)
		SELECT count(*) FROM revoked
	`, claims.Subject, reason).Scan(&revokedCount); err != nil {
		return 0, fmt.Errorf("revoke all auth sessions: %w", err)
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES ($1, 'auth.logout_all', 'user', $1, jsonb_build_object('revoked_count', $2::bigint))
	`, claims.Subject, revokedCount); err != nil {
		return 0, fmt.Errorf("audit all-session revoke: %w", err)
	}
	if err := tx.Commit(ctx); err != nil {
		return 0, err
	}
	return revokedCount, nil
}
