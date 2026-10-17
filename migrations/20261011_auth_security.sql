-- Shared throttling across workers and server-side reset verification.
ALTER TABLE password_reset ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS auth_rate_limit (
    bucket_key CHAR(64) PRIMARY KEY,
    window_start TIMESTAMPTZ NOT NULL,
    attempts INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS auth_rate_limit_window_idx ON auth_rate_limit(window_start);
ALTER TABLE auth_rate_limit ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON auth_rate_limit FROM PUBLIC;
DO $$
DECLARE
    browser_role TEXT;
BEGIN
    FOREACH browser_role IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = browser_role) THEN
            EXECUTE FORMAT('REVOKE ALL ON auth_rate_limit FROM %I', browser_role);
        END IF;
    END LOOP;
END $$;
