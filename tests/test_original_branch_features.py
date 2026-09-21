"""Original-branch audit, title-only comparison, and private COR workflow."""
from contextlib import closing
from datetime import date
from importlib import import_module
from io import BytesIO
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
from urllib.parse import urlsplit

from flask import Flask, g, session
from flask_wtf.csrf import CSRFProtect
from playwright.sync_api import expect
import psycopg2
import pytest
from werkzeug.datastructures import FileStorage

from app.db import auth as auth_db, audit_reader, verification_documents
from app.db.connection import _PooledConnection
from app.services.recommender import TopicRecommender
from app.utils.cor_upload import read_cor_upload, resolve_cor_file, MAX_COR_BYTES
from app.utils.uploads import manuscript_upload_folder, resolve_manuscript_file
from app.utils.audit_summary import summarize_audit

ROOT = Path(__file__).resolve().parents[1]
admin = import_module('app.routes.admin')
auth = import_module('app.routes.authentication')
pages = import_module('app.routes.pages')


def pdf_bytes():
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 400] /Resources << >> /Contents 4 0 R >>',
               b'<< /Length 0 >>\nstream\n\nendstream']
    data, offsets = b'%PDF-1.4\n', [0]
    for number, value in enumerate(objects, 1):
        offsets.append(len(data))
        data += f'{number} 0 obj\n'.encode() + value + b'\nendobj\n'
    xref = len(data)
    data += b'xref\n0 5\n0000000000 65535 f \n'
    data += b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
    return data + f'trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()


def test_cor_validation():
    valid = read_cor_upload(FileStorage(stream=BytesIO(pdf_bytes()), filename='../../my COR.pdf'))
    assert valid['filename'] == 'my_COR.pdf' and valid['content'] == pdf_bytes()
    for name, content in [('bad.html', pdf_bytes()), ('fake.pdf', b'<script>alert(1)</script>'),
                          ('empty.pdf', b''), ('large.pdf', b'%PDF-' + b'x' * MAX_COR_BYTES),
                          ('broken.pdf', b'%PDF-1.4\nnot a document')]:
        with pytest.raises(ValueError):
            read_cor_upload(FileStorage(stream=BytesIO(content), filename=name))


def test_title_only_similarity():
    corpus = [dict(capstone_id=1, capstone_title='Attendance Tracking System', capstone_keywords='gardening'),
              dict(capstone_id=2, capstone_title='Garden Irrigation', capstone_keywords='Attendance Tracking System')]
    matches = TopicRecommender(corpus).find_similar('Attendance Tracking System')
    assert matches[0]['capstone_id'] == 1 and matches[0]['similarity'] == 1
    assert all(match['capstone_id'] != 2 for match in matches)
    assert TopicRecommender([]).find_similar('Anything') == []


@pytest.fixture(scope='module')
def isolated_database(tmp_path_factory):
    initdb, pg_ctl = shutil.which('initdb'), shutil.which('pg_ctl')
    if not initdb or not pg_ctl:
        pytest.skip('Isolated PostgreSQL requires initdb and pg_ctl')
    cluster = tmp_path_factory.mktemp('original-features-postgres')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]

    def run(*args):
        with tempfile.TemporaryFile() as output:
            result = subprocess.run(args, stdout=output, stderr=subprocess.STDOUT, timeout=45,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            output.seek(0)
            assert result.returncode == 0, output.read().decode(errors='replace')

    run(initdb, '-D', str(cluster), '-A', 'trust', '-U', 'postgres', '--encoding=UTF8', '--no-locale')
    run(pg_ctl, '-D', str(cluster), '-l', str(cluster / 'server.log'), '-o', f'-h 127.0.0.1 -p {port} -F', '-w', 'start')
    try:
        yield dict(host='127.0.0.1', port=port, user='postgres', dbname='postgres')
    finally:
        run(pg_ctl, '-D', str(cluster), '-m', 'fast', '-w', 'stop')


@pytest.fixture
def feature_db(isolated_database, monkeypatch):
    import uuid
    schema = 'features_' + uuid.uuid4().hex
    with closing(psycopg2.connect(**isolated_database)) as conn, conn.cursor() as cursor:
        cursor.execute(f'CREATE SCHEMA "{schema}"')
        cursor.execute(f'SET search_path TO "{schema}"')
        cursor.execute((ROOT / 'database/capreDB.sql').read_text(encoding='utf-8'))
        cursor.execute("INSERT INTO role (role_id, role_name) VALUES (1, 'Student'), (2, 'Faculty'), (3, 'Admin'), (4, 'Capstone Professor')")
        conn.commit()

    class ClosingPool:
        def putconn(self, conn, **kwargs):
            conn.close()

    def connect():
        conn = psycopg2.connect(**isolated_database, options=f'-c search_path={schema}')
        return _PooledConnection(ClosingPool(), conn)

    for module in (auth_db, audit_reader, verification_documents):
        monkeypatch.setattr(module, 'db_connect', connect)
    return connect


@pytest.fixture
def feature_app(monkeypatch, tmp_path):
    app = Flask(__name__, template_folder=str(ROOT / 'app/templates'), static_folder=str(ROOT / 'app/static'))
    app.config.update(TESTING=True, SECRET_KEY='features-test', WTF_CSRF_ENABLED=False)
    app.config['UPLOAD_REGISTRATION_FOLDER'] = str(tmp_path / 'registration')
    app.config['UPLOAD_MANUSCRIPT_FOLDER'] = str(tmp_path / 'manuscripts')
    CSRFProtect(app)
    app.register_blueprint(admin.admin)
    app.register_blueprint(auth.auth)
    app.register_blueprint(pages.pages)
    app.add_url_rule('/', endpoint='main.home', view_func=lambda: 'Home')

    @app.before_request
    def user():
        g.user = {'role_id': session.get('role_id')}

    @app.context_processor
    def context():
        return dict(hide_header=True, hide_nav=True)

    monkeypatch.setattr(pages.topics, 'get_capstones_corpus', lambda: [dict(capstone_id=1, capstone_title='Attendance Tracking System')])
    return app


def login(client, role=3):
    with client.session_transaction() as state:
        state.update(user_id=1, role_id=role)


@pytest.mark.parametrize('path', [
    '/user-info/promotion',
    '/user-info/promotion/cancel/1',
    '/manage_users/promotion/1',
])
def test_promotion_endpoints_removed(feature_app, path):
    client = feature_app.test_client()
    login(client)
    assert client.post(path).status_code == 404


@pytest.mark.parametrize('role', [1, 3])
def test_direct_role_change_remains_admin_only(feature_app, monkeypatch, role):
    calls = []

    def update_role(user_id, new_role_id, acting_admin_id):
        calls.append((user_id, new_role_id, acting_admin_id))
        return True, None

    monkeypatch.setattr(admin.users, 'update_user_role', update_role)
    client = feature_app.test_client()
    login(client, role=role)
    response = client.post('/manage_users/update_role/2', data={'role_id': '4'})
    assert response.status_code == 302
    assert calls == ([(2, '4', 1)] if role == 3 else [])
    if role == 3:
        assert response.location == '/manage_users'


def signup_data(file=True):
    data = dict(first_name='Maria', middle_name='', last_name='Cruz', email='maria@example.com', username='maria', password='secure-password', accept_terms='y')
    if file:
        data['cor'] = (BytesIO(pdf_bytes()), 'my COR.pdf')
    return data


def test_signup_requires_terms_before_storage_or_account_creation(feature_app, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail('Signup must not store a file or create an account without consent')
    monkeypatch.setattr(auth.registration, 'save_cor_upload', unexpected)
    monkeypatch.setattr(auth.registration, 'create_user', unexpected)
    data = signup_data()
    data.pop('accept_terms')
    response = feature_app.test_client().post('/signup', data=data)
    assert response.status_code == 200
    assert b'You must accept the Terms and Agreements' in response.data


def test_signup_atomic_document_and_admin_access(feature_app, feature_db):
    client = feature_app.test_client()
    assert client.post('/signup', data=signup_data(False)).status_code == 200
    assert client.post('/signup', data=signup_data()).status_code == 302
    # Duplicate signup rolls back the user and cleans up its new file.
    assert client.post('/signup', data=signup_data()).status_code == 200
    with feature_db() as conn, conn.cursor() as cursor:
        cursor.execute('SELECT r.request_id, u.cor_filename FROM request r JOIN "user" u ON u.user_id = r.user_id')
        ids = cursor.fetchall()
        assert len(ids) == 1
        request_id = ids[0][0]
        filename = ids[0][1]
        cursor.execute('SELECT COUNT(*) FROM "user"')
        assert cursor.fetchone()[0] == 1
    folder = Path(feature_app.config['UPLOAD_REGISTRATION_FOLDER'])
    assert [path.name for path in folder.iterdir()] == [filename]
    assert (folder / filename).read_bytes() == pdf_bytes()
    base = f'/manage_users/verify/{request_id}'
    assert client.get(base + '/document').status_code == 302
    for role in (1, 2, 4):
        login(client, role)
        assert client.get(base + '/document').status_code == 302
        assert client.get(base + '/details').status_code == 302
        assert client.get('/audit-logs').status_code == 302
    login(client)
    details = client.get(base + '/details').get_json()
    assert details['username'] == 'maria' and details['filename'] == filename
    assert filename.startswith('my_COR_') and filename.endswith('.pdf')
    assert 'content' not in details
    response = client.get(details['document_url'])
    assert response.data == pdf_bytes()
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.headers['Content-Disposition'].startswith('attachment;')
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert client.get('/manage_users/verify/999999/document').status_code == 404
    assert client.get('/audit-logs').status_code == 200
    with feature_db() as conn, conn.cursor() as cursor:
        cursor.execute('DELETE FROM request WHERE request_id = %s', (request_id,))
        cursor.execute('SELECT cor_filename FROM "user"')
        assert cursor.fetchone()[0] == filename  # The file belongs to the user, not one request.
    assert (folder / filename).is_file()


def test_legacy_request_and_migration(feature_db):
    assert auth_db.create_user('Old', '', 'Student', None, 'old@example.com', 'old_user', 'password')[0]
    with feature_db() as conn, conn.cursor() as cursor:
        cursor.execute((ROOT / 'migrations/20260910_verification_documents.sql').read_text())
        cursor.execute('SELECT request_id FROM request')
        request_id = cursor.fetchone()[0]
    details = verification_documents.get_verification_details(request_id)
    assert details['filename'] is None
    assert verification_documents.get_verification_document(request_id) is None


def test_audit_filters_and_safe_details(feature_db, feature_app):
    with feature_db() as conn, conn.cursor() as cursor:
        cursor.execute('''INSERT INTO audit (action_type, affected_record_id, new_values, action_timestamp)
            SELECT 'login', n, 'SECRET_TOKEN', '2026-09-10'::timestamp FROM generate_series(1, 27) n''')
        cursor.execute("INSERT INTO audit (action_type, affected_record_id, action_timestamp) VALUES ('unknown', 99, '2026-09-11')")
    result = audit_reader.get_audit_logs({'start': date(2026, 9, 10), 'end': date(2026, 9, 11)}, 99)
    assert result['total'] == 27 and result['page'] == 2 and len(result['events']) == 2
    assert result['counts']['account'] == 27
    assert 'SECRET_TOKEN' not in str(result)
    assert result['events'][0]['actor'] == 'Unknown / deleted user'
    assert audit_reader.get_audit_logs({'category': 'other'})['total'] == 1
    assert audit_reader.get_audit_logs({'q': "%' OR 1=1 --"})['total'] == 0
    client = feature_app.test_client()
    login(client)
    for query in ('page=0', 'category=invalid', 'action=invalid', 'start=invalid', 'start=2026-09-12&end=2026-09-10'):
        assert client.get('/audit-logs?' + query).status_code == 400


def test_title_api_validation(feature_app):
    client = feature_app.test_client()
    login(client, 1)
    for data in ([], {'title': 5}, {'title': 'a' * 256}):
        assert client.post('/api/topic-similarity', json=data).status_code == 400
    response = client.post('/api/topic-similarity', json={'title': 'Attendance Tracking System', 'keywords': 'ignored'})
    assert response.json['matches'][0]['similarity'] == 1


def test_signup_csrf(feature_app):
    feature_app.config['WTF_CSRF_ENABLED'] = True
    assert feature_app.test_client().post('/signup', data=signup_data()).status_code == 400


@pytest.mark.parametrize('decision,fail_mail', [('approved', False), ('rejected', False), ('approved', True)])
def test_verification_email_after_saved_decision(feature_app, feature_db, monkeypatch, decision, fail_mail):
    from types import SimpleNamespace
    from flask_mail import Mail
    feature_app.config['MAIL_DEFAULT_SENDER'] = 'noreply@example.com'
    Mail(feature_app)
    assert auth_db.create_user('Maria', '', 'Cruz', None, 'maria@example.com', 'maria', 'password')[0]
    with feature_db() as conn, conn.cursor() as cursor:
        cursor.execute('SELECT request_id FROM request')
        request_id = cursor.fetchone()[0]
    sent = []

    def send(message):
        if fail_mail:
            raise OSError('simulated mail failure')
        sent.append(message)
    monkeypatch.setattr(admin.users, 'mail', SimpleNamespace(send=send))
    client = feature_app.test_client()
    login(client)
    endpoint = f'/manage_users/verify/{request_id}'
    assert client.post(endpoint, data={'decision': decision, 'status_reason': 'Please check your COR.'}).status_code == 302
    with feature_db() as conn, conn.cursor() as cursor:
        cursor.execute('SELECT request_status FROM request WHERE request_id = %s', (request_id,))
        assert cursor.fetchone()[0] == decision
    if fail_mail:
        with client.session_transaction() as state:
            assert any('Email notification could not be sent' in message for _, message in state['_flashes'])
    else:
        assert sent[0].recipients == ['maria@example.com']
        assert sent[0].html and sent[0].body
        assert ('Your account is ready' if decision == 'approved' else 'Please check your COR.') in sent[0].html
    # A repeated review must not change status or send another email.
    client.post(endpoint, data={'decision': 'rejected' if decision == 'approved' else 'approved'})
    assert len(sent) == (0 if fail_mail else 1)
    with feature_db() as conn, conn.cursor() as cursor:
        cursor.execute('SELECT request_status FROM request WHERE request_id = %s', (request_id,))
        assert cursor.fetchone()[0] == decision


def test_registration_path_guards_and_missing_files(feature_app, monkeypatch):
    folder = Path(feature_app.config['UPLOAD_REGISTRATION_FOLDER'])
    folder.mkdir()
    (folder / 'COR.pdf').write_bytes(pdf_bytes())
    with feature_app.app_context():
        assert resolve_cor_file('COR.pdf') == folder / 'COR.pdf'
        for filename in ('../COR.pdf', '..\\COR.pdf', str(folder / 'COR.pdf'), 'missing.pdf', 'COR.html'):
            assert resolve_cor_file(filename) is None
    client = feature_app.test_client()
    login(client)
    monkeypatch.setattr(admin.users, 'get_verification_document', lambda _: {'filename': '../COR.pdf'})
    assert client.get('/manage_users/verify/1/document').status_code == 404
    monkeypatch.setattr(admin.users, 'get_verification_details', lambda _: {'filename': 'missing.pdf'})
    response = client.get('/manage_users/verify/1/details')
    assert response.json['document_url'] is None and response.json['size_bytes'] is None


def test_failed_database_signup_removes_new_file(feature_app, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('database unavailable')
    monkeypatch.setattr(auth.registration, 'create_user', fail)
    with pytest.raises(RuntimeError):
        feature_app.test_client().post('/signup', data=signup_data())
    assert list(Path(feature_app.config['UPLOAD_REGISTRATION_FOLDER']).iterdir()) == []


def test_upload_storage_error_does_not_create_account(feature_app, monkeypatch):
    def fail(_):
        raise OSError('storage unavailable')
    monkeypatch.setattr(auth.registration, 'save_cor_upload', fail)
    monkeypatch.setattr(auth.registration, 'create_user', lambda *args, **kwargs: pytest.fail('Must not create account without a file'))
    response = feature_app.test_client().post('/signup', data=signup_data())
    assert response.status_code == 200 and b'Could not save your COR' in response.data


def test_separate_manuscript_folder_and_legacy_fallback(feature_app, tmp_path):
    current = Path(feature_app.config['UPLOAD_MANUSCRIPT_FOLDER'])
    current.mkdir()
    (current / 'new.pdf').write_bytes(pdf_bytes())
    legacy = tmp_path / 'legacy'
    legacy.mkdir()
    (legacy / 'old.pdf').write_bytes(pdf_bytes())
    feature_app.config['UPLOAD_FOLDER'] = str(legacy)
    with feature_app.app_context():
        assert manuscript_upload_folder() == str(current)
        assert Path(resolve_manuscript_file('uploads/new.pdf')) == current / 'new.pdf'
        assert Path(resolve_manuscript_file('uploads/old.pdf')) == legacy / 'old.pdf'


@pytest.mark.parametrize('path', ['/signin', '/signup', '/reset_password'])
def test_password_icons_without_internet(feature_app, page, path):
    client = feature_app.test_client()
    if path == '/reset_password':
        with client.session_transaction() as state:
            state.update(otp_verified=True, reset_id=1, reset_user_id=1)

    def handle(route):
        url = urlsplit(route.request.url)
        if url.netloc != 'offline.test':
            route.abort()
            return
        response = client.get(url.path)
        route.fulfill(status=response.status_code, body=response.data, content_type=response.content_type)

    page.route('**/*', handle)
    page.goto('http://offline.test' + path)
    assert page.evaluate("async () => (await document.fonts.load('16px boxicons')).some(font => font.status === 'loaded')")
    for button in page.locator('.input-toggle-btn').all():
        field = page.locator('#' + button.get_attribute('aria-controls'))
        icon = button.locator('i')
        expect(icon).to_be_visible()
        assert icon.evaluate("el => getComputedStyle(el, '::before').content") not in ('none', 'normal', '""')
        expect(button).to_have_accessible_name('Show password')
        field.fill('offline-password')
        button.focus()
        page.keyboard.press('Enter')
        expect(field).to_have_attribute('type', 'text')
        expect(button).to_have_accessible_name('Hide password')
        expect(button).to_have_attribute('aria-pressed', 'true')
        page.keyboard.press('Enter')
        expect(field).to_have_attribute('type', 'password')
        expect(button).to_have_accessible_name('Show password')


@pytest.mark.parametrize('theme,width', [('light', 1280), ('dark', 1280), ('light', 390), ('dark', 390)])
def test_browser_pages(feature_app, page, monkeypatch, theme, width):
    client = feature_app.test_client()
    login(client)
    event = dict(audit_id=1, user_id=None, actor_name='<script>alert(1)</script>', action_type='update_contact', affected_record_id=22,
                 affected_table='contact', new_values='SECRET', old_values=None, action_timestamp=None)
    monkeypatch.setattr(admin.audit, 'get_audit_logs', lambda *args: dict(events=[summarize_audit(event, {})], counts=dict(account=1, capstone=0, workflow=0, other=0), total=1, page=1, pages=1))
    monkeypatch.setattr(admin.users, 'get_users', lambda **kwargs: ([dict(user_id=2, full_name='Maria Cruz', university_no='2026-002', email='maria@example.com', role='Student', role_id=1, account_status='active')], 1))
    monkeypatch.setattr(admin.users, 'get_all_roles', lambda: [(1, 'Student'), (3, 'Admin'), (4, 'Faculty')])
    monkeypatch.setattr(admin.users, 'get_pending_verifications', lambda: [dict(request_id=1, full_name='Maria Cruz', role='Student', email='maria@example.com', university_no=None)])
    monkeypatch.setattr(admin.users, 'get_verification_details', lambda request_id: dict(request_id=1, full_name='<img src=x onerror=alert(1)>', filename='COR.pdf', size_bytes=500))
    folder = Path(feature_app.config['UPLOAD_REGISTRATION_FOLDER'])
    folder.mkdir()
    (folder / 'COR.pdf').write_bytes(pdf_bytes())

    def handle(route):
        url = urlsplit(route.request.url)
        if url.netloc != 'features.test':
            route.abort()
            return
        response = client.open(url.path + ('?' + url.query if url.query else ''), method=route.request.method,
                               data=route.request.post_data, content_type=route.request.headers.get('content-type'))
        route.fulfill(status=response.status_code, body=response.data, content_type=response.content_type)

    page.route('**/*', handle)
    page.add_init_script(f"localStorage.setItem('capre-theme', '{theme}')")
    page.set_viewport_size({'width': width, 'height': 1000})
    page.goto('http://features.test/audit-logs')
    expect(page.locator('.audit-page')).to_be_visible()
    page.get_by_role('combobox', name='Category', exact=True).click()
    page.screenshot(path=str(ROOT / '.pytest_cache' / f'dropdown-{theme}-{width}.png'))
    page.get_by_role('option', name='Accounts', exact=True).click()
    expect(page.locator('#audit-category')).to_have_value('account')
    action = page.get_by_role('combobox', name='Action', exact=True)
    action.fill('Updated contact')
    page.get_by_role('option', name='Updated contact information', exact=True).click()
    expect(page.locator('#audit-action')).to_have_value('update_contact')
    page.get_by_role('button', name='View details', exact=False).click()
    expect(page.get_by_role('dialog')).to_be_visible()
    page.keyboard.press('Escape')
    expect(page.get_by_role('dialog')).not_to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.goto('http://features.test/manage_users')
    edit_button = page.get_by_role('button', name='Edit', exact=True)
    edit_button.click()
    edit_dialog = page.get_by_role('dialog', name='Edit User', exact=True)
    expect(edit_dialog).to_be_visible()
    expect(edit_dialog.locator('#info-name')).to_have_text('Maria Cruz')
    expect(edit_dialog.locator('#form-role')).to_have_attribute('action', '/manage_users/update_role/2')
    expect(page.locator('#panel-list')).to_be_visible()
    edit_dialog.get_by_role('combobox', name='Assign New Role', exact=False).click()
    page.get_by_role('option', name='Faculty', exact=True).click()
    expect(edit_dialog.locator('#role_id')).to_have_value('4')
    assert edit_dialog.evaluate('(el) => el.scrollWidth <= el.clientWidth')
    page.screenshot(path=str(ROOT / '.pytest_cache' / f'edit-user-{theme}-{width}.png'))
    page.keyboard.press('Escape')
    expect(edit_dialog).not_to_be_visible()
    expect(edit_button).to_be_focused()
    page.get_by_role('tab', name='Verify Accounts', exact=False).click()
    page.get_by_role('button', name='Review request', exact=True).click()
    expect(page.get_by_role('dialog')).to_contain_text('<img src=x onerror=alert(1)>')
    expect(page.get_by_role('dialog').locator('img')).to_have_count(0)
    expect(page.get_by_role('link', name='Download COR (PDF)', exact=True)).to_be_visible()
    page.screenshot(path=str(ROOT / '.pytest_cache' / f'cor-{theme}-{width}.png'))
    page.get_by_role('button', name='Close', exact=True).click()
    login(client, 1)
    page.goto('http://features.test/propose-topic')
    expect(page.locator('#pt-description')).to_contain_text('term frequency')
    expect(page.locator('#pt-keywords')).to_have_count(0)
    page.locator('#pt-title').fill('Attendance Tracking System')
    expect(page.locator('#pt-list')).to_contain_text('Attendance Tracking System')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    if width > 900:
        assert page.evaluate("Math.abs(document.querySelector('#pt-results').offsetHeight - document.querySelector('#propose-topic-form').offsetHeight) <= 2")
    page.screenshot(path=str(ROOT / '.pytest_cache' / f'title-{theme}-{width}.png'))
    projects = [dict(capstone_id=i, capstone_title=f'Project {i}', capstone_year=2026,
                     program_name='BSIT', specialization_name='Web', capstone_keywords='web', semester='First') for i in (1, 2)]
    monkeypatch.setattr(pages.archive, 'get_archive_capstones', lambda **kwargs: (projects, 2))
    monkeypatch.setattr(pages.archive, 'get_archive_years', lambda: [2026])
    monkeypatch.setattr(pages.archive, 'get_programs', lambda: [])
    monkeypatch.setattr(pages.archive, 'get_specializations', lambda: [])
    monkeypatch.setattr(pages.archive, 'get_saved_capstone_ids', lambda user_id: set())
    with client.session_transaction() as state:
        state['role_name'] = 'Student'
    page.goto('http://features.test/archive')
    page.locator('.archive-card[data-id="2"]').click()
    page.locator('#sb-request-link').click()
    request_dialog = page.get_by_role('dialog', name='Request Full Manuscript', exact=True)
    expect(request_dialog).to_be_visible()
    expect(request_dialog.locator('#manuscript-request-project')).to_have_text('Project 2')
    expect(request_dialog.locator('form')).to_have_attribute('action', '/request_manuscript/2')
    reason = request_dialog.get_by_role('textbox', name='Reason for requesting')
    expect(reason).to_be_focused()
    request_dialog.get_by_role('button', name='Submit Request').click()
    expect(request_dialog).to_be_visible()
    reason.fill('Reference for our capstone research.')
    assert request_dialog.evaluate('(el) => el.scrollWidth <= el.clientWidth')
    page.screenshot(path=str(ROOT / '.pytest_cache' / f'request-{theme}-{width}.png'))
    submitted = []

    def capture_request(route):
        submitted.append(route.request.post_data)
        route.fulfill(status=200, content_type='text/html', body='Request received')

    page.route('**/request_manuscript/2', capture_request)
    request_dialog.get_by_role('button', name='Submit Request').click()
    expect(page.locator('body')).to_have_text('Request received')
    assert 'request_reason=Reference+for+our+capstone+research.' in submitted[0]
    page.goto('http://features.test/signup')
    expect(page.locator('#cor')).to_be_visible()
