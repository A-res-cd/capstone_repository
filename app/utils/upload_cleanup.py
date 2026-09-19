"""Read-only inventory of private files no longer referenced by the database."""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import current_app
from werkzeug.utils import secure_filename

from app.db.upload_references import get_referenced_uploads
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
    try:
        return {
            stored_name
            for value in get_referenced_uploads()
            if (stored_name := _stored_name(value))
        }
    except Exception:
        logger.exception("Upload inventory stopped: could not read file references")
        return None


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


def _retention_days():
    try:
        retention_days = int(current_app.config.get("UPLOAD_ORPHAN_RETENTION_DAYS", 30))
    except (TypeError, ValueError):
        logger.error("UPLOAD_ORPHAN_RETENTION_DAYS must be an integer")
        return None
    if retention_days < 1:
        logger.error("UPLOAD_ORPHAN_RETENTION_DAYS must be at least 1")
        return None
    return retention_days

def _upload_folders():
    return {
        Path(manuscript_upload_folder()).resolve(),
        registration_upload_folder(),
        avatar_upload_folder(),
    }


def _orphaned_uploads(referenced, retention_days):
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    orphaned = []

    for folder in _upload_folders():
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
                        "modified_at_ns": stat.st_mtime_ns,
                    })
            except OSError:
                logger.warning("Could not inspect upload during inventory: %s", path)
    return orphaned


def find_orphaned_uploads():
    """Return old unreferenced files without changing the filesystem."""
    retention_days = _retention_days()
    if retention_days is None:
        return []
    referenced = _referenced_upload_names()
    if referenced is None:
        return []
    return _orphaned_uploads(referenced, retention_days)


def delete_orphaned_uploads():
    """Delete only unchanged candidates after a fresh reference check."""
    retention_days = _retention_days()
    if retention_days is None:
        return 0
    referenced = _referenced_upload_names()
    if referenced is None:
        return 0

    allowed_folders = _upload_folders()
    deleted = 0
    for entry in _orphaned_uploads(referenced, retention_days):
        path = Path(entry["path"])
        try:
            resolved = path.resolve()
            if not any(resolved.is_relative_to(folder) for folder in allowed_folders):
                continue
            if path.is_symlink() or not path.is_file():
                continue
            stat = path.stat()
            if stat.st_size != entry["size_bytes"] or stat.st_mtime_ns != entry["modified_at_ns"]:
                continue
            path.unlink()
            deleted += 1
        except OSError:
            logger.warning("Could not remove orphaned upload: %s", path)
    return deleted
