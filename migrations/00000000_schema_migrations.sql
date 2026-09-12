-- Tracks database migrations applied by migrate.py.
CREATE TABLE IF NOT EXISTS schema_migration (
    migration_name VARCHAR(255) PRIMARY KEY,
    checksum CHAR(64) NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    applied_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER
);
