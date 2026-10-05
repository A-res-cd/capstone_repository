-- Repository improvements only; retain current roles and existing features.
ALTER TABLE capstone ADD COLUMN IF NOT EXISTS is_published BOOLEAN;
ALTER TABLE capstone ALTER COLUMN is_published SET DEFAULT FALSE;
ALTER TABLE capstone ADD COLUMN IF NOT EXISTS abstract_text TEXT;

ALTER TABLE program ADD COLUMN IF NOT EXISTS program_code VARCHAR(30);
ALTER TABLE specialization ADD COLUMN IF NOT EXISTS specialization_code VARCHAR(30);
UPDATE program SET program_code = CASE
    WHEN program_name = 'Bachelor of Science in Information Technology' THEN 'BSIT'
    WHEN program_name = 'Bachelor of Science in Data Science' THEN 'BSDS'
    ELSE CASE WHEN LENGTH(program_name) <= 30 THEN program_name END
    END WHERE program_code IS NULL;
UPDATE specialization SET specialization_code = CASE
    WHEN specialization_name = 'Database Systems Technology' THEN 'DST'
    WHEN specialization_name = 'Network Systems Technology' THEN 'NST'
    WHEN specialization_name = 'Web Systems Technology' THEN 'WST'
    WHEN specialization_name = 'No specialization' THEN 'GENERAL'
    ELSE CASE WHEN LENGTH(specialization_name) <= 30 THEN specialization_name END
    END WHERE specialization_code IS NULL;
UPDATE program SET program_name = 'Bachelor of Science in Information Technology'
WHERE program_code = 'BSIT';
INSERT INTO program (program_code, program_name)
SELECT 'BSDS', 'Bachelor of Science in Data Science'
WHERE NOT EXISTS (SELECT 1 FROM program WHERE program_code = 'BSDS');
INSERT INTO specialization (specialization_code, specialization_name)
SELECT 'GENERAL', 'No specialization'
WHERE NOT EXISTS (SELECT 1 FROM specialization WHERE specialization_code = 'GENERAL');
UPDATE specialization SET specialization_name = CASE specialization_code
    WHEN 'DST' THEN 'Database Systems Technology'
    WHEN 'NST' THEN 'Network Systems Technology'
    WHEN 'WST' THEN 'Web Systems Technology'
    ELSE specialization_name END;

CREATE TABLE IF NOT EXISTS capstone_view_history (
    user_id INTEGER NOT NULL REFERENCES "user"(user_id) ON DELETE CASCADE,
    capstone_id INTEGER NOT NULL REFERENCES capstone(capstone_id) ON DELETE CASCADE,
    viewed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, capstone_id)
);
CREATE INDEX IF NOT EXISTS capstone_view_history_recent_idx
ON capstone_view_history (user_id, viewed_at DESC, capstone_id DESC);
CREATE INDEX IF NOT EXISTS request_review_history_idx
ON request (decision_date DESC, request_id DESC) WHERE decision_date IS NOT NULL;
