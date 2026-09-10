"""Validate a small, readable COR PDF without trusting its filename or MIME header."""
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from flask import current_app
import pdfplumber
from werkzeug.utils import secure_filename

MAX_COR_BYTES = 5 * 1024 * 1024


def read_cor_upload(upload):
    if not upload or not upload.filename or not upload.filename.lower().endswith('.pdf'):
        raise ValueError('Upload your Certificate of Registration (COR) as a PDF.')
    content = upload.stream.read(MAX_COR_BYTES + 1)
    if len(content) > MAX_COR_BYTES:
        raise ValueError('COR must be 5 MB or smaller.')
    if not content.startswith(b'%PDF-'):
        raise ValueError('The uploaded file is not a valid PDF.')
    try:
        with pdfplumber.open(BytesIO(content)) as pdf:
            if not 1 <= len(pdf.pages) <= 20:
                raise ValueError('COR must contain between 1 and 20 pages.')
            if not all(page.width > 0 and page.height > 0 for page in pdf.pages):
                raise ValueError('Invalid page size.')
    except Exception as exc:
        raise ValueError('Upload a readable, unencrypted PDF containing 1–20 pages.') from exc
    return {'filename': (secure_filename(upload.filename) or 'cor.pdf')[-200:], 'content': content}


def registration_upload_folder():
    configured = current_app.config.get('UPLOAD_REGISTRATION_FOLDER')
    return Path(configured).resolve() if configured else Path(current_app.instance_path, 'registration').resolve()


def resolve_cor_file(filename):
    if not filename or filename != secure_filename(filename) or not filename.lower().endswith('.pdf'):
        return None
    folder = registration_upload_folder()
    path = (folder / filename).resolve()
    if not path.is_relative_to(folder) or not path.is_file():
        return None
    return path


def save_cor_upload(upload):
    document = read_cor_upload(upload)
    folder = registration_upload_folder()
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{Path(document['filename']).stem[:150]}_{uuid4().hex}.pdf"
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
    path = resolve_cor_file(filename)
    if path:
        path.unlink()
