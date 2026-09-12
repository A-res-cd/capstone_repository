"""Read-only inventory of private files no longer referenced by the database."""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import current_app
from werkzeug.utils import secure_filename

from app.db.connection import db_connect
from app.utils.avatar_uploads import avatar_upload_folder
from app.utils.cor_upload import registration_upload_folder
from app.utils.uploads import manuscript_upload_folder


logger = logging.getLogger(__name__)


def _stored_name(value):
    if not value:
        return None
    normalized = str(value).replace("\\", "/")
    return secure_filename(Path(normalized).name) or None


def _referenced_upload_names():
    conn = None
    cursor = None
    try:
        conn = db_connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT capstone_file FROM capstone WHERE capstone_file IS NOT NULL
            UNION ALL
            SELECT cor_filename FROM "user" WHERE cor_filename IS NOT NULL
            UNION ALL
            SELECT cor_filename FROM cor_registration
            WHERE cor_filename IS NOT NULL
            UNION ALL
            SELECT storage_key FROM user_avatar
            """
        )
        return {
            stored_name
            for row in cursor.fetchall()
            if (stored_name := _stored_name(row[0]))
        }
    except Exception:
        conn.rollback()
        logger.exception("Upload inventory stopped: could not read file references")
        return None
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def _files_in(folder):
    folder = Path(folder).resolve()
    if not folder.is_dir():
        return []

    files = []
    for path in folder.iterdir():
        if path.is_symlink() or not path.is_file():
            continue
        resolved = path.resolve()
        if resolved.is_relative_to(folder):
            files.append(path)
    return files


def find_orphaned_uploads():
    """Return old unreferenced files without changing the filesystem."""
    try:
        retention_days = int(
            current_app.config.get("UPLOAD_ORPHAN_RETENTION_DAYS", 30)
        )
    except (TypeError, ValueError):
        logger.error("UPLOAD_ORPHAN_RETENTION_DAYS must be an integer")
        return []
    if retention_days < 1:
        logger.error("UPLOAD_ORPHAN_RETENTION_DAYS must be at least 1")
        return []

    referenced = _referenced_upload_names()
    if referenced is None:
        return []

    folders = {
        Path(manuscript_upload_folder()).resolve(),
        registration_upload_folder(),
        avatar_upload_folder(),
    }
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    orphaned = []

    for folder in folders:
        for path in _files_in(folder):
            if path.name in referenced:
                continue
            try:
                stat = path.stat()
                modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                if modified_at < cutoff:
                    orphaned.append({
                        "path": str(path),
                        "size_bytes": stat.st_size,
                        "modified_at": modified_at,
                    })
            except OSError:
                logger.warning("Could not inspect upload during inventory: %s", path)
    return orphaned
