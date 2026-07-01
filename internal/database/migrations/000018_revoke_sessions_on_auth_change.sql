CREATE OR REPLACE FUNCTION revoke_user_sessions_on_auth_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE auth_sessions
    SET revoked_at = now(), revoked_reason = 'principal_changed'
    WHERE user_id = NEW.id AND revoked_at IS NULL;
    RETURN NULL;
END;
$$;

CREATE TRIGGER users_revoke_sessions_on_auth_change
AFTER UPDATE OF auth_version ON users
FOR EACH ROW
WHEN (OLD.auth_version IS DISTINCT FROM NEW.auth_version)
EXECUTE FUNCTION revoke_user_sessions_on_auth_change();
