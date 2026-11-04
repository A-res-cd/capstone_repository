"""Inline verification keeps signup in one tab and gates document extraction."""
from urllib.parse import urlsplit

import pytest

from app.routes.authentication import registration
from tests.test_original_branch_features import feature_app, pdf_bytes


@pytest.fixture
def email_flow(feature_app, monkeypatch):
    state = {'verified': False}
    monkeypatch.setattr(registration, 'create_email_code', lambda *args: ('verification-1', '123456'))
    monkeypatch.setattr(registration, 'signup_verification_email', lambda *args: object())
    monkeypatch.setattr(registration.mail, 'send', lambda message: None)
    def verify(ident, email, code):
        state['verified'] = ident == 'verification-1' and email == 'student@example.edu' and code == '123456'
        return state['verified']
    monkeypatch.setattr(registration, 'verify_email_code', verify)
    monkeypatch.setattr(registration, 'signup_email_is_verified', lambda ident, email: state['verified'] and email == 'student@example.edu')
    return feature_app.test_client()


def test_inline_email_send_verify_and_status(email_flow):
    headers = {'X-Requested-With': 'XMLHttpRequest'}
    assert not email_flow.get('/signup/verify-email', headers=headers).json['verified']
    response = email_flow.post('/signup/verify-email', data={'action': 'send', 'email': 'student@example.edu'}, headers=headers)
    assert response.status_code == 200 and response.json['sent']
    response = email_flow.post('/signup/verify-email', data={'action': 'verify', 'email': 'student@example.edu', 'code': '000000'}, headers=headers)
    assert response.status_code == 400 and response.json['error']
    response = email_flow.post('/signup/verify-email', data={'action': 'verify', 'email': 'student@example.edu', 'code': '123456'}, headers=headers)
    assert response.status_code == 200 and response.json['verified']
    assert email_flow.get('/signup/verify-email', headers=headers).json == {'verified': True, 'email': 'student@example.edu'}


@pytest.mark.parametrize('width,height', [(1280, 900), (390, 844)])
def test_signup_five_steps_in_one_tab(email_flow, tmp_path, width, height):
    playwright = pytest.importorskip('playwright.sync_api')
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': width, 'height': height})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        def handle(route):
            url = urlsplit(route.request.url)
            if url.netloc != 'signup.test':
                route.abort()
                return
            if url.path == '/signup/extract-cor':
                route.fulfill(json={'student_no': 'SUM2026-12345', 'first_name': 'Alex', 'last_name': 'Doe'})
                return
            response = email_flow.open(url.path, method=route.request.method,
                                       data=route.request.post_data_buffer,
                                       content_type=route.request.headers.get('content-type'),
                                       headers={'X-Requested-With': route.request.headers.get('x-requested-with', '')})
            route.fulfill(status=response.status_code, body=response.data, content_type=response.content_type)
        page.route('**/*', handle)
        page.goto('http://signup.test/signup')
        assert page.locator('[data-signup-next]').is_hidden()
        page.locator('#email').fill('student@example.edu')
        page.locator('#signup-send-code').click()
        page.locator('#signup-email-code').fill('123456')
        assert page.locator('[data-signup-next]').is_hidden()
        assert page.locator('#signup-email-code').evaluate('el => parseFloat(getComputedStyle(el).borderRadius) > 0')
        page.locator('#signup-verify-code').click()
        page.locator('#cor').wait_for(state='visible')
        assert len(browser.contexts[0].pages) == 1
        page.locator('#cor').set_input_files({'name': 'cor.pdf', 'mimeType': 'application/pdf', 'buffer': pdf_bytes()})
        page.wait_for_function("document.getElementById('cor').dataset.extracting === 'false'")
        page.locator('[data-signup-next]').click()
        page.locator('#username').fill('alexdoe')
        page.locator('#password').fill('Secure123')
        page.locator('#confirm_password').fill('Secure123')
        page.locator('[data-signup-next]').click()
        page.locator('#preferred_contact').select_option('email')
        page.locator('[data-signup-next]').click()
        assert page.locator('#signup-submit').is_visible()
        assert page.locator('[data-signup-step]:visible').count() == 1
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(tmp_path / 'signup-review.png'))
        assert not errors
        browser.close()
