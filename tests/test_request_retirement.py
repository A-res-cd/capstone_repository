from tests.roster_test_helpers import create_legacy_account
"""Retired workflow contracts and migration safety on disposable PostgreSQL."""
from contextlib import closing
from pathlib import Path
import re
import shutil

import psycopg2
import pytest

from app.constants.nav import get_nav_links
from app.db import auth, migration_runner
from tests.test_original_branch_features import feature_app, feature_db, isolated_database, login
from tests.test_roster_signup_revision import empty_database


ROOT = Path(__file__).resolve().parents[1]
RETIREMENT = '20261105_remove_legacy_request.sql'


@pytest.fixture
def retirement_db(empty_database, tmp_path):
    with closing(empty_database()) as conn, conn.cursor() as cursor:
        cursor.execute((ROOT / 'database/capre_original_final.sql').read_text(encoding='utf-8'))
        conn.commit()
    historical = tmp_path / 'historical'
    historical.mkdir()
    for path in migration_runner.migration_files():
        if path.name < RETIREMENT:
            shutil.copyfile(path, historical / path.name)
    migration_runner.upgrade_database(historical)
    return empty_database


def test_empty_retirement_through_normal_runner_preserves_retained_data(retirement_db):
    with closing(retirement_db()) as conn, conn.cursor() as cursor:
        cursor.execute("INSERT INTO role (role_name) VALUES ('Student') RETURNING role_id")
        role = cursor.fetchone()[0]
        cursor.execute('INSERT INTO "user" (role_id) VALUES (%s) RETURNING user_id', (role,))
        user = cursor.fetchone()[0]
        cursor.execute("INSERT INTO capstone (capstone_title) VALUES ('Retained') RETURNING capstone_id")
        capstone = cursor.fetchone()[0]
        cursor.execute('INSERT INTO capstone_view_history (user_id, capstone_id) VALUES (%s, %s)', (user, capstone))
        conn.commit()
    assert migration_runner.upgrade_database() == [RETIREMENT, '20261106_roster_auto_signup.sql']
    assert migration_runner.upgrade_database() == []
    with closing(retirement_db()) as conn, conn.cursor() as cursor:
        for name in ('request', 'capstone_requests'):
            cursor.execute('SELECT to_regclass(%s)', ('public.' + name,))
            assert cursor.fetchone()[0] is None
        for name in ('user', 'signup', 'roster', 'uploaded_by', 'contact', 'login',
                     'password_reset', 'capstone', 'capstone_view_history', 'audit'):
            cursor.execute('SELECT to_regclass(%s)', ('public.' + name,))
            assert cursor.fetchone()[0] is not None
        cursor.execute('SELECT user_id, capstone_id FROM capstone_view_history')
        assert cursor.fetchall() == [(user, capstone)]
        cursor.execute('SELECT checksum FROM schema_migration WHERE migration_name = %s', (RETIREMENT,))
        assert cursor.fetchone()[0] == migration_runner.migration_checksum(ROOT / 'migrations' / RETIREMENT)


@pytest.mark.parametrize('populated', ['request', 'capstone_requests'])
def test_either_populated_legacy_table_blocks_without_data_loss(retirement_db, populated):
    # Historical SQL is intentional here: verify the destructive migration refuses it.
    with closing(retirement_db()) as conn, conn.cursor() as cursor:
        if populated == 'request':
            cursor.execute("INSERT INTO request (request_status) VALUES ('pending')")
        else:
            cursor.execute("INSERT INTO capstone (capstone_title) VALUES ('Historical') RETURNING capstone_id")
            cursor.execute('INSERT INTO capstone_requests (capstone_id) VALUES (%s)', (cursor.fetchone()[0],))
        conn.commit()
    with pytest.raises(psycopg2.Error, match='Refusing to remove'):
        migration_runner.upgrade_database()
    with closing(retirement_db()) as conn, conn.cursor() as cursor:
        cursor.execute('SELECT count(*) FROM ' + populated)
        assert cursor.fetchone()[0] == 1
        for name in ('request', 'capstone_requests'):
            cursor.execute('SELECT to_regclass(%s)', ('public.' + name,))
            assert cursor.fetchone()[0] is not None
        cursor.execute('SELECT count(*) FROM schema_migration WHERE migration_name = %s', (RETIREMENT,))
        assert cursor.fetchone()[0] == 0


def test_restrict_dependency_failure_rolls_back_both_drops(retirement_db):
    with closing(retirement_db()) as conn, conn.cursor() as cursor:
        cursor.execute('CREATE VIEW legacy_dependency AS SELECT id FROM capstone_requests')
        conn.commit()
    with pytest.raises(psycopg2.errors.DependentObjectsStillExist):
        migration_runner.upgrade_database()
    with closing(retirement_db()) as conn, conn.cursor() as cursor:
        cursor.execute("SELECT to_regclass('public.request'), to_regclass('public.capstone_requests')")
        assert all(cursor.fetchone())
        cursor.execute('SELECT count(*) FROM schema_migration WHERE migration_name = %s', (RETIREMENT,))
        assert cursor.fetchone()[0] == 0


@pytest.mark.parametrize('role', ['Student', 'Faculty', 'Admin', 'Capstone Professor'])
def test_navigation_has_no_retired_endpoints(feature_app, role):
    links, _ = get_nav_links(role)
    endpoints = {rule.endpoint for rule in feature_app.url_map.iter_rules()}
    assert all(link['url'] in endpoints for link in links)
    assert not any('request' in link['url'] or 'review_history' in link['url'] for link in links)


@pytest.mark.parametrize('path,method', [('/my-requests', 'GET'), ('/requests', 'GET'),
    ('/requests/1', 'GET'), ('/request_manuscript/1', 'POST'), ('/cancel_request/1', 'POST'),
    ('/repository/decide/1', 'POST'), ('/review-history', 'GET'),
    ('/most-requested', 'GET'), ('/capstones/most-requested', 'GET'), ('/notifications/read', 'POST')])
def test_retired_routes_are_absent_even_for_admin(feature_app, path, method):
    client = feature_app.test_client()
    login(client)
    assert client.open(path, method=method).status_code == 404


def test_students_cannot_use_old_approved_view_or_image_routes(feature_app):
    client = feature_app.test_client()
    login(client, 1)
    for path in ('/manuscript/view/1', '/manuscript/pages/1', '/manuscript/pages/1/1', '/manuscript/file/1'):
        assert client.get(path).status_code == 403


def test_existing_pending_signup_without_review_metadata_still_reviewable(feature_db):
    assert auth.create_user('Pending', '', 'Faculty', None, 'pending@example.com', 'pending_user', 'Secure123',requested_role='Faculty')[0]
    with feature_db() as conn, conn.cursor() as cursor:
        cursor.execute('UPDATE signup SET status = NULL, requested_at = NULL RETURNING signup_id, user_id')
        signup_id, user_id = cursor.fetchone()
    pending = auth.get_pending_verifications()
    assert len(pending) == 1 and pending[0]['request_id'] == signup_id
    assert auth.review_verification_request(signup_id, 'approved', '', user_id)[0]
    assert auth.get_pending_verifications() == []
    assert not auth.review_verification_request(signup_id, 'rejected', 'Duplicate review', user_id)[0]


def test_faculty_reapplication_keeps_signup_identity_and_clears_previous_decision(feature_db):
    assert auth.create_user('Retry', '', 'Faculty', None, 'retry@example.com', 'retry_user', 'Secure123', requested_role='Faculty')[0]
    with feature_db() as conn, conn.cursor() as cursor:
        cursor.execute('SELECT signup_id, user_id FROM signup')
        signup_id, user_id = cursor.fetchone()
    assert auth.review_verification_request(signup_id, 'rejected', 'Readable COR required', user_id)[0]
    assert auth.reapply_for_verification(user_id)[0]
    with feature_db() as conn, conn.cursor() as cursor:
        cursor.execute('SELECT signup_id, status, reason, decided_at, reviewed_by, attempt_count FROM signup')
        assert cursor.fetchone() == (signup_id, 'pending', None, None, None, 2)


def test_active_application_and_setup_have_no_retired_sql():
    pattern = re.compile(r'\b(?:FROM|JOIN|INTO|UPDATE|TABLE)\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?"?(?:request|capstone_requests)"?\b', re.I)
    paths = list((ROOT / 'app').rglob('*.py'))
    paths += [ROOT / 'scripts' / name for name in ('data_seeder.py', 'data_seeder_current.py')]
    paths += [ROOT / 'database' / name for name in ('capreDB.sql', 'capre_revised_schema.sql', 'supabase_setup.sql')]
    for path in paths:
        code = '\n'.join(line for line in path.read_text(encoding='utf-8').splitlines()
                         if not line.lstrip().startswith(('#', '--')))
        assert not pattern.search(code), str(path)
