from contextlib import closing
from io import BytesIO
from pathlib import Path
import uuid

import psycopg2
import pytest
from flask import Flask
from PIL import Image
from werkzeug.datastructures import FileStorage, MultiDict

from tests.test_original_branch_features import isolated_database, feature_app, login
from app.db import auth, users, capstones, analytics, profile_settings, review_history, view_history
from app.db.connection import _PooledConnection
from app.routes.forms import SignupForm, ResetPasswordForm, ChangePasswordForm
from app.services.recommender import TopicRecommender
from app.utils.avatars import save_avatar, avatar_path
from app.utils.contact_policy import normalize_phone
from app.utils.password_policy import password_error

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = 'TestPass123'


@pytest.mark.parametrize('value,valid', [('Aa12345', False), ('Aa123456', True),
    ('Aa1234567890', True), ('Aa12345678901', False), ('aaaaaaaa', False),
    ('AAAAAAAA', False), ('12345678', False), ('Aaabcdef', False)])
def test_password_boundaries(value, valid):
    assert (password_error(value) is None) == valid


def test_reset_and_change_enforce_same_policy():
    app = Flask(__name__)
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_request_context():
        data = MultiDict(dict(new_password='short', confirm_password='short', current_password='old'))
        assert not ResetPasswordForm(data).validate()
        assert not ChangePasswordForm(data).validate()


def test_phone_normalization():
    assert normalize_phone('0917 123 4567') == '+639171234567'
    assert normalize_phone('+63 (917) 123-4567') == '+639171234567'
    with pytest.raises(ValueError):
        normalize_phone('++++123abc')


def test_phone_preference_requires_number():
    app = Flask(__name__)
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_request_context():
        form = SignupForm(MultiDict(dict(preferred_contact='phone', phone='')))
        form.validate()
        assert form.preferred_contact.errors


def test_abstract_and_keywords_find_related_work():
    corpus = [dict(capstone_id=1, capstone_title='Project Alpha',
                   abstract_text='Detect crop disease using image recognition',
                   capstone_keywords='agriculture, imaging'),
              dict(capstone_id=2, capstone_title='Payroll management')]
    matches = TopicRecommender(corpus).find_similar('Crop disease imaging')
    assert matches[0]['capstone_id'] == 1
    assert 'imaging' in matches[0]['matched_keywords']
    assert TopicRecommender([dict(capstone_id=3, capstone_title='Payroll management')]).find_similar('Payroll management')[0]['similarity'] == 1


def test_duplicate_keywords_do_not_inflate_score():
    first = TopicRecommender([dict(capstone_id=1, capstone_title='Project Alpha', capstone_keywords='imaging')])
    second = TopicRecommender([dict(capstone_id=1, capstone_title='Project Alpha', capstone_keywords='IMAGING, imaging, imaging')])
    assert first.find_similar('imaging systems') == second.find_similar('imaging systems')


def test_picture_validation_and_reencoding(tmp_path):
    app = Flask(__name__, instance_path=str(tmp_path))
    image = BytesIO()
    Image.new('RGB', (400, 300)).save(image, 'PNG')
    image.seek(0)
    with app.app_context():
        name = save_avatar(FileStorage(image, filename='../../unsafe.svg'))
        assert '/' not in name
        with Image.open(avatar_path(name)) as result:
            assert result.size == (256, 256)
            assert result.format == 'PNG'
        with pytest.raises(ValueError):
            save_avatar(FileStorage(BytesIO(b'<svg onload="alert(1)"></svg>'), filename='photo.png'))
        with pytest.raises(ValueError):
            save_avatar(FileStorage(BytesIO(b'x' * (2 * 1024 * 1024 + 1)), filename='photo.png'))


@pytest.fixture
def workflow_db(isolated_database, monkeypatch):
    schema = 'workflow_' + uuid.uuid4().hex
    with closing(psycopg2.connect(**isolated_database)) as conn, conn.cursor() as cursor:
        cursor.execute(f'CREATE SCHEMA "{schema}"')
        cursor.execute(f'SET search_path TO "{schema}"')
        cursor.execute((ROOT / 'database/capreDB.sql').read_text(encoding='utf-8'))
        cursor.execute("INSERT INTO role (role_id, role_name) VALUES (1, 'Student'), (2, 'Faculty'), (3, 'RET Chair'), (4, 'Capstone Professor')")
        cursor.execute("INSERT INTO program (program_name) VALUES ('BSIT')")
        cursor.execute("INSERT INTO specialization (specialization_name) VALUES ('DST'), ('NST'), ('WST')")
        cursor.execute((ROOT / 'migrations/20261003_account_repository_workflows.sql').read_text(encoding='utf-8'))
        cursor.execute((ROOT / "migrations/20261003_remove_program_specialization.sql").read_text(encoding="utf-8"))
        cursor.execute((ROOT / "migrations/20261003_student_view_history.sql").read_text(encoding="utf-8"))
        conn.commit()

    class Pool:
        def putconn(self, conn, **kwargs):
            conn.close()

    def connect():
        return _PooledConnection(Pool(), psycopg2.connect(**isolated_database, options=f'-c search_path={schema}'))

    for module in (auth, users, capstones, analytics, profile_settings, review_history, view_history):
        monkeypatch.setattr(module, 'db_connect', connect)
    return connect


def make_user(connect, name):
    ok, error = auth.create_user(name, '', 'Test', None, name + '@example.com', name,
                                 PASSWORD, preferred_contact='phone', phone='09171234567', terms_version='2026-10-03')
    assert ok, error
    with connect() as conn, conn.cursor() as cursor:
        cursor.execute('SELECT user_id FROM "user" WHERE user_first_name = %s', (name,))
        return cursor.fetchone()[0]


def test_registration_persists_privacy_and_contact(workflow_db):
    user_id = make_user(workflow_db, 'student')
    with workflow_db() as conn, conn.cursor() as cursor:
        cursor.execute('SELECT preferred_contact, terms_version, terms_accepted_at FROM "user" WHERE user_id = %s', (user_id,))
        row = cursor.fetchone()
        assert row[0:2] == ('phone', '2026-10-03') and row[2]
        cursor.execute("SELECT contact_value FROM contact WHERE user_id = %s AND contact_type = 'phone'", (user_id,))
        assert cursor.fetchone()[0] == '+639171234567'
        cursor.execute("SELECT COUNT(*) FROM contact WHERE user_id = %s AND contact_type = 'email'", (user_id,))
        assert cursor.fetchone()[0] == 0


@pytest.mark.parametrize('preference,email,phone,stored', [
    ('email', 'signup@example.edu', '09171234567', ('email', 'signup@example.edu')),
    ('phone', '', '09171234567', ('phone', '+639171234567')),
])
def test_signup_stores_only_chosen_contact(workflow_db, preference, email, phone, stored):
    ok, error = auth.create_user('Contact', '', 'Test', None, email, 'contact_user', PASSWORD,
                                 preferred_contact=preference, phone=phone)
    assert ok, error
    with workflow_db() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT contact_type, contact_value FROM contact")
        assert cursor.fetchall() == [stored]


def test_concurrent_verification_retries_create_one_pending_request(workflow_db):
    from concurrent.futures import ThreadPoolExecutor
    user_id = make_user(workflow_db, 'retry_user')
    with workflow_db() as conn, conn.cursor() as cursor:
        cursor.execute("UPDATE request SET request_status = 'rejected', decision_date = CURRENT_TIMESTAMP WHERE user_id = %s", (user_id,))
        conn.commit()
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(auth.reapply_for_verification, [user_id] * 5))
    assert all(ok for ok, _ in results)
    with workflow_db() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM request WHERE user_id = %s AND request_type = 'verification_student' AND request_status = 'pending'", (user_id,))
        assert cursor.fetchone()[0] == 1


def test_decision_notifications_join_target_role(workflow_db, monkeypatch):
    from app.db import qol
    monkeypatch.setattr(qol, 'db_connect', workflow_db)
    user_id = make_user(workflow_db, 'notified_user')
    with workflow_db() as conn, conn.cursor() as cursor:
        cursor.execute("UPDATE request SET request_status = 'approved', decision_date = CURRENT_TIMESTAMP WHERE user_id = %s", (user_id,))
        conn.commit()
    notifications, unread = qol.get_user_notification_summary(user_id)
    assert len(notifications) == 1 and unread == 1
    assert notifications[0]['target_role_name'] is None


def test_password_change_keeps_current_username_and_new_login(workflow_db):
    from werkzeug.security import generate_password_hash
    user_id = make_user(workflow_db, 'password_user')
    with workflow_db() as conn, conn.cursor() as cursor:
        cursor.execute('UPDATE "user" SET account_status = %s WHERE user_id = %s', ('active', user_id))
        cursor.execute("INSERT INTO kappa (username) VALUES ('historical_username') RETURNING username_id")
        username_id = cursor.fetchone()[0]
        cursor.execute('INSERT INTO ror (password) VALUES (%s) RETURNING password_id', (generate_password_hash('OldPass123'),))
        password_id = cursor.fetchone()[0]
        cursor.execute("INSERT INTO slug (username_id, password_id, user_id, assigned_at, is_current) VALUES (%s, %s, %s, CURRENT_TIMESTAMP + INTERVAL '1 day', FALSE)", (username_id, password_id, user_id))
        conn.commit()
    assert auth.change_own_password(user_id, PASSWORD, 'NextPass456') == (True, None)
    user, error = auth.sign_in('password_user', 'NextPass456')
    assert user and user['user_id'] == user_id, error
    assert auth.sign_in('password_user', PASSWORD)[0] is None


def test_concurrent_password_changes_only_accept_current_password(workflow_db):
    from concurrent.futures import ThreadPoolExecutor
    user_id = make_user(workflow_db, 'password_race')
    with workflow_db() as conn, conn.cursor() as cursor:
        cursor.execute('UPDATE "user" SET account_status = %s WHERE user_id = %s', ('active', user_id))
        conn.commit()
    new_passwords = ['NextPass456', 'OtherPass789']
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda value: auth.change_own_password(user_id, PASSWORD, value), new_passwords))
    assert sum(ok for ok, _ in results) == 1
    winner = new_passwords[next(i for i, (ok, _) in enumerate(results) if ok)]
    assert auth.sign_in('password_race', winner)[0]['user_id'] == user_id


@pytest.mark.parametrize('current,new', [('wrong', 'NextPass456'), (None, 'NextPass456'), (PASSWORD, 'short'), (PASSWORD, 'lowercase123')])
def test_rejected_password_change_preserves_login(workflow_db, current, new):
    user_id = make_user(workflow_db, 'unchanged_user')
    with workflow_db() as conn, conn.cursor() as cursor:
        cursor.execute('UPDATE "user" SET account_status = %s WHERE user_id = %s', ('active', user_id))
        conn.commit()
    assert not auth.change_own_password(user_id, current, new)[0]
    assert auth.sign_in('unchanged_user', PASSWORD)[0]['user_id'] == user_id


def test_promotion_password_lockout_and_success(workflow_db):
    actor = make_user(workflow_db, 'administrator')
    target = make_user(workflow_db, 'student')
    with workflow_db() as conn, conn.cursor() as cursor:
        cursor.execute('UPDATE "user" SET role_id = 3, account_status = \'active\' WHERE user_id = %s', (actor,))
        conn.commit()
    for _ in range(5):
        assert not users.update_user_role(target, 2, actor, 'wrong')[0]
    assert not users.update_user_role(target, 2, actor, PASSWORD)[0]
    with workflow_db() as conn, conn.cursor() as cursor:
        cursor.execute('UPDATE "user" SET promotion_locked_until = CURRENT_TIMESTAMP - INTERVAL \'1 minute\' WHERE user_id = %s', (actor,))
        conn.commit()
    assert users.update_user_role(target, 2, actor, PASSWORD)[0]
    assert not users.update_user_role(actor, 1, actor, PASSWORD)[0]


def test_rejection_reason_and_history(workflow_db):
    user_id = make_user(workflow_db, 'student')
    with workflow_db() as conn, conn.cursor() as cursor:
        cursor.execute('SELECT request_id FROM request WHERE user_id = %s', (user_id,))
        request_id = cursor.fetchone()[0]
    assert not auth.review_verification_request(request_id, 'rejected', '  ', user_id)[0]
    assert auth.review_verification_request(request_id, 'rejected', 'Upload a readable COR.', user_id)[0]
    rows, total, _ = review_history.get_review_history(verification_only=True)
    assert total == 1 and rows[0]['status_reason'] == 'Upload a readable COR.'
    assert not auth.review_verification_request(request_id, 'approved', '', user_id)[0]


def test_bsds_mapping_and_publication_counts(workflow_db):
    with workflow_db() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT program_id FROM program WHERE program_code = 'BSDS'")
        program_id = cursor.fetchone()[0]
        cursor.execute("SELECT specialization_id FROM specialization WHERE specialization_code = 'GENERAL'")
        specialization_id = cursor.fetchone()[0]
        cursor.execute("INSERT INTO capstone (program_id, specialization_id, capstone_title, is_published) VALUES (%s, %s, 'Legacy', NULL), (%s, %s, 'Published', TRUE), (%s, %s, 'Unpublished', FALSE)", (program_id, specialization_id) * 3)
        conn.commit()
    assert (specialization_id, 'No specialization', 'GENERAL') in capstones.get_specializations(include_codes=True)
    with workflow_db() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT to_regclass('program_specialization')")
        assert cursor.fetchone()[0] is None
    flags, error = analytics.get_capstone_status_flags()
    assert error is None
    assert [flags[key] for key in ('published', 'not_published', 'publication_unknown')] == [1, 1, 1]


def test_request_purpose_is_required_and_explanation_optional(feature_app, monkeypatch):
    from app.routes.pages import manuscripts
    calls = []
    monkeypatch.setattr(manuscripts, 'request_fullview', lambda *args: (calls.append(args) or True, None))
    client = feature_app.test_client()
    login(client, 1)
    client.post('/request_manuscript/1', data={'request_purpose': 'forged'})
    assert not calls
    client.post('/request_manuscript/1', data={'request_purpose': 'Literature review'})
    assert calls[-1] == (1, 1, 'Literature review')


def test_profile_picture_routes_and_cleanup(feature_app, workflow_db, tmp_path):
    feature_app.instance_path = str(tmp_path)
    user_id = make_user(workflow_db, 'student')
    client = feature_app.test_client()
    assert client.get('/user-info/picture').status_code == 302
    with client.session_transaction() as state:
        state.update(user_id=user_id, role_id=1, role_name='Student')
    image = BytesIO()
    Image.new('RGB', (100, 100)).save(image, 'PNG')
    image.seek(0)
    assert client.post('/user-info/picture', data={'picture': (image, 'picture.png')}).status_code == 302
    response = client.get('/user-info/picture')
    assert response.status_code == 200 and response.mimetype == 'image/png'
    assert 'no-store' in response.headers['Cache-Control']
    assert client.get('/user-info').status_code == 200
    client.post('/user-info/picture', data={'action': 'remove'})
    assert client.get('/user-info/picture').status_code == 404
    assert not list((tmp_path / 'uploads/avatars').iterdir())


def test_mismatched_program_specialization_rejected(feature_app, monkeypatch):
    from app.routes.admin import repository
    from app.routes.forms import CreateCapstoneForm
    monkeypatch.setattr(repository, 'get_programs', lambda include_codes=False: [(1, 'BSIT', 'BSIT'), (2, 'BSDS', 'BSDS')])
    monkeypatch.setattr(repository, 'get_specializations', lambda include_codes=False: [(9, 'No specialization', 'GENERAL'), (1, 'Database Systems Technology', 'DST')])
    with feature_app.test_request_context(method='POST', data={'program_id': '2', 'specialization_id': '1'}):
        form = CreateCapstoneForm()
        repository._populate_capstone_choices(form)
        form.validate()
        assert form.specialization_id.errors


def test_history_permissions(feature_app, monkeypatch):
    from app.routes.admin import history
    calls = []
    monkeypatch.setattr(history, 'get_review_history', lambda **kwargs: (calls.append(kwargs['reviewed_by']) or [], 0, 20))
    client = feature_app.test_client()
    login(client, 1)
    assert client.get('/review-history').status_code == 302
    assert not calls
    login(client, 4)
    with client.session_transaction() as state:
        reviewer_id = state['user_id']
    assert client.get('/review-history').status_code == 200 and calls[-1] == reviewer_id
    login(client, 3)
    assert client.get('/review-history?view=recent').status_code == 200 and calls[-1] is None


def test_migrations_allow_line_endings_but_reject_sql_changes(workflow_db, monkeypatch, tmp_path):
    from app.db import migration_runner
    monkeypatch.setattr(migration_runner, 'db_connect', workflow_db)
    migration = tmp_path / 'test.sql'
    migration.write_bytes(b'SELECT 1;\n')
    assert migration_runner.upgrade_database(tmp_path) == ['test.sql']
    migration.write_bytes(b'SELECT 1;\r\n')
    assert migration_runner.upgrade_database(tmp_path) == []
    migration.write_bytes(b'SELECT 2;\r\n')
    with pytest.raises(migration_runner.MigrationError):
        migration_runner.upgrade_database(tmp_path)


def test_student_view_history_is_private_and_recent(workflow_db):
    first = make_user(workflow_db, 'first_student')
    second = make_user(workflow_db, 'second_student')
    with workflow_db() as conn, conn.cursor() as cursor:
        cursor.execute("INSERT INTO capstone (capstone_title) VALUES ('First project'), ('Second project') RETURNING capstone_id")
        first_project, second_project = [row[0] for row in cursor.fetchall()]
        conn.commit()
    assert view_history.record_capstone_view(first, first_project)
    assert view_history.record_capstone_view(first, second_project)
    assert view_history.record_capstone_view(second, second_project)
    assert view_history.record_capstone_view(first, first_project)
    rows, total = view_history.get_view_history(first)
    assert total == 2 and rows[0]['capstone_id'] == first_project
    rows, total = view_history.get_view_history(second)
    assert total == 1 and rows[0]['capstone_id'] == second_project
    rows, total = view_history.get_view_history(first, page=2, page_size=1)
    assert total == 2 and rows[0]['capstone_id'] == second_project
    with workflow_db() as conn, conn.cursor() as cursor:
        cursor.execute('UPDATE capstone SET is_archived = TRUE WHERE capstone_id = %s', (first_project,))
        conn.commit()
    assert not view_history.record_capstone_view(first, first_project)
    assert view_history.get_view_history(first)[1] == 1
    with workflow_db() as conn, conn.cursor() as cursor:
        cursor.execute('DELETE FROM capstone WHERE capstone_id = %s', (second_project,))
        conn.commit()
    assert view_history.get_view_history(first) == ([], 0)


def test_student_history_routes_use_session_identity(feature_app, monkeypatch):
    from app.routes.pages import history
    reads, writes = [], []
    monkeypatch.setattr(history, 'get_view_history', lambda user_id, *args: (reads.append(user_id) or [], 0))
    monkeypatch.setattr(history, 'record_capstone_view', lambda *args: writes.append(args) or True)
    client = feature_app.test_client()
    assert client.get('/view-history').status_code == 302
    login(client, 3)
    assert client.get('/view-history').status_code == 302
    assert client.post('/view-history/1').status_code == 302
    assert not reads and not writes
    login(client, 1)
    response = client.get('/view-history?user_id=999')
    assert response.status_code == 200 and b'No viewing history yet' in response.data
    assert reads == [1]
    assert client.post('/view-history/2', data={'user_id': 999}).status_code == 200
    assert writes == [(1, 2)]
    feature_app.config['WTF_CSRF_ENABLED'] = True
    assert client.post('/view-history/2').status_code == 400


def test_history_records_successful_student_views_only(feature_app, monkeypatch):
    from app.routes.pages import history
    calls = []
    monkeypatch.setattr(history, 'record_capstone_view', lambda *args: calls.append(args) or True)
    monkeypatch.setitem(feature_app.view_functions, 'pages.view_approved_manuscript', lambda capstone_id: ('Denied', 403))
    client = feature_app.test_client()
    login(client, 1)
    client.get('/manuscript/view/12')
    assert not calls
    monkeypatch.setitem(feature_app.view_functions, 'pages.view_approved_manuscript', lambda capstone_id: 'Reader')
    client.get('/manuscript/view/12')
    assert calls == [(1, 12)]
    login(client, 3)
    client.get('/manuscript/view/12')
    assert calls == [(1, 12)]
