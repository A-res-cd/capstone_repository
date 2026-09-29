"""Private file storage for advisory progress submissions."""

import mimetypes
import os
import re
from pathlib import Path
from uuid import uuid4

from flask import current_app
from werkzeug.utils import secure_filename

from app.utils.malware_scan import scan_uploaded_file


ALLOWED_PROGRESS_EXTENSIONS = {
    "pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "txt", "rtf",
}
DEFAULT_PROGRESS_MAX_BYTES = 20 * 1024 * 1024


def progress_upload_folder():
    configured = current_app.config.get("UPLOAD_PROGRESS_FOLDER")
    if configured:
        folder = Path(configured).resolve()
    else:
        folder = Path(current_app.instance_path, "uploads", "advisory-progress").resolve()
    static_folder = Path(current_app.static_folder).resolve()
    try:
        folder.relative_to(static_folder)
    except ValueError:
        return folder
    raise RuntimeError("Advisory progress uploads must be stored outside the public static folder.")


def resolve_progress_upload(storage_key):
    if not isinstance(storage_key, str) or not re.fullmatch(
            r"progress_[a-f0-9]{32}\.[a-z0-9]{1,8}", storage_key):
        return None
    folder = progress_upload_folder()
    path = (folder / storage_key).resolve()
    return path if path.parent == folder else None


def save_progress_upload(upload):
    if not upload or not upload.filename:
        raise ValueError("Choose a file to submit.")

    original_name = secure_filename(upload.filename)
    extension = Path(original_name).suffix.lower().lstrip(".")
    if extension not in ALLOWED_PROGRESS_EXTENSIONS:
        raise ValueError("Use a PDF, Word, PowerPoint, Excel, RTF, or TXT file.")

    stream = upload.stream
    position = stream.tell()
    try:
        stream.seek(0, os.SEEK_END)
        file_size = stream.tell()
        stream.seek(0)
        max_bytes = current_app.config.get("UPLOAD_PROGRESS_MAX_BYTES", DEFAULT_PROGRESS_MAX_BYTES)
        if file_size <= 0 or file_size > max_bytes:
            raise ValueError("The file must be smaller than 20 MB.")

        folder = progress_upload_folder()
        folder.mkdir(parents=True, exist_ok=True)
        storage_key = f"progress_{uuid4().hex}.{extension}"
        path = folder / storage_key
        try:
            upload.save(path)
            scan_uploaded_file(path)
        except Exception:
            path.unlink(missing_ok=True)
            raise
    finally:
        stream.seek(position)

    mime_type = mimetypes.guess_type(original_name)[0] or "application/octet-stream"
    return {
        "storage_key": storage_key,
        "original_filename": original_name[:255] or f"submission.{extension}",
        "mime_type": mime_type[:127],
        "file_size": file_size,
        "path": path,
    }
