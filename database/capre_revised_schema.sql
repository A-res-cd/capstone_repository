-- CAPRE REVISED SCHEMA based on database/capre_original_final.sql
-- This is a fresh-database reference schema, not a migration for an existing database.
-- The original SQL has been preserved. ERD-driven additions: uploaded_by, roster,
-- signup roster/contact/review metadata. Legacy signup.registration_date retained.
-- A separate additive migration is provided for existing installations.

-- CAPRE PostgreSQL schema / ERD image reference, updated 2026-10-17.
-- Each CREATE TABLE defines an entity; PRIMARY KEY and REFERENCES define
-- diagram keys and relationships. Nullable foreign keys are optional links.
-- For an image, use a crow's-foot ERD with column types and PK/FK markers;
-- preserve these table names and draw only explicitly declared relationships.
-- Account entities: role, user, kappa (usernames), ror (password history),
-- slug (credential assignments), contact, login, signup, password_reset.
-- Repository entities: program, specialization, capstone, keyword, author.
-- Junctions: capstone_keyword links capstones/keywords; capauth links
-- capstones/authors and stores Author/Adviser roles and display order.
-- Workflow/history: request, capstone_requests, capstone_view_history, audit.
-- request stores manuscript access and account-verification decisions.
-- capstone_requests logs deduplicated manuscript submissions for popularity;
-- capstone_view_history stores each user's most recent view of each capstone.
-- auth_rate_limit is infrastructure with no foreign-key relationships.
-- signup_email_verifications stores short-lived pre-account email ownership
-- proofs. It has no user foreign key because verification precedes signup.
-- contact_changes stores pending contact ownership checks linked to a user.
-- Indexes, access policies and migration bookkeeping are applied separately
-- by scripts/migrate.py or scripts/setup_supabase.py.

CREATE TABLE role (
    role_id SERIAL PRIMARY KEY,
    role_name VARCHAR(50),
    role_level INT
);

CREATE TABLE "user" (
    user_id SERIAL PRIMARY KEY,
    role_id INT,
    user_first_name VARCHAR(100),
    user_middle_name VARCHAR(100),
    user_last_name VARCHAR(100),
    university_no VARCHAR(50), -- Student examples: 2017100890, 2026-12345, SUM2023-01246.
    locked_until TIMESTAMP,
    account_status VARCHAR(20) DEFAULT 'pending',
    cor_filename VARCHAR(200),
    preferred_contact VARCHAR(10) NOT NULL DEFAULT 'email'
        CHECK (preferred_contact IN ('email', 'phone')),
    avatar_filename TEXT,
    terms_version VARCHAR(30),
    terms_accepted_at TIMESTAMPTZ,
    promotion_failures INTEGER NOT NULL DEFAULT 0,
    promotion_locked_until TIMESTAMPTZ,

    CONSTRAINT fk_user_role
        FOREIGN KEY (role_id)
        REFERENCES role(role_id)
);

CREATE TABLE kappa (
    username_id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL
);

CREATE TABLE ror (
    password_id SERIAL PRIMARY KEY,
    password VARCHAR(255),
    updated_at TIMESTAMP,
    previous_password_id INT DEFAULT NULL,

    CONSTRAINT fk_previous_password
        FOREIGN KEY (previous_password_id)
        REFERENCES ror(password_id)
);

CREATE TABLE slug (
    username_id INT,
    password_id INT,
    user_id INT,
    assigned_at TIMESTAMP,
    updated_at TIMESTAMP,
    is_current BOOLEAN,

    PRIMARY KEY (username_id, password_id),

    CONSTRAINT fk_slug_username
        FOREIGN KEY (username_id)
        REFERENCES kappa(username_id),

    CONSTRAINT fk_slug_password
        FOREIGN KEY (password_id)
        REFERENCES ror(password_id),

    CONSTRAINT fk_slug_user
        FOREIGN KEY (user_id)
        REFERENCES "user"(user_id)
);

CREATE TABLE login (
    log_in_id SERIAL PRIMARY KEY,
    user_id INT,
    log_in_time TIMESTAMP,
    login_device_ip VARCHAR(50),
    failed_attempts INT DEFAULT 0,

    CONSTRAINT fk_login_user
        FOREIGN KEY (user_id)
        REFERENCES "user"(user_id)
);


-- ERD revision: enrollment/roster source uploads and roster identities.
-- upload_id represents an imported roster file, not the application user who uploaded it.
CREATE TABLE uploaded_by (
    upload_id SERIAL PRIMARY KEY,
    file_name TEXT NOT NULL,
    class_name VARCHAR(150),
    academic_year VARCHAR(30),
    semester VARCHAR(30),
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE roster (
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

CREATE INDEX roster_upload_id_idx ON roster(upload_id);
CREATE INDEX roster_university_no_idx ON roster(university_no);
CREATE INDEX roster_contact_lower_idx ON roster(LOWER(contact));



CREATE TABLE audit (
    audit_id SERIAL PRIMARY KEY,
    user_id INT,
    action_type VARCHAR(50),
    affected_table VARCHAR(100),
    affected_record_id INT,
    old_values TEXT,
    new_values TEXT,
    action_timestamp TIMESTAMP,

    CONSTRAINT fk_audit_user
        FOREIGN KEY (user_id)
        REFERENCES "user"(user_id)
);

CREATE TABLE contact (
    contact_id SERIAL PRIMARY KEY,
    user_id INT,
    contact_type VARCHAR(50),
    contact_value VARCHAR(100),
    is_primary BOOLEAN,
    created_at TIMESTAMP,
    verified_at TIMESTAMPTZ,

    CONSTRAINT fk_contact_user
        FOREIGN KEY (user_id)
        REFERENCES "user"(user_id)
);

CREATE TABLE signup (
    signup_id SERIAL PRIMARY KEY,
    user_id INT,
    registration_date TIMESTAMP, -- Retained for compatibility with existing registration logic.
    roster_id INT,
    contact_id INT,
    sub_person_type VARCHAR(50),
    method VARCHAR(50),
    status VARCHAR(30),
    attempt_count INT NOT NULL DEFAULT 0 CONSTRAINT signup_attempt_count_nonnegative CHECK (attempt_count >= 0),
    reason TEXT,
    reviewed_by INT,
    requested_at TIMESTAMPTZ,
    decided_at TIMESTAMPTZ,

    CONSTRAINT fk_signup_user FOREIGN KEY (user_id) REFERENCES "user"(user_id),
    CONSTRAINT fk_signup_roster FOREIGN KEY (roster_id) REFERENCES roster(roster_id),
    CONSTRAINT fk_signup_contact FOREIGN KEY (contact_id) REFERENCES contact(contact_id),
    CONSTRAINT fk_signup_reviewer FOREIGN KEY (reviewed_by) REFERENCES "user"(user_id)
);

CREATE INDEX signup_roster_id_idx ON signup(roster_id);
CREATE INDEX signup_user_id_idx ON signup(user_id);
CREATE INDEX signup_contact_id_idx ON signup(contact_id);
CREATE INDEX signup_reviewer_idx ON signup(reviewed_by);
CREATE INDEX signup_status_requested_idx ON signup(status, requested_at DESC);

CREATE TABLE contact_changes (
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

CREATE TABLE password_reset (
    reset_id SERIAL PRIMARY KEY,
    contact_id INT,
    reset_token VARCHAR(255),
    expiry_date TIMESTAMP,
    is_primary BOOLEAN,
    is_used BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    attempt_count INT DEFAULT 0,
    verified_at TIMESTAMPTZ,

    CONSTRAINT fk_password_reset_contact
        FOREIGN KEY (contact_id)
        REFERENCES contact(contact_id)
);

CREATE TABLE program (
    program_id SERIAL PRIMARY KEY,
    program_name VARCHAR(100),
    program_code VARCHAR(30)
);

CREATE TABLE specialization (
    specialization_id SERIAL PRIMARY KEY,
    specialization_name VARCHAR(100),
    specialization_code VARCHAR(30)
);

CREATE TABLE keyword (
    keyword_id SERIAL PRIMARY KEY,
    keyword_text TEXT NOT NULL,
    CONSTRAINT keyword_text_unique UNIQUE (keyword_text),
    CONSTRAINT keyword_text_normalized CHECK (
        keyword_text <> '' AND keyword_text = LOWER(BTRIM(keyword_text))
        AND POSITION(',' IN keyword_text) = 0
    )
);

CREATE TABLE capstone (
    capstone_id SERIAL PRIMARY KEY,
    specialization_id INT,
    program_id INT,
    capstone_title VARCHAR(255),
    capstone_year INT,
    capstone_file TEXT,
    semester VARCHAR(20),
    term INT,
    is_archived BOOLEAN DEFAULT FALSE,
    archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_utilized BOOLEAN DEFAULT FALSE,
    is_presented BOOLEAN DEFAULT FALSE,
    is_copyright_registered BOOLEAN DEFAULT FALSE,
    is_published BOOLEAN DEFAULT FALSE,
    abstract_text TEXT,

    CONSTRAINT fk_capstone_specialization
        FOREIGN KEY (specialization_id)
        REFERENCES specialization(specialization_id),

    CONSTRAINT fk_capstone_program
        FOREIGN KEY (program_id)
        REFERENCES program(program_id)
);

CREATE TABLE capstone_keyword (
    capstone_id INT REFERENCES capstone(capstone_id) ON DELETE CASCADE,
    keyword_id INT REFERENCES keyword(keyword_id) ON DELETE CASCADE,
    PRIMARY KEY (capstone_id, keyword_id)
);

CREATE TABLE author (
    author_id SERIAL PRIMARY KEY,
    aut_first_name VARCHAR(100),
    aut_middle_name VARCHAR(100),
    aut_last_name VARCHAR(100)
);

CREATE TABLE capauth (
    capstone_id INT,
    author_id INT,
    role VARCHAR(50),
    author_order INT,

    PRIMARY KEY (capstone_id, author_id),

    CONSTRAINT fk_capauth_capstone
        FOREIGN KEY (capstone_id)
        REFERENCES capstone(capstone_id),

    CONSTRAINT fk_capauth_author
        FOREIGN KEY (author_id)
        REFERENCES author(author_id)
);

CREATE TABLE request (
    request_id SERIAL PRIMARY KEY,
    user_id INT,
    capstone_id INT,
    request_status VARCHAR(50),
    request_reason TEXT,
    request_date TIMESTAMP,
    decision_date TIMESTAMP,
    reviewed_by INT,
    status_reason TEXT,
    request_type VARCHAR(50) DEFAULT 'manuscript',
    notification_seen_at TIMESTAMP,

    target_role_id INT,

    CONSTRAINT fk_request_user
        FOREIGN KEY (user_id)
        REFERENCES "user"(user_id),

    CONSTRAINT fk_request_capstone
        FOREIGN KEY (capstone_id)
        REFERENCES capstone(capstone_id)
        ON DELETE SET NULL,

    CONSTRAINT fk_request_reviewer
        FOREIGN KEY (reviewed_by)
        REFERENCES "user"(user_id),

    CONSTRAINT fk_request_target_role
        FOREIGN KEY (target_role_id)
        REFERENCES role(role_id)
);

CREATE TABLE capstone_view_history (
    user_id INTEGER NOT NULL REFERENCES "user"(user_id) ON DELETE CASCADE,
    capstone_id INTEGER NOT NULL REFERENCES capstone(capstone_id) ON DELETE CASCADE,
    viewed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, capstone_id)
);

CREATE TABLE capstone_requests (
    id BIGSERIAL PRIMARY KEY,
    capstone_id INTEGER NOT NULL REFERENCES capstone(capstone_id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES "user"(user_id) ON DELETE SET NULL,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE auth_rate_limit (
    bucket_key CHAR(64) PRIMARY KEY,
    window_start TIMESTAMPTZ NOT NULL,
    attempts INTEGER NOT NULL
);

CREATE TABLE signup_email_verifications (
    verification_id UUID PRIMARY KEY,
    email VARCHAR(254) NOT NULL,
    code_hash TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    verified_at TIMESTAMPTZ,
    consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
