"""Account email rendering and delivery integration; no real emails are sent."""
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

from flask import Flask
from flask_mail import Mail
from playwright.sync_api import expect
import pytest

from app.utils.account_emails import password_reset_email, verification_email

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def email_app():
    app = Flask(__name__, template_folder=str(ROOT / 'app/templates'))
    app.config.update(SECRET_KEY='email-test', WTF_CSRF_ENABLED=False, MAIL_DEFAULT_SENDER='noreply@example.com')
    Mail(app)
    return app


def message_for(kind):
    if kind == 'otp':
        return password_reset_email('student@example.com', 'Maria_Cruz', '004201', 4)
    return verification_email({'email': 'student@example.com', 'full_name': 'Maria Cruz'}, kind, 'Please provide your university ID.')


def test_otp_has_html_and_plain_text_without_exposing_code_in_subject(email_app):
    with email_app.app_context():
        message = message_for('otp')
        mime = message._message()
    assert message.subject == 'Your CAPRE password reset code'
    assert '004201' not in message.subject
    assert '004201' in message.html and '004201' in message.body
    assert '4 minutes' in message.html and '4 minutes' in message.body
    assert 'Do not share it' in message.body
    assert 'multipart/alternative' in mime.as_string()
    assert 'text/plain' in mime.as_string() and 'text/html' in mime.as_string()


def test_names_and_feedback_are_escaped_in_html(email_app):
    with email_app.app_context():
        message = verification_email(
            {'email': 'student@example.com', 'full_name': '<img src=x onerror=alert(1)>'},
            'rejected', '<script>alert(1)</script>\nMissing document.',
        )
    assert '<script>' not in message.html and '<img' not in message.html
    assert '&lt;script&gt;' in message.html and '&lt;img' in message.html
    assert 'Missing document.' in message.body and 'NOT APPROVED' in message.body


@pytest.mark.parametrize('kind', ['otp', 'approved', 'rejected'])
@pytest.mark.parametrize('width', [320, 900])
def test_email_layout_without_external_assets(email_app, page, kind, width, tmp_path):
    with email_app.app_context():
        message = message_for(kind)
    requests = []
    page.on('request', lambda request: requests.append(request.url))
    page.set_viewport_size({'width': width, 'height': 900})
    page.set_content(message.html)
    expect(page.get_by_role('heading', level=1)).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert requests == []
    if kind == 'otp':
        expect(page.get_by_text('004201', exact=True)).to_be_visible()
        assert '004201' not in page.locator('body > div').inner_text()
    page.screenshot(path=str(tmp_path / f'email-{kind}-{width}.png'), full_page=True)


def test_password_reset_route_sends_formatted_email_and_retains_failure_handling(email_app, monkeypatch):
    routes = import_module('app.routes.authentication')
    email_app.register_blueprint(routes.auth)
    sent = []
    monkeypatch.setattr(routes, 'lookup_user_for_reset', lambda username, email: (11, 7, None))
    monkeypatch.setattr(routes, 'create_otp', lambda contact_id: ('004201', 9))
    monkeypatch.setattr(routes, 'mail', SimpleNamespace(send=sent.append))
    client = email_app.test_client()
    response = client.post('/forgot_password', data={'username': 'Maria_Cruz', 'email': 'student@example.com'})
    assert response.status_code == 302
    assert sent[0].recipients == ['student@example.com']
    assert '004201' in sent[0].html and '004201' in sent[0].body
    with client.session_transaction() as session:
        assert session['reset_id'] == 9 and session['reset_user_id'] == 7
        session.clear()

    def fail_send(message):
        raise OSError('mail server unavailable')

    monkeypatch.setattr(routes, 'mail', SimpleNamespace(send=fail_send))
    monkeypatch.setattr(routes, 'render_template', lambda *args, **kwargs: 'Password reset form')
    response = client.post('/forgot_password', data={'username': 'Maria_Cruz', 'email': 'student@example.com'})
    assert response.status_code == 200
    with client.session_transaction() as session:
        assert 'reset_id' not in session
