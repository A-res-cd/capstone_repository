"""Audit browsing: isolated PostgreSQL, authorization, and themed browser UI."""
from datetime import datetime, date
from importlib import import_module
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, g, session
from playwright.sync_api import expect
import pytest

from app.db import audit_reader
from app.utils.audit_summary import summarize_audit
from app.constants.nav import get_nav_links
from tests.test_author_account_links import author_postgres, author_db

ROOT = Path(__file__).resolve().parents[1]
routes = import_module('app.routes.admin.audit')


def sample(action='update_contact', **values):
    row = dict(audit_id=1, user_id=None, action_type=action, affected_table='contact',
                affected_record_id=22, old_values='SECRET OLD', new_values='SECRET NEW',
                action_timestamp=datetime(2026, 9, 10, 14, 30), actor_name=None)
    row.update(values)
    return row


def test_safe_summary_and_unknown_actor():
    event = summarize_audit(sample(), {})
    assert event['actor'] == 'Unknown / deleted user'
    assert 'SECRET' not in str(event)
    row = sample('role_change')
    row.update(old_values='1', new_values='2')
    assert 'Student → Faculty' in summarize_audit(row, {1: 'Student', 2: 'Faculty'})['summary']
    row.update(action_type='review_verification_request', new_values='approved -> account_status=active')
    assert ('Decision', 'Approved') in summarize_audit(row, {})['changes']
    row.update(action_type='unrecognized', new_values='<script>secret</script>')
    assert summarize_audit(row, {})['category'] == 'Other'
    assert '<script>' not in str(summarize_audit(row, {}))


@pytest.fixture
def audit_app(monkeypatch):
    app = Flask(__name__, template_folder=str(ROOT / 'app/templates'), static_folder=str(ROOT / 'app/static'))
    app.config.update(TESTING=True, SECRET_KEY='audit-test')
    app.register_blueprint(routes.admin)
    app.add_url_rule('/signin', endpoint='auth.signin', view_func=lambda: 'Sign in')
    app.add_url_rule('/', endpoint='main.home', view_func=lambda: 'Home')
    app.jinja_env.globals['csrf_token'] = lambda: ''

    @app.before_request
    def user():
        g.user = {'role_id': session.get('role_id')}

    @app.context_processor
    def context():
        return dict(hide_nav=True, hide_header=True)

    monkeypatch.setattr(routes, 'get_audit_logs', lambda filters, page: {
        'events': [summarize_audit(sample(actor_name='<script>alert(1)</script>'), {})],
        'counts': {'account': 26, 'capstone': 0, 'workflow': 0, 'other': 0},
        'total': 26, 'page': 1, 'pages': 2,
    })
    return app


def sign_in(client, role=3):
    with client.session_transaction() as state:
        state.update(user_id=1, role_id=role)


def test_admin_only_and_no_mutations(audit_app):
    client = audit_app.test_client()
    assert client.get('/audit-logs').status_code == 302
    for role in (1, 2, 4):
        sign_in(client, role)
        assert client.get('/audit-logs').status_code == 302
    sign_in(client)
    response = client.get('/audit-logs?q=Maria')
    assert response.status_code == 200
    assert b'&lt;script&gt;' in response.data and b'SECRET' not in response.data
    assert b'page=2' in response.data and b'q=Maria' in response.data
    assert client.post('/audit-logs').status_code == 405
    assert any(link['url'] == 'admin.audit_logs' for link in get_nav_links('Admin')[0])
    assert not any(link['url'] == 'admin.audit_logs' for link in get_nav_links('Student')[0])


@pytest.mark.parametrize('query', ['page=0', 'page=no', 'category=bad', 'action=bad', 'start=invalid', 'start=2026-09-11&end=2026-09-10', 'end=9999-12-31'])
def test_invalid_filters(audit_app, query):
    client = audit_app.test_client()
    sign_in(client)
    assert client.get('/audit-logs?' + query).status_code == 400


def test_database_filters_counts_and_pagination(author_db, monkeypatch):
    monkeypatch.setattr(audit_reader, 'db_connect', author_db)
    with author_db() as conn, conn.cursor() as cursor:
        cursor.execute('''INSERT INTO audit (user_id, action_type, affected_table, affected_record_id, action_timestamp)
            SELECT 1, 'login', 'login', n, '2026-09-10 12:00:00'::timestamp FROM generate_series(1, 27) n''')
        cursor.execute('''INSERT INTO audit (action_type, affected_record_id, action_timestamp)
            VALUES ('create_capstone', 99, '2026-09-11'), ('unknown', 98, '2026-09-09')''')
    conn.close()
    all_rows = audit_reader.get_audit_logs({})
    assert all_rows['total'] == 29 and len(all_rows['events']) == 25
    assert all_rows['counts'] == dict(account=27, capstone=1, workflow=0, other=1)
    assert all_rows['events'][0]['target_id'] == 99
    result = audit_reader.get_audit_logs({'category': 'account', 'start': date(2026, 9, 10), 'end': date(2026, 9, 11)}, 999)
    assert result['page'] == 2 and len(result['events']) == 2 and result['total'] == 27
    assert audit_reader.get_audit_logs({'q': 'Maria Cruz'})['total'] == 27
    assert audit_reader.get_audit_logs({'q': '99'})['total'] == 1
    assert audit_reader.get_audit_logs({'q': "%' OR 1=1 --"})['total'] == 0
    assert audit_reader.get_audit_logs({'category': 'other'})['total'] == 1
    assert audit_reader.get_audit_logs({'action': 'create_capstone'})['total'] == 1


def test_empty_results_and_inclusive_date_filter(audit_app, monkeypatch):
    def empty(filters, page):
        assert filters['start'] == date(2026, 9, 10)
        assert filters['end'] == date(2026, 9, 11)
        return dict(events=[], counts=dict(account=0, capstone=0, workflow=0, other=0), total=0, page=1, pages=1)
    monkeypatch.setattr(routes, 'get_audit_logs', empty)
    client = audit_app.test_client()
    sign_in(client)
    response = client.get('/audit-logs?start=2026-09-10&end=2026-09-10')
    assert response.status_code == 200
    assert b'No recorded activity matches' in response.data


def test_database_failure_is_not_reported_as_empty_history(audit_app, monkeypatch):
    def fail(*args):
        raise RuntimeError('private database details')
    monkeypatch.setattr(routes, 'get_audit_logs', fail)
    client = audit_app.test_client()
    sign_in(client)
    response = client.get('/audit-logs')
    assert response.status_code == 503
    assert b'private database details' not in response.data


@pytest.mark.parametrize('theme,width', [('light', 1280), ('dark', 1280), ('light', 390), ('dark', 390)])
def test_browser_theme_dialog_and_select(audit_app, page, theme, width):
    client = audit_app.test_client()
    sign_in(client)

    def handle(route):
        url = urlsplit(route.request.url)
        if url.netloc != 'audit.test':
            route.abort()
            return
        response = client.get(url.path + ('?' + url.query if url.query else ''))
        route.fulfill(status=response.status_code, body=response.data, content_type=response.content_type)

    page.route('**/*', handle)
    page.add_init_script(f"localStorage.setItem('capre-theme', '{theme}')")
    page.set_viewport_size({'width': width, 'height': 900})
    page.goto('http://audit.test/audit-logs')
    expect(page.locator('.audit-page')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    expect(page.get_by_role('combobox', name='Category', exact=True)).to_be_visible()
    page.get_by_role('combobox', name='Category', exact=True).click()
    page.get_by_role('option', name='Accounts', exact=True).click()
    expect(page.locator('#audit-category')).to_have_value('account')
    page.get_by_role('button', name='View details', exact=False).click()
    expect(page.get_by_role('dialog')).to_be_visible()
    assert page.get_by_role('dialog').evaluate('(node) => { const r = node.getBoundingClientRect(); return r.x >= 0 && r.y >= 0 && r.right <= innerWidth && r.bottom <= innerHeight; }')
    page.keyboard.press('Escape')
    expect(page.get_by_role('dialog')).not_to_be_visible()
    page.get_by_role('button', name='View details', exact=False).click()
    page.get_by_role('button', name='Close', exact=True).click()
    expect(page.get_by_role('dialog')).not_to_be_visible()
    page.locator('.audit-note').first.scroll_into_view_if_needed()
    page.screenshot(path=str(ROOT / '.pytest_cache' / f'audit-{theme}-{width}.png'), full_page=True)
    page.evaluate("document.querySelector('#page-content').replaceChildren()")
    expect(page.locator('.audit-page, .audit-dialog')).to_have_count(0)
