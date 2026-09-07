BEGIN;

-- Run after 20260907_author_account_links.sql. No role/account-status changes,
-- and no existing user or author is automatically registered or linked.
CREATE UNIQUE INDEX IF NOT EXISTS idx_request_capstoner_open
    ON request(user_id)
    WHERE request_type = 'capstoner' AND request_status IN ('pending', 'approved');

COMMIT;
