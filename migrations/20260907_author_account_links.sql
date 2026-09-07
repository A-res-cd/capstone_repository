BEGIN;

-- Existing authors stay unlinked; names are never used to claim an account.
ALTER TABLE author ADD COLUMN IF NOT EXISTS user_id INT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_author_user' AND conrelid = 'author'::regclass
    ) THEN
        ALTER TABLE author ADD CONSTRAINT fk_author_user
            FOREIGN KEY (user_id) REFERENCES "user"(user_id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_author_user ON author(user_id);

COMMIT;
