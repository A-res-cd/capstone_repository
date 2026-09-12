"""Explicit, repeatable PostgreSQL migration runner for production deploys."""

import hashlib
import re
from pathlib import Path

from app.db.connection import db_connect


ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = ROOT / "migrations"
MIGRATION_LOCK_KEY = "capre.schema-migrations"
MIGRATION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_migration (
    migration_name VARCHAR(255) PRIMARY KEY,
    checksum CHAR(64) NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    applied_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER
)
"""
OUTER_TRANSACTION_MARKER = re.compile(r"(?im)^\s*(BEGIN|COMMIT);\s*$")


class MigrationError(RuntimeError):
    """Raised when migration state is unsafe to continue."""


def migration_files(migrations_dir=MIGRATIONS_DIR):
    return sorted(Path(migrations_dir).glob("*.sql"), key=lambda path: path.name)


def migration_checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _migration_sql(path):
    sql = path.read_text(encoding="utf-8")
    # Existing files contain their own outer BEGIN/COMMIT. Remove only those
    # standalone markers so the runner can commit the migration and its record
    # atomically. DO $$ BEGIN ... END $$ blocks remain untouched.
    return OUTER_TRANSACTION_MARKER.sub("", sql).strip()


def _lock_and_prepare(cursor):
    cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (MIGRATION_LOCK_KEY,))
    cursor.execute(MIGRATION_TABLE_SQL)


def _applied_migrations(cursor):
    cursor.execute(
        "SELECT migration_name, checksum FROM schema_migration ORDER BY migration_name"
    )
    return {row[0]: row[1] for row in cursor.fetchall()}


def _validate_applied_files(applied, files):
    known_names = {path.name for path in files}
    missing = sorted(set(applied) - known_names)
    if missing:
        raise MigrationError(
            "Applied migration file is missing from the repository: "
            + ", ".join(missing)
        )


def migration_status(migrations_dir=MIGRATIONS_DIR):
    files = migration_files(migrations_dir)
    conn = db_connect()
    cursor = conn.cursor()
    try:
        _lock_and_prepare(cursor)
        conn.commit()
        applied = _applied_migrations(cursor)
        _validate_applied_files(applied, files)

        return {
            "applied": [path.name for path in files if path.name in applied],
            "pending": [path.name for path in files if path.name not in applied],
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def upgrade_database(migrations_dir=MIGRATIONS_DIR):
    files = migration_files(migrations_dir)
    conn = db_connect()
    cursor = conn.cursor()
    applied_now = []
    try:
        _lock_and_prepare(cursor)
        conn.commit()
        _validate_applied_files(_applied_migrations(cursor), files)

        for path in files:
            checksum = migration_checksum(path)
            cursor.execute("SELECT checksum FROM schema_migration WHERE migration_name = %s", (path.name,))
            existing = cursor.fetchone()

            if existing:
                if existing[0] != checksum:
                    raise MigrationError(
                        f"Migration checksum changed after application: {path.name}"
                    )
                continue

            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (MIGRATION_LOCK_KEY,))
            cursor.execute(_migration_sql(path))
            cursor.execute(
                """
                INSERT INTO schema_migration (migration_name, checksum)
                VALUES (%s, %s)
                """,
                (path.name, checksum),
            )
            conn.commit()
            applied_now.append(path.name)

        _validate_applied_files(_applied_migrations(cursor), files)
        return applied_now
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()
