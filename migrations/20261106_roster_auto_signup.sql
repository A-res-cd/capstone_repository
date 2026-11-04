-- Pending additive migration: diagram-aligned student-list eligibility.
-- Existing identity conflicts and unclassified uploads require explicit review.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM "user" WHERE NULLIF(UPPER(BTRIM(university_no)), '') IS NOT NULL
               GROUP BY UPPER(BTRIM(university_no)) HAVING COUNT(*) > 1) THEN
        RAISE EXCEPTION 'Duplicate normalized university numbers: resolve explicitly before migration';
    END IF;
    IF EXISTS (SELECT 1 FROM uploaded_by WHERE status NOT IN ('active','superseded') OR status IS NULL) THEN
        RAISE EXCEPTION 'Historical pending uploads require explicit review; preserve unclassified history as superseded, never auto-activate';
    END IF;
    IF EXISTS (SELECT 1 FROM signup WHERE status IN ('pending','approved') AND roster_id IS NOT NULL
               GROUP BY roster_id,status HAVING COUNT(*) > 1) THEN
        RAISE EXCEPTION 'Conflicting pending/approved roster claims: resolve explicitly before migration';
    END IF;
    IF EXISTS (SELECT 1 FROM roster WHERE person_type IS NULL OR person_type NOT IN ('Student','Faculty')
               OR NULLIF(BTRIM(university_no),'') IS NULL OR NULLIF(BTRIM(contact),'') IS NULL) THEN
        RAISE EXCEPTION 'Invalid historical roster identities require explicit review before migration';
    END IF;
    IF EXISTS (SELECT 1 FROM roster GROUP BY upload_id,UPPER(BTRIM(university_no)) HAVING COUNT(*)>1) THEN
        RAISE EXCEPTION 'Duplicate normalized roster identities within an upload require explicit review before migration';
    END IF;
END $$;

ALTER TABLE uploaded_by ADD COLUMN file_type VARCHAR(30) CHECK (file_type = 'student_list');
ALTER TABLE uploaded_by ALTER COLUMN status SET DEFAULT 'active';
ALTER TABLE uploaded_by ADD CONSTRAINT roster_upload_status CHECK (status IN ('active','superseded'));
ALTER TABLE uploaded_by ADD CONSTRAINT active_roster_metadata CHECK (status <> 'active' OR
    (file_type IS NOT NULL AND file_type='student_list' AND class_name IS NOT NULL AND BTRIM(class_name)<>''
     AND academic_year IS NOT NULL AND semester IS NOT NULL AND semester IN ('First','Second','Summer')));
ALTER TABLE uploaded_by ADD CONSTRAINT roster_upload_term CHECK (status <> 'active' OR
    CASE WHEN academic_year ~ '^[0-9]{4}-[0-9]{4}$' THEN
       SPLIT_PART(academic_year,'-',1)::int BETWEEN 1900 AND 2200
       AND SPLIT_PART(academic_year,'-',2)::int = SPLIT_PART(academic_year,'-',1)::int + 1
    ELSE FALSE END);
ALTER TABLE roster ADD CONSTRAINT roster_student_type CHECK (person_type IN ('Student','Faculty'));
ALTER TABLE roster ALTER COLUMN person_type SET NOT NULL;
ALTER TABLE roster ADD CONSTRAINT roster_number_required CHECK (NULLIF(BTRIM(university_no),'') IS NOT NULL);
ALTER TABLE roster ADD CONSTRAINT roster_email_required CHECK (NULLIF(BTRIM(contact),'') IS NOT NULL);
CREATE UNIQUE INDEX user_normalized_number_unique ON "user" (NULLIF(UPPER(BTRIM(university_no)), ''));
CREATE UNIQUE INDEX signup_pending_roster_unique ON signup(roster_id) WHERE status='pending' AND roster_id IS NOT NULL;
CREATE UNIQUE INDEX signup_approved_roster_unique ON signup(roster_id) WHERE status='approved' AND roster_id IS NOT NULL;
CREATE UNIQUE INDEX roster_upload_number_unique ON roster(upload_id,UPPER(BTRIM(university_no)));
CREATE INDEX roster_matching_idx ON roster(UPPER(BTRIM(university_no)),LOWER(BTRIM(contact)),person_type,upload_id);
CREATE INDEX uploaded_by_active_list_idx ON uploaded_by(file_type) WHERE status='active';

CREATE TABLE signup_decision_delivery (
    delivery_id BIGSERIAL PRIMARY KEY,
    signup_id INT NOT NULL UNIQUE REFERENCES signup(signup_id) ON DELETE CASCADE,
    recipient_email VARCHAR(254) NOT NULL,
    attempts INT NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    delivered_at TIMESTAMPTZ
);
CREATE INDEX signup_delivery_pending_idx ON signup_decision_delivery(available_at,delivery_id) WHERE delivered_at IS NULL;
ALTER TABLE signup_decision_delivery ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON signup_decision_delivery FROM PUBLIC;
REVOKE ALL ON SEQUENCE signup_decision_delivery_delivery_id_seq FROM PUBLIC;
DO $$
DECLARE browser_role TEXT;
BEGIN
    FOREACH browser_role IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = browser_role) THEN
            EXECUTE FORMAT('REVOKE ALL ON signup_decision_delivery FROM %I', browser_role);
            EXECUTE FORMAT('REVOKE ALL ON SEQUENCE signup_decision_delivery_delivery_id_seq FROM %I', browser_role);
        END IF;
    END LOOP;
END $$;

-- Necessary transient infrastructure: trusted payloads, session binding and receipts.
CREATE TABLE roster_import_stage (
    stage_id UUID PRIMARY KEY,
    actor_id INT NOT NULL REFERENCES "user"(user_id) ON DELETE CASCADE,
    session_hash CHAR(64) NOT NULL,
    payload JSONB NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    upload_id INT UNIQUE REFERENCES uploaded_by(upload_id) ON DELETE RESTRICT
);
CREATE INDEX roster_stage_expiry_idx ON roster_import_stage(expires_at);
ALTER TABLE roster_import_stage ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON roster_import_stage FROM PUBLIC;
DO $$
DECLARE browser_role TEXT;
BEGIN
    FOREACH browser_role IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=browser_role) THEN
            EXECUTE FORMAT('REVOKE ALL ON roster_import_stage FROM %I',browser_role);
        END IF;
    END LOOP;
END $$;
