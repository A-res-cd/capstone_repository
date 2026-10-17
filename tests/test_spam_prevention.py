from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import re
import time
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from flask import Flask
from flask_mail import Mail
from playwright.sync_api import expect

from app.db import auth as auth_db, signup_verification as verification
from app.db import requests as request_db
from app.routes.authentication import registration
from app.utils import auth_rate_limit
from tests.test_original_branch_features import feature_app, feature_db, isolated_database, signup_data
from tests.test_most_requested_capstones import ranking_db, seed
from tests.test_manuscript_reader import reader_app

REAL_FORM_READY = registration.signup_form_ready


@pytest.fixture
def verification_db(feature_db, monkeypatch):
    monkeypatch.setattr(verification, 'db_connect', feature_db)
    return feature_db


def test_code_owner_attempt_cap_and_expiry(verification_db):
    proof, code = verification.create_email_code(' Reader@Example.com ')
    assert not verification.verify_email_code(proof, 'other@example.com', code)
    wrong = '000000' if code != '000000' else '111111'
    with ThreadPoolExecutor(max_workers=3) as pool:
        assert not any(pool.map(lambda _: verification.verify_email_code(proof, 'reader@example.com', wrong), range(6)))
    assert not verification.verify_email_code(proof, 'reader@example.com', code)
    with closing(verification_db()) as conn, conn.cursor() as cursor:
        cursor.execute('SELECT attempts FROM signup_email_verifications WHERE verification_id = %s', (proof,))
        assert cursor.fetchone()[0] == 5
    proof, code = verification.create_email_code('reader@example.com', proof)
    assert verification.verify_email_code(proof, 'reader@example.com', code)
    assert verification.signup_email_is_verified(proof, 'reader@example.com')
    with closing(verification_db()) as conn, conn.cursor() as cursor:
        cursor.execute("UPDATE signup_email_verifications SET expires_at = CURRENT_TIMESTAMP - INTERVAL '1 second'")
        conn.commit()
    assert not verification.signup_email_is_verified(proof, 'reader@example.com')
    assert not verification.verify_email_code(proof, 'reader@example.com', code)


def test_replacement_and_atomic_account_consumption(verification_db):
    old, old_code = verification.create_email_code('reader@example.com')
    proof, code = verification.create_email_code('reader@example.com', old)
    assert not verification.verify_email_code(old, 'reader@example.com', old_code)
    assert verification.verify_email_code(proof, 'reader@example.com', code)

    def create(username):
        return auth_db.create_user('Test', '', 'Reader', None, 'reader@example.com', username,
                                   'Secure123', signup_verification_id=proof)[0]

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(create, ('reader_one', 'reader_two'))) == 1
    assert not verification.signup_email_is_verified(proof, 'reader@example.com')
    assert not create('reader_three')


def test_other_session_cannot_invalidate_email_proof_or_create_duplicate_account(verification_db):
    proof, code = verification.create_email_code('reader@example.com')
    assert verification.verify_email_code(proof, 'reader@example.com', code)
    other_proof, other_code = verification.create_email_code('reader@example.com')
    assert verification.signup_email_is_verified(proof, 'reader@example.com')
    assert verification.verify_email_code(other_proof, 'reader@example.com', other_code)
    assert auth_db.create_user('Test', '', 'Reader', None, 'reader@example.com', 'first_reader',
                               'Secure123', signup_verification_id=proof)[0]
    assert not auth_db.create_user('Test', '', 'Reader', None, 'READER@example.com', 'second_reader',
                                   'Secure123', signup_verification_id=other_proof)[0]


def test_failed_account_creation_preserves_proof(verification_db):
    assert auth_db.create_user('Test', '', 'Reader', None, 'first@example.com', 'reader', 'Secure123')[0]
    proof, code = verification.create_email_code('second@example.com')
    assert verification.verify_email_code(proof, 'second@example.com', code)
    assert not auth_db.create_user('Test', '', 'Reader', None, 'second@example.com', 'reader',
                                    'Secure123', signup_verification_id=proof)[0]
    assert verification.signup_email_is_verified(proof, 'second@example.com')


@pytest.mark.parametrize('age,website', [(None, ''), (0, ''), (3601, ''), (5, 'spam')])
def test_signup_bot_guard_blocks_before_upload(feature_app, monkeypatch, age, website):
    monkeypatch.setattr(registration, 'signup_form_ready', REAL_FORM_READY)
    monkeypatch.setattr(registration, 'save_cor_document', lambda *args: pytest.fail('Must block before saving uploads'))
    client = feature_app.test_client()
    if age is not None:
        with client.session_transaction() as state:
            state['signup_started_at'] = time.time() - age
    data = signup_data()
    data['website'] = website
    assert client.post('/signup', data=data).status_code == 400


def test_unverified_signup_does_not_save_upload(feature_app, verification_db, monkeypatch):
    monkeypatch.setattr(registration, 'signup_email_is_verified', verification.signup_email_is_verified)
    monkeypatch.setattr(registration, 'save_cor_document', lambda *args: pytest.fail('Must verify before saving'))
    response = feature_app.test_client().post('/signup', data=signup_data())
    assert b'Verify this email before creating' in response.data
    with closing(verification_db()) as conn, conn.cursor() as cursor:
        cursor.execute('SELECT COUNT(*) FROM "user"')
        assert cursor.fetchone()[0] == 0


def test_email_signup_flow_without_javascript(feature_app, verification_db, monkeypatch):
    feature_app.config['MAIL_DEFAULT_SENDER'] = 'noreply@example.com'
    Mail(feature_app)
    sent = []
    monkeypatch.setattr(registration, 'mail', SimpleNamespace(send=sent.append))
    monkeypatch.setattr(registration, 'signup_form_ready', REAL_FORM_READY)
    monkeypatch.setattr(registration, 'signup_email_is_verified', verification.signup_email_is_verified)
    client = feature_app.test_client()
    assert client.get('/signup').status_code == 200
    response = client.post('/signup/verify-email', data={'email': 'maria@example.com', 'action': 'send'})
    assert b'Code sent' in response.data and len(sent) == 1
    code = re.search(r'\b[0-9]{6}\b', sent[0].body).group()
    response = client.post('/signup/verify-email', data={'email': 'maria@example.com', 'action': 'verify', 'code': code})
    assert b'Email verified' in response.data
    with client.session_transaction() as state:
        proof = state['signup_email_verification_id']
        state['signup_started_at'] = time.time() - 5
    assert client.post('/signup', data=signup_data()).status_code == 302
    assert not verification.signup_email_is_verified(proof, 'maria@example.com')
    with closing(verification_db()) as conn, conn.cursor() as cursor:
        cursor.execute('SELECT account_status FROM "user"')
        assert cursor.fetchone()[0] == 'pending'


def test_email_delivery_failure_and_csrf(feature_app, verification_db, monkeypatch):
    feature_app.config['MAIL_DEFAULT_SENDER'] = 'noreply@example.com'
    Mail(feature_app)

    def failed(message):
        raise OSError('SMTP unavailable')

    monkeypatch.setattr(registration, 'mail', SimpleNamespace(send=failed))
    client = feature_app.test_client()
    response = client.post('/signup/verify-email', data={'email': 'reader@example.com', 'action': 'send'})
    assert b'Could not send' in response.data
    with client.session_transaction() as state:
        assert 'signup_email_verification_id' not in state
    feature_app.config['WTF_CSRF_ENABLED'] = True
    assert client.post('/signup/verify-email', data={'email': 'reader@example.com', 'action': 'send'}).status_code == 400


def test_recipient_and_global_limits_survive_ip_changes(feature_app, verification_db, monkeypatch):
    feature_app.config['AUTH_RATE_LIMIT_ENABLED'] = True
    monkeypatch.setattr(auth_rate_limit, 'db_connect', verification_db)
    monkeypatch.setattr(registration, 'create_email_code', lambda email, previous_id=None: ('proof', '123456'))
    feature_app.config['MAIL_DEFAULT_SENDER'] = 'noreply@example.com'
    Mail(feature_app)
    sent = []
    monkeypatch.setattr(registration, 'mail', SimpleNamespace(send=sent.append))
    client = feature_app.test_client()
    for index in range(4):
        response = client.post('/signup/verify-email', data={'email': 'reader@example.com', 'action': 'send'},
                               environ_overrides={'REMOTE_ADDR': f'10.0.0.{index}'}, headers={'Accept': 'application/json'})
        assert response.status_code == (200 if index < 3 else 429)
    assert len(sent) == 3 and int(response.headers['Retry-After']) > 0
    assert client.post('/forgot_password', data={'username': 'reader', 'email': 'reader@example.com'},
                       environ_overrides={'REMOTE_ADDR': '10.2.0.1'},
                       headers={'Accept': 'application/json'}).status_code == 429
    # A new recipient must still obey the shared application ceiling.
    monkeypatch.setitem(auth_rate_limit.GLOBAL_LIMITS, 'auth.verify_signup_email', (4, 3600))
    response = client.post('/signup/verify-email', data={'email': 'other@example.com', 'action': 'send'},
                           environ_overrides={'REMOTE_ADDR': '10.1.0.1'}, headers={'Accept': 'application/json'})
    assert response.status_code == 429 and len(sent) == 3


@pytest.mark.parametrize('endpoint,method,limit', [
    ('pages.topic_similarity', 'POST', 10), ('pages.update_picture', 'POST', 3),
    ('pages.request_manuscript', 'POST', 5), ('pages.browse', 'GET', 120),
    ('pages.cite_capstone', 'GET', 30),
])
def test_user_action_limits_survive_ip_changes(feature_db, monkeypatch, endpoint, method, limit):
    monkeypatch.setattr(auth_rate_limit, 'db_connect', feature_db)
    app = Flask(__name__)
    app.secret_key = 'test-actions'
    app.before_request(auth_rate_limit.throttle_actions)
    app.add_url_rule('/action', endpoint=endpoint, view_func=lambda: 'Allowed', methods=[method])
    app.add_url_rule('/cancel', endpoint='pages.cancel_request', view_func=lambda: 'Allowed', methods=['POST'])
    client = app.test_client()
    with client.session_transaction() as state:
        state['user_id'] = 1
    for index in range(limit + 1):
        response = client.open('/action', method=method, environ_overrides={'REMOTE_ADDR': f'10.0.0.{index}'},
                               headers={'Accept': 'application/json'})
        assert response.status_code == (200 if index < limit else 429)
    assert int(response.headers['Retry-After']) > 0
    if endpoint == 'pages.request_manuscript':
        assert client.post('/cancel', headers={'Accept': 'application/json'}).status_code == 429
    with client.session_transaction() as state:
        state['user_id'] = 2
    assert client.open('/action', method=method).status_code == 200


def test_signin_username_quota_survives_ip_changes(feature_db, monkeypatch):
    monkeypatch.setattr(auth_rate_limit, 'db_connect', feature_db)
    app = Flask(__name__)
    app.before_request(auth_rate_limit.throttle_auth)
    app.add_url_rule('/signin', endpoint='auth.signin', view_func=lambda: 'Allowed', methods=['POST'])
    client = app.test_client()
    for index in range(31):
        response = client.post('/signin', data={'username': 'Reader'},
                               environ_overrides={'REMOTE_ADDR': f'10.0.0.{index}'},
                               headers={'Accept': 'application/json'})
        assert response.status_code == (200 if index < 30 else 429)


def test_manuscript_hourly_quota_survives_minute_reset(feature_db, monkeypatch):
    monkeypatch.setattr(auth_rate_limit, 'db_connect', feature_db)
    app = Flask(__name__)
    app.secret_key = 'test-actions'
    app.before_request(auth_rate_limit.throttle_actions)
    app.add_url_rule('/action', endpoint='pages.request_manuscript', view_func=lambda: 'Allowed', methods=['POST'])
    client = app.test_client()
    with client.session_transaction() as state:
        state['user_id'] = 1
    for batch in range(2):
        for _ in range(5):
            assert client.post('/action').status_code == 200
        with closing(feature_db()) as conn, conn.cursor() as cursor:
            cursor.execute("UPDATE auth_rate_limit SET window_start = window_start - INTERVAL '61 seconds'")
            conn.commit()
    assert client.post('/action', headers={'Accept': 'application/json'}).status_code == 429


def test_cancelled_manuscript_cooldown_and_expiry(ranking_db):
    user, (capstone, _, _) = seed(ranking_db)
    assert request_db.request_fullview(user, capstone, 'Research')[0]
    with closing(ranking_db()) as conn, conn.cursor() as cursor:
        cursor.execute("UPDATE request SET request_status = 'cancelled'")
        conn.commit()
    accepted, message = request_db.request_fullview(user, capstone, 'Research')
    assert not accepted and '15 minutes' in message
    with closing(ranking_db()) as conn, conn.cursor() as cursor:
        cursor.execute("UPDATE request SET request_date = CURRENT_TIMESTAMP - INTERVAL '16 minutes'")
        conn.commit()
    assert request_db.request_fullview(user, capstone, 'Research')[0]


def test_schema_reference_and_repeatable_migration(feature_db):
    from tests.test_original_branch_features import ROOT
    with closing(feature_db()) as conn, conn.cursor() as cursor:
        cursor.execute((ROOT / 'migrations/20261011_signup_spam_prevention.sql').read_text())
        cursor.execute('CREATE SCHEMA reference_spam')
        cursor.execute('SET LOCAL search_path TO reference_spam')
        cursor.execute((ROOT / 'database/capre_original_final.sql').read_text())
        cursor.execute((ROOT / 'migrations/20261011_signup_spam_prevention.sql').read_text())
        cursor.execute('SELECT COUNT(*) FROM signup_email_verifications')
        assert cursor.fetchone()[0] == 0
        conn.rollback()


def test_application_hook_blocks_before_topic_processing(reader_app, monkeypatch):
    from app.routes.pages import topics
    reader_app.config['ACTION_RATE_LIMIT_ENABLED'] = True
    monkeypatch.setattr(auth_rate_limit, 'consume_limit', lambda *args: 30)
    monkeypatch.setattr(topics, 'get_capstones_corpus', lambda: pytest.fail('Blocked before expensive work'))
    client = reader_app.test_client()
    with client.session_transaction() as state:
        state['user_id'] = 1
    response = client.post('/api/topic-similarity', json={'title': 'Research topic'})
    assert response.status_code == 429 and response.headers['Retry-After'] == '30'


@pytest.mark.parametrize('width', [390, 1280])
def test_verification_page_without_javascript(feature_app, verification_db, monkeypatch, browser, width):
    feature_app.config['MAIL_DEFAULT_SENDER'] = 'noreply@example.com'
    Mail(feature_app)
    sent = []
    monkeypatch.setattr(registration, 'mail', SimpleNamespace(send=sent.append))
    client = feature_app.test_client()

    def handle(route):
        url = urlsplit(route.request.url)
        if url.netloc != 'verification.test':
            route.abort()
            return
        response = client.open(url.path, method=route.request.method, data=route.request.post_data_buffer,
                               content_type=route.request.headers.get('content-type'))
        route.fulfill(status=response.status_code, body=response.data, headers=dict(response.headers))

    with browser.new_context(java_script_enabled=False, viewport={'width': width, 'height': 900}) as context:
        page = context.new_page()
        page.route('**/*', handle)
        page.goto('http://verification.test/signup/verify-email')
        page.locator('#email').fill('reader@example.com')
        page.locator('#code').fill('bad')
        page.get_by_role('button', name='Send code', exact=True).click()
        expect(page.get_by_text('Code sent.', exact=False)).to_be_visible()
        code = re.search(r'\b[0-9]{6}\b', sent[0].body).group()
        page.locator('#code').fill(code)
        page.get_by_role('button', name='Verify email', exact=True).click()
        expect(page.get_by_text('Email verified.', exact=False)).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
