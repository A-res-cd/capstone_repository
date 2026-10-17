CREATE TABLE IF NOT EXISTS signup_email_verifications (
    verification_id UUID PRIMARY KEY,
    email VARCHAR(254) NOT NULL,
    code_hash TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    verified_at TIMESTAMPTZ,
    consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS signup_email_verifications_email_idx
ON signup_email_verifications (email, created_at DESC);
CREATE INDEX IF NOT EXISTS signup_email_verifications_expiry_idx
ON signup_email_verifications (expires_at);
CREATE INDEX IF NOT EXISTS request_submission_cooldown_idx
ON request (user_id, capstone_id, request_date DESC) WHERE request_type = 'manuscript';
ALTER TABLE signup_email_verifications ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON signup_email_verifications FROM PUBLIC;
DO $$
DECLARE browser_role TEXT;
BEGIN
    FOREACH browser_role IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = browser_role) THEN
            EXECUTE FORMAT('REVOKE ALL ON signup_email_verifications FROM %I', browser_role);
        END IF;
    END LOOP;
END $$;
