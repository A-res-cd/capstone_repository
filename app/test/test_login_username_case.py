"""Login casing regressions against an isolated PostgreSQL database."""
from datetime import datetime, timedelta, timezone
from importlib import import_module

import pytest
from flask import Flask
from werkzeug.security import generate_password_hash

from app.db import auth
from app.test.test_author_account_links import author_db, author_postgres


def add_credentials(connect, user_id, username, password='CorrectPassword1!'):
    with connect() as conn, conn.cursor() as cursor:
        cursor.execute('INSERT INTO kappa (username) VALUES (%s) RETURNING username_id', (username,))
        username_id = cursor.fetchone()[0]
        cursor.execute('INSERT INTO ror (password) VALUES (%s) RETURNING password_id',
                       (generate_password_hash(password),))
        password_id = cursor.fetchone()[0]
        cursor.execute('INSERT INTO slug (username_id, password_id, user_id, is_current) VALUES (%s, %s, %s, TRUE)',
                       (username_id, password_id, user_id))
    conn.close()


@pytest.fixture
def login_db(author_db, monkeypatch):
    monkeypatch.setattr(auth, 'db_connect', author_db)
    add_credentials(author_db, 1, 'Maria_Cruz')
    return author_db


@pytest.mark.parametrize('username', ['Maria_Cruz', 'maria_cruz', 'MARIA_CRUZ', 'mArIa_CrUz', '  maria_cruz  '])
def test_login_ignores_username_case_and_preserves_display_name(login_db, username):
    user, error = auth.sign_in(username, 'CorrectPassword1!')
    assert error is None
    assert user['user_id'] == 1
    assert user['username'] == 'Maria_Cruz'


def test_password_case_and_shared_lockout_are_unchanged(login_db):
    for username in ['maria_cruz', 'MARIA_CRUZ', 'Maria_Cruz', 'mArIa_CrUz']:
        user, error = auth.sign_in(username, 'correctpassword1!')
        assert user is None and error == 'Invalid username or password.'
    user, error = auth.sign_in('MARIA_CRUZ', 'incorrect')
    assert user is None and 'locked' in error.lower()
    user, error = auth.sign_in('maria_cruz', 'CorrectPassword1!')
    assert user is None and 'locked' in error.lower()


def test_pending_accounts_remain_blocked_and_unknown_names_stay_generic(login_db):
    with login_db() as conn, conn.cursor() as cursor:
        cursor.execute('UPDATE "user" SET account_status = %s WHERE user_id = 1', ('pending',))
    conn.close()
    user, error = auth.sign_in('MARIA_CRUZ', 'CorrectPassword1!')
    assert user is None and 'waiting for verification' in error
    assert auth.sign_in('unknown', 'CorrectPassword1!') == (None, 'Invalid username or password.')


def test_case_only_duplicate_accounts_are_not_confused(login_db):
    add_credentials(login_db, 2, 'maria_cruz', 'AnotherPassword2!')
    assert auth.sign_in('MARIA_CRUZ', 'CorrectPassword1!') == (None, 'Invalid username or password.')
    user, error = auth.sign_in('Maria_Cruz', 'CorrectPassword1!')
    assert error is None and user['user_id'] == 1
    user, error = auth.sign_in('maria_cruz', 'AnotherPassword2!')
    assert error is None and user['user_id'] == 2
    assert auth.sign_in('maria_cruz', 'CorrectPassword1!') == (None, 'Invalid username or password.')


def test_signin_route_session_and_lockout_timer_use_case_insensitive_name(login_db, monkeypatch):
    routes = import_module('app.routes.authentication')
    app = Flask(__name__)
    app.config.update(SECRET_KEY='login-case-test', WTF_CSRF_ENABLED=False)
    app.register_blueprint(routes.auth)
    app.add_url_rule('/archive', endpoint='pages.browse', view_func=lambda: 'Archive')
    monkeypatch.setattr(routes, 'db_connect', login_db)
    monkeypatch.setattr(routes, 'render_template', lambda template, **context: context.get('locked_until') or 'missing timer')
    client = app.test_client()
    response = client.post('/signin', data={'username': 'MARIA_CRUZ', 'password': 'CorrectPassword1!'})
    assert response.status_code == 302 and response.location.endswith('/archive')
    with client.session_transaction() as session:
        assert session['user_id'] == 1 and session['username'] == 'Maria_Cruz'
        session.clear()
    locked_until = datetime.now(timezone.utc) + timedelta(minutes=10)
    with login_db() as conn, conn.cursor() as cursor:
        cursor.execute('UPDATE "user" SET locked_until = %s WHERE user_id = 1 RETURNING locked_until', (locked_until,))
        stored_deadline = cursor.fetchone()[0]
    conn.close()
    response = client.post('/signin', data={'username': '  mArIa_CrUz  ', 'password': 'CorrectPassword1!'})
    assert response.status_code == 200
    assert response.get_data(as_text=True) == stored_deadline.isoformat()
    with client.session_transaction() as session:
        assert 'user_id' not in session
