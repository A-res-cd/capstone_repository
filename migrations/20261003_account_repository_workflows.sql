ALTER TABLE "user"
    ADD COLUMN IF NOT EXISTS preferred_contact VARCHAR(10) NOT NULL DEFAULT 'email'
        CHECK (preferred_contact IN ('email', 'phone')),
    ADD COLUMN IF NOT EXISTS avatar_filename TEXT,
    ADD COLUMN IF NOT EXISTS terms_version VARCHAR(30),
    ADD COLUMN IF NOT EXISTS terms_accepted_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS promotion_failures INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS promotion_locked_until TIMESTAMPTZ;

-- NULL means that a historical record still needs publication review.
ALTER TABLE capstone ADD COLUMN IF NOT EXISTS is_published BOOLEAN;
ALTER TABLE capstone ALTER COLUMN is_published SET DEFAULT FALSE;
ALTER TABLE capstone ADD COLUMN IF NOT EXISTS abstract_text TEXT;

ALTER TABLE program ADD COLUMN IF NOT EXISTS program_code VARCHAR(30);
ALTER TABLE specialization ADD COLUMN IF NOT EXISTS specialization_code VARCHAR(30);
UPDATE program SET program_code = program_name WHERE program_code IS NULL;
UPDATE specialization SET specialization_code = specialization_name
WHERE specialization_code IS NULL;
UPDATE program SET program_name = 'Bachelor of Science in Information Technology'
WHERE program_code = 'BSIT';
INSERT INTO program (program_code, program_name)
SELECT 'BSDS', 'Bachelor of Science in Data Science'
WHERE NOT EXISTS (SELECT 1 FROM program WHERE program_code = 'BSDS');

CREATE TABLE IF NOT EXISTS program_specialization (
    program_id INTEGER REFERENCES program(program_id),
    specialization_id INTEGER REFERENCES specialization(specialization_id),
    PRIMARY KEY (program_id, specialization_id)
);
INSERT INTO program_specialization (program_id, specialization_id)
SELECT DISTINCT program_id, specialization_id FROM capstone
WHERE program_id IS NOT NULL AND specialization_id IS NOT NULL
ON CONFLICT DO NOTHING;
INSERT INTO program_specialization (program_id, specialization_id)
SELECT p.program_id, s.specialization_id FROM program p CROSS JOIN specialization s
WHERE p.program_code = 'BSIT' AND s.specialization_code IN ('DST', 'NST', 'WST')
ON CONFLICT DO NOTHING;
-- BSDS can be catalogued without inventing an institution-specific track.
INSERT INTO specialization (specialization_code, specialization_name)
SELECT 'GENERAL', 'No specialization'
WHERE NOT EXISTS (SELECT 1 FROM specialization WHERE specialization_code = 'GENERAL');
INSERT INTO program_specialization (program_id, specialization_id)
SELECT p.program_id, s.specialization_id FROM program p CROSS JOIN specialization s
WHERE p.program_code = 'BSDS' AND s.specialization_code = 'GENERAL'
ON CONFLICT DO NOTHING;

CREATE INDEX IF NOT EXISTS request_review_history_idx
ON request (decision_date DESC, request_id DESC) WHERE decision_date IS NOT NULL;

UPDATE specialization SET specialization_name = CASE specialization_code
    WHEN 'DST' THEN 'Database Systems Technology'
    WHEN 'NST' THEN 'Network Systems Technology'
    WHEN 'WST' THEN 'Web Systems Technology'
    ELSE specialization_name END;
