-- Existing contacts retain recovery authority; no ownership evidence is invented.
ALTER TABLE contact ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ;
CREATE TABLE IF NOT EXISTS contact_changes (
    change_id UUID PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES "user"(user_id) ON DELETE CASCADE,
    contact_type TEXT NOT NULL CHECK (contact_type IN ('email', 'phone')),
    destination TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    session_hash TEXT NOT NULL,
    password_id INTEGER NOT NULL,
    preference TEXT NOT NULL CHECK (preference IN ('email', 'phone')),
    expires_at TIMESTAMPTZ NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    delivered_at TIMESTAMPTZ,
    consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS contact_changes_account_idx ON contact_changes(user_id);
ALTER TABLE contact_changes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON contact_changes FROM PUBLIC;
DO $$
DECLARE browser_role TEXT;
BEGIN
    FOREACH browser_role IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = browser_role) THEN
            EXECUTE format('REVOKE ALL ON contact_changes FROM %I', browser_role);
        END IF;
    END LOOP;
END $$;
