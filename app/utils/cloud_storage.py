"""Server-only access to private Supabase files, cached for PDF processing."""
import json
import mimetypes
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from flask import current_app
from werkzeug.utils import secure_filename


def cloud_storage_enabled():
    backend = current_app.config.get('UPLOAD_STORAGE_BACKEND', 'local')
    if backend not in ('local', 'supabase'):
        raise ValueError('UPLOAD_STORAGE_BACKEND must be local or supabase.')
    return backend == 'supabase'


def _settings(kind):
    base_url = current_app.config.get('SUPABASE_URL', '').rstrip('/')
    key = current_app.config.get('SUPABASE_SECRET_KEY', '')
    endpoint = urlsplit(base_url)
    if (endpoint.scheme != 'https' or not endpoint.hostname
            or not endpoint.hostname.endswith('.supabase.co')
            or endpoint.path or endpoint.query or endpoint.fragment or endpoint.username):
        raise ValueError('Set SUPABASE_URL to your HTTPS Supabase project URL.')
    if not key or key.startswith('sb_publishable_'):
        raise ValueError('Set SUPABASE_SECRET_KEY to a server-side secret key.')
    bucket = current_app.config.get('SUPABASE_' + kind.upper() + '_BUCKET', '')
    if not bucket or secure_filename(bucket) != bucket:
        raise ValueError('Configure the private Supabase storage bucket.')
    return base_url, key, bucket


def validate_cloud_storage():
    if cloud_storage_enabled():
        for kind in ('manuscript', 'registration', 'avatar'):
            _settings(kind)


def _request(kind, filename, method, data=None, content_type=None, max_bytes=25 * 1024 * 1024):
    if not filename or secure_filename(filename) != filename:
        raise ValueError('Invalid storage filename.')
    base_url, key, bucket = _settings(kind)
    headers = {'apikey': key}
    # Opaque sb_secret keys belong only in apikey, not in the JWT Bearer header.
    if not key.startswith('sb_secret_'):
        headers['Authorization'] = 'Bearer ' + key
    endpoint = f'{base_url}/storage/v1/object/{quote(bucket, safe="")}'
    if method == 'DELETE':
        data = json.dumps({'prefixes': [filename]}).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    else:
        endpoint += '/' + quote(filename, safe='')
        if method == 'POST':
            headers['Content-Type'] = content_type or mimetypes.guess_type(filename)[0] or 'application/octet-stream'
            headers['x-upsert'] = 'false'
    request = Request(endpoint, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            content = response.read(max_bytes + 1)
            if len(content) > max_bytes:
                raise OSError('Stored file exceeds the allowed size.')
            return content
    except HTTPError as exc:
        status = exc.code
        try:
            payload = json.loads(exc.read(4096))
            object_missing = str(payload.get('statusCode')) == '404'
        except (ValueError, AttributeError):
            object_missing = False
        exc.close()
        if (status == 404 or (status == 400 and object_missing)) and method in ('GET', 'DELETE'):
            return None
        raise OSError(f'Supabase Storage request failed (HTTP {status}).') from None
    except (URLError, TimeoutError):
        raise OSError('Supabase Storage is unavailable. Try again.') from None


def upload_cloud_file(kind, filename, content, content_type, max_bytes):
    if not content or len(content) > max_bytes:
        raise ValueError('Upload is empty or exceeds the allowed size.')
    _request(kind, filename, 'POST', data=content, content_type=content_type)


def cloud_file_path(kind, filename, max_bytes):
    if not filename or secure_filename(filename) != filename:
        return None
    base_url, _, bucket = _settings(kind)
    folder = Path(current_app.instance_path) / 'storage-cache' / urlsplit(base_url).hostname / bucket
    path = folder / filename
    if path.is_file():
        return path
    content = _request(kind, filename, 'GET', max_bytes=max_bytes)
    if content is None:
        return None
    folder.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(dir=folder, delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path


def remove_cloud_file(kind, filename):
    base_url, _, bucket = _settings(kind)
    _request(kind, filename, 'DELETE')
    path = Path(current_app.instance_path) / 'storage-cache' / urlsplit(base_url).hostname / bucket / filename
    path.unlink(missing_ok=True)
