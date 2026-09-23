"""Original-file authorization and protected page viewing, without a database."""
from importlib import import_module
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

from flask import g, session
from PIL import Image
import pdfplumber
import pytest
from playwright.sync_api import expect

import app as application
from app.routes import decorators
from app.services import manuscript_reader


pages = import_module('app.routes.pages.manuscripts')
admin = import_module('app.routes.admin.manuscripts')


def pdf_bytes(page_total=2):
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'']
    kids = []
    for index in range(page_total):
        page_id = len(objects) + 1
        kids.append(f'{page_id} 0 R')
        text = f'BT /F1 14 Tf 24 350 Td (Confidential page {index + 1}) Tj ET'.encode()
        objects.extend([
            (f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 400] '
             f'/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> '
             f'/Contents {page_id + 1} 0 R >>').encode(),
            f'<< /Length {len(text)} >>\nstream\n'.encode() + text + b'\nendstream',
        ])
    objects[1] = f'<< /Type /Pages /Kids [{" ".join(kids)}] /Count {page_total} >>'.encode()
    data, offsets = b'%PDF-1.4\n', [0]
    for number, value in enumerate(objects, 1):
        offsets.append(len(data))
        data += f'{number} 0 obj\n'.encode() + value + b'\nendobj\n'
    xref = len(data)
    data += f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode()
    data += b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
    return data + (f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n'
                   f'startxref\n{xref}\n%%EOF\n').encode()


@pytest.fixture
def reader_app(monkeypatch, tmp_path):
    roles = {1: 'Student', 2: 'Faculty', 3: 'Admin', 4: 'Capstone Professor', 5: 'Student'}
    users = {uid: dict(user_id=uid, role_id=uid if uid < 5 else 1, role_name=name)
             for uid, name in roles.items()}
    approved = {1, 5}
    record = dict(capstone_id=7, capstone_title='Private manuscript', capstone_file='uploads/private.pdf')

    def load_user():
        g.user = users.get(session.get('user_id'))
        if not g.user:
            session.clear()

    monkeypatch.setenv('FLASK_DEBUG', '0')
    monkeypatch.setattr(application, 'load_current_user', load_user)
    monkeypatch.setattr(application, 'BackgroundScheduler', lambda **kwargs: SimpleNamespace(
        add_job=lambda *args, **kwargs: None, start=lambda: None))
    app = application.create_app()
    app.config.update(TESTING=True, SECRET_KEY='reader-test', WTF_CSRF_ENABLED=False,
                      UPLOAD_MANUSCRIPT_FOLDER=str(tmp_path / 'manuscripts'))
    folder = Path(app.config['UPLOAD_MANUSCRIPT_FOLDER'])
    folder.mkdir()
    (folder / 'private.pdf').write_bytes(pdf_bytes())
    for module in (pages, admin):
        monkeypatch.setattr(module, 'get_capstone_details', lambda cid: record if cid == 7 else None)
        monkeypatch.setattr(module, 'get_capstone_authors', lambda cid: [])
    monkeypatch.setattr(admin, 'extract_abstract_text', lambda path: 'Public abstract only.')
    monkeypatch.setattr(decorators, 'get_user_requests', lambda uid: [
        dict(capstone_id=7, request_status='approved' if uid in approved else 'pending')])
    app.reader_state = SimpleNamespace(users=users, approved=approved, record=record, file=folder / 'private.pdf')
    yield app
    manuscript_reader._page_count.cache_clear()
    manuscript_reader._render_page.cache_clear()


def login(client, uid=1):
    with client.session_transaction() as state:
        # These stale session claims must never grant original-file privileges.
        state.update(user_id=uid, role_id=3, role_name='Admin')


@pytest.mark.parametrize('uid', [1, 2, 4, 5])
@pytest.mark.parametrize('path', ['/manuscript/file/7', '/repository/file/7'])
def test_non_admin_cannot_fetch_original_even_with_approval(reader_app, uid, path):
    client = reader_app.test_client()
    login(client, uid)
    for method in ['GET', 'HEAD']:
        response = client.open(path, method=method, headers={'Range': 'bytes=0-100'})
        assert response.status_code == 403
        assert not response.data.startswith(b'%PDF')


@pytest.mark.parametrize('path', ['/manuscript/file/7', '/repository/file/7'])
def test_admin_original_access_and_immediate_role_demotion(reader_app, path):
    client = reader_app.test_client()
    login(client, 3)
    assert client.get(path).data == pdf_bytes()
    reader_app.reader_state.users[3].update(role_id=2, role_name='Faculty')
    assert client.get(path).status_code == 403


@pytest.mark.parametrize('path', ['/manuscript/pages/7', '/manuscript/pages/7/1',
                                  '/manuscript/pages/7/1?format=pdf'])
def test_page_access_rechecked_after_revocation_and_logout(reader_app, path):
    client = reader_app.test_client()
    assert client.get(path).status_code == 401
    login(client)
    assert client.get(path).status_code == 200
    reader_app.reader_state.approved.remove(1)
    response = client.get(path)
    assert response.status_code == 403
    assert 'no-store' in response.headers['Cache-Control']
    reader_app.reader_state.users.pop(1)
    assert client.get(path).status_code == 401


def test_rendered_pages_are_watermarked_private_and_bounded(reader_app):
    client = reader_app.test_client()
    login(client)
    assert client.get('/manuscript/pages/7').json == {'page_count': 2}
    first = client.get('/manuscript/pages/7/1')
    assert first.status_code == 200 and first.mimetype == 'image/jpeg'
    assert 'private' in first.headers['Cache-Control'] and 'no-store' in first.headers['Cache-Control']
    assert first.headers['X-Content-Type-Options'] == 'nosniff'
    assert 'ETag' not in first.headers
    assert b'%PDF' not in first.data and b'Confidential' not in first.data
    with Image.open(BytesIO(first.data)) as image:
        assert max(image.size) <= manuscript_reader.MAX_PAGE_DIMENSION
    login(client, 5)
    assert client.get('/manuscript/pages/7/1').data != first.data
    assert client.get('/manuscript/pages/7/2').data != first.data
    for path in ['/manuscript/pages/7/0', '/manuscript/pages/7/3', '/manuscript/pages/8/1']:
        assert client.get(path).status_code in (403, 404)


def test_replaced_missing_corrupt_and_non_pdf_manuscripts(reader_app):
    client = reader_app.test_client()
    login(client)
    assert client.get('/manuscript/pages/7').json['page_count'] == 2
    reader_app.reader_state.file.write_bytes(pdf_bytes(3))
    assert client.get('/manuscript/pages/7').json['page_count'] == 3
    assert client.get('/manuscript/pages/7/3').status_code == 200
    reader_app.reader_state.file.write_bytes(b'broken pdf')
    assert client.get('/manuscript/pages/7').status_code == 422
    assert client.get('/manuscript/pages/7/1').status_code == 422
    word = reader_app.reader_state.file.with_suffix('.docx')
    word.write_bytes(b'private word document')
    reader_app.reader_state.record['capstone_file'] = word.name
    assert client.get('/manuscript/pages/7').status_code == 415
    assert client.get('/manuscript/pages/7/1').status_code == 415
    assert client.get('/manuscript/file/7').status_code == 403
    reader_app.reader_state.record['capstone_file'] = 'missing.pdf'
    assert client.get('/manuscript/pages/7').status_code == 404


def test_pdfjs_receives_only_one_watermarked_image_page(reader_app):
    client = reader_app.test_client()
    login(client)
    response = client.get('/manuscript/pages/7/1?format=pdf')
    assert response.status_code == 200 and response.mimetype == 'application/pdf'
    assert 'no-store' in response.headers['Cache-Control']
    assert response.data != pdf_bytes()
    with pdfplumber.open(BytesIO(response.data)) as pdf:
        assert len(pdf.pages) == 1
        assert len(pdf.pages[0].images) == 1
        assert not pdf.pages[0].extract_text()
        image_data = pdf.pages[0].images[0]['stream'].get_data()
    login(client, 5)
    other = client.get('/manuscript/pages/7/1?format=pdf')
    with pdfplumber.open(BytesIO(other.data)) as pdf:
        assert pdf.pages[0].images[0]['stream'].get_data() != image_data


@pytest.mark.parametrize('uid', [1, 2, 4])
@pytest.mark.parametrize('path', ['/manuscript/view/7', '/repository/pdf/7'])
def test_full_view_uses_protected_reader_for_non_admin(reader_app, uid, path):
    client = reader_app.test_client()
    login(client, uid)
    response = client.get(path)
    assert response.status_code == 200
    assert b'data-manuscript-reader' in response.data
    assert b'/manuscript/pages/7' in response.data
    assert b'<iframe' not in response.data
    assert b'/repository/file/' not in response.data and b'/manuscript/file/' not in response.data
    assert b'private.pdf' not in response.data


def test_unapproved_student_keeps_abstract_only_access(reader_app):
    client = reader_app.test_client()
    login(client)
    reader_app.reader_state.approved.clear()
    response = client.get('/repository/pdf/7')
    assert response.status_code == 200 and b'Public abstract only.' in response.data
    assert b'data-manuscript-reader' not in response.data
    assert client.get('/manuscript/view/7').status_code == 302
    assert client.get('/manuscript/pages/7/1').status_code == 403


@pytest.mark.parametrize('path', ['/static/uploads/private.pdf', '/static/./uploads/private.pdf',
                                  '/static/%2e/uploads/private.pdf', '/static/css/../uploads/private.pdf',
                                  '/static/Uploads/private.pdf', '/static/uploads./private.pdf',
                                  '/static/uploads%20/private.pdf'])
def test_legacy_uploads_cannot_bypass_protected_routes(reader_app, tmp_path, path):
    static = tmp_path / 'static'
    (static / 'uploads').mkdir(parents=True)
    (static / 'uploads/private.pdf').write_bytes(pdf_bytes())
    reader_app.static_folder = str(static)
    assert reader_app.test_client().get(path).status_code == 404


@pytest.mark.parametrize('theme,width', [('light', 1280), ('dark', 1280), ('light', 390), ('dark', 390)])
def test_reader_browser_navigation_zoom_and_revoked_access(reader_app, page, theme, width):
    client = reader_app.test_client()
    login(client)
    requests, errors = [], []

    def handle(route):
        url = urlsplit(route.request.url)
        if url.netloc != 'reader.test':
            route.abort()
            return
        requests.append(url.path)
        response = client.get(url.path + ('?' + url.query if url.query else ''))
        route.fulfill(status=response.status_code, body=response.data, headers=dict(response.headers))

    page.route('**/*', handle)
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.add_init_script(f"localStorage.setItem('capre-theme', '{theme}')")
    page.set_viewport_size({'width': width, 'height': 900})
    page.goto('http://reader.test/manuscript/view/7')
    canvas = page.locator('[data-reader-page="1"]')
    expect(canvas).to_be_visible()
    expect(page.locator('.meta-panel .capstone-title')).to_have_text('Private manuscript')
    expect(page.get_by_role('heading', name='Full Manuscript', exact=True)).to_be_visible()
    expect(canvas).to_have_attribute('aria-label', 'Manuscript page 1 of 2')
    assert canvas.evaluate('el => el.width') > 0
    expect(page.get_by_role('button', name='Previous', exact=True)).to_be_disabled()
    page.get_by_role('button', name='Next', exact=True).click()
    canvas = page.locator('[data-reader-page="2"]')
    expect(canvas).to_be_visible()
    expect(canvas).to_have_attribute('aria-label', 'Manuscript page 2 of 2')
    expect(page.get_by_role('button', name='Next', exact=True)).to_be_disabled()
    page.locator('#manuscript-page').select_option('1')
    canvas = page.locator('[data-reader-page="1"]')
    expect(page.get_by_role('status')).to_have_text('Page 1 of 2')
    before = canvas.bounding_box()['width']
    page.locator('#manuscript-zoom').select_option('2')
    assert canvas.bounding_box()['width'] >= before * 1.9
    stage = page.locator('[data-reader-stage]')
    stage.scroll_into_view_if_needed()
    stage.hover()
    wheel_before = canvas.bounding_box()['width']
    stage.evaluate('el => el.scrollTop = 0')
    page.mouse.wheel(0, 100)
    expect(stage).to_have_js_property('scrollTop', 100)
    expect(page.locator('#manuscript-zoom')).to_have_value('2')
    assert canvas.bounding_box()['width'] == wheel_before
    page.keyboard.down('Control')
    try:
        page.mouse.wheel(0, -100)
        expect(page.locator('#manuscript-zoom')).not_to_have_value('2')
        assert canvas.bounding_box()['width'] > wheel_before
        page.mouse.wheel(0, 100)
        expect(page.locator('#manuscript-zoom')).to_have_value('2')
    finally:
        page.keyboard.up('Control')
    stage.evaluate('el => el.scrollTop = 100')
    scroll_before = stage.evaluate('el => el.scrollTop')
    bounds = stage.bounding_box()
    page.mouse.move(bounds['x'] + bounds['width'] / 2, bounds['y'] + bounds['height'] / 2)
    page.mouse.down()
    page.mouse.move(bounds['x'] + bounds['width'] / 2, bounds['y'] + bounds['height'] / 2 - 50)
    page.mouse.up()
    assert stage.evaluate('el => el.scrollTop') > scroll_before
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    stage.evaluate('el => el.scrollTop = el.scrollHeight - el.clientHeight')
    expect(page.locator('#manuscript-page')).to_have_value('2')
    expect(page.locator('[data-reader-page="2"]')).to_be_visible()
    expect(page.locator('#manuscript-page option')).to_have_count(2)
    view = page.locator('#manuscript-view')
    view.select_option('single')
    expect(page.locator('.manuscript-reader__page:visible')).to_have_count(1)
    expect(page.locator('#manuscript-page')).to_have_value('2')
    expect(canvas).to_be_hidden()
    page.get_by_role('button', name='Previous', exact=True).click()
    expect(canvas).to_be_visible()
    expect(page.locator('[data-reader-page="2"]')).to_be_hidden()
    expect(page.locator('#manuscript-zoom')).to_have_value('2')
    view.select_option('continuous')
    expect(page.locator('.manuscript-reader__page:visible')).to_have_count(2)
    expect(page.locator('#manuscript-page')).to_have_value('1')
    page.locator('#manuscript-page').select_option('1')
    expect(canvas).to_have_attribute('aria-label', 'Manuscript page 1 of 2')
    expect(page.get_by_role('status')).to_have_text('Page 1 of 2')
    reader_app.reader_state.approved.clear()
    page.get_by_role('button', name='Next', exact=True).click()
    expect(page.get_by_role('status')).to_have_text('You no longer have access to this manuscript.')
    expect(canvas).to_be_hidden()
    assert not any('/file/' in path for path in requests)
    assert not errors
