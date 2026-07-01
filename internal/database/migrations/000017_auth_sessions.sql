ALTER TABLE users
ADD COLUMN auth_version bigint NOT NULL DEFAULT 1 CHECK (auth_version > 0);

CREATE OR REPLACE FUNCTION bump_user_auth_version()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.auth_version = OLD.auth_version + 1;
    RETURN NEW;
END;
$$;

CREATE TRIGGER users_bump_auth_version
BEFORE UPDATE OF password_hash, status ON users
FOR EACH ROW
WHEN (
    OLD.password_hash IS DISTINCT FROM NEW.password_hash
    OR OLD.status IS DISTINCT FROM NEW.status
)
EXECUTE FUNCTION bump_user_auth_version();

CREATE OR REPLACE FUNCTION bump_user_auth_version_for_role()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE users SET auth_version = auth_version + 1 WHERE id = NEW.user_id;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE users SET auth_version = auth_version + 1 WHERE id = OLD.user_id;
    ELSE
        UPDATE users SET auth_version = auth_version + 1 WHERE id = OLD.user_id;
        IF NEW.user_id IS DISTINCT FROM OLD.user_id THEN
            UPDATE users SET auth_version = auth_version + 1 WHERE id = NEW.user_id;
        END IF;
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER user_roles_bump_auth_version_insert_delete
AFTER INSERT OR DELETE ON user_roles
FOR EACH ROW EXECUTE FUNCTION bump_user_auth_version_for_role();

CREATE TRIGGER user_roles_bump_auth_version_update
AFTER UPDATE OF user_id, role_name ON user_roles
FOR EACH ROW
WHEN (
    OLD.user_id IS DISTINCT FROM NEW.user_id
    OR OLD.role_name IS DISTINCT FROM NEW.role_name
)
EXECUTE FUNCTION bump_user_auth_version_for_role();

CREATE TABLE auth_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    jti_hash char(64) NOT NULL UNIQUE
        CHECK (jti_hash ~ '^[0-9a-f]{64}$'),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    auth_version bigint NOT NULL CHECK (auth_version > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    idle_expires_at timestamptz NOT NULL,
    absolute_expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    revoked_reason text,
    CHECK (idle_expires_at <= absolute_expires_at),
    CHECK (absolute_expires_at > created_at),
    CHECK (revoked_reason IS NULL OR length(btrim(revoked_reason)) > 0)
);

CREATE INDEX auth_sessions_user_active_idx
ON auth_sessions (user_id, absolute_expires_at DESC)
WHERE revoked_at IS NULL;

CREATE INDEX auth_sessions_expiry_idx
ON auth_sessions (absolute_expires_at)
WHERE revoked_at IS NULL;

CREATE TABLE login_rate_limits (
    scope text NOT NULL CHECK (scope IN ('account', 'ip')),
    key_hash char(64) NOT NULL CHECK (key_hash ~ '^[0-9a-f]{64}$'),
    failure_count integer NOT NULL DEFAULT 0 CHECK (failure_count >= 0),
    window_started_at timestamptz NOT NULL,
    blocked_until timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (scope, key_hash)
);

CREATE INDEX login_rate_limits_blocked_idx
ON login_rate_limits (blocked_until)
WHERE blocked_until IS NOT NULL;
