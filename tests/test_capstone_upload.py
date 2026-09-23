from io import BytesIO
from pathlib import Path

from flask import Flask, g
import pytest

from app.routes.admin import admin
from app.routes.admin import repository


@pytest.fixture
def upload_client(tmp_path):
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY='test', WTF_CSRF_ENABLED=False,
                      UPLOAD_MANUSCRIPT_FOLDER=str(tmp_path / 'manuscripts'))
    app.register_blueprint(admin)

    @app.before_request
    def load_user():
        g.user = {'user_id': 1, 'role_id': 3}

    client = app.test_client()
    with client.session_transaction() as session:
        session['user_id'] = 1
    return client, tmp_path / 'manuscripts'


@pytest.mark.parametrize('fails', [False, True])
def test_extraction_cleans_temporary_upload(upload_client, monkeypatch, fails):
    client, permanent = upload_client
    paths = []

    def extract(path):
        path = Path(path)
        paths.append(path)
        assert path.read_bytes() == b'pdf contents'
        assert not path.is_relative_to(permanent)
        if fails:
            raise RuntimeError('Extraction failed')
        return {'title': 'Test manuscript'}

    monkeypatch.setattr(repository, 'extract_capstone_data', extract)
    data = {'capstone_file': (BytesIO(b'pdf contents'), 'test.pdf')}
    if fails:
        with pytest.raises(RuntimeError, match='Extraction failed'):
            client.post('/repository/extract', data=data)
    else:
        response = client.post('/repository/extract', data=data)
        assert response.json == {'success': True, 'data': {'title': 'Test manuscript'}}
    assert len(paths) == 1
    assert not paths[0].parent.exists()
    assert not permanent.exists()


@pytest.mark.parametrize('extension', ['pdf', 'doc', 'docx'])
def test_extract_then_submit_saves_one_copy(upload_client, monkeypatch, extension):
    client, permanent = upload_client
    monkeypatch.setattr(repository, 'extract_capstone_data', lambda path: {})
    monkeypatch.setattr(repository, 'get_programs', lambda: [(1, 'Program')])
    monkeypatch.setattr(repository, 'get_specializations', lambda: [(1, 'Specialization')])
    monkeypatch.setattr(repository, 'insert_keywords', lambda value: (True, 1))
    stored = []

    def create(*args, **kwargs):
        stored.append(args[5])
        return True, 1

    monkeypatch.setattr(repository, 'create_capstone_project', create)
    monkeypatch.setattr(repository, 'set_capstone_people', lambda *args, **kwargs: (True, None))
    filename = f'test.{extension}'
    response = client.post('/repository/extract', data={
        'capstone_file': (BytesIO(b'manuscript contents'), filename),
    })
    assert response.status_code == 200
    assert not permanent.exists()
    response = client.post('/repository/create', data={
        'capstone_file': (BytesIO(b'manuscript contents'), filename),
        'capstone_title': 'Test manuscript', 'capstone_year': '2026',
        'program_id': '1', 'specialization_id': '1', 'semester': '1st',
        'capstone_keywords': 'test', 'adviser-first_name': 'Test',
        'adviser-last_name': 'Adviser',
    })
    assert response.status_code == 302
    files = list(permanent.iterdir())
    assert len(files) == 1
    assert files[0].read_bytes() == b'manuscript contents'
    assert stored == [f'uploads/{files[0].name}']
