-- Run on the ORIGINAL branch database before starting the updated app.
-- Additive: existing accounts remain valid without a COR filename.
BEGIN;
ALTER TABLE "user" ADD COLUMN IF NOT EXISTS cor_filename VARCHAR(200);
-- Any table from an earlier draft is deliberately left untouched to preserve data.
COMMIT;
