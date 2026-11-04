-- CAPRE ERD-driven revision; additive upgrade for existing PostgreSQL installations.
-- Keep historical migrations intact; run this via scripts/migrate.py after a DB backup.
-- Existing signup rows remain valid and legacy registration writes continue working.

CREATE TABLE IF NOT EXISTS uploaded_by (
    upload_id SERIAL PRIMARY KEY,
    file_name TEXT NOT NULL,
    class_name VARCHAR(150),
    academic_year VARCHAR(30),
    semester VARCHAR(30),
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS roster (
    roster_id SERIAL PRIMARY KEY,
    upload_id INT NOT NULL REFERENCES uploaded_by(upload_id) ON DELETE RESTRICT,
    university_no VARCHAR(50),
    person_type VARCHAR(50),
    user_first_name VARCHAR(100),
    user_middle_name VARCHAR(100),
    user_last_name VARCHAR(100),
    contact VARCHAR(254),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE signup ADD COLUMN IF NOT EXISTS roster_id INT;
ALTER TABLE signup ADD COLUMN IF NOT EXISTS contact_id INT;
ALTER TABLE signup ADD COLUMN IF NOT EXISTS sub_person_type VARCHAR(50);
ALTER TABLE signup ADD COLUMN IF NOT EXISTS method VARCHAR(50);
ALTER TABLE signup ADD COLUMN IF NOT EXISTS status VARCHAR(30);
ALTER TABLE signup ADD COLUMN IF NOT EXISTS attempt_count INT NOT NULL DEFAULT 0;
ALTER TABLE signup ADD COLUMN IF NOT EXISTS reason TEXT;
ALTER TABLE signup ADD COLUMN IF NOT EXISTS reviewed_by INT;
ALTER TABLE signup ADD COLUMN IF NOT EXISTS requested_at TIMESTAMPTZ;
ALTER TABLE signup ADD COLUMN IF NOT EXISTS decided_at TIMESTAMPTZ;

-- Named FK creation is conditional to allow re-running the SQL safely.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'signup'::regclass AND conname = 'fk_signup_roster') THEN
        ALTER TABLE signup ADD CONSTRAINT fk_signup_roster FOREIGN KEY (roster_id) REFERENCES roster(roster_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'signup'::regclass AND conname = 'fk_signup_contact') THEN
        ALTER TABLE signup ADD CONSTRAINT fk_signup_contact FOREIGN KEY (contact_id) REFERENCES contact(contact_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'signup'::regclass AND conname = 'fk_signup_reviewer') THEN
        ALTER TABLE signup ADD CONSTRAINT fk_signup_reviewer FOREIGN KEY (reviewed_by) REFERENCES "user"(user_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'signup'::regclass AND conname = 'signup_attempt_count_nonnegative') THEN
        ALTER TABLE signup ADD CONSTRAINT signup_attempt_count_nonnegative CHECK (attempt_count >= 0);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS roster_upload_id_idx ON roster(upload_id);
CREATE INDEX IF NOT EXISTS roster_university_no_idx ON roster(university_no);
CREATE INDEX IF NOT EXISTS roster_contact_lower_idx ON roster(LOWER(contact));
CREATE INDEX IF NOT EXISTS signup_roster_id_idx ON signup(roster_id);
CREATE INDEX IF NOT EXISTS signup_user_id_idx ON signup(user_id);
CREATE INDEX IF NOT EXISTS signup_contact_id_idx ON signup(contact_id);
CREATE INDEX IF NOT EXISTS signup_reviewer_idx ON signup(reviewed_by);
CREATE INDEX IF NOT EXISTS signup_status_requested_idx ON signup(status, requested_at DESC);

-- Match existing server-only authentication tables on Supabase installations.
ALTER TABLE uploaded_by ENABLE ROW LEVEL SECURITY;
ALTER TABLE roster ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON uploaded_by, roster FROM PUBLIC;
DO $$
DECLARE
    browser_role TEXT;
BEGIN
    FOREACH browser_role IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = browser_role) THEN
            EXECUTE FORMAT('REVOKE ALL ON uploaded_by, roster FROM %I', browser_role);
        END IF;
    END LOOP;
END $$;

-- Preserve every legacy field and its original timestamp before removing storage.
-- The runner commits this archive, DROP and migration checksum atomically.
DO $$
BEGIN
    IF to_regclass('public.logout') IS NOT NULL THEN
        LOCK TABLE public.logout IN ACCESS EXCLUSIVE MODE;
        INSERT INTO public.audit
            (user_id, action_type, affected_table, affected_record_id,
             new_values, action_timestamp)
        SELECT user_id, 'logout', 'logout', log_out_id,
               row_to_json(legacy)::text, log_out_time
        FROM public.logout AS legacy;
    END IF;
END $$;

DROP TABLE IF EXISTS public.logout RESTRICT;
