"""Read-only database checks used by deployment health probes."""

import logging

from app.db.connection import db_connect
from app.db.migration_runner import migration_checksum, migration_files


logger = logging.getLogger(__name__)


def database_is_ready():
    """Return True only when PostgreSQL and every tracked migration are ready."""
    conn = None
    cursor = None
    try:
        conn = db_connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT to_regclass('public."user"'),
                   to_regclass('public.capstone'),
                   to_regclass('public.schema_migration')
            """
        )
        tables = cursor.fetchone()
        if not tables or any(table is None for table in tables):
            logger.warning("Database readiness failed: required tables are missing")
            return False

        cursor.execute("SELECT migration_name, checksum FROM schema_migration")
        applied = {name: checksum for name, checksum in cursor.fetchall()}
        expected = {
            path.name: migration_checksum(path)
            for path in migration_files()
        }

        if set(expected) - set(applied):
            logger.warning("Database readiness failed: migrations are pending")
            return False
        if set(applied) - set(expected):
            logger.warning("Database readiness failed: an applied migration is missing")
            return False
        if any(applied[name] != checksum for name, checksum in expected.items()):
            logger.warning("Database readiness failed: a migration checksum changed")
            return False
        return True
    except Exception:
        logger.exception("Database readiness check failed")
        return False
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()
