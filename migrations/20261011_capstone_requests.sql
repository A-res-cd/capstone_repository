CREATE TABLE IF NOT EXISTS capstone_requests (
    id BIGSERIAL PRIMARY KEY,
    capstone_id INTEGER NOT NULL REFERENCES capstone(capstone_id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES "user"(user_id) ON DELETE SET NULL,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS capstone_requests_dedupe_idx
ON capstone_requests (capstone_id, user_id, requested_at DESC);
CREATE INDEX IF NOT EXISTS capstone_requests_period_idx
ON capstone_requests (requested_at DESC, capstone_id);

-- The Flask backend owns access; individual request logs are not public API data.
ALTER TABLE capstone_requests ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON capstone_requests FROM PUBLIC;
REVOKE ALL ON SEQUENCE capstone_requests_id_seq FROM PUBLIC;
DO $$
DECLARE
    browser_role TEXT;
BEGIN
    FOREACH browser_role IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = browser_role) THEN
            EXECUTE FORMAT('REVOKE ALL ON capstone_requests FROM %I', browser_role);
            EXECUTE FORMAT('REVOKE ALL ON SEQUENCE capstone_requests_id_seq FROM %I', browser_role);
        END IF;
    END LOOP;
END $$;
