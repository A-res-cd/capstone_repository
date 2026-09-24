"""Role split, maintenance state, durable jobs, and protected console flows."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
from importlib import import_module
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, g, session
import pytest

from app import csrf
from app.constants.roles import ROLE_ADMIN, ROLE_RET_CHAIR, landing_endpoint
from app.constants.nav import get_nav_links
from app.db import system, auth, session_users, users, migration_runner
from app.db.role_security import guard_account_change
from app.routes.system import system as blueprint, PAGES
from app.services import system_maintenance as service
from app.utils.auth_utils import load_current_user
from app.utils.maintenance_gate import maintenance_gate
from tests.test_author_account_links import author_db, author_postgres
from tests.test_login_username_case import add_credentials

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def system_db(author_db, monkeypatch):
    with closing(author_db()) as conn, conn.cursor() as cur:
        for name in ['20260924_system_administration.sql']:
            cur.execute((ROOT / 'migrations' / name).read_text(encoding='utf-8'))
        cur.execute('''INSERT INTO "user"(user_id,user_first_name,user_last_name,role_id,account_status)
                       VALUES (3,'Chair','User',3,'active'),
                       (4,'System','Operator',(SELECT role_id FROM role WHERE role_name='System Administrator'),'active')''')
        conn.commit()
    add_credentials(author_db, 4, 'operator')
    for module in [system, auth, session_users, users, migration_runner, service]:
        monkeypatch.setattr(module, 'db_connect', author_db)
    return author_db


@pytest.fixture
def system_app(system_db, monkeypatch, tmp_path):
    app = Flask(__name__, template_folder=str(ROOT / 'app/templates'), static_folder=str(ROOT / 'app/static'))
    app.config.update(SECRET_KEY='system-tests', TESTING=True, WTF_CSRF_ENABLED=False,
                      MAINTENANCE_BACKUP_ROOT=str(tmp_path / 'backups'))
    folders = {tmp_path / name for name in ['manuscripts', 'avatars', 'registration']}
    for folder in folders:
        folder.mkdir()
    monkeypatch.setattr(service, '_upload_folders', lambda: folders)
    monkeypatch.setattr(service, '_referenced_upload_names', lambda: set())
    monkeypatch.setattr(service, '_orphaned_uploads', lambda refs, days: [])
    csrf.init_app(app)
    app.register_blueprint(blueprint)
    app.register_blueprint(import_module('app.routes.admin').admin)
    app.register_blueprint(import_module('app.routes.pages').pages)
    app.add_url_rule('/signin', endpoint='auth.signin', view_func=lambda: 'Sign in')
    app.add_url_rule('/', endpoint='main.home', view_func=lambda: 'Home')
    app.before_request(load_current_user)
    app.context_processor(lambda: {'hide_nav': True, 'hide_header': True})
    return app


def identity(client, user_id=4, role=ROLE_ADMIN):
    with client.session_transaction() as state:
        state.update(user_id=user_id, role_name=role, username='operator', session_version=0)


def test_migration_preserves_academic_authority(system_db):
    with closing(system_db()) as conn, conn.cursor() as cur:
        cur.execute('SELECT role_name FROM role WHERE role_id=3')
        assert cur.fetchone()[0] == ROLE_RET_CHAIR
    assert landing_endpoint(ROLE_ADMIN) == 'system.overview'
    assert landing_endpoint(ROLE_RET_CHAIR) == 'admin.overview'
    assert all(not row['url'].startswith('admin.') for row in get_nav_links(ROLE_ADMIN)[0])
    assert all(not row['url'].startswith('system.') for row in get_nav_links(ROLE_RET_CHAIR)[0])


def test_legacy_admin_migration_does_not_grant_system_access(system_db):
    with closing(system_db()) as conn, conn.cursor() as cur:
        cur.execute("UPDATE role SET role_name='Admin' WHERE role_id=3")
        cur.execute((ROOT / 'migrations/20260924_system_administration.sql').read_text(encoding='utf-8'))
        cur.execute('SELECT r.role_name FROM "user" u JOIN role r ON r.role_id=u.role_id WHERE u.user_id=3')
        assert cur.fetchone()[0] == ROLE_RET_CHAIR
        cur.execute('SELECT COUNT(*) FROM "user" u JOIN role r ON r.role_id=u.role_id WHERE r.role_name=%s', (ROLE_ADMIN,))
        assert cur.fetchone()[0] == 1  # Only the explicitly provisioned test operator.


def test_public_signup_cannot_infer_privileged_role():
    assert auth.detect_role('admin001') == 'Faculty'
    for number in ['2026-00001', 'admin001', 'ADMIN999']:
        assert auth.detect_role(number) not in (ROLE_ADMIN, ROLE_RET_CHAIR)


def test_password_change_and_reactivation_do_not_revive_old_sessions(system_db):
    previous_version = session_users.get_current_user(4)['session_version']
    assert auth.change_own_password(4, 'CorrectPassword1!', 'NewPassword2!')[0]
    assert session_users.get_current_user(4)['session_version'] > previous_version
    previous_version = session_users.get_current_user(4)['session_version']
    with closing(system_db()) as conn, conn.cursor() as cur:
        cur.execute("UPDATE \"user\" SET account_status='deactivated' WHERE user_id=4")
        cur.execute("UPDATE \"user\" SET account_status='active' WHERE user_id=4")
        conn.commit()
    assert session_users.get_current_user(4)['session_version'] > previous_version


def test_security_reactivation_cannot_approve_pending_account(system_db):
    with closing(system_db()) as conn, conn.cursor() as cur:
        cur.execute("UPDATE \"user\" SET account_status='pending' WHERE user_id=1")
        conn.commit()
    with pytest.raises(ValueError, match='Only a suspended'):
        system.secure_account(4, 1, 'reactivate', 'Attempted verification bypass')
    assert session_users.get_current_user(1)['account_status'] == 'pending'


def test_concurrent_deactivation_preserves_last_ret_chair(system_db):
    with closing(system_db()) as conn, conn.cursor() as cur:
        cur.execute('UPDATE "user" SET role_id=3 WHERE user_id=2')
        conn.commit()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda uid: users.set_account_status(uid, 'deactivated', 4)[0], [2, 3]))
    assert sum(results) == 1
    with closing(system_db()) as conn, conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) FROM "user" WHERE role_id=3 AND account_status=\'active\'')
        assert cur.fetchone()[0] == 1


def test_cleanup_stops_on_changed_preview(system_app, monkeypatch):
    monkeypatch.setattr(service, 'cleanup_preview', lambda: ({'candidates': []}, 'new-digest'))
    with system_app.app_context(), pytest.raises(ValueError, match='inventory changed'):
        service.cleanup_confirmed('old-digest')


def test_console_navigation_queue_and_mobile_layout(system_app, monkeypatch, page):
    from playwright.sync_api import expect
    from urllib.parse import urlsplit
    main_routes = import_module('app.routes.main')
    monkeypatch.setattr(main_routes, 'get_user_avatar', lambda uid: None)
    monkeypatch.setattr(main_routes, 'get_user_notification_summary', lambda uid: ([], 0))
    monkeypatch.setattr(main_routes, 'get_admin_pending_nav_counts', lambda: {})
    @system_app.context_processor
    def navigation():
        return dict(main_routes.inject_global_template_vars(), hide_nav=False, hide_header=False)
    client = system_app.test_client()
    identity(client)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    def serve(route):
        url = urlsplit(route.request.url)
        response = client.open(url.path + ('?' + url.query if url.query else ''),
                               method=route.request.method, data=route.request.post_data,
                               content_type=route.request.headers.get('content-type'), follow_redirects=True)
        route.fulfill(status=response.status_code, body=response.data,
                      headers={key: value for key, value in response.headers if key.lower() not in {'content-length', 'set-cookie'}})
        response.close()
    page.route('http://system.test/**', serve)
    page.goto('http://system.test/system/')
    expect(page.get_by_role('heading', name='System Overview', exact=True)).to_be_visible()
    expect(page.get_by_role('link', name='Account Security', exact=True)).to_be_visible()
    assert page.get_by_role('link', name='Capstone Repository', exact=True).count() == 0
    page.get_by_label('Reason', exact=True).fill('Inspect current service status')
    page.get_by_role('button', name='Run diagnostics', exact=True).click()
    assert system.jobs(), page.locator('body').inner_text()
    page.wait_for_url('**/system/jobs')
    expect(page.get_by_role('heading', name='#1 · Diagnostics · queued')).to_be_visible()
    page.get_by_role('link', name='Maintenance Mode', exact=True).click()
    expect(page.get_by_label('Public notice')).to_be_visible()
    page.set_viewport_size({'width': 390, 'height': 844})
    expect(page.get_by_role('heading', name='Maintenance Mode', exact=True)).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(ROOT / '.pytest_cache/system-maintenance-mobile.png'), full_page=True)
    light_surface = page.locator('.system-workspace').evaluate('(node) => getComputedStyle(node).backgroundColor')
    page.evaluate("localStorage.setItem('capre-theme', 'dark')")
    page.reload()
    assert page.locator('.system-workspace').evaluate('(node) => getComputedStyle(node).backgroundColor') != light_surface
    overview_routes = import_module('app.routes.admin.overview')
    monkeypatch.setattr(overview_routes, 'get_admin_pending_nav_counts', lambda: {})
    identity(client, 3, ROLE_RET_CHAIR)
    page.goto('http://system.test/academic-overview')
    expect(page.get_by_role('heading', name='Academic Overview', exact=True)).to_be_visible()
    assert page.locator('.system-overview-grid article').count() == 6
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert not errors


@pytest.mark.parametrize('name', PAGES)
def test_all_system_pages_render_and_deny_chair(system_app, name):
    client = system_app.test_client()
    path = '/system/' if name == 'overview' else '/system/' + name
    assert client.get(path).status_code == 302
    identity(client, 3, ROLE_RET_CHAIR)
    assert client.get(path).status_code == 403
    identity(client)
    response = client.get(path)
    assert response.status_code == 200
    assert PAGES[name][0].encode() in response.data.replace(b'&amp;', b'&')


def test_system_admin_denied_academic_routes(system_app):
    client = system_app.test_client()
    identity(client)
    for path in ['/analytics', '/manage_users', '/requests', '/repository', '/capstoners', '/recyclebin', '/academic-overview']:
        assert client.get(path).status_code == 302
    assert client.get('/archive').status_code == 403


def test_jobs_deduplicate_claim_finish_and_record_history(system_db):
    first = system.enqueue('diagnostics', 4, 'Inspect service status')
    with pytest.raises(ValueError, match='already'):
        system.enqueue('diagnostics', 4, 'Duplicate service check')
    with ThreadPoolExecutor(max_workers=2) as executor:
        rows = list(executor.map(lambda _: system.claim_job(), range(2)))
    assert sum(row is not None for row in rows) == 1
    system.finish_job(first, {'checks': []})
    assert system.job(first)['status'] == 'succeeded'
    assert system.events()[0]['action'] == 'job_completed'
    assert system.enqueue('diagnostics', 4, 'Fresh service check') > first


def test_last_privileged_accounts_and_role_escalation_blocked(system_db):
    for user_id, role_id in [(4, None), (3, 1), (1, 5)]:
        with closing(system_db()) as conn, pytest.raises(ValueError):
            guard_account_change(conn, user_id, target_role_id=role_id)
    assert users.update_user_role(1, 5, 3)[0] is False
    assert users.submit_promotion_request(1, 5, 'please promote')[0] is False
    assert users.delete_user_account(4, 3)[0] is False


def test_security_revoke_invalidates_web_session(system_app):
    client = system_app.test_client()
    identity(client)
    system.secure_account(3, 4, 'revoke', 'Compromised device reported')
    assert client.get('/system/').status_code == 302
    with client.session_transaction() as state:
        assert 'user_id' not in state


def test_suspension_cannot_remove_last_operator(system_db):
    with pytest.raises(ValueError, match='at least one'):
        system.secure_account(3, 4, 'suspend', 'Compromised account')
    system.secure_account(4, 1, 'suspend', 'Compromised student account')
    assert session_users.get_current_user(1)['account_status'] == 'deactivated'


def test_maintenance_schedule_and_consistent_web_api_gate(system_app):
    system_app.before_request(maintenance_gate)
    system_app.add_url_rule('/api/v1/test', view_func=lambda: 'private')
    now = datetime.now(timezone.utc)
    system.save_settings(4, 'Planned maintenance', enabled=True, start=now + timedelta(hours=1), end=None, notice='Planned work')
    assert not system.maintenance_active(system.settings())
    system.save_settings(4, 'Immediate maintenance', enabled=True, start=None, end=None, notice='Repairs underway')
    client = system_app.test_client()
    response = client.get('/api/v1/test')
    assert response.status_code == 503 and response.json['maintenance']
    assert response.headers['Retry-After'] == '300'
    assert client.get('/archive').status_code == 503
    assert client.get('/signin').status_code == 200
    identity(client)
    assert client.get('/system/maintenance').status_code == 200


@pytest.mark.parametrize('missing_schema', [True, False])
def test_unavailable_state_renders_safe_browser_page(system_app, monkeypatch, missing_schema):
    from psycopg2.errors import UndefinedTable

    def unavailable():
        if missing_schema:
            raise UndefinedTable('relation system_setting does not exist')
        raise RuntimeError('private database connection details')

    monkeypatch.setattr(system, 'settings', unavailable)
    system_app.before_request(maintenance_gate)
    client = system_app.test_client()
    response = client.get('/')
    assert response.status_code == 503
    assert response.mimetype == 'text/html'
    assert b'Service unavailable' in response.data
    assert (b'pending database migrations' in response.data) is missing_schema
    assert b'private database connection details' not in response.data
    assert response.headers['Cache-Control'] == 'no-store'
    assert client.get('/signin').status_code == 200


def test_native_mobile_blueprint_is_removed():
    from app.routes import blueprints
    assert 'mobile' not in {blueprint.name for blueprint in blueprints}


def test_csrf_and_reauthentication_for_security_actions(system_app):
    client = system_app.test_client()
    identity(client)
    system_app.config['WTF_CSRF_ENABLED'] = True
    assert client.post('/system/jobs', data={'kind': 'diagnostics', 'reason': 'inspect'}).status_code == 400
    system_app.config['WTF_CSRF_ENABLED'] = False
    response = client.post('/system/security/1', data={'action': 'suspend', 'reason': 'security incident', 'password': 'bad'})
    assert response.status_code == 302
    assert session_users.get_current_user(1)['account_status'] == 'active'


def test_cleanup_confirmation_is_actor_bound_and_not_browser_paths(system_app):
    client = system_app.test_client()
    identity(client)
    response = client.post('/system/jobs', data={'kind': 'cleanup', 'reason': 'old files', 'password': 'CorrectPassword1!',
                                               'confirm': 'CLEANUP', 'preview': '../../arbitrary'})
    assert response.status_code == 302
    assert not system.jobs()


def test_queued_checks_run_in_worker_and_failures_are_sanitized(system_app, monkeypatch):
    worker = import_module('scripts.system_worker')
    system.enqueue('diagnostics', 4, 'Check service availability')
    monkeypatch.setattr(worker, 'run_job', lambda row: (_ for _ in ()).throw(RuntimeError('PASSWORD=do-not-show')))
    with system_app.app_context():
        assert worker.process_next()
    row = system.jobs()[0]
    assert row['status'] == 'failed' and 'do-not-show' not in str(row['result'])


def test_restore_test_refuses_production_database(system_app):
    system_app.config.update(PG_DB='production', MAINTENANCE_RESTORE_TEST_DB='production')
    with system_app.app_context(), pytest.raises(ValueError, match='dedicated'):
        service.restore_test('a' * 32)


def test_backup_paths_cannot_escape_root(system_app):
    with system_app.app_context():
        for value in ['../../other', 'A' * 32, 'x', '', None]:
            with pytest.raises(ValueError):
                service.bundle_path(value)
