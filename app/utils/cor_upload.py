"""Validate private student COR PDFs and faculty ID images."""
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from flask import current_app
from app.utils.document_processing import process_document
import os
import shutil
import pytesseract
from werkzeug.utils import secure_filename

MAX_COR_BYTES = 5 * 1024 * 1024


def configure_tesseract():
    configured_command = os.getenv("TESSERACT_CMD")
    if configured_command:
        pytesseract.pytesseract.tesseract_cmd = configured_command
    elif not shutil.which("tesseract"):
        for command in (r"C:\Program Files\Tesseract-OCR\tesseract.exe", r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"):
            if Path(command).is_file():
                pytesseract.pytesseract.tesseract_cmd = command
                break


def read_cor_upload(upload, extract=False):
    if not upload or not upload.filename:
        raise ValueError('Upload your verification document.')
    extension = Path(upload.filename).suffix.lower()
    if extension not in ('.pdf', '.jpg', '.jpeg', '.png'):
        raise ValueError('Upload a PDF or JPG/PNG image.')
    position = upload.stream.tell()
    try:
        content = upload.stream.read(MAX_COR_BYTES + 1)
    finally:
        upload.stream.seek(position)
    if len(content) > MAX_COR_BYTES:
        raise ValueError('COR must be 5 MB or smaller.')
    if extension == '.pdf' and not content.startswith(b'%PDF-'):
        raise ValueError('The uploaded file is not a valid PDF.')
    fields = process_document(content, extension, 'extract' if extract else 'validate')
    fallback = 'faculty-id' + extension if extension != '.pdf' else 'cor.pdf'
    return {'filename': (secure_filename(upload.filename) or fallback)[-200:], 'content': content, 'fields': fields}


def registration_upload_folder():
    configured = current_app.config.get('UPLOAD_REGISTRATION_FOLDER')
    if configured:
        folder = Path(configured)
        if not folder.is_absolute():
            folder = Path(current_app.root_path).parent / folder
        return folder.resolve()
    return Path(current_app.instance_path, 'uploads', 'registration').resolve()


def resolve_cor_file(filename):
    if not filename or filename != secure_filename(filename) or Path(filename).suffix.lower() not in ('.pdf', '.jpg', '.jpeg', '.png'):
        return None
    from app.utils.cloud_storage import cloud_storage_enabled, cloud_file_path
    if cloud_storage_enabled():
        return cloud_file_path('registration', filename, MAX_COR_BYTES)
    folder = registration_upload_folder()
    path = (folder / filename).resolve()
    if not path.is_relative_to(folder) or not path.is_file():
        return None
    return path


def save_cor_upload(upload):
    document = read_cor_upload(upload)
    return save_cor_document(document)


def save_cor_document(document):
    """Persist a document already validated by read_cor_upload."""
    from app.utils.cloud_storage import cloud_storage_enabled, upload_cloud_file
    if cloud_storage_enabled():
        extension = Path(document['filename']).suffix.lower()
        filename = f"{Path(document['filename']).stem[:150]}_{uuid4().hex}{extension}"
        content_type = 'application/pdf' if extension == '.pdf' else f"image/{'jpeg' if extension in ('.jpg', '.jpeg') else 'png'}"
        upload_cloud_file('registration', filename, document['content'], content_type, MAX_COR_BYTES)
        return filename
    folder = registration_upload_folder()
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Use an app-owned workspace folder when deployment's configured path
        # is unavailable or read-only.
        folder = (Path(current_app.root_path).parent / 'instance' / 'uploads' / 'registration').resolve()
        folder.mkdir(parents=True, exist_ok=True)
    extension = Path(document['filename']).suffix.lower()
    filename = f"{Path(document['filename']).stem[:150]}_{uuid4().hex}{extension}"
    path = folder / filename
    created = False
    try:
        with path.open('xb') as output:
            created = True
            output.write(document['content'])
    except OSError:
        if created:
            path.unlink(missing_ok=True)
        raise
    return filename


def remove_cor_file(filename):
    """Remove only the file created for an unsuccessful signup."""
    from app.utils.cloud_storage import cloud_storage_enabled, remove_cloud_file
    if cloud_storage_enabled():
        if filename:
            remove_cloud_file('registration', filename)
        return
    path = resolve_cor_file(filename)
    if path:
        path.unlink()
