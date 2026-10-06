-- Repair account/profile columns independently of repository migrations.
ALTER TABLE "user"
    ADD COLUMN IF NOT EXISTS preferred_contact VARCHAR(10) NOT NULL DEFAULT 'email'
        CHECK (preferred_contact IN ('email', 'phone')),
    ADD COLUMN IF NOT EXISTS avatar_filename TEXT,
    ADD COLUMN IF NOT EXISTS terms_version VARCHAR(30),
    ADD COLUMN IF NOT EXISTS terms_accepted_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS promotion_failures INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS promotion_locked_until TIMESTAMPTZ;
