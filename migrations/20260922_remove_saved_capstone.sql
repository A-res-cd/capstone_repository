-- Remove the retired Save Capstone feature and its saved entries.
BEGIN;

DROP TABLE IF EXISTS saved_capstone;

COMMIT;
