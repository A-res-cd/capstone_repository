-- =========================================
-- CREATE DATABASE
-- =========================================
CREATE DATABASE capre;

-- Connect to capre database first in pgAdmin
-- Then run everything below


-- =========================================
-- ROLE TABLE
-- =========================================
CREATE TABLE IF NOT EXISTS role (
    role_id SERIAL PRIMARY KEY,
    role_name VARCHAR(50),
    role_level INT
);

-- =========================================
-- USER TABLE
-- =========================================
CREATE TABLE IF NOT EXISTS "user" (
    user_id SERIAL PRIMARY KEY,
    role_id INT,
    user_first_name VARCHAR(100),
    user_middle_name VARCHAR(100),
    user_last_name VARCHAR(100),
    university_no VARCHAR(50),
    locked_until TIMESTAMP,

    CONSTRAINT fk_user_role
        FOREIGN KEY (role_id)
        REFERENCES role(role_id)
);

-- =========================================
-- USERNAME TABLE
-- =========================================
CREATE TABLE IF NOT EXISTS kappa (
    username_id SERIAL PRIMARY KEY,
    username VARCHAR(100)
);

-- =========================================
-- PASSWORD TABLE
-- =========================================
CREATE TABLE IF NOT EXISTS ror (
    password_id SERIAL PRIMARY KEY,
    password VARCHAR(255),
    updated_at TIMESTAMP,
    previous_password_id INT DEFAULT NULL,

    CONSTRAINT fk_previous_password
        FOREIGN KEY (previous_password_id)
        REFERENCES ror(password_id)
);

-- =========================================
-- USER CREDENTIAL MAPPING
-- =========================================
CREATE TABLE IF NOT EXISTS slug (
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

-- =========================================
-- LOGIN TABLE
-- =========================================
CREATE TABLE IF NOT EXISTS login (
    log_in_id SERIAL PRIMARY KEY,
    user_id INT,
    log_in_time TIMESTAMP,
    login_device_ip VARCHAR(50),
    failed_attempts INT DEFAULT 0,

    CONSTRAINT fk_login_user
        FOREIGN KEY (user_id)
        REFERENCES "user"(user_id)
);

-- =========================================
-- LOGOUT TABLE
-- =========================================
CREATE TABLE IF NOT EXISTS logout (
    log_out_id SERIAL PRIMARY KEY,
    user_id INT,
    log_out_time TIMESTAMP,
    logout_device_ip VARCHAR(50),

    CONSTRAINT fk_logout_user
        FOREIGN KEY (user_id)
        REFERENCES "user"(user_id)
);

-- =========================================
-- SIGNUP TABLE
-- =========================================
CREATE TABLE IF NOT EXISTS signup (
    signup_id SERIAL PRIMARY KEY,
    user_id INT,
    registration_date TIMESTAMP,

    CONSTRAINT fk_signup_user
        FOREIGN KEY (user_id)
        REFERENCES "user"(user_id)
);

-- =========================================
-- AUDIT TABLE
-- =========================================
CREATE TABLE IF NOT EXISTS audit (
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

-- =========================================
-- CONTACT TABLE
-- =========================================
CREATE TABLE IF NOT EXISTS contact (
    contact_id SERIAL PRIMARY KEY,
    user_id INT,
    contact_type VARCHAR(50),
    contact_value VARCHAR(100),
    is_primary BOOLEAN,
    created_at TIMESTAMP,

    CONSTRAINT fk_contact_user
        FOREIGN KEY (user_id)
        REFERENCES "user"(user_id)
);

-- =========================================
-- PASSWORD RESET TABLE
-- =========================================
CREATE TABLE IF NOT EXISTS password_reset (
    reset_id SERIAL PRIMARY KEY,
    contact_id INT,
    reset_token VARCHAR(255),
    expiry_date TIMESTAMP,
    is_primary BOOLEAN,
    is_used BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    attempt_count INT DEFAULT 0,

    CONSTRAINT fk_password_reset_contact
        FOREIGN KEY (contact_id)
        REFERENCES contact(contact_id)
);

-- =========================================
-- PROGRAM TABLE
-- =========================================
CREATE TABLE IF NOT EXISTS program (
    program_id SERIAL PRIMARY KEY,
    program_name VARCHAR(100)
);

-- =========================================
-- SPECIALIZATION TABLE
-- =========================================
CREATE TABLE IF NOT EXISTS specialization (
    specialization_id SERIAL PRIMARY KEY,
    specialization_name VARCHAR(100)
);

-- =========================================
-- KEYWORD TABLE
-- =========================================
CREATE TABLE IF NOT EXISTS keyword (
    keyword_id SERIAL PRIMARY KEY,
    capstone_keywords TEXT
);

-- =========================================
-- CAPSTONE TABLE
-- =========================================
CREATE TABLE IF NOT EXISTS capstone (
    capstone_id SERIAL PRIMARY KEY,
    keyword_id INT,
    specialization_id INT,
    program_id INT,
    capstone_title VARCHAR(255),
    capstone_year INT,
    capstone_file TEXT,
    citation_count INT,
    semester VARCHAR(20),
    term INT,
    is_archived BOOLEAN DEFAULT FALSE,
    archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 

    CONSTRAINT fk_capstone_keyword
        FOREIGN KEY (keyword_id)
        REFERENCES keyword(keyword_id),

    CONSTRAINT fk_capstone_specialization
        FOREIGN KEY (specialization_id)
        REFERENCES specialization(specialization_id),

    CONSTRAINT fk_capstone_program
        FOREIGN KEY (program_id)
        REFERENCES program(program_id)
);

-- =========================================
-- AUTHOR TABLE
-- =========================================
CREATE TABLE IF NOT EXISTS author (
    author_id SERIAL PRIMARY KEY,
    aut_first_name VARCHAR(100),
    aut_middle_name VARCHAR(100),
    aut_last_name VARCHAR(100)
);

-- =========================================
-- CAPSTONE AUTHOR TABLE
-- =========================================
CREATE TABLE IF NOT EXISTS capauth (
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

-- =========================================
-- REQUEST TABLE
-- =========================================
CREATE TABLE IF NOT EXISTS request (
    request_id SERIAL PRIMARY KEY,
    user_id INT,
    capstone_id INT,
    request_status VARCHAR(50),
    request_reason TEXT,
    request_date TIMESTAMP,
    decision_date TIMESTAMP,
    reviewed_by INT,
    status_reason TEXT,

    CONSTRAINT fk_request_user
        FOREIGN KEY (user_id)
        REFERENCES "user"(user_id),

    CONSTRAINT fk_request_capstone
        FOREIGN KEY (capstone_id)
        REFERENCES capstone(capstone_id),

    CONSTRAINT fk_request_reviewer
        FOREIGN KEY (reviewed_by)
        REFERENCES "user"(user_id)
);