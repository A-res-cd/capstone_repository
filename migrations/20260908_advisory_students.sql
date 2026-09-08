BEGIN;

-- Explicit rosters, independent of registration decisions and capstone credits.
-- A student may be on multiple professors' rosters; no roster is transferred.
CREATE TABLE IF NOT EXISTS advisory_student (
    professor_user_id INT NOT NULL REFERENCES "user"(user_id) ON DELETE CASCADE,
    student_user_id INT NOT NULL REFERENCES "user"(user_id) ON DELETE CASCADE,
    added_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (professor_user_id, student_user_id),
    CHECK (professor_user_id <> student_user_id)
);

CREATE INDEX IF NOT EXISTS idx_advisory_student_student
    ON advisory_student(student_user_id);

COMMIT;
