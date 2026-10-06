"""Verify the selected integration without changing existing role permissions."""
from contextlib import closing
from importlib import import_module
from io import BytesIO
from pathlib import Path
import uuid

from flask import Flask, g, session
from flask_wtf.csrf import CSRFProtect
from PIL import Image, ImageStat
import psycopg2
import pypdfium2 as pdfium
import pytest

from app.db import capstones, archive, view_history, review_history
from app.routes import decorators
from app.services import manuscript_reader
from app.constants.roles import LEGACY_ROLE_NAMES_BY_ID, ROLE_ADMIN, landing_endpoint
from tests.test_original_branch_features import isolated_database


ROOT = Path(__file__).resolve().parents[1]
pages = import_module('app.routes.pages')
admin = import_module('app.routes.admin')


@pytest.fixture
def preview_app(monkeypatch, tmp_path):
    app = Flask(__name__, template_folder=str(ROOT / 'app/templates'),
                static_folder=str(ROOT / 'app/static'))
    app.config.update(TESTING=True, SECRET_KEY='css-preview', WTF_CSRF_ENABLED=False,
                      UPLOAD_MANUSCRIPT_FOLDER=str(tmp_path))
    CSRFProtect(app)
    for name, attribute in [('pages', 'pages'), ('admin', 'admin'),
                            ('authentication', 'auth'), ('faculty', 'faculty'), ('system', 'system')]:
        app.register_blueprint(getattr(import_module('app.routes.' + name), attribute))
    app.add_url_rule('/', endpoint='main.home', view_func=lambda: 'Home')
    roles = {1: 'Student', 2: 'Faculty', 3: 'RET Chair', 4: 'Capstone Professor',
             5: 'System Administrator', 6: 'Student'}
    approved = {1}
    records = []

    @app.before_request
    def user():
        uid = session.get('user_id')
        g.user = dict(user_id=uid, role_name=roles[uid], account_status='active') if uid else None

    @app.context_processor
    def context():
        return dict(hide_header=True, hide_nav=True, current_user={})

    with pdfium.PdfDocument.new() as document:
        for _ in range(2):
            with closing(document.new_page(300, 400)):
                pass
        document.save(str(tmp_path / 'sample.pdf'))
    record = dict(capstone_id=7, capstone_title='Watermarked manuscript',
                  capstone_file='sample.pdf', capstone_year=2026)
    for module in (pages.manuscripts, admin.repository, admin.manuscripts):
        monkeypatch.setattr(module, 'get_capstone_details', lambda cid: record if cid == 7 else None)
        monkeypatch.setattr(module, 'get_capstone_authors', lambda cid: [])
        monkeypatch.setattr(module, 'record_capstone_activity', lambda *args, **kwargs: True)
    monkeypatch.setattr(decorators, 'get_user_requests', lambda uid: [
        dict(capstone_id=7, request_status='approved')
    ] if uid in approved else [])
    monkeypatch.setattr(pages.history, 'record_capstone_view', lambda *args: records.append(args) or True)
    app.preview_roles, app.preview_approved, app.preview_records = roles, approved, records
    return app


def login(client, uid):
    with client.session_transaction() as state:
        state.update(user_id=uid, role_id=3, role_name='RET Chair')


@pytest.mark.parametrize('uid,allowed', [(1, True), (2, True), (3, True), (4, True), (5, False), (6, False)])
def test_reader_uses_current_database_role_and_approval(preview_app, uid, allowed):
    client = preview_app.test_client()
    login(client, uid)
    result = client.get('/manuscript/pages/7')
    assert result.status_code == (200 if allowed else 403)
    if allowed:
        assert result.json == {'page_count': 2}
    assert ROLE_ADMIN == 'System Administrator'
    assert landing_endpoint(ROLE_ADMIN) == 'system.overview'


def test_reader_rechecks_revocation_and_logout(preview_app):
    client = preview_app.test_client()
    login(client, 1)
    assert client.get('/manuscript/pages/7/1').status_code == 200
    preview_app.preview_approved.clear()
    assert client.get('/manuscript/pages/7/1').status_code == 403
    with client.session_transaction() as state:
        state.clear()
    assert client.get('/manuscript/pages/7/1').status_code == 401


def test_page_rendering_is_bounded_watermarked_and_not_cached(preview_app):
    client = preview_app.test_client()
    login(client, 1)
    result = client.get('/manuscript/pages/7/1')
    assert result.status_code == 200
    assert 'no-store' in result.headers['Cache-Control']
    with Image.open(BytesIO(result.data)) as image:
        assert max(image.size) <= manuscript_reader.MAX_PAGE_DIMENSION
        assert max(ImageStat.Stat(image).stddev) > 0  # Watermark on the blank test PDF.
    result = client.get('/manuscript/pages/7/1?format=pdf')
    with pdfium.PdfDocument(result.data) as document:
        assert len(document) == 1
        with closing(document[0]) as page, closing(page.get_textpage()) as text:
            assert text.get_text_range() == ''
    assert client.get('/manuscript/pages/7/0').status_code == 404
    assert client.get('/manuscript/pages/7/3').status_code == 404


def test_reader_ui_uses_merged_download_permissions_and_history(preview_app):
    client = preview_app.test_client()
    login(client, 1)
    assert b'data-manuscript-reader' in client.get('/manuscript/view/7').data
    assert client.get('/manuscript/file/7').status_code == 403
    assert preview_app.preview_records == [(1, 7)]
    login(client, 2)
    assert b'data-manuscript-reader' in client.get('/repository/pdf/7').data
    assert client.get('/repository/file/7').status_code == 403
    assert preview_app.preview_records == [(1, 7)]
    login(client, 3)
    assert client.get('/repository/file/7').status_code == 200


def test_histories_use_authenticated_identity_and_current_roles(preview_app, monkeypatch):
    reads = []
    monkeypatch.setattr(pages.history, 'get_view_history', lambda uid, *args: (reads.append(uid) or [], 0))
    reviews = []
    monkeypatch.setattr(admin.history, 'get_review_history', lambda **kwargs: (reviews.append(kwargs) or [], 0, 20))
    client = preview_app.test_client()
    login(client, 1)
    assert client.get('/view-history?user_id=6').status_code == 200
    assert reads == [1]
    assert client.post('/view-history/7', data={'user_id': 6}).status_code == 200
    assert preview_app.preview_records == [(1, 7)]
    login(client, 4)
    assert client.get('/review-history?view=recent').status_code == 200
    assert reviews[-1]['reviewed_by'] == 4
    assert reviews[-1]['recent'] is True
    login(client, 3)
    assert client.get('/review-history').status_code == 200
    assert reviews[-1]['reviewed_by'] is None
    login(client, 5)
    assert client.get('/review-history').status_code == 302
    assert len(reviews) == 2


def test_current_feature_routes_remain_registered(preview_app):
    endpoints = set(preview_app.view_functions)
    assert {'pages.toggle_saved_capstone_route', 'pages.submit_promotion_request_route',
            'pages.profile_overview', 'pages.register_capstoner', 'pages.my_progress',
            'faculty.manage_capstone_users', 'admin.capstoner_review',
            'system.overview', 'admin.overview'} <= endpoints
    assert LEGACY_ROLE_NAMES_BY_ID[3] == 'RET Chair'


@pytest.mark.parametrize('width', [390, 1280])
def test_reader_browser_navigation_and_zoom(preview_app, page, width):
    from urllib.parse import urlsplit
    from playwright.sync_api import expect

    client = preview_app.test_client()
    login(client, 1)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))

    def serve(route):
        url = urlsplit(route.request.url)
        if url.netloc != 'preview.test':
            route.abort()
            return
        response = client.open(url.path + ('?' + url.query if url.query else ''),
                               method=route.request.method, data=route.request.post_data)
        route.fulfill(status=response.status_code, body=response.data,
                      headers={key: value for key, value in response.headers if key.lower() != 'content-length'})

    page.route('**/*', serve)
    page.set_viewport_size({'width': width, 'height': 900})
    page.goto('http://preview.test/manuscript/view/7')
    expect(page.locator('[data-reader-status]')).to_contain_text('Page 1', timeout=20000)
    page.locator('#manuscript-view').select_option('single')
    page.locator('[data-next]').click()
    expect(page.locator('[data-reader-status]')).to_contain_text('Page 2')
    page.locator('#manuscript-zoom').select_option('1.5')
    assert page.locator('[data-reader-stage]').evaluate('element => element.scrollWidth > element.clientWidth')
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 2')
    assert errors == []


@pytest.fixture
def preview_db(isolated_database, monkeypatch):
    schema = 'css_preview_' + uuid.uuid4().hex
    with closing(psycopg2.connect(**isolated_database)) as conn, conn.cursor() as cursor:
        cursor.execute(f'CREATE SCHEMA "{schema}"')
        cursor.execute(f'SET search_path TO "{schema}"')
        cursor.execute((ROOT / 'database/capreDB.sql').read_text(encoding='utf-8'))
        cursor.execute('ALTER TABLE capstone DROP COLUMN is_published, DROP COLUMN abstract_text')
        cursor.execute('ALTER TABLE program DROP COLUMN program_code')
        cursor.execute('ALTER TABLE specialization DROP COLUMN specialization_code')
        cursor.execute('DROP TABLE capstone_view_history')
        cursor.execute("INSERT INTO role(role_id, role_name) VALUES (1, 'Student'), (3, 'RET Chair')")
        cursor.execute('INSERT INTO "user" (user_id, role_id) VALUES (1, 1), (2, 1)')
        cursor.execute("INSERT INTO program (program_name) VALUES ('BSIT')")
        cursor.execute("INSERT INTO specialization (specialization_name) VALUES ('DST')")
        cursor.execute("INSERT INTO program (program_name) VALUES ('A legacy program name longer than thirty characters')")
        cursor.execute("INSERT INTO specialization (specialization_name) VALUES ('A legacy specialization name longer than thirty characters')")
        cursor.execute("INSERT INTO keyword (capstone_keywords) VALUES ('orchard weather')")
        cursor.execute("INSERT INTO capstone (program_id, specialization_id, keyword_id, capstone_title, capstone_year) VALUES (1, 1, 1, 'Historical capstone', 2025)")
        cursor.execute('INSERT INTO saved_capstone(user_id, capstone_id) VALUES (1, 1)')
        migration = (ROOT / 'migrations/20261005_css_preview_repository.sql').read_text()
        cursor.execute(migration)
        cursor.execute(migration)  # Idempotent; existing publication status remains unknown.
        conn.commit()

    def connect():
        return psycopg2.connect(**isolated_database, options=f'-c search_path={schema}')

    for module in (capstones, archive, view_history, review_history):
        monkeypatch.setattr(module, 'db_connect', connect)
    return connect


def test_additive_migration_publication_filters_and_saved_records(preview_db):
    assert capstones.get_capstone_details(1)['is_published'] is None
    assert capstones.get_capstones_corpus()[0]['capstone_keywords'] == 'orchard weather'
    ok, cid = capstones.create_capstone_project(1, 1, 1, 'New capstone', 2026,
                                               'new.pdf', '1st', abstract_text='Weather sensors')
    assert ok
    assert capstones.get_capstone_details(cid)['is_published'] is False
    rows, total = capstones.get_all_capstones(year=2026)
    assert total == 1 and rows[0]['capstone_id'] == cid
    rows, total = archive.get_archive_capstones(search='orchard', search_scope='title')
    assert total == 0
    rows, total = archive.get_archive_capstones(search='orchard', search_scope='keyword', saved_by=1)
    assert total == 1 and rows[0]['capstone_id'] == 1
    with closing(preview_db()) as conn, conn.cursor() as cursor:
        cursor.execute('SELECT COUNT(*) FROM saved_capstone')
        assert cursor.fetchone()[0] == 1
        cursor.execute('SELECT role_name FROM role WHERE role_id = 3')
        assert cursor.fetchone()[0] == 'RET Chair'
        cursor.execute('SELECT program_code FROM program WHERE program_id = 2')
        assert cursor.fetchone()[0] is None
        cursor.execute('SELECT specialization_code FROM specialization WHERE specialization_id = 2')
        assert cursor.fetchone()[0] is None


def test_database_history_is_private_and_updates_recency(preview_db):
    assert view_history.record_capstone_view(1, 1)
    assert view_history.record_capstone_view(1, 1)
    rows, total = view_history.get_view_history(1)
    assert total == 1 and rows[0]['capstone_id'] == 1
    assert view_history.get_view_history(2) == ([], 0)
    with closing(preview_db()) as conn, conn.cursor() as cursor:
        cursor.execute('UPDATE capstone SET is_archived = TRUE WHERE capstone_id = 1')
        conn.commit()
    assert view_history.get_view_history(1) == ([], 0)


def test_program_specialization_validation_preserves_account_choices(preview_app, preview_db):
    from app.routes.forms import CreateCapstoneForm

    with preview_app.test_request_context('/'):
        g.user = {'role_name': 'Faculty'}
        form = CreateCapstoneForm()
        programs = capstones.get_programs(include_codes=True)
        form.program_id.data = next(row[0] for row in programs if row[2] == 'BSDS')
        admin.repository._populate_capstone_choices(form)
        general = next(row[0] for row in capstones.get_specializations(include_codes=True) if row[2] == 'GENERAL')
        assert form.specialization_id.choices == [(general, 'No specialization')]
        assert form.authors[0].user_id.choices == [(0, 'No linked account')]


def test_review_database_filters_professor_to_own_decisions(preview_db):
    with closing(preview_db()) as conn, conn.cursor() as cursor:
        cursor.execute("INSERT INTO request (user_id, request_type, request_status, reviewed_by, decision_date) VALUES (1, 'verification_student', 'approved', 1, NOW()), (2, 'verification_student', 'rejected', 2, NOW())")
        conn.commit()
    rows, total, _ = review_history.get_review_history(reviewed_by=1)
    assert total == 1 and rows[0]['requester'] == ''
    assert review_history.get_review_history()[1] == 2
