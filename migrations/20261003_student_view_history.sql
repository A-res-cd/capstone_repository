CREATE TABLE IF NOT EXISTS capstone_view_history (
    user_id INTEGER NOT NULL REFERENCES "user"(user_id) ON DELETE CASCADE,
    capstone_id INTEGER NOT NULL REFERENCES capstone(capstone_id) ON DELETE CASCADE,
    viewed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, capstone_id)
);
CREATE INDEX IF NOT EXISTS capstone_view_history_recent_idx
ON capstone_view_history (user_id, viewed_at DESC, capstone_id DESC);
