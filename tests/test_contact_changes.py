from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from app.db import auth as auth_db, contact_changes
from app.routes.pages import profile
from app.utils import auth_rate_limit
from tests.test_auth_security import account, PASSWORD, NEW_PASSWORD
from tests.test_original_branch_features import feature_app, feature_db, isolated_database


@pytest.fixture
def contact_db(feature_db, monkeypatch):
    monkeypatch.setattr(contact_changes, 'db_connect', feature_db)
    monkeypatch.setattr(auth_rate_limit, 'db_connect', feature_db)
    return feature_db


def pending(connect, user_id, kind='email'):
    values = {'email': 'replacement@example.com' if kind == 'email' else 'student@example.com',
              'phone': '+639171234567' if kind == 'phone' else ''}
    result = contact_changes.request_change(user_id, PASSWORD, 'session-a', values, kind)
    contact_changes.finish_delivery(user_id, result[0], True)
    return result


@pytest.mark.parametrize('password', [None, '', 'Wrong123', 'x' * 1025])
def test_session_alone_cannot_request(contact_db, password):
    user_id, _ = account(contact_db)
    with pytest.raises(ValueError, match='password'):
        contact_changes.request_change(user_id, password, 'session-a', {'email': 'replacement@example.com', 'phone': ''}, 'email')
    with contact_db() as conn, conn.cursor() as cursor:
        cursor.execute('SELECT count(*) FROM contact_changes')
        assert cursor.fetchone()[0] == 0


def test_pending_has_no_reset_authority(contact_db):
    user_id, _ = account(contact_db)
    pending(contact_db, user_id)
    assert auth_db.lookup_user_for_reset('student', 'replacement@example.com')[0] is None
    assert auth_db.lookup_user_for_reset('student', 'student@example.com')[0] is not None
    with contact_db() as conn, conn.cursor() as cursor:
        cursor.execute('SELECT verified_at FROM contact WHERE user_id = %s', (user_id,))
        assert cursor.fetchone()[0] is None


def test_contact_route_requires_password_and_csrf(feature_app, contact_db):
    user_id, _ = account(contact_db)
    client = feature_app.test_client()
    with client.session_transaction() as state:
        state['user_id'] = user_id
    data = {'email': 'replacement@example.com', 'phone': '', 'preferred_contact': 'email'}
    assert client.post('/user-info/contact', data=data).status_code == 302
    with contact_db() as conn, conn.cursor() as cursor:
        cursor.execute('SELECT count(*) FROM contact_changes')
        assert cursor.fetchone()[0] == 0
    feature_app.config['WTF_CSRF_ENABLED'] = True
    data['current_password'] = PASSWORD
    assert client.post('/user-info/contact', data=data).status_code == 400


def test_resend_is_limited_by_account_and_ip(contact_db):
    for _ in range(5):
        assert auth_rate_limit.consume_limit('profile-contact:user', 'account', 5, 600) is None
    assert auth_rate_limit.consume_limit('profile-contact:user', 'account', 5, 600)
    for _ in range(30):
        assert auth_rate_limit.consume_limit('profile-contact:ip', '127.0.0.1', 30, 600) is None
    assert auth_rate_limit.consume_limit('profile-contact:ip', '127.0.0.1', 30, 600)


@pytest.mark.parametrize('invalid', ['wrong', 'expired', 'exhausted', 'account', 'session', 'replaced', 'reused', 'password', 'undelivered'])
def test_invalid_contact_proofs(contact_db, invalid):
    user_id, _ = account(contact_db)
    change_id, code, _, _ = pending(contact_db, user_id)
    binding, caller = 'session-a', user_id
    if invalid == 'wrong':
        code = 'invalid'
    elif invalid == 'account':
        caller, _ = account(contact_db, 'other')
    elif invalid == 'session':
        binding = 'session-b'
    elif invalid == 'replaced':
        pending(contact_db, user_id)
    elif invalid == 'reused':
        contact_changes.confirm_change(user_id, change_id, binding, code)
    elif invalid == 'password':
        assert auth_db.change_own_password(user_id, PASSWORD, NEW_PASSWORD)[0]
    else:
        sql = {'expired': "expires_at = CURRENT_TIMESTAMP - INTERVAL '1 second'",
               'exhausted': 'attempt_count = 5', 'undelivered': 'delivered_at = NULL'}[invalid]
        with contact_db() as conn, conn.cursor() as cursor:
            cursor.execute('UPDATE contact_changes SET ' + sql + ' WHERE change_id = %s', (change_id,))
            conn.commit()
    with pytest.raises(ValueError):
        contact_changes.confirm_change(caller, change_id, binding, code)


def test_concurrent_confirmation_and_reset_revocation(contact_db):
    user_id, contact_id = account(contact_db)
    otp, reset_id = auth_db.create_otp(contact_id)
    assert auth_db.verify_otp(reset_id, otp)[0]
    change_id, code, _, _ = pending(contact_db, user_id)
    def confirm():
        try:
            contact_changes.confirm_change(user_id, change_id, 'session-a', code)
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: confirm(), range(2))) == [False, True]
    assert not auth_db.change_password(reset_id, user_id, NEW_PASSWORD)[0]
    with pytest.raises(RuntimeError):
        auth_db.create_otp(contact_id, 'student@example.com')
    with contact_db() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT contact_value, verified_at IS NOT NULL FROM contact WHERE contact_id = %s", (contact_id,))
        assert cursor.fetchone() == ('replacement@example.com', True)


def test_concurrent_wrong_codes_exhaust_proof(contact_db):
    user_id, _ = account(contact_db)
    change_id, code, _, _ = pending(contact_db, user_id)
    def wrong(_):
        with pytest.raises(ValueError):
            contact_changes.confirm_change(user_id, change_id, 'session-a', 'wrong!')
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(wrong, range(6)))
    with pytest.raises(ValueError):
        contact_changes.confirm_change(user_id, change_id, 'session-a', code)


@pytest.mark.parametrize('kind', ['email', 'phone'])
@pytest.mark.parametrize('role_id', [1, 2, 3, 4])
def test_all_roles_can_verify_contacts(contact_db, kind, role_id):
    user_id, _ = account(contact_db)
    with contact_db() as conn, conn.cursor() as cursor:
        cursor.execute('UPDATE "user" SET role_id = %s WHERE user_id = %s', (role_id, user_id))
        conn.commit()
    change_id, code, _, _ = pending(contact_db, user_id, kind)
    assert contact_changes.confirm_change(user_id, change_id, 'session-a', code)[0] == kind


def test_delivery_failure_preserves_contact(feature_app, contact_db, monkeypatch):
    user_id, contact_id = account(contact_db)
    def fail(message):
        raise OSError('provider failure')
    monkeypatch.setattr(profile, 'mail', SimpleNamespace(send=fail))
    client = feature_app.test_client()
    with client.session_transaction() as state:
        state['user_id'] = user_id
    response = client.post('/user-info/contact', data={'email': 'replacement@example.com', 'phone': '',
                           'preferred_contact': 'email', 'current_password': PASSWORD})
    assert response.status_code == 302
    with contact_db() as conn, conn.cursor() as cursor:
        cursor.execute('SELECT contact_value FROM contact WHERE contact_id = %s', (contact_id,))
        assert cursor.fetchone()[0] == 'student@example.com'
        cursor.execute('SELECT consumed_at IS NOT NULL FROM contact_changes')
        assert cursor.fetchone()[0]


def test_notification_failure_keeps_confirmed_change(feature_app, contact_db, monkeypatch):
    user_id, contact_id = account(contact_db)
    change_id, code, _, _ = pending(contact_db, user_id)
    def fail(message):
        raise OSError('provider failure')
    monkeypatch.setattr(profile, 'mail', SimpleNamespace(send=fail))
    client = feature_app.test_client()
    with client.session_transaction() as state:
        state.update(user_id=user_id, contact_change_id=change_id, contact_change_binding='session-a')
    assert client.post('/user-info/contact/confirm', data={'code': code}).status_code == 302
    with contact_db() as conn, conn.cursor() as cursor:
        cursor.execute('SELECT contact_value FROM contact WHERE contact_id = %s', (contact_id,))
        assert cursor.fetchone()[0] == 'replacement@example.com'
        cursor.execute("SELECT count(*) FROM audit WHERE action_type = 'contact_change_notification_failed'")
        assert cursor.fetchone()[0] == 1


def test_cannot_remove_last_recovery_channel(contact_db):
    user_id, _ = account(contact_db)
    with pytest.raises(ValueError):
        contact_changes.request_change(user_id, PASSWORD, 'session-a', {'email': '', 'phone': ''}, 'email')
