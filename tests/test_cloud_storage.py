from io import BytesIO
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit

from flask import Flask, g, session
from PIL import Image
import pytest
from werkzeug.datastructures import FileStorage

from app.utils import cloud_storage, uploads, cor_upload, avatars


@pytest.fixture
def storage_app(tmp_path, monkeypatch):
    app = Flask(__name__, instance_path=str(tmp_path / 'instance'))
    app.config.update(
        UPLOAD_STORAGE_BACKEND='supabase', SUPABASE_URL='https://test-project.supabase.co',
        SUPABASE_SECRET_KEY='sb_secret_test', SUPABASE_MANUSCRIPT_BUCKET='capre-manuscripts',
        SUPABASE_REGISTRATION_BUCKET='capre-registration', SUPABASE_AVATAR_BUCKET='capre-avatars',
    )
    objects = {}
    calls = []

    def request(req, timeout):
        assert timeout == 30
        calls.append(req)
        path = urlsplit(req.full_url).path.split('/storage/v1/object/', 1)[1]
        if req.method == 'POST':
            assert path not in objects
            objects[path] = req.data
            return BytesIO(b'{}')
        if req.method == 'DELETE':
            for filename in json.loads(req.data)['prefixes']:
                objects.pop(path + '/' + filename, None)
            return BytesIO(b'[]')
        if path not in objects:
            raise HTTPError(req.full_url, 404, 'Missing', {}, BytesIO(b'{}'))
        return BytesIO(objects[path])

    monkeypatch.setattr(cloud_storage, 'urlopen', request)
    with app.app_context():
        yield app, objects, calls


def test_manuscript_upload_download_cache_and_cleanup(storage_app):
    _, objects, calls = storage_app
    filename, error = uploads.save_manuscript_upload(FileStorage(stream=BytesIO(b'%PDF-test'), filename='Study.pdf'))
    assert error is None
    assert objects['capre-manuscripts/' + filename] == b'%PDF-test'
    path = uploads.resolve_manuscript_file(uploads.stored_manuscript_path(filename))
    assert Path(path).read_bytes() == b'%PDF-test'
    assert uploads.resolve_manuscript_file('uploads/' + filename) == path
    assert [call.method for call in calls] == ['POST', 'GET']
    uploads.remove_manuscript_file('uploads/' + filename)
    assert not objects
    assert not Path(path).exists()
    assert uploads.resolve_manuscript_file('uploads/' + filename) is None


def test_cor_document_uses_private_registration_bucket(storage_app):
    _, objects, _ = storage_app
    filename = cor_upload.save_cor_document({'filename': 'COR.pdf', 'content': b'%PDF-test'})
    assert objects['capre-registration/' + filename] == b'%PDF-test'
    path = cor_upload.resolve_cor_file(filename)
    assert path.read_bytes() == b'%PDF-test'
    cor_upload.remove_cor_file(filename)
    assert not objects and not path.exists()


def test_avatar_is_sanitized_before_cloud_upload(storage_app):
    _, objects, _ = storage_app
    picture = BytesIO()
    Image.new('RGB', (20, 30), 'red').save(picture, format='JPEG')
    picture.seek(0)
    filename = avatars.save_avatar(FileStorage(stream=picture, filename='photo.jpg'))
    with Image.open(BytesIO(objects['capre-avatars/' + filename])) as result:
        assert result.format == 'PNG' and result.size == (256, 256)
    path = avatars.avatar_path(filename)
    assert path.is_file()
    avatars.remove_avatar(filename)
    assert not objects and not path.exists()


@pytest.mark.parametrize('key, bearer', [('sb_secret_test', False), ('legacy-service-role-jwt', True)])
def test_keys_stay_in_server_request_headers(storage_app, key, bearer):
    app, _, calls = storage_app
    app.config['SUPABASE_SECRET_KEY'] = key
    cloud_storage.upload_cloud_file('avatar', 'test.png', b'png', 'image/png', 1024)
    request = calls[0]
    assert request.get_header('Apikey') == key
    assert ('Authorization' in request.headers) is bearer
    assert key not in request.full_url
    assert request.get_header('X-upsert') == 'false'


def test_missing_storage_object_returns_none_for_http_400(storage_app, monkeypatch):
    def missing(request, **kwargs):
        raise HTTPError(request.full_url, 400, 'Missing', {}, BytesIO(b'{"statusCode":"404"}'))

    monkeypatch.setattr(cloud_storage, 'urlopen', missing)
    assert cor_upload.resolve_cor_file('missing.pdf') is None


def test_failed_upload_does_not_report_success(storage_app, monkeypatch):
    def fail(request, **kwargs):
        raise HTTPError(request.full_url, 403, 'Forbidden', {}, BytesIO(b'{}'))

    monkeypatch.setattr(cloud_storage, 'urlopen', fail)
    filename, error = uploads.save_manuscript_upload(FileStorage(stream=BytesIO(b'pdf'), filename='test.pdf'))
    assert filename is None and error
    assert not storage_app[1]


def test_oversized_cloud_download_does_not_create_cache(storage_app):
    app, objects, _ = storage_app
    objects['capre-avatars/test.png'] = b'12345'
    with pytest.raises(OSError, match='allowed size'):
        cloud_storage.cloud_file_path('avatar', 'test.png', 4)
    assert not (Path(app.instance_path) / 'storage-cache').exists()


@pytest.mark.parametrize('filename', ['../file.pdf', '..\\file.pdf', '/file.pdf'])
def test_cor_path_traversal_never_calls_storage(storage_app, filename):
    assert cor_upload.resolve_cor_file(filename) is None
    assert not storage_app[2]


def test_publishable_key_rejected_before_network_request(storage_app):
    app, _, calls = storage_app
    app.config['SUPABASE_SECRET_KEY'] = 'sb_publishable_test'
    with pytest.raises(ValueError, match='server-side secret'):
        cloud_storage.validate_cloud_storage()
    assert not calls


def test_cloud_cache_does_not_use_files_from_other_project(storage_app):
    app, objects, calls = storage_app
    objects['capre-avatars/test.png'] = b'first'
    first = cloud_storage.cloud_file_path('avatar', 'test.png', 10)
    app.config['SUPABASE_URL'] = 'https://other-project.supabase.co'
    objects['capre-avatars/test.png'] = b'second'
    second = cloud_storage.cloud_file_path('avatar', 'test.png', 10)
    assert first != second
    assert second.read_bytes() == b'second'
    assert len(calls) == 2


@pytest.mark.parametrize('role, expected', [(None, 401), ('Student', 403), ('Admin', 200)])
def test_private_download_checks_role_before_storage(storage_app, monkeypatch, role, expected):
    from app.routes.pages import pages
    from app.routes.pages import manuscripts

    app, objects, calls = storage_app
    app.config['SECRET_KEY'] = 'test'
    app.register_blueprint(pages)
    objects['capre-manuscripts/private.pdf'] = b'private PDF content'
    monkeypatch.setattr(manuscripts, 'get_capstone_details',
                        lambda _: {'capstone_file': 'uploads/private.pdf'})

    @app.before_request
    def load_user():
        g.user = {'user_id': 1, 'role_name': role} if session.get('user_id') else None

    client = app.test_client()
    if role:
        with client.session_transaction() as state:
            state['user_id'] = 1
    response = client.get('/manuscript/file/1')
    assert response.status_code == expected
    if role == 'Admin':
        assert response.data == b'private PDF content'
        assert len(calls) == 1
        assert b'sb_secret_' not in response.data
    else:
        assert not calls
