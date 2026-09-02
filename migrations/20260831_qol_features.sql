BEGIN;

ALTER TABLE request
    ADD COLUMN IF NOT EXISTS notification_seen_at TIMESTAMP;

CREATE TABLE IF NOT EXISTS saved_capstone (
    user_id INT NOT NULL REFERENCES "user"(user_id) ON DELETE CASCADE,
    capstone_id INT NOT NULL REFERENCES capstone(capstone_id) ON DELETE CASCADE,
    saved_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, capstone_id)
);

CREATE INDEX IF NOT EXISTS idx_saved_capstone_capstone
    ON saved_capstone(capstone_id);

CREATE INDEX IF NOT EXISTS idx_request_user_decision
    ON request(user_id, decision_date DESC)
    WHERE decision_date IS NOT NULL;

COMMIT;
