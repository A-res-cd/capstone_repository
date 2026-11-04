"""Revision checks use disposable databases in a locally started test cluster."""
from contextlib import closing
from pathlib import Path
import re
import shutil
from uuid import uuid4

import psycopg2
from psycopg2 import sql
import pytest
from flask import Flask, session
from flask_wtf.csrf import CSRFProtect, generate_csrf

from app.db import auth, migration_runner, users
from app.routes.authentication import auth as blueprint, sessions
from scripts import setup_supabase
from tests.test_original_branch_features import isolated_database


ROOT = Path(__file__).resolve().parents[1]
REVISION = '20261104_roster_signup_revision.sql'
PASSWORD = 'Secure123'


@pytest.fixture
def empty_database(isolated_database, monkeypatch):
    name = 'revision_' + uuid4().hex
    with closing(psycopg2.connect(**isolated_database)) as admin:
        admin.autocommit = True
        with admin.cursor() as cursor:
            cursor.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))

    def connect():
        return psycopg2.connect(**{**isolated_database, 'dbname': name})

    try:
        for module in (auth, users, migration_runner):
            monkeypatch.setattr(module, 'db_connect', connect)
        yield connect
    finally:
        with closing(psycopg2.connect(**isolated_database)) as admin:
            admin.autocommit = True
            with admin.cursor() as cursor:
                cursor.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))


@pytest.fixture
def revision_db(empty_database, tmp_path):
    connect = empty_database
    with closing(connect()) as conn, conn.cursor() as cursor:
        cursor.execute((ROOT / 'database/capre_original_final.sql').read_text(encoding='utf-8'))
        cursor.execute("INSERT INTO role (role_name, role_level) VALUES ('Student', 1), ('Faculty', 2), ('Admin', 3)")
        conn.commit()
    historical = tmp_path / 'historical'
    historical.mkdir()
    for path in migration_runner.migration_files():
        if path.name != REVISION:
            shutil.copyfile(path, historical / path.name)
    migration_runner.upgrade_database(historical)
    with closing(connect()) as conn, conn.cursor() as cursor:
        cursor.execute('''INSERT INTO "user" (user_first_name) VALUES ('Legacy') RETURNING user_id''')
        user_id = cursor.fetchone()[0]
        cursor.execute("INSERT INTO signup (user_id, registration_date) VALUES (%s, '2026-01-02 03:04:05')", (user_id,))
        cursor.execute("INSERT INTO logout (user_id, log_out_time, logout_device_ip) VALUES (%s, '2026-01-02 04:05:06', '192.0.2.10'), (NULL, NULL, NULL)", (user_id,))
        conn.commit()
    return connect


def upgrade():
    assert migration_runner.upgrade_database() == [REVISION]


def test_populated_migration_preserves_records_and_tracks_checksum(revision_db):
    with closing(revision_db()) as conn, conn.cursor() as cursor:
        cursor.execute('SELECT * FROM "user" ORDER BY user_id')
        original_users = cursor.fetchall()
        cursor.execute('SELECT signup_id, user_id, registration_date FROM signup')
        original_signups = cursor.fetchall()
        cursor.execute('SELECT row_to_json(legacy) FROM logout AS legacy ORDER BY log_out_id')
        original_logout = [row[0] for row in cursor.fetchall()]
    upgrade()
    assert migration_runner.upgrade_database() == []
    with closing(revision_db()) as conn, conn.cursor() as cursor:
        cursor.execute('SELECT * FROM "user" ORDER BY user_id')
        assert cursor.fetchall() == original_users
        cursor.execute('SELECT signup_id, user_id, registration_date FROM signup')
        assert cursor.fetchall() == original_signups
        cursor.execute('SELECT attempt_count, roster_id, contact_id, reviewed_by FROM signup')
        assert cursor.fetchone() == (0, None, None, None)
        cursor.execute("SELECT new_values::json, action_timestamp FROM audit WHERE action_type = 'logout' ORDER BY affected_record_id")
        archived = cursor.fetchall()
        assert [row[0] for row in archived] == original_logout
        assert archived[0][1].isoformat() == original_logout[0]['log_out_time']
        assert archived[1][1] is None
        cursor.execute("SELECT to_regclass('public.logout')")
        assert cursor.fetchone() == (None,)
        cursor.execute('SELECT checksum FROM schema_migration WHERE migration_name = %s', (REVISION,))
        assert cursor.fetchone()[0] == migration_runner.migration_checksum(ROOT / 'migrations' / REVISION)


def test_schema_matches_revised_definition(revision_db):
    upgrade()
    with closing(revision_db()) as conn, conn.cursor() as cursor:
        cursor.execute('CREATE SCHEMA reference')
        cursor.execute('SET LOCAL search_path TO reference')
        cursor.execute((ROOT / 'database/capre_revised_schema.sql').read_text(encoding='utf-8'))
        for table in ('uploaded_by', 'roster', 'signup'):
            shapes = []
            for schema in ('public', 'reference'):
                cursor.execute('''SELECT column_name, data_type, character_maximum_length,
                                         is_nullable, column_default
                                  FROM information_schema.columns
                                  WHERE table_schema = %s AND table_name = %s
                                  ORDER BY column_name''', (schema, table))
                columns = [(*row[:4], re.sub(r"nextval\(.*", 'serial', row[4] or ''))
                           for row in cursor.fetchall()]
                cursor.execute('''SELECT pg_get_constraintdef(c.oid)
                                  FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
                                  JOIN pg_namespace n ON n.oid = t.relnamespace
                                  WHERE n.nspname = %s AND t.relname = %s''', (schema, table))
                constraints = sorted(row[0].replace('public.', '').replace('reference.', '')
                                     for row in cursor.fetchall())
                cursor.execute('SELECT indexdef FROM pg_indexes WHERE schemaname = %s AND tablename = %s', (schema, table))
                indexes = sorted(row[0].split(' USING ', 1)[1] for row in cursor.fetchall())
                shapes.append((columns, constraints, indexes))
            assert shapes[0] == shapes[1], table


def test_constraints_and_duplicate_university_numbers(revision_db):
    upgrade()
    with closing(revision_db()) as conn, conn.cursor() as cursor:
        cursor.execute("INSERT INTO uploaded_by (file_name) VALUES ('class.csv') RETURNING upload_id, status, uploaded_at")
        upload_id, status, timestamp = cursor.fetchone()
        assert status == 'pending' and timestamp is not None
        cursor.execute("INSERT INTO roster (upload_id, university_no) VALUES (%s, 'same'), (%s, 'same') RETURNING roster_id", (upload_id, upload_id))
        roster_id = cursor.fetchone()[0]
        conn.commit()
        for statement in (
            'INSERT INTO roster (upload_id) VALUES (-1)',
            'INSERT INTO signup (user_id) VALUES (-1)',
            'INSERT INTO signup (roster_id) VALUES (-1)',
            'INSERT INTO signup (contact_id) VALUES (-1)',
            'INSERT INTO signup (reviewed_by) VALUES (-1)',
            'INSERT INTO signup (attempt_count) VALUES (-1)',
            f'DELETE FROM uploaded_by WHERE upload_id = {upload_id}',
        ):
            with pytest.raises(psycopg2.IntegrityError):
                cursor.execute(statement)
            conn.rollback()
        cursor.execute('INSERT INTO signup (roster_id) VALUES (%s)', (roster_id,))
        conn.commit()
        with pytest.raises(psycopg2.IntegrityError):
            cursor.execute('DELETE FROM roster WHERE roster_id = %s', (roster_id,))


def test_drop_dependency_rolls_back_archive_and_schema(revision_db):
    with closing(revision_db()) as conn, conn.cursor() as cursor:
        cursor.execute('CREATE VIEW logout_dependency AS SELECT * FROM logout')
        conn.commit()
    with pytest.raises(psycopg2.errors.DependentObjectsStillExist):
        migration_runner.upgrade_database()
    with closing(revision_db()) as conn, conn.cursor() as cursor:
        cursor.execute('SELECT COUNT(*) FROM logout')
        assert cursor.fetchone()[0] == 2
        cursor.execute("SELECT COUNT(*) FROM audit WHERE action_type = 'logout'")
        assert cursor.fetchone()[0] == 0
        cursor.execute("SELECT to_regclass('public.roster')")
        assert cursor.fetchone()[0] is None
        cursor.execute('SELECT COUNT(*) FROM schema_migration WHERE migration_name = %s', (REVISION,))
        assert cursor.fetchone()[0] == 0


def test_new_tables_are_private_to_server(revision_db):
    with closing(revision_db()) as conn, conn.cursor() as cursor:
        for role in ('anon', 'authenticated'):
            cursor.execute('SELECT 1 FROM pg_roles WHERE rolname = %s', (role,))
            if not cursor.fetchone():
                cursor.execute(sql.SQL('CREATE ROLE {}').format(sql.Identifier(role)))
        cursor.execute('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO anon, authenticated')
        conn.commit()
    upgrade()
    with closing(revision_db()) as conn, conn.cursor() as cursor:
        for table in ('uploaded_by', 'roster'):
            cursor.execute('SELECT relrowsecurity FROM pg_class WHERE oid = %s::regclass', (table,))
            assert cursor.fetchone()[0]
            for role in ('anon', 'authenticated'):
                cursor.execute("SELECT has_table_privilege(%s, %s, 'SELECT')", (role, table))
                assert not cursor.fetchone()[0]


def test_fresh_supabase_setup_without_logout(empty_database):
    with closing(empty_database()) as conn, conn.cursor() as cursor:
        for role in ('anon', 'authenticated'):
            cursor.execute('SELECT 1 FROM pg_roles WHERE rolname = %s', (role,))
            if not cursor.fetchone():
                cursor.execute(sql.SQL('CREATE ROLE {}').format(sql.Identifier(role)))
        cursor.execute('CREATE SCHEMA storage')
        cursor.execute('''CREATE TABLE storage.buckets (
            id TEXT PRIMARY KEY, name TEXT, public BOOLEAN, file_size_limit BIGINT,
            allowed_mime_types TEXT[])''')
        conn.commit()
        setup_supabase.initialize(conn)
        cursor.execute("SELECT to_regclass('public.logout'), to_regclass('public.roster')")
        assert cursor.fetchone() == (None, 'roster')
        cursor.execute('SELECT COUNT(*) FROM schema_migration')
        assert cursor.fetchone()[0] == len(migration_runner.migration_files())
        cursor.execute("SELECT COUNT(*) FROM pg_constraint WHERE conrelid = 'signup'::regclass AND contype = 'c'")
        assert cursor.fetchone()[0] == 1


def register(connect, username):
    result = auth.create_user('Test', '', 'Student', None, username + '@example.com', username, PASSWORD)
    assert result[0], result
    with closing(connect()) as conn, conn.cursor() as cursor:
        cursor.execute('''UPDATE "user" SET account_status = 'active'
                          WHERE user_id = (SELECT user_id FROM contact WHERE contact_value = %s)
                          RETURNING user_id''', (username + '@example.com',))
        user_id = cursor.fetchone()[0]
        conn.commit()
    return user_id


def test_registration_login_logout_and_deletion_without_legacy_table(revision_db):
    upgrade()
    user_id = register(revision_db, 'student')
    other_id = register(revision_db, 'other')
    assert auth.sign_in('student', PASSWORD)[0]
    assert auth.sign_out(user_id, device_ip='192.0.2.20') == (True, None)
    with closing(revision_db()) as conn, conn.cursor() as cursor:
        cursor.execute("SELECT affected_table, affected_record_id, new_values FROM audit WHERE action_type = 'logout' AND affected_table = 'user'")
        assert cursor.fetchone() == ('user', user_id, '192.0.2.20')
        cursor.execute('SELECT contact_id FROM contact WHERE user_id = %s LIMIT 1', (user_id,))
        contact_id = cursor.fetchone()[0]
        cursor.execute('UPDATE signup SET reviewed_by = %s, contact_id = %s WHERE user_id = %s', (user_id, contact_id, other_id))
        conn.commit()
    # Exercise the shared deletion path, including another signup referencing this user.
    assert users.delete_user_account(user_id, other_id) == (True, None)
    with closing(revision_db()) as conn, conn.cursor() as cursor:
        cursor.execute('SELECT reviewed_by, contact_id FROM signup WHERE user_id = %s', (other_id,))
        assert cursor.fetchone() == (None, None)
        cursor.execute('SELECT COUNT(*) FROM "user" WHERE user_id = %s', (user_id,))
        assert cursor.fetchone()[0] == 0
    assert auth.sign_in('other', PASSWORD)[0]


def test_session_user_helper_uses_user_names_and_contact_email(revision_db, monkeypatch):
    upgrade()
    user_id = register(revision_db, 'student')
    monkeypatch.setattr(sessions, 'db_connect', revision_db)
    user = sessions.get_current_user(user_id)
    assert (user['first_name'], user['middle_name'], user['last_name']) == ('Test', '', 'Student')
    assert user['email'] == 'student@example.com'
    assert sessions.get_current_user(None) is None


@pytest.mark.parametrize('audit_failure', [False, True])
def test_logout_clears_authenticated_session_with_csrf(monkeypatch, audit_failure):
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY='revision-test', WTF_CSRF_ENABLED=True)
    CSRFProtect(app)
    app.register_blueprint(blueprint)
    calls = []

    def sign_out(user_id, device_ip=None):
        calls.append((user_id, device_ip))
        if audit_failure:
            raise psycopg2.OperationalError('test audit outage')
        return True, None

    monkeypatch.setattr(sessions, 'sign_out', sign_out)
    client = app.test_client()
    with app.test_request_context():
        token = generate_csrf()
        raw_token = session['csrf_token']
    with client.session_transaction() as state:
        state.update(user_id=42, password_id=7, role_id=1, csrf_token=raw_token)
    assert client.get('/logout').status_code == 405
    assert client.post('/logout').status_code == 400
    assert calls == []
    assert client.post('/logout', data={'csrf_token': token}).status_code == 302
    assert calls == [(42, '127.0.0.1')]
    with client.session_transaction() as state:
        assert not {'user_id', 'password_id', 'role_id', 'csrf_token'} & state.keys()
