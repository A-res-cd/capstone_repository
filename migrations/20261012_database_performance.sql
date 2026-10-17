-- Optional additive indexes for measured public-page query patterns.
-- For a live database, build with CREATE INDEX CONCURRENTLY outside a transaction.
CREATE INDEX IF NOT EXISTS request_notifications_recent_idx
ON request (user_id, decision_date DESC, request_id DESC)
INCLUDE (notification_seen_at)
WHERE request_type IS DISTINCT FROM 'promotion'
  AND decision_date IS NOT NULL AND request_status IN ('approved', 'rejected');

CREATE INDEX IF NOT EXISTS request_approved_capstone_idx
ON request (user_id, capstone_id)
WHERE request_status = 'approved';
