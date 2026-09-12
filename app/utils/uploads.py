import mimetypes
import os
import uuid

from flask import current_app
from werkzeug.utils import secure_filename


ALLOWED_MANUSCRIPT_EXTENSIONS = {"pdf", "doc", "docx"}
DEFAULT_MANUSCRIPT_MAX_BYTES = 20 * 1024 * 1024
PDF_SIGNATURE = b"%PDF-"
OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def allowed_manuscript(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_MANUSCRIPT_EXTENSIONS
    )


def manuscript_upload_folder():
    configured = current_app.config.get("UPLOAD_MANUSCRIPT_FOLDER") or current_app.config.get("UPLOAD_FOLDER")
    if configured:
        return os.path.abspath(configured)
    return os.path.join(current_app.instance_path, "uploads")


def unique_manuscript_filename(filename):
    filename = secure_filename(filename)
    name, ext = os.path.splitext(filename)
    return f"{name}_{uuid.uuid4().hex[:8]}{ext}"


def validate_manuscript_upload(file_obj):
    if not file_obj or not file_obj.filename:
        return "No file uploaded."
    if not allowed_manuscript(file_obj.filename):
        return "Invalid file type. Only PDF, DOC, and DOCX are allowed."

    max_bytes = current_app.config.get(
        "UPLOAD_MANUSCRIPT_MAX_BYTES", DEFAULT_MANUSCRIPT_MAX_BYTES
    )
    stream = file_obj.stream
    position = stream.tell()
    try:
        stream.seek(0, os.SEEK_END)
        file_size = stream.tell()
        stream.seek(0)
        signature = stream.read(8)
    finally:
        stream.seek(position)

    if file_size <= 0 or file_size > max_bytes:
        return f"Manuscript files must be smaller than {max_bytes // (1024 * 1024)} MB."

    extension = file_obj.filename.rsplit(".", 1)[1].lower()
    if extension == "pdf" and not signature.startswith(PDF_SIGNATURE):
        return "The uploaded PDF file is not valid."
    if extension in {"doc", "docx"} and not (
        signature.startswith(OLE_SIGNATURE) or signature.startswith(b"PK")
    ):
        return "The uploaded document file is not valid."
    return None


def save_manuscript_upload(file_obj):
    if not file_obj or not file_obj.filename:
        return None, None
    validation_error = validate_manuscript_upload(file_obj)
    if validation_error:
        return None, validation_error

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
        os.path.join(current_app.instance_path, "uploads", filename),
    ]
    legacy_folder = current_app.config.get('UPLOAD_FOLDER')
    if legacy_folder:
        candidates.append(os.path.join(os.path.abspath(legacy_folder), filename))

    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def manuscript_mimetype(path):
    return mimetypes.guess_type(path)[0] or "application/octet-stream"
