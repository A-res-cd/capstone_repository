import io
import json
from urllib.parse import parse_qs

import pytest
from flask import Flask

from app.utils import account_sms
from app.routes.authentication import passwords


@pytest.fixture
def sms_app():
    app = Flask(__name__, template_folder='../app/templates')
    app.config.update(SECRET_KEY='sms-test', WTF_CSRF_ENABLED=False,
                      AUTH_RATE_LIMIT_ENABLED=False, SEMAPHORE_API_KEY='private-key',
                      SEMAPHORE_SENDER_NAME='CAPRE')
    app.register_blueprint(passwords.auth)
    return app


def test_sms_preserves_leading_zero_code_and_normalizes_phone(sms_app, monkeypatch):
    def send(request, timeout):
        assert request.full_url == 'https://api.semaphore.co/api/v4/otp'
        assert timeout == 10
        payload = parse_qs(request.data.decode())
        assert payload['number'] == ['639171234567']
        assert payload['code'] == ['004201']
        assert payload['sendername'] == ['CAPRE']
        assert '{otp}' in payload['message'][0]
        return io.StringIO('[{"message_id": 123, "status": "Pending"}]')
    monkeypatch.setattr(account_sms, 'urlopen', send)
    with sms_app.app_context():
        account_sms.send_password_reset_sms('09171234567', '004201', 4)


def test_notification_uses_messages_endpoint_and_default_sender(sms_app, monkeypatch):
    sms_app.config['SEMAPHORE_SENDER_NAME'] = ''
    def send(request, timeout):
        assert request.full_url == 'https://api.semaphore.co/api/v4/messages'
        assert request.get_method() == 'POST'
        assert timeout == 10
        payload = parse_qs(request.data.decode())
        assert payload['apikey'] == ['private-key']
        assert payload['number'] == ['639171234567']
        assert payload['message'] == ['Your manuscript request was approved.']
        assert 'code' not in payload
        assert 'sendername' not in payload
        return io.StringIO('[{"message_id": 123, "status": "Queued"}]')
    monkeypatch.setattr(account_sms, 'urlopen', send)
    with sms_app.app_context():
        assert account_sms.send_sms('09171234567', 'Your manuscript request was approved.') == 123


@pytest.mark.parametrize('message', ['', '   ', None])
def test_notification_rejects_empty_message(sms_app, monkeypatch, message):
    monkeypatch.setattr(account_sms, 'urlopen', lambda *args, **kwargs: pytest.fail('Must not send'))
    with sms_app.app_context(), pytest.raises(OSError):
        account_sms.send_sms('09171234567', message)


def test_sms_timeout_does_not_expose_credentials(sms_app, monkeypatch):
    def send(*args, **kwargs):
        raise TimeoutError('private-key')
    monkeypatch.setattr(account_sms, 'urlopen', send)
    with sms_app.app_context(), pytest.raises(OSError, match='provider is unavailable') as error:
        account_sms.send_sms('09171234567', 'CAPRE notification')
    assert 'private-key' not in str(error.value)


@pytest.mark.parametrize('result', [{}, [], [{'message_id': 1, 'status': 'Failed'}],
                                    [{'message_id': 1, 'status': None}]])
def test_sms_rejects_provider_errors(sms_app, monkeypatch, result):
    monkeypatch.setattr(account_sms, 'urlopen', lambda *args, **kwargs: io.StringIO(json.dumps(result)))
    with sms_app.app_context(), pytest.raises(OSError):
        account_sms.send_password_reset_sms('+639171234567', '004201', 4)


@pytest.mark.parametrize('phone', ['', '+14155552671', 'not-a-number', '+639171234567,639171234568'])
def test_sms_rejects_invalid_or_multiple_recipients(sms_app, monkeypatch, phone):
    def unexpected_send(*args, **kwargs):
        pytest.fail('Invalid phone must not reach the provider')
    monkeypatch.setattr(account_sms, 'urlopen', unexpected_send)
    with sms_app.app_context(), pytest.raises(OSError):
        account_sms.send_password_reset_sms(phone, '004201', 4)


@pytest.mark.parametrize('outcome', ['accepted', 'missing_phone', 'provider_failure', 'unconfigured'])
def test_reset_sms_uses_registered_phone_and_only_sets_session_on_acceptance(sms_app, monkeypatch, outcome):
    calls = []
    monkeypatch.setattr(passwords, 'render_template', lambda *args, **kwargs: 'Recovery form')
    monkeypatch.setattr(passwords, 'lookup_user_for_reset', lambda username, email: (11, 7, None))
    def lookup_phone(user_id):
        assert user_id == 7
        return None if outcome == 'missing_phone' else {'contact_id': 12, 'contact_value': '+639171234567'}
    monkeypatch.setattr(passwords, 'lookup_phone_for_reset', lookup_phone)
    def create_otp(contact_id, destination):
        assert contact_id == 12
        assert destination == '+639171234567'
        return '004201', 9
    monkeypatch.setattr(passwords, 'create_otp', create_otp)
    def send(phone, code, expiry):
        calls.append((phone, code))
        if outcome == 'provider_failure':
            raise OSError('provider unavailable')
    monkeypatch.setattr(passwords, 'send_password_reset_sms', send)
    if outcome == 'unconfigured':
        sms_app.config['SEMAPHORE_API_KEY'] = ''
    client = sms_app.test_client()
    response = client.post('/forgot_password', data={
        'username': 'student', 'email': 'student@example.com',
        'delivery_channel': 'sms', 'phone': '+639999999999',
    })
    assert response.status_code == (302 if outcome == 'accepted' else 200)
    assert calls == ([('+639171234567', '004201')] if outcome in ('accepted', 'provider_failure') else [])
    with client.session_transaction() as state:
        assert ('reset_id' in state) == (outcome == 'accepted')
