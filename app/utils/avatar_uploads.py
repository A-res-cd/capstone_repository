"""Validated storage helpers for private user avatar images."""

import os
from pathlib import Path
from uuid import uuid4

from flask import current_app
from PIL import Image, UnidentifiedImageError
from werkzeug.utils import secure_filename
from app.utils.malware_scan import scan_uploaded_file


ALLOWED_AVATAR_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
ALLOWED_AVATAR_FORMATS = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}
DEFAULT_AVATAR_MAX_BYTES = 5 * 1024 * 1024


def avatar_upload_folder():
    configured = current_app.config.get("UPLOAD_AVATAR_FOLDER")
    if configured:
        return Path(configured).resolve()

    return Path(current_app.instance_path, "uploads", "avatars").resolve()


def _avatar_size(upload):
    stream = upload.stream
    position = stream.tell()
    try:
        stream.seek(0, os.SEEK_END)
        return stream.tell()
    finally:
        stream.seek(position)


def validate_avatar_upload(upload):
    if not upload or not upload.filename:
        raise ValueError("Choose a profile image to upload.")

    original_name = secure_filename(upload.filename)
    extension = Path(original_name).suffix.lower().lstrip(".")
    if extension not in ALLOWED_AVATAR_EXTENSIONS:
        raise ValueError("Profile image must be JPG, PNG, or WEBP.")

    file_size = _avatar_size(upload)
    max_bytes = current_app.config.get("UPLOAD_AVATAR_MAX_BYTES", DEFAULT_AVATAR_MAX_BYTES)
    if file_size <= 0 or file_size > max_bytes:
        raise ValueError("Profile image must be smaller than 5 MB.")

    stream = upload.stream
    position = stream.tell()
    try:
        stream.seek(0)
        with Image.open(stream) as image:
            image.verify()

        stream.seek(0)
        with Image.open(stream) as image:
            image_format = image.format
            width, height = image.size
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("Upload a readable JPG, PNG, or WEBP image.") from exc
    finally:
        stream.seek(position)

    mime_type = ALLOWED_AVATAR_FORMATS.get(image_format)
    if not mime_type:
        raise ValueError("Profile image must be JPG, PNG, or WEBP.")

    return {
        "original_name": original_name[:255] or "profile-image",
        "mime_type": mime_type,
        "file_size": file_size,
        "width": width,
        "height": height,
        "extension": {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}[image_format],
    }


def save_avatar_upload(upload):
    metadata = validate_avatar_upload(upload)
    folder = avatar_upload_folder()
    folder.mkdir(parents=True, exist_ok=True)

    storage_key = f"avatar_{uuid4().hex}.{metadata['extension']}"
    path = folder / storage_key
    upload.stream.seek(0)
    try:
        with path.open("xb") as output:
            upload.save(output)
        scan_uploaded_file(path)
    except Exception:
        path.unlink(missing_ok=True)
        raise

    metadata["storage_key"] = storage_key
    return metadata


def resolve_avatar_file(storage_key):
    if not storage_key or storage_key != os.path.basename(str(storage_key)):
        return None

    folder = avatar_upload_folder()
    path = (folder / storage_key).resolve()
    if not path.is_relative_to(folder) or not path.is_file():
        return None
    return path


def remove_avatar_file(storage_key):
    path = resolve_avatar_file(storage_key)
    if path:
        path.unlink(missing_ok=True)
