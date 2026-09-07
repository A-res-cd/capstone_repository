from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit

from flask import Flask, g, session
from flask_wtf.csrf import CSRFProtect
from werkzeug.serving import make_server
import pytest

from app.db import capstoners, capstones, qol, requests as requests_db
from app.test.test_author_account_links import author_db, author_postgres, ADVISER, AUTHOR

ROOT = Path(__file__).resolve().parents[2]
pages = import_module("app.routes.pages")
admin = import_module("app.routes.admin")
main = import_module("app.routes.main")


@pytest.fixture
def capstoner_db(author_db, monkeypatch):
    with author_db() as conn, conn.cursor() as cursor:
        cursor.execute("DELETE FROM request WHERE request_type = 'capstoner'")
        cursor.execute('''
            INSERT INTO "user" (user_id, role_id, user_first_name, user_last_name, account_status)
            VALUES (3, 3, 'Amy', 'Admin', 'active'), (4, 4, 'Jane', 'Professor', 'active'),
                   (5, 4, 'John', 'Professor', 'active'), (6, 2, 'Faye', 'Faculty', 'active'),
                   (7, 1, 'Pat', 'Pending', 'pending');
        ''')
    conn.close()
    monkeypatch.setattr(capstoners, "db_connect", author_db)
    monkeypatch.setattr(qol, "db_connect", author_db)
    monkeypatch.setattr(requests_db, "db_connect", author_db)
    return author_db


def query(connect, sql, params=()):
    with connect() as conn, conn.cursor() as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall() if cursor.description else []
    conn.close()
    return rows


def unlinked_credit():
    assert capstones.set_capstone_people(1, [dict(AUTHOR, user_id=None)], ADVISER)[0]
    return capstones.get_capstone_people(1)[0]["author_id"]


def test_registration_approval_is_not_login_role_or_capstone_assignment(capstoner_db):
    assert capstoners.submit_capstoner_registration(1, "Our capstone: archive search; adviser: Jane.") == (True, None)
    registration = capstoners.get_capstoner_registration(1)
    assert registration["request_status"] == "pending"
    assert len(capstoners.get_pending_capstoners()) == 1
    assert not capstoners.submit_capstoner_registration(1, "Duplicate")[0]
    assert capstoners.review_capstoner_registration(registration["request_id"], "approved", "Verified with adviser", 4)[0]
    assert capstoners.get_capstoner_registration(1)["request_status"] == "approved"
    assert query(capstoner_db, 'SELECT role_id, account_status FROM "user" WHERE user_id = 1') == [(1, "active")]
    assert query(capstoner_db, "SELECT COUNT(*) FROM capauth") == [(0,)]
    assert capstones.get_user_authored_capstones(1) == []
    assert not capstoners.submit_capstoner_registration(1, "Already approved")[0]
    assert not capstoners.review_capstoner_registration(registration["request_id"], "rejected", "Stale form", 5)[0]
    alerts, unread = qol.get_user_notification_summary(1)
    assert unread == 1 and alerts[0]["request_type"] == "capstoner"
    assert qol.get_user_notification_summary(2) == ([], 0)
    assert qol.mark_all_notifications_read(1)
    assert qol.get_user_notification_summary(1)[1] == 0


def test_rejection_feedback_reapplication_and_registration_validation(capstoner_db):
    for reason in ("", "   ", "x" * 2001):
        assert not capstoners.submit_capstoner_registration(1, reason)[0]
    assert not capstoners.submit_capstoner_registration(7, "Account still pending")[0]
    assert capstoners.submit_capstoner_registration(1, "Capstone details")[0]
    request_id = capstoners.get_capstoner_registration(1)["request_id"]
    assert not capstoners.review_capstoner_registration(request_id, "rejected", "", 4)[0]
    assert not capstoners.review_capstoner_registration(request_id, "anything", "", 4)[0]
    assert capstoners.review_capstoner_registration(request_id, "rejected", "Confirm your adviser first.", 4)[0]
    assert capstoners.get_capstoner_registration(1)["status_reason"] == "Confirm your adviser first."
    assert capstoners.submit_capstoner_registration(1, "Corrected capstone details")[0]
    assert capstoners.get_capstoner_registration(1)["request_status"] == "pending"


@pytest.mark.parametrize("reviewer", [None, 1, 3, 6, 7, 99])
def test_non_professors_cannot_review_or_assign(capstoner_db, reviewer):
    credit = unlinked_credit()
    assert capstoners.submit_capstoner_registration(2, "Details")[0]
    request_id = capstoners.get_capstoner_registration(2)["request_id"]
    assert not capstoners.review_capstoner_registration(request_id, "approved", "", reviewer)[0]
    assert not capstoners.assign_capstoner_credit(1, credit, 2, reviewer)[0]
    assert capstoners.get_capstoner_registration(2)["request_status"] == "pending"
    assert capstones.get_capstone_people(1)[0]["user_id"] is None


def test_professor_cannot_self_approve_or_self_assign(capstoner_db):
    credit = unlinked_credit()
    assert capstoners.submit_capstoner_registration(4, "Professor's own capstone")[0]
    request_id = capstoners.get_capstoner_registration(4)["request_id"]
    assert not capstoners.review_capstoner_registration(request_id, "approved", "", 4)[0]
    assert not capstoners.assign_capstoner_credit(1, credit, 4, 4)[0]
    assert capstoners.review_capstoner_registration(request_id, "approved", "", 5)[0]


@pytest.mark.parametrize("prior_status", [None, "pending", "rejected", "approved"])
def test_direct_assignment_verifies_registration_and_links_only_exact_credit(capstoner_db, prior_status):
    credit = unlinked_credit()
    if prior_status:
        assert capstoners.submit_capstoner_registration(1, "Capstone details")[0]
        if prior_status != "pending":
            registration = capstoners.get_capstoner_registration(1)
            assert capstoners.review_capstoner_registration(registration["request_id"], prior_status, "Checked", 4)[0]
    assert capstoners.assign_capstoner_credit(1, credit, 1, 4) == (True, None)
    assert capstoners.get_capstoner_registration(1)["request_status"] == "approved"
    assert capstoners.get_capstoner_registration(2) is None
    assert [work["capstone_id"] for work in capstones.get_user_authored_capstones(1)] == [1]
    assert capstones.get_user_authored_capstones(2) == []
    assert query(capstoner_db, "SELECT COUNT(*) FROM audit WHERE action_type = 'assign_capstoner_credit'") == [(1,)]
    assert not capstoners.assign_capstoner_credit(1, credit, 2, 4)[0]
    assert capstoners.get_capstoner_registration(2) is None


def test_direct_assignment_isolates_shared_credits_and_rejects_bad_targets(capstoner_db):
    credit = unlinked_credit()
    query(capstoner_db, "INSERT INTO capauth VALUES (2, %s, 'Author', 1)", (credit,))
    adviser = capstones.get_capstone_people(1)[1]["author_id"]
    for capstone_id, author_id, user_id in [(99, credit, 1), (3, credit, 1), (1, 99, 1), (1, adviser, 1), (1, credit, 7)]:
        assert not capstoners.assign_capstoner_credit(capstone_id, author_id, user_id, 4)[0]
    assert capstoners.assign_capstoner_credit(1, credit, 1, 4)[0]
    assert capstones.get_capstone_people(1)[0]["author_id"] != credit
    assert capstones.get_capstone_people(2)[0]["user_id"] is None
    assert capstoners.assign_capstoner_credit(2, credit, 2, 4)[0]


def test_repository_requires_approval_and_cannot_overwrite_existing_account(capstoner_db):
    assert not capstones.set_capstone_people(1, [AUTHOR], ADVISER)[0]
    credit = unlinked_credit()
    assert capstones.get_author_account_choices() == []
    assert capstoners.assign_capstoner_credit(1, credit, 1, 4)[0]
    before = capstones.get_capstone_people(1)
    author = dict(AUTHOR, author_id=credit, user_id=2)
    assert not capstones.set_capstone_people(1, [author], ADVISER)[0]
    assert capstones.get_capstone_people(1) == before
    assert not capstones.set_capstone_people(2, [AUTHOR], ADVISER, acting_user_id=1)[0]


def test_capstoner_review_cannot_decide_an_account_verification_request(capstoner_db):
    request_id = query(capstoner_db, """
        INSERT INTO request (user_id, request_type, request_status)
        VALUES (7, 'verification_student', 'pending') RETURNING request_id
    """)[0][0]
    assert not capstoners.review_capstoner_registration(request_id, "approved", "", 4)[0]
    assert query(capstoner_db, 'SELECT account_status FROM "user" WHERE user_id = 7') == [("pending",)]
    assert capstoners.get_pending_capstoners() == []


def test_manuscript_handlers_cannot_bypass_professor_review(capstoner_db):
    assert capstoners.submit_capstoner_registration(1, "Capstone details")[0]
    request_id = capstoners.get_capstoner_registration(1)["request_id"]
    assert not requests_db.review_request(request_id, "approved", "", 3)[0]
    assert not requests_db.cancel_manuscript_request(request_id, 1)[0]
    assert capstoners.get_capstoner_registration(1)["request_status"] == "pending"


def test_concurrent_submissions_and_decisions_are_single_winner(capstoner_db):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: capstoners.submit_capstoner_registration(1, "Concurrent request"), range(2)))
    assert sum(ok for ok, _ in results) == 1
    request_id = capstoners.get_capstoner_registration(1)["request_id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda reviewer: capstoners.review_capstoner_registration(request_id, "approved", "", reviewer), [4, 5]))
    assert sum(ok for ok, _ in results) == 1


def test_concurrent_author_claims_do_not_overwrite_or_approve_loser(capstoner_db):
    credit = unlinked_credit()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda user: capstoners.assign_capstoner_credit(1, credit, user, 4), [1, 2]))
    assert sum(ok for ok, _ in results) == 1
    assert query(capstoner_db, "SELECT COUNT(*) FROM request WHERE request_type = 'capstoner' AND request_status = 'approved'") == [(1,)]


def test_registration_migration_is_idempotent_and_makes_no_claims(capstoner_db):
    migration = (ROOT / "migrations/20260907_capstoner_registration.sql").read_text(encoding="utf-8")
    query(capstoner_db, migration)
    query(capstoner_db, migration)
    assert capstoners.get_capstoner_registration(1) is None
    assert query(capstoner_db, "SELECT COUNT(*) FROM capauth") == [(0,)]


@pytest.fixture
def workflow_app(capstoner_db, monkeypatch):
    app = Flask(__name__, template_folder=str(ROOT / "app/templates"), static_folder=str(ROOT / "app/static"))
    app.config.update(SECRET_KEY="capstoner-test", TESTING=True, WTF_CSRF_ENABLED=False)
    CSRFProtect(app)
    app.register_blueprint(main.main)
    app.register_blueprint(pages.pages)
    app.register_blueprint(admin.admin)

    @app.before_request
    def current_user():
        user_id = session.get("user_id")
        rows = query(capstoner_db, 'SELECT role_id FROM "user" WHERE user_id = %s', (user_id,))
        g.user = {"role_id": rows[0][0]} if rows else None

    def profile(user_id):
        row = query(capstoner_db, 'SELECT user_first_name, user_last_name, account_status FROM "user" WHERE user_id = %s', (user_id,))[0]
        return {"user_first_name": row[0], "user_last_name": row[1], "account_status": row[2], "role_name": "Student"}

    monkeypatch.setattr(pages, "get_own_profile", profile)
    monkeypatch.setattr(pages, "get_user_contacts", lambda _: [])
    return app


def sign_in(client, user_id):
    with client.session_transaction() as state:
        state["user_id"] = user_id
    if hasattr(client, "browser_context"):
        client.browser_context.add_cookies([{
            "name": "session", "value": client.get_cookie("session").value,
            "url": client.browser_url,
        }])


def test_profile_professor_review_and_direct_assignment_routes(workflow_app):
    credit = unlinked_credit()
    with workflow_app.test_client() as client:
        sign_in(client, 1)
        assert b"Register as Capstoner" in client.get("/profile").data
        assert client.post("/profile/capstoner", data={"reason": "Archive search project", "user_id": "2"}).status_code == 302
        pending = client.get("/profile").data
        assert b"waiting for a capstone professor" in pending
        assert b"Register as Capstoner" not in pending
        request_id = capstoners.get_capstoner_registration(1)["request_id"]
        assert capstoners.get_capstoner_registration(2) is None
        assert client.get("/capstoners").status_code == 302
        assert client.post(f"/capstoners/review/{request_id}", data={"decision": "approved"}).status_code == 302
        assert capstoners.get_capstoner_registration(1)["request_status"] == "pending"
        sign_in(client, 4)
        assert b"Archive search project" in client.get("/capstoners").data
        assert client.post(f"/capstoners/review/{request_id}", data={"decision": "approved"}).status_code == 302
        assert client.post("/capstoners/assign", data={"user_id": "1", "credit": f"1:{credit}"}).status_code == 400
        assert client.post("/capstoners/assign", data={"user_id": "1", "credit": f"1:{credit}", "confirmed": "y"}).status_code == 302
        sign_in(client, 1)
        result = client.get("/profile").data
        assert b"You are an approved capstoner" in result and b"Linked Work" in result


def test_forms_require_csrf_and_feedback_is_escaped(workflow_app):
    with workflow_app.test_client() as client:
        sign_in(client, 1)
        assert client.post("/profile/capstoner", data={"reason": "<script>unsafe()</script>"}).status_code == 302
        sign_in(client, 4)
        page = client.get("/capstoners").data
        assert b"&lt;script&gt;unsafe()&lt;/script&gt;" in page
        assert b"<script>unsafe()</script>" not in page
    workflow_app.config["WTF_CSRF_ENABLED"] = True
    with workflow_app.test_client() as client:
        for user_id, endpoint in [(1, "/profile/capstoner"), (4, "/capstoners/assign"), (4, "/capstoners/review/1")]:
            sign_in(client, user_id)
            assert client.post(endpoint, data={"reason": "test", "decision": "approved"}).status_code == 400


@pytest.fixture
def workflow_browser(workflow_app, page):
    # Real local HTTP exercises browser redirects and cookies without sharing
    # Flask request contexts with Playwright's routing greenlets.
    workflow_app.config["WTF_CSRF_ENABLED"] = True
    client = workflow_app.test_client()
    server = make_server("127.0.0.1", 0, workflow_app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client.browser_url = f"http://127.0.0.1:{server.server_port}"
    client.browser_context = page.context
    page.route("**/*", lambda route: route.continue_()
               if urlsplit(route.request.url).netloc == f"127.0.0.1:{server.server_port}" else route.abort())
    try:
        yield page, client
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_browser_registration_review_and_author_assignment(workflow_browser):
    from playwright.sync_api import expect

    credit = unlinked_credit()
    page, client = workflow_browser
    sign_in(client, 1)
    page.goto(f"{client.browser_url}/profile")
    page.get_by_label("Capstone details", exact=True).fill("Archive search project, adviser Jane.")
    page.get_by_role("button", name="Register as Capstoner", exact=True).click()
    expect(page.locator("#capstoner-registration")).to_contain_text("waiting for a capstone professor")
    sign_in(client, 4)
    page.goto(f"{client.browser_url}/capstoners")
    page.get_by_role("button", name="Approve registration").click()
    expect(page.locator(".capstoner-review__requests")).to_contain_text("No capstoner registrations waiting")
    sign_in(client, 1)
    page.goto(f"{client.browser_url}/profile")
    expect(page.locator("#capstoner-registration")).to_contain_text("approved capstoner")
    expect(page.locator(".profile-work")).to_have_count(0)
    sign_in(client, 4)
    page.goto(f"{client.browser_url}/capstoners")
    page.get_by_label("User account", exact=True).select_option("1")
    page.get_by_label("Unlinked author credit", exact=True).select_option(f"1:{credit}")
    page.locator("#confirmed").check()
    page.get_by_role("button", name="Verify capstoner & link author").click()
    expect(page.locator(".flash-list")).to_contain_text("Author credit linked")
    sign_in(client, 1)
    page.goto(f"{client.browser_url}/profile")
    expect(page.locator(".profile-work")).to_have_count(1)
    expect(page.locator(".profile-work")).to_contain_text("Linked Work")


@pytest.mark.parametrize("width,dark", [(1322, False), (768, False), (390, False), (320, False), (1322, True), (390, True)])
def test_capstoner_forms_follow_paper_theme_without_overflow(workflow_browser, width, dark, tmp_path):
    from playwright.sync_api import expect

    unlinked_credit()
    assert capstoners.submit_capstoner_registration(2, "Archive search project. " + "Details" * 50)[0]
    page, client = workflow_browser
    page.set_viewport_size({"width": width, "height": 850})
    for user_id, path in [(1, "profile"), (4, "capstoners")]:
        sign_in(client, user_id)
        page.goto(f"{client.browser_url}/{path}")
        if dark:
            page.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
        expect(page.locator(".profile-paper")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        for field in page.locator(".capstoner-form textarea, .capstoner-form select, .capstoner-form button").all():
            assert field.evaluate("el => el.getBoundingClientRect().right <= window.innerWidth")
        assert page.locator(".profile-paper").evaluate("el => getComputedStyle(el, '::before').width") == "8px"
        page.screenshot(path=str(tmp_path / f"capstoner-{path}-{width}-{'dark' if dark else 'light'}.png"), full_page=True)
