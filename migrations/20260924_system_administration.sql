-- Preserve existing academic authority; never auto-grant maintenance access.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM role WHERE role_name = 'Admin')
       AND EXISTS (SELECT 1 FROM role WHERE role_name = 'RET Chair') THEN
        RAISE EXCEPTION 'Both Admin and RET Chair exist. Resolve role mapping before migration.';
    END IF;
END $$;
UPDATE role SET role_name = 'RET Chair' WHERE role_name = 'Admin';
CREATE UNIQUE INDEX IF NOT EXISTS role_name_unique_idx ON role(role_name);
INSERT INTO role (role_id, role_name)
SELECT COALESCE(MAX(role_id), 0) + 1, 'RET Chair' FROM role
HAVING NOT EXISTS (SELECT 1 FROM role WHERE role_name = 'RET Chair');
INSERT INTO role (role_id, role_name)
SELECT COALESCE(MAX(role_id), 0) + 1, 'System Administrator' FROM role
HAVING NOT EXISTS (SELECT 1 FROM role WHERE role_name = 'System Administrator');
SELECT setval(pg_get_serial_sequence('role', 'role_id'), (SELECT MAX(role_id) FROM role));

ALTER TABLE "user" ADD COLUMN IF NOT EXISTS session_version BIGINT NOT NULL DEFAULT 0;
CREATE OR REPLACE FUNCTION invalidate_changed_identity() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.role_id IS DISTINCT FROM OLD.role_id
       OR NEW.account_status IS DISTINCT FROM OLD.account_status THEN
        NEW.session_version := OLD.session_version + 1;
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS invalidate_changed_identity ON "user";
CREATE TRIGGER invalidate_changed_identity BEFORE UPDATE ON "user"
FOR EACH ROW EXECUTE FUNCTION invalidate_changed_identity();

CREATE OR REPLACE FUNCTION invalidate_changed_password() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.is_current AND EXISTS (
        SELECT 1 FROM slug WHERE user_id=NEW.user_id AND password_id<>NEW.password_id
    ) THEN
        UPDATE "user" SET session_version=session_version+1 WHERE user_id=NEW.user_id;
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS invalidate_changed_password ON slug;
CREATE TRIGGER invalidate_changed_password AFTER INSERT OR UPDATE OF password_id, is_current ON slug
FOR EACH ROW EXECUTE FUNCTION invalidate_changed_password();

CREATE TABLE IF NOT EXISTS system_setting (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    maintenance_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    maintenance_start TIMESTAMPTZ,
    maintenance_end TIMESTAMPTZ,
    notice VARCHAR(500) NOT NULL DEFAULT 'Scheduled maintenance. Please try again shortly.',
    backup_interval_hours INT NOT NULL DEFAULT 24 CHECK (backup_interval_hours BETWEEN 1 AND 720),
    backup_keep INT NOT NULL DEFAULT 7 CHECK (backup_keep BETWEEN 2 AND 365),
    worker_seen_at TIMESTAMPTZ
);
INSERT INTO system_setting(singleton) VALUES (TRUE) ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS maintenance_job (
    job_id BIGSERIAL PRIMARY KEY,
    kind VARCHAR(40) NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}',
    status VARCHAR(20) NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    actor_id INT REFERENCES "user"(user_id) ON DELETE SET NULL,
    reason VARCHAR(500) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    result JSONB NOT NULL DEFAULT '{}'
);
CREATE UNIQUE INDEX IF NOT EXISTS maintenance_job_active_kind
ON maintenance_job(kind) WHERE status IN ('queued', 'running');

CREATE TABLE IF NOT EXISTS system_event (
    event_id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actor_id INT REFERENCES "user"(user_id) ON DELETE SET NULL,
    category VARCHAR(30) NOT NULL,
    severity VARCHAR(10) NOT NULL DEFAULT 'info',
    action VARCHAR(100) NOT NULL,
    request_id VARCHAR(50),
    reason VARCHAR(500) NOT NULL DEFAULT '',
    details JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS system_event_time_idx ON system_event(created_at DESC);
