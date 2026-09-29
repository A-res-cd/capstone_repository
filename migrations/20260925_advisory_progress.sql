BEGIN;

CREATE TABLE IF NOT EXISTS advisory_requirement (
    requirement_id SERIAL PRIMARY KEY,
    professor_user_id INT NOT NULL REFERENCES "user"(user_id) ON DELETE CASCADE,
    group_id INT NOT NULL,
    title VARCHAR(160) NOT NULL CHECK (LENGTH(BTRIM(title)) > 0),
    instructions TEXT NOT NULL DEFAULT '',
    due_date DATE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (professor_user_id, requirement_id),
    FOREIGN KEY (professor_user_id, group_id)
        REFERENCES advisory_group(professor_user_id, group_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_advisory_requirement_group
    ON advisory_requirement(professor_user_id, group_id, is_active);

CREATE TABLE IF NOT EXISTS advisory_submission (
    submission_id SERIAL PRIMARY KEY,
    professor_user_id INT NOT NULL,
    requirement_id INT NOT NULL,
    student_user_id INT NOT NULL REFERENCES "user"(user_id) ON DELETE CASCADE,
    submission_kind VARCHAR(8) NOT NULL CHECK (submission_kind IN ('file', 'link')),
    external_url TEXT,
    storage_key VARCHAR(255),
    original_filename VARCHAR(255),
    mime_type VARCHAR(127),
    file_size BIGINT,
    student_note VARCHAR(2000) NOT NULL DEFAULT '',
    review_status VARCHAR(20) NOT NULL DEFAULT 'submitted'
        CHECK (review_status IN ('submitted', 'revision_requested', 'approved')),
    advisor_feedback VARCHAR(2000),
    reviewed_by_user_id INT REFERENCES "user"(user_id) ON DELETE SET NULL,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMPTZ,
    FOREIGN KEY (professor_user_id, requirement_id)
        REFERENCES advisory_requirement(professor_user_id, requirement_id) ON DELETE CASCADE,
    CHECK (
        (submission_kind = 'link' AND external_url IS NOT NULL
            AND storage_key IS NULL AND original_filename IS NULL
            AND mime_type IS NULL AND file_size IS NULL)
        OR
        (submission_kind = 'file' AND external_url IS NULL
            AND storage_key IS NOT NULL AND original_filename IS NOT NULL
            AND mime_type IS NOT NULL AND file_size IS NOT NULL AND file_size > 0)
    )
);

CREATE INDEX IF NOT EXISTS idx_advisory_submission_latest
    ON advisory_submission(requirement_id, student_user_id, submitted_at DESC, submission_id DESC);

COMMIT;
