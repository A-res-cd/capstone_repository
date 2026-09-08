BEGIN;

-- Apply after 20260908_advisory_students.sql. Names are unique per professor.
CREATE TABLE IF NOT EXISTS advisory_group (
    group_id SERIAL PRIMARY KEY,
    professor_user_id INT NOT NULL REFERENCES "user"(user_id) ON DELETE CASCADE,
    group_name VARCHAR(100) NOT NULL CHECK (LENGTH(BTRIM(group_name)) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (professor_user_id, group_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_advisory_group_name
    ON advisory_group(professor_user_id, LOWER(BTRIM(group_name)));

ALTER TABLE advisory_student ADD COLUMN IF NOT EXISTS group_id INT;

-- Preserve existing rosters only; professors with no students get no auto-group.
INSERT INTO advisory_group (professor_user_id, group_name)
SELECT DISTINCT professor_user_id, 'Existing advisory students'
FROM advisory_student WHERE group_id IS NULL
ON CONFLICT DO NOTHING;

UPDATE advisory_student s SET group_id = g.group_id
FROM advisory_group g
WHERE s.group_id IS NULL AND s.professor_user_id = g.professor_user_id
  AND LOWER(BTRIM(g.group_name)) = 'existing advisory students';

ALTER TABLE advisory_student ALTER COLUMN group_id SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'advisory_student_group_owner_fk'
          AND conrelid = 'advisory_student'::regclass
    ) THEN
        ALTER TABLE advisory_student
            ADD CONSTRAINT advisory_student_group_owner_fk
            FOREIGN KEY (professor_user_id, group_id)
            REFERENCES advisory_group(professor_user_id, group_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_advisory_student_group
    ON advisory_student(professor_user_id, group_id);

COMMIT;
