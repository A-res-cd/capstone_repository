-- Opaque mobile credentials. Only SHA-256 token digests are stored.
CREATE TABLE IF NOT EXISTS mobile_session (
    mobile_session_id BIGSERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES "user"(user_id) ON DELETE CASCADE,
    password_id INT NOT NULL REFERENCES ror(password_id) ON DELETE CASCADE,
    access_hash CHAR(64) NOT NULL UNIQUE,
    refresh_hash CHAR(64) NOT NULL UNIQUE,
    access_expires_at TIMESTAMPTZ NOT NULL,
    refresh_expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS mobile_session_user_idx ON mobile_session(user_id);
