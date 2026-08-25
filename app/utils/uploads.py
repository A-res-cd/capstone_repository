import mimetypes
import os
import uuid

from flask import current_app
from werkzeug.utils import secure_filename


ALLOWED_MANUSCRIPT_EXTENSIONS = {"pdf", "doc", "docx"}


def allowed_manuscript(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_MANUSCRIPT_EXTENSIONS
    )


def manuscript_upload_folder():
    configured = current_app.config.get("UPLOAD_FOLDER")
    if configured:
        return os.path.abspath(configured)
    return os.path.join(current_app.instance_path, "uploads")


def unique_manuscript_filename(filename):
    filename = secure_filename(filename)
    name, ext = os.path.splitext(filename)
    return f"{name}_{uuid.uuid4().hex[:8]}{ext}"


def save_manuscript_upload(file_obj):
    if not file_obj or not file_obj.filename:
        return None, None
    if not allowed_manuscript(file_obj.filename):
        return None, "Invalid file type. Only PDF, DOC, and DOCX are allowed."

    folder = manuscript_upload_folder()
    os.makedirs(folder, exist_ok=True)

    filename = unique_manuscript_filename(file_obj.filename)
    file_obj.save(os.path.join(folder, filename))
    return filename, None


def stored_manuscript_path(filename):
    return f"uploads/{secure_filename(filename)}"


def resolve_manuscript_file(file_rel):
    if not file_rel:
        return None

    normalized = str(file_rel).replace("\\", "/").lstrip("/")
    if normalized.startswith("static/"):
        normalized = normalized.split("static/", 1)[1]

    filename = secure_filename(os.path.basename(normalized))
    if not filename:
        return None

    candidates = [
        os.path.join(manuscript_upload_folder(), filename),
        os.path.join(current_app.root_path, "static", "uploads", filename),
    ]

    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def manuscript_mimetype(path):
    return mimetypes.guess_type(path)[0] or "application/octet-stream"
