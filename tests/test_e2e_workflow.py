"""
Playwright E2E test for CAPRE core user workflow.
Install:  pip install pytest-playwright && playwright install
Run:      pytest tests/test_e2e_workflow.py --headed (or headless for CI).
The fixture starts its own loopback server and disposable PostgreSQL database.
"""

import re
from contextlib import closing
from threading import Thread

import pytest
from playwright.sync_api import Page, expect
from werkzeug.serving import make_server

from app.db import connection
from app.utils.auth_utils import load_current_user
from tests.test_original_branch_features import feature_app, pdf_bytes
from tests.test_roster_signup_revision import (
    empty_database, isolated_database, register, revision_db, upgrade, PASSWORD,
)


@pytest.fixture
def live_server(feature_app, revision_db, monkeypatch):
    upgrade()
    register(revision_db, 'student')
    with closing(revision_db()) as conn, conn.cursor() as cursor:
        cursor.execute("INSERT INTO program (program_name, program_code) VALUES ('E2E Program', 'E2E') RETURNING program_id")
        program_id = cursor.fetchone()[0]
        cursor.execute("INSERT INTO specialization (specialization_name, specialization_code) VALUES ('E2E Track', 'E2E') RETURNING specialization_id")
        specialization_id = cursor.fetchone()[0]
        cursor.execute("""INSERT INTO capstone (capstone_title, capstone_year, is_archived, program_id, specialization_id)
                          VALUES ('Test Capstone Research', 2026, FALSE, %s, %s)""", (program_id, specialization_id))
        conn.commit()

    class TestPool:
        def getconn(self):
            return revision_db()

        def putconn(self, conn, **kwargs):
            conn.close()

    # Every imported db_connect uses this isolated pool; no app DB credentials.
    monkeypatch.setattr(connection, '_get_pool', lambda: TestPool())
    feature_app.config.update(WTF_CSRF_ENABLED=True, SESSION_COOKIE_SECURE=False)
    feature_app.before_request(load_current_user)
    server = make_server('127.0.0.1', 0, feature_app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_signin_search_logout(page: Page, live_server, revision_db):
    page.route(re.compile(r'^https://'), lambda route: route.abort())
    # 1. Open login page
    page.goto(f"{live_server}/signin")
    expect(page).to_have_url(re.compile(r".*signin"))

    # 2. Sign in with the active account created in the isolated database.
    page.fill("input[name='username']", "student")
    page.fill("input[name='password']", PASSWORD)

    # 3. Submit sign in
    page.click("button[type='submit']")
    page.wait_for_load_state("networkidle")

    # 4. Search the archive
    page.goto(f"{live_server}/archive")
    page.fill('#archive-search', "capstone")
    page.press('#archive-search', "Enter")
    page.wait_for_load_state("networkidle")

    results = page.locator(".archive-card")
    expect(results.first).to_be_visible(timeout=5000)
    expect(results.first).to_contain_text('Test Capstone Research')

    # 5. Log out
    page.click("button.logout")
    page.wait_for_load_state("networkidle")
    expect(page).to_have_url(re.compile(r".*(signin|/)$"))
    page.goto(f'{live_server}/archive')
    expect(page).to_have_url(re.compile(r'.*/signin$'))
    with closing(revision_db()) as conn, conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM audit WHERE action_type = 'logout' AND affected_table = 'user'")
        assert cursor.fetchone()[0] == 1


def test_signup_validation(page: Page, browser, live_server, revision_db):
    page.route(re.compile(r'^https://'), lambda route: route.abort())
    page.goto(f"{live_server}/signup")

    # The current signup wizard requires a COR before leaving its first step.
    page.locator('[data-signup-next]').click()
    expect(page.locator('#signup-step-error')).to_have_text('Upload your COR PDF to continue.')
    expect(page.locator('[data-signup-step]').first).to_be_visible()
    expect(page.locator('[data-signup-step]').nth(1)).to_be_hidden()

    # Also retain the original invalid-ID check through the server-side form.
    with browser.new_context(java_script_enabled=False) as context:
        form = context.new_page()
        form.route(re.compile(r'^https://'), lambda route: route.abort())
        form.goto(f'{live_server}/signup')
        form.locator('#cor').set_input_files(dict(name='cor.pdf', mimeType='application/pdf', buffer=pdf_bytes()))
        for name, value in dict(student_no='INVALID123', first_name='New', last_name='Student',
                                username='newuser', password=PASSWORD, confirm_password=PASSWORD,
                                email='newuser@example.com').items():
            form.locator('#' + name).fill(value)
        form.locator('#preferred_contact').select_option('email')
        form.locator('#accept_terms').check()
        form.locator('#signup-submit').click()
        expect(form.get_by_text('University number format not recognized', exact=True)).to_be_visible()
    with closing(revision_db()) as conn, conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM contact WHERE contact_value = 'newuser@example.com'")
        assert cursor.fetchone()[0] == 0
