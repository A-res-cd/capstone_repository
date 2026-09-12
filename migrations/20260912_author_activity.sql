BEGIN;

-- One row represents a deduplicated interaction with a capstone.
CREATE TABLE IF NOT EXISTS capstone_activity (
    activity_id BIGSERIAL PRIMARY KEY,
    capstone_id INT NOT NULL REFERENCES capstone(capstone_id) ON DELETE CASCADE,
    actor_user_id INT REFERENCES "user"(user_id) ON DELETE SET NULL,
    event_type VARCHAR(30) NOT NULL CHECK (event_type IN ('view', 'citation', 'request')),
    event_variant VARCHAR(30),
    activity_day DATE NOT NULL,
    request_id INT UNIQUE REFERENCES request(request_id) ON DELETE SET NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_capstone_activity_daily_actor
    ON capstone_activity(capstone_id, actor_user_id, event_type, activity_day)
    WHERE event_type IN ('view', 'citation') AND actor_user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_capstone_activity_capstone
    ON capstone_activity(capstone_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS notification (
    notification_id BIGSERIAL PRIMARY KEY,
    recipient_user_id INT NOT NULL REFERENCES "user"(user_id) ON DELETE CASCADE,
    activity_id BIGINT REFERENCES capstone_activity(activity_id) ON DELETE CASCADE,
    notification_type VARCHAR(50) NOT NULL,
    notification_title VARCHAR(160) NOT NULL,
    notification_message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    read_at TIMESTAMPTZ,
    UNIQUE (activity_id, recipient_user_id)
);

CREATE INDEX IF NOT EXISTS idx_notification_recipient_unread
    ON notification(recipient_user_id, read_at, created_at DESC);

COMMIT;
