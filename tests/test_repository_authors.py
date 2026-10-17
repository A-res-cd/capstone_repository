from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect

from app.routes.admin import repository
from app.routes.forms import CreateCapstoneForm
from tests.test_original_branch_features import feature_app, login

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('count', [0, 1, 2, 3, 4, 5, 6])
def test_server_accepts_only_one_to_five_complete_authors(feature_app, count):
    data = {'capstone_title': 'Test', 'capstone_year': '2026', 'program_id': '1',
            'specialization_id': '1', 'semester': '1st', 'capstone_keywords': 'network',
            'adviser-first_name': 'Test', 'adviser-last_name': 'Adviser'}
    for i in range(count):
        data.update({f'authors-{i}-first_name': f'Member {i}', f'authors-{i}-last_name': 'Author'})
    data['capstone_file'] = (BytesIO(b'%PDF-content'), 'test.pdf')
    with feature_app.test_request_context(method='POST', data=data):
        form = CreateCapstoneForm()
        form.program_id.choices = [(1, 'BSIT')]
        form.specialization_id.choices = [(1, 'Web')]
        assert form.validate() == (1 <= count <= 5)
        if not 1 <= count <= 5:
            assert form.authors.errors


def test_partial_author_is_rejected(feature_app):
    with feature_app.test_request_context(method='POST', data={'authors-0-first_name': 'First'}):
        form = CreateCapstoneForm()
        form.program_id.choices = []
        form.specialization_id.choices = []
        form.validate()
        assert form.authors.errors == ['Each author needs a first and last name.']


def test_member_count_and_extracted_five_authors_in_browser(feature_app, page, monkeypatch):
    monkeypatch.setattr(repository, 'get_all_capstones', lambda **_: ([], 0))
    monkeypatch.setattr(repository, 'get_programs', lambda include_codes=False: [(1, 'BSIT', 'BSIT')])
    monkeypatch.setattr(repository, 'get_specializations', lambda include_codes=False: [(1, 'Web', 'WST')])
    monkeypatch.setattr(repository, 'get_capstone_years', lambda: [])
    client = feature_app.test_client()
    login(client)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    def route(request_route):
        url = urlsplit(request_route.request.url)
        if url.netloc != 'repository.test':
            request_route.abort()
            return
        if url.path.startswith('/static/'):
            file = ROOT / 'app' / url.path.lstrip('/')
            request_route.fulfill(path=str(file))
            return
        if url.path == '/repository/extract':
            request_route.fulfill(json={'success': True, 'data': {
                'authors': [{'first': f'Member {i}', 'middle': '', 'last': 'Author'} for i in range(5)],
                'adviser': {'first': 'Racquel', 'middle': 'L.', 'last': 'Pula'},
            }})
            return
        response = client.get(url.path)
        request_route.fulfill(status=response.status_code, body=response.get_data(), content_type='text/html')
    page.route('**/*', route)
    page.goto('http://repository.test/repository')
    page.locator('#btn-open-create').click()
    page.evaluate("document.querySelectorAll('.form-step').forEach(el => el.classList.remove('form-step--hidden'))")
    expect(page.locator('[data-author-row]:visible')).to_have_count(1)
    page.locator('#author-count').select_option('5', force=True)
    expect(page.locator('[data-author-row]:visible')).to_have_count(5)
    page.locator('#authors-4-first_name').fill('Fifth')
    page.locator('#authors-4-last_name').fill('Member')
    page.locator('#author-count').select_option('1', force=True)
    assert page.locator('#authors-4-first_name').is_disabled()
    assert 'authors-4-first_name' not in page.evaluate("Object.fromEntries(new FormData(document.getElementById('capstone-form')))")
    page.locator('#extract-file-input').set_input_files({'name': 'template.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-template'})
    expect(page.locator('[data-author-row]:visible')).to_have_count(5)
    expect(page.locator('#authors-4-first_name')).to_have_value('Member 4')
    expect(page.locator('#adviser-last_name')).to_have_value('Pula')
    assert not errors
