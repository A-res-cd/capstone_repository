from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from flask import Flask, session
from flask_wtf.csrf import CSRFProtect
from playwright.sync_api import expect

from app.db import auth as auth_db
from app.routes.authentication import auth, registration
from app.routes.decorators import login_required
from app.utils import auth_rate_limit, auth_utils
from tests.test_original_branch_features import feature_app, feature_db, isolated_database, pdf_bytes

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = 'Secure123'
NEW_PASSWORD = 'NewSecure123'


def account(connect, username='student'):
    assert auth_db.create_user('Test', '', 'Student', None, username + '@example.com', username, PASSWORD)[0]
    with connect() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT user_id, contact_id FROM contact WHERE contact_value = %s", (username + '@example.com',))
        user_id, contact_id = cursor.fetchone()
        cursor.execute('UPDATE "user" SET account_status = \'active\' WHERE user_id = %s', (user_id,))
        conn.commit()
    return user_id, contact_id


@pytest.mark.parametrize('invalid', ['unverified', 'expired', 'used', 'wrong_owner'])
def test_reset_rechecks_database_state(feature_db, invalid):
    user_id, contact_id = account(feature_db)
    otp, reset_id = auth_db.create_otp(contact_id)
    if invalid != 'unverified':
        assert auth_db.verify_otp(reset_id, otp)[0]
    target_id = account(feature_db, 'other')[0] if invalid == 'wrong_owner' else user_id
    with feature_db() as conn, conn.cursor() as cursor:
        if invalid == 'expired':
            cursor.execute("UPDATE password_reset SET expiry_date = CURRENT_TIMESTAMP - INTERVAL '1 minute'")
        elif invalid == 'used':
            cursor.execute('UPDATE password_reset SET is_used = TRUE')
        conn.commit()
    assert not auth_db.change_password(reset_id, target_id, NEW_PASSWORD)[0]
    assert auth_db.sign_in('student', PASSWORD)[0]


def test_concurrent_reset_is_single_use(feature_db):
    user_id, contact_id = account(feature_db)
    otp, reset_id = auth_db.create_otp(contact_id)
    assert auth_db.verify_otp(reset_id, otp)[0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: auth_db.change_password(reset_id, user_id, NEW_PASSWORD), range(2)))
    assert sum(success for success, _ in results) == 1
    assert not auth_db.change_password(reset_id, user_id, PASSWORD)[0]
    assert auth_db.sign_in('student', NEW_PASSWORD)[0]
    with feature_db() as conn, conn.cursor() as cursor:
        cursor.execute('SELECT COUNT(*) FROM slug WHERE user_id = %s AND is_current = TRUE', (user_id,))
        assert cursor.fetchone()[0] == 1


def test_verified_cookie_replay_cannot_reset_again(feature_app, feature_db):
    user_id, contact_id = account(feature_db)
    otp, reset_id = auth_db.create_otp(contact_id)
    client = feature_app.test_client()
    with client.session_transaction() as state:
        state.update(reset_id=reset_id, reset_user_id=user_id)
    assert client.post('/verify_otp', data={'otp': otp}).status_code == 302
    saved_cookie = client.get_cookie('session').value
    data = dict(new_password=NEW_PASSWORD, confirm_password=NEW_PASSWORD)
    assert client.post('/reset_password', data=data).status_code == 302
    client.set_cookie('session', saved_cookie)
    assert client.post('/reset_password', data=dict(new_password=PASSWORD, confirm_password=PASSWORD)).status_code == 200
    assert auth_db.sign_in('student', NEW_PASSWORD)[0]


def test_current_password_is_checked_atomically(feature_db):
    user_id, _ = account(feature_db)
    assert not auth_db.change_password(None, user_id, NEW_PASSWORD)[0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: auth_db.change_own_password(user_id, PASSWORD, NEW_PASSWORD), range(2)))
    assert sum(success for success, _ in results) == 1


def test_concurrent_otp_attempts_are_bounded(feature_db):
    _, contact_id = account(feature_db)
    otp, reset_id = auth_db.create_otp(contact_id)
    wrong = '000000' if otp != '000000' else '111111'
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: auth_db.verify_otp(reset_id, wrong), range(4)))
    assert not any(success for success, _ in results)
    with feature_db() as conn, conn.cursor() as cursor:
        cursor.execute('SELECT attempt_count FROM password_reset WHERE reset_id = %s', (reset_id,))
        assert cursor.fetchone()[0] == auth_db.OTP_MAX_ATTEMPTS


def test_bad_guesses_do_not_lock_victim(feature_db):
    account(feature_db)
    for _ in range(6):
        assert auth_db.sign_in('student', 'wrong')[1] == 'Invalid username or password.'
    assert auth_db.sign_in('missing', 'wrong')[1] == 'Invalid username or password.'
    assert auth_db.sign_in('student', PASSWORD)[0]


def test_sessions_revoke_after_password_change_or_status_change(feature_db, monkeypatch):
    user_id, contact_id = account(feature_db)
    monkeypatch.setattr(auth_utils, 'db_connect', feature_db)
    app = Flask(__name__, template_folder=str(ROOT / 'app/templates'), static_folder=str(ROOT / 'app/static'))
    app.config.update(SECRET_KEY='auth-test', WTF_CSRF_ENABLED=False, AUTH_RATE_LIMIT_ENABLED=False)
    CSRFProtect(app)
    app.register_blueprint(auth)
    app.add_url_rule('/', endpoint='main.home', view_func=lambda: 'Home')
    app.add_url_rule('/browse', endpoint='pages.all_requests', view_func=lambda: 'Browse')
    app.before_request(auth_utils.load_current_user)

    @app.route('/protected')
    @login_required
    def protected():
        return 'Private'

    client = app.test_client()
    with client.session_transaction() as state:
        state['otp_verified'] = True
    assert client.post('/signin', data=dict(username='student', password=PASSWORD)).status_code == 302
    with client.session_transaction() as state:
        assert 'otp_verified' not in state and state['password_id']
    assert client.get('/protected').status_code == 200
    otp, reset_id = auth_db.create_otp(contact_id)
    assert auth_db.verify_otp(reset_id, otp)[0]
    assert auth_db.change_password(reset_id, user_id, NEW_PASSWORD)[0]
    assert client.get('/protected').status_code == 302
    assert client.post('/signin', data=dict(username='student', password=NEW_PASSWORD)).status_code == 302
    with feature_db() as conn, conn.cursor() as cursor:
        cursor.execute('UPDATE "user" SET account_status = \'rejected\' WHERE user_id = %s', (user_id,))
        conn.commit()
    assert client.get('/protected').status_code == 302


def test_throttle_shared_atomic_and_expiring(feature_db, monkeypatch):
    monkeypatch.setattr(auth_rate_limit, 'db_connect', feature_db)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: auth_rate_limit.consume_limit('auth.signin', '127.0.0.1', 10, 60), range(11)))
    assert sum(result is None for result in results) == 10
    assert auth_rate_limit.consume_limit('auth.signin', '127.0.0.2', 10, 60) is None
    with feature_db() as conn, conn.cursor() as cursor:
        cursor.execute("UPDATE auth_rate_limit SET window_start = CURRENT_TIMESTAMP - INTERVAL '2 minutes'")
        conn.commit()
    assert auth_rate_limit.consume_limit('auth.signin', '127.0.0.1', 10, 60) is None


def test_forwarded_header_cannot_bypass_throttle(feature_app, feature_db, monkeypatch):
    monkeypatch.setattr(auth_rate_limit, 'db_connect', feature_db)
    feature_app.config['AUTH_RATE_LIMIT_ENABLED'] = True
    client = feature_app.test_client()
    for i in range(10):
        response = client.post('/signin', data=dict(username='missing', password=PASSWORD),
                               headers={'X-Forwarded-For': f'10.0.0.{i}'})
        assert response.status_code == 200
    response = client.post('/signin', data=dict(username='missing', password=PASSWORD),
                           headers={'X-Forwarded-For': '10.0.0.99'})
    assert response.status_code == 429 and int(response.headers['Retry-After']) > 0
    assert b'account has not been locked' in response.data


def test_extraction_throttle_is_json_and_storage_failure_is_closed(feature_app, monkeypatch):
    feature_app.config['AUTH_RATE_LIMIT_ENABLED'] = True
    monkeypatch.setattr(auth_rate_limit, 'consume_limit', lambda *args: 30)
    response = feature_app.test_client().post('/signup/extract-cor')
    assert response.status_code == 429 and response.json['error']
    assert response.headers['Retry-After'] == '30'

    def unavailable(*args):
        raise RuntimeError('database unavailable')

    monkeypatch.setattr(auth_rate_limit, 'consume_limit', unavailable)
    response = feature_app.test_client().post('/signin', data=dict(username='student', password=PASSWORD))
    assert response.status_code == 503 and b'database unavailable' not in response.data


def test_logout_requires_post_and_csrf(feature_app):
    client = feature_app.test_client()
    with client.session_transaction() as state:
        state['user_id'] = 1
    assert client.get('/logout').status_code == 405
    with client.session_transaction() as state:
        assert state['user_id'] == 1
    feature_app.config['WTF_CSRF_ENABLED'] = True
    assert client.post('/logout').status_code == 400
    with client.session_transaction() as state:
        state['csrf_token'] = 'test-token'
        state.pop('user_id')
    from flask_wtf.csrf import generate_csrf
    with feature_app.test_request_context():
        session['csrf_token'] = 'test-token'
        token = generate_csrf()
    assert client.post('/logout', data={'csrf_token': token}).status_code == 302


def test_signup_without_javascript(feature_app, browser, monkeypatch):
    client = feature_app.test_client()
    captured = []
    monkeypatch.setattr(registration, 'create_user', lambda *args, **kwargs: (captured.append((args, kwargs)) or True, {}))

    def handle(route):
        url = urlsplit(route.request.url)
        if url.netloc != 'offline.test':
            route.abort()
            return
        response = client.open(url.path, method=route.request.method, data=route.request.post_data_buffer,
                               content_type=route.request.headers.get('content-type'))
        route.fulfill(status=response.status_code, body=response.data, headers=dict(response.headers))

    with browser.new_context(java_script_enabled=False) as context:
        page = context.new_page()
        page.route('**/*', handle)
        page.goto('http://offline.test/signup')
        expect(page.locator('[data-signup-step]:visible')).to_have_count(4)
        expect(page.locator('#terms-modal')).to_be_visible()
        page.locator('#cor').set_input_files(dict(name='cor.pdf', mimeType='application/pdf', buffer=pdf_bytes()))
        for name, value in dict(first_name='Test', last_name='Student', username='student',
                                password=NEW_PASSWORD, confirm_password=NEW_PASSWORD,
                                email='student@example.com').items():
            page.locator('#' + name).fill(value)
        page.locator('#preferred_contact').select_option('email')
        page.locator('#accept_terms').check()
        with page.expect_response(lambda r: r.url.endswith('/signup') and r.request.method == 'POST') as response:
            page.locator('#signup-submit').click()
        assert response.value.status == 302 and len(captured) == 1
