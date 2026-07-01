package auth

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type LoginRatePolicy struct {
	AccountFailureLimit int
	IPFailureLimit      int
	FailureWindow       time.Duration
	LockoutDuration     time.Duration
}

type LoginRateKeys struct {
	Account string
	IP      string
}

type LoginLimiter struct {
	pool   *pgxpool.Pool
	policy LoginRatePolicy
	key    []byte
	now    func() time.Time
}

func NewLoginLimiter(pool *pgxpool.Pool, policy LoginRatePolicy, secret string) *LoginLimiter {
	derivation := hmac.New(sha256.New, []byte(secret))
	derivation.Write([]byte("derlem-login-rate-limit-v1"))
	return &LoginLimiter{pool: pool, policy: policy, key: derivation.Sum(nil), now: time.Now}
}

func (l *LoginLimiter) Keys(email, ip string) LoginRateKeys {
	return LoginRateKeys{
		Account: l.hashRateValue("account:" + email),
		IP:      l.hashRateValue("ip:" + ip),
	}
}

func (l *LoginLimiter) hashRateValue(value string) string {
	mac := hmac.New(sha256.New, l.key)
	mac.Write([]byte(value))
	return hex.EncodeToString(mac.Sum(nil))
}

func (l *LoginLimiter) Check(ctx context.Context, keys LoginRateKeys) (time.Duration, error) {
	now := l.now().UTC()
	var blockedUntil time.Time
	err := l.pool.QueryRow(ctx, `
		SELECT blocked_until
		FROM login_rate_limits
		WHERE (
			(scope = 'account' AND key_hash = $1)
			OR (scope = 'ip' AND key_hash = $2)
		) AND blocked_until > $3
		ORDER BY blocked_until DESC
		LIMIT 1
	`, keys.Account, keys.IP, now).Scan(&blockedUntil)
	if errors.Is(err, pgx.ErrNoRows) {
		return 0, nil
	}
	if err != nil {
		return 0, fmt.Errorf("check login rate limit: %w", err)
	}
	return blockedUntil.Sub(now), nil
}

func (l *LoginLimiter) RecordFailure(ctx context.Context, keys LoginRateKeys, userID, reason string) (time.Duration, error) {
	now := l.now().UTC()
	tx, err := l.pool.Begin(ctx)
	if err != nil {
		return 0, err
	}
	defer tx.Rollback(ctx)

	accountBlockedUntil, err := l.recordFailure(ctx, tx, "account", keys.Account, l.policy.AccountFailureLimit, now)
	if err != nil {
		return 0, err
	}
	ipBlockedUntil, err := l.recordFailure(ctx, tx, "ip", keys.IP, l.policy.IPFailureLimit, now)
	if err != nil {
		return 0, err
	}
	blockedUntil := laterTime(accountBlockedUntil, ipBlockedUntil)
	if err := auditLoginFailure(ctx, tx, userID, "auth.login_failed", keys, reason, blockedUntil); err != nil {
		return 0, err
	}
	if err := tx.Commit(ctx); err != nil {
		return 0, err
	}
	if blockedUntil == nil {
		return 0, nil
	}
	return blockedUntil.Sub(now), nil
}

func (l *LoginLimiter) RecordBlockedAttempt(ctx context.Context, keys LoginRateKeys) (bool, error) {
	now := l.now().UTC()
	tx, err := l.pool.Begin(ctx)
	if err != nil {
		return false, err
	}
	defer tx.Rollback(ctx)
	result, err := tx.Exec(ctx, `
		UPDATE login_rate_limits
		SET updated_at = $3
		WHERE (
			(scope = 'account' AND key_hash = $1)
			OR (scope = 'ip' AND key_hash = $2)
		) AND blocked_until > $3
			AND updated_at <= $3 - interval '1 minute'
	`, keys.Account, keys.IP, now)
	if err != nil {
		return false, fmt.Errorf("throttle blocked-login audit: %w", err)
	}
	if result.RowsAffected() == 0 {
		if err := tx.Commit(ctx); err != nil {
			return false, err
		}
		return false, nil
	}
	if err := auditLoginFailure(ctx, tx, "", "auth.login_blocked", keys, "rate_limited", nil); err != nil {
		return false, err
	}
	if err := tx.Commit(ctx); err != nil {
		return false, err
	}
	return true, nil
}

func (l *LoginLimiter) RecordSuccess(ctx context.Context, keys LoginRateKeys) error {
	_, err := l.pool.Exec(ctx, `
		DELETE FROM login_rate_limits
		WHERE scope = 'account' AND key_hash = $1
	`, keys.Account)
	return err
}

func (l *LoginLimiter) recordFailure(ctx context.Context, tx pgx.Tx, scope, key string, limit int, now time.Time) (*time.Time, error) {
	var blockedUntil *time.Time
	err := tx.QueryRow(ctx, `
		INSERT INTO login_rate_limits AS rate (
			scope, key_hash, failure_count, window_started_at, blocked_until, updated_at
		)
		VALUES ($1, $2, 1, $3, NULL, $3)
		ON CONFLICT (scope, key_hash) DO UPDATE SET
			failure_count = CASE
				WHEN rate.window_started_at <= $3 - make_interval(secs => $4::double precision) THEN 1
				ELSE rate.failure_count + 1
			END,
			window_started_at = CASE
				WHEN rate.window_started_at <= $3 - make_interval(secs => $4::double precision) THEN $3
				ELSE rate.window_started_at
			END,
			blocked_until = CASE
				WHEN rate.blocked_until > $3 THEN rate.blocked_until
				WHEN (
					CASE
						WHEN rate.window_started_at <= $3 - make_interval(secs => $4::double precision) THEN 1
						ELSE rate.failure_count + 1
					END
				) >= $5 THEN $3 + make_interval(secs => $6::double precision)
				ELSE NULL
			END,
			updated_at = $3
		RETURNING blocked_until
	`, scope, key, now, l.policy.FailureWindow.Seconds(), limit, l.policy.LockoutDuration.Seconds()).Scan(&blockedUntil)
	if err != nil {
		return nil, fmt.Errorf("record %s login failure: %w", scope, err)
	}
	return blockedUntil, nil
}

func auditLoginFailure(ctx context.Context, tx pgx.Tx, userID, action string, keys LoginRateKeys, reason string, blockedUntil *time.Time) error {
	var actorID any
	if userID != "" {
		actorID = userID
	}
	_, err := tx.Exec(ctx, `
		INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details)
		VALUES (
			$1, $2, 'auth_identity', $1,
			jsonb_strip_nulls(jsonb_build_object(
				'account_key', $3::text,
				'ip_key', $4::text,
				'reason', $5::text,
				'blocked_until', $6::timestamptz
			))
		)
	`, actorID, action, keys.Account, keys.IP, reason, blockedUntil)
	if err != nil {
		return fmt.Errorf("audit login failure: %w", err)
	}
	return nil
}

func laterTime(left, right *time.Time) *time.Time {
	if left == nil {
		return right
	}
	if right == nil || left.After(*right) {
		return left
	}
	return right
}
