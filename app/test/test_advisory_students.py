"""Professor-owned rosters, tested only against temporary PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module

from flask import g, session
import psycopg2
import pytest

from app.db import advisories, capstoners, capstones
from app.test.test_author_account_links import author_db, author_postgres, ADVISER, AUTHOR
from app.test.test_capstoner_registration import (
    ROOT, capstoner_db, query, sign_in, workflow_app, workflow_browser,
)

faculty = import_module("app.routes.faculty")
BASE = "/faculty/advisory-students"


def choose_group(modal, group_id):
    option = modal.locator(f'#group_id option[value="{group_id}"]').text_content()
    modal.get_by_role("combobox", name="Advisory group", exact=True).click()
    modal.get_by_role("option", name=option, exact=True).click()


@pytest.fixture
def advisory_db(capstoner_db, monkeypatch):
    monkeypatch.setattr(advisories, "db_connect", capstoner_db)
    query(capstoner_db, 'UPDATE "user" SET university_no = %s WHERE user_id = 1', ("2026-001",))
    return capstoner_db


@pytest.fixture
def advisory_groups(advisory_db):
    groups = {}
    for professor_id in (4, 5):
        assert advisories.create_advisory_group(professor_id, "Archive Search Team")[0]
        groups[professor_id] = advisories.get_advisory_groups(professor_id)[0]["group_id"]
    return groups


@pytest.fixture
def capacity_students(advisory_db):
    query(advisory_db, '''
        INSERT INTO "user" (user_id, role_id, user_first_name, user_last_name, account_status)
        VALUES (8, 1, 'Student', 'Eight', 'active'), (9, 1, 'Student', 'Nine', 'active'),
               (10, 1, 'Student', 'Ten', 'active'), (11, 1, 'Student', 'Eleven', 'active');
    ''')
    return [1, 2, 8, 9, 10, 11]


@pytest.fixture
def advisory_app(workflow_app, advisory_db):
    workflow_app.register_blueprint(faculty.faculty)
    workflow_app.register_blueprint(import_module("app.routes.authentication").auth)

    @workflow_app.before_request
    def professor_details():
        if g.user and g.user["role_id"] == 4:
            row = query(advisory_db, 'SELECT user_first_name, user_last_name FROM "user" WHERE user_id = %s',
                        (session["user_id"],))[0]
            g.user.update(user_first_name=row[0], user_last_name=row[1], role_name="Capstone Professor")

    return workflow_app


@pytest.fixture
def advisory_browser(advisory_app, workflow_browser):
    return workflow_browser


def test_roster_is_explicit_and_never_registers_or_claims_works(advisory_db):
    assert capstoners.submit_capstoner_registration(2, "Details")[0]
    request_id = capstoners.get_capstoner_registration(2)["request_id"]
    assert capstoners.review_capstoner_registration(request_id, "approved", "Verified", 4)[0]
    assert advisories.get_advisory_roster(4) == []
    assert [s["user_id"] for s in advisories.get_available_advisory_students(4)] == [1, 2]
    assert not advisories.add_advisory_student(4, 1, None)[0]
    assert advisories.create_advisory_group(4, "Archive Search Team")[0]
    group_id = advisories.get_advisory_groups(4)[0]["group_id"]
    assert advisories.add_advisory_student(4, 1, group_id) == (True, None)
    student = advisories.get_advisory_roster(4)[0]
    assert student["user_id"] == 1 and student["capstoner_status"] == "unregistered" and student["works"] == []
    assert capstoners.get_capstoner_registration(1) is None
    assert query(advisory_db, "SELECT COUNT(*) FROM capauth") == [(0,)]
    assert query(advisory_db, 'SELECT role_id, account_status FROM "user" WHERE user_id = 1') == [(1, "active")]
    assert advisories.get_advisory_roster(5) == []
    assert [s["user_id"] for s in advisories.get_available_advisory_students(4)] == [2]


def test_same_name_and_coadviser_rosters_stay_independent(advisory_db, advisory_groups):
    assert advisories.add_advisory_student(4, 1, advisory_groups[4])[0]
    assert advisories.add_advisory_student(5, 2, advisory_groups[5])[0]
    assert not advisories.remove_advisory_student(5, 1)[0]
    assert advisories.add_advisory_student(5, 1, advisory_groups[5])[0]
    assert advisories.remove_advisory_student(4, 1)[0]
    assert advisories.get_advisory_roster(4) == []
    assert [s["user_id"] for s in advisories.get_advisory_roster(5)] == [1, 2]
    assert advisories.add_advisory_student(4, 1, advisory_groups[4])[0]  # Recoverable membership removal.


@pytest.mark.parametrize("actor", [None, 1, 3, 6, 7, 99])
def test_non_professors_cannot_read_or_change_rosters(advisory_db, actor):
    assert not advisories.add_advisory_student(actor, 2, None)[0]
    assert not advisories.remove_advisory_student(actor, 2)[0]
    for read in (advisories.get_advisory_roster, advisories.get_available_advisory_students, advisories.get_advisory_groups):
        with pytest.raises(PermissionError):
            read(actor)
    assert not advisories.create_advisory_group(actor, "Unauthorized")[0]
    assert not advisories.rename_advisory_group(actor, 1, "Unauthorized")[0]


@pytest.mark.parametrize("student", [None, 3, 4, 5, 6, 7, 99])
def test_only_verified_students_can_be_added(advisory_db, advisory_groups, student):
    assert not advisories.add_advisory_student(4, student, advisory_groups[4])[0]
    assert advisories.get_advisory_roster(4) == []


def test_latest_registration_real_author_works_and_safe_removal(advisory_db, advisory_groups):
    assert capstoners.submit_capstoner_registration(1, "Project details")[0]
    request_id = capstoners.get_capstoner_registration(1)["request_id"]
    assert capstoners.review_capstoner_registration(request_id, "rejected", "Confirm details", 4)[0]
    assert advisories.add_advisory_student(4, 1, advisory_groups[4])[0]
    assert advisories.get_advisory_roster(4)[0]["capstoner_status"] == "rejected"
    assert capstoners.submit_capstoner_registration(1, "Corrected details")[0]
    assert advisories.get_advisory_roster(4)[0]["capstoner_status"] == "pending"
    request_id = capstoners.get_capstoner_registration(1)["request_id"]
    assert capstoners.review_capstoner_registration(request_id, "approved", "", 4)[0]
    assert capstones.set_capstone_people(1, [AUTHOR], ADVISER)[0]
    assert capstones.set_capstone_people(3, [AUTHOR], ADVISER)[0]
    assert capstones.set_capstone_people(4, [], ADVISER)[0]
    query(advisory_db, "UPDATE author SET user_id = 1 WHERE author_id IN (SELECT author_id FROM capauth WHERE capstone_id = 4)")
    student = advisories.get_advisory_roster(4)[0]
    assert student["capstoner_status"] == "approved"
    assert [w["capstone_id"] for w in student["works"]] == [1]
    before = capstones.get_capstone_people(1)
    assert advisories.remove_advisory_student(4, 1)[0]
    assert capstones.get_capstone_people(1) == before
    assert capstoners.get_capstoner_registration(1)["request_status"] == "approved"
    assert query(advisory_db, 'SELECT COUNT(*) FROM "user" WHERE user_id = 1') == [(1,)]
    assert query(advisory_db, "SELECT action_type FROM audit WHERE affected_table = 'advisory_student' ORDER BY action_timestamp") == [
        ("add_advisory_student",), ("remove_advisory_student",),
    ]


def test_duplicates_and_concurrent_submissions_create_one_audit(advisory_db, advisory_groups):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: advisories.add_advisory_student(4, 1, advisory_groups[4]), range(2)))
    assert sum(ok for ok, _ in results) == 1
    assert len(advisories.get_advisory_roster(4)) == 1
    assert query(advisory_db, "SELECT COUNT(*) FROM audit WHERE action_type = 'add_advisory_student'") == [(1,)]


def test_audit_failure_rolls_back_membership(advisory_db, advisory_groups, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("Audit unavailable")

    monkeypatch.setattr(advisories, "log_audit", fail)
    assert not advisories.add_advisory_student(4, 1, advisory_groups[4])[0]
    assert advisories.get_advisory_roster(4) == []


def test_migration_is_idempotent_and_does_not_enroll_accounts(advisory_db):
    migration = (ROOT / "migrations/20260908_advisory_students.sql").read_text(encoding="utf-8")
    query(advisory_db, migration)
    query(advisory_db, migration)
    assert advisories.get_advisory_roster(4) == []
    assert capstoners.get_capstoner_registration(1) is None


def test_groups_are_required_owned_and_one_per_student(advisory_db, advisory_groups):
    assert not advisories.add_advisory_student(4, 1, None)[0]
    assert not advisories.add_advisory_student(4, 1, 999)[0]
    assert not advisories.add_advisory_student(4, 1, advisory_groups[5])[0]
    assert advisories.add_advisory_student(4, 1, advisory_groups[4])[0]
    assert advisories.create_advisory_group(4, "Second team")[0]
    second_group = advisories.get_advisory_groups(4)[1]["group_id"]
    assert not advisories.add_advisory_student(4, 1, second_group)[0]
    assert advisories.get_advisory_roster(4)[0]["group_id"] == advisory_groups[4]
    with pytest.raises(psycopg2.errors.ForeignKeyViolation):
        query(advisory_db, "INSERT INTO advisory_student (professor_user_id, student_user_id, group_id) VALUES (4, 2, %s)",
              (advisory_groups[5],))
    with pytest.raises(psycopg2.errors.NotNullViolation):
        query(advisory_db, "INSERT INTO advisory_student (professor_user_id, student_user_id) VALUES (4, 2)")


@pytest.mark.parametrize("name", ["", "   ", "\n\t", "x" * 101])
def test_invalid_group_names_never_change_groups(advisory_db, advisory_groups, name):
    assert not advisories.create_advisory_group(4, name)[0]
    assert not advisories.rename_advisory_group(4, advisory_groups[4], name)[0]
    assert advisories.get_advisory_groups(4) == [{"group_id": advisory_groups[4], "group_name": "Archive Search Team", "student_count": 0}]


def test_group_rename_keeps_membership_and_only_owner_can_rename(advisory_db, advisory_groups):
    assert advisories.add_advisory_student(4, 1, advisory_groups[4])[0]
    before = advisories.get_advisory_roster(4)
    assert not advisories.rename_advisory_group(5, advisory_groups[4], "Take over")[0]
    assert not advisories.rename_advisory_group(4, None, "Missing group")[0]
    assert not advisories.rename_advisory_group(4, 999, "Unknown group")[0]
    assert advisories.rename_advisory_group(4, advisory_groups[4], "  Team CAPRE  ")[0]
    assert advisories.get_advisory_roster(4) == before
    assert advisories.get_advisory_groups(4)[0]["group_name"] == "Team CAPRE"
    assert advisories.get_advisory_groups(5)[0]["group_name"] == "Archive Search Team"
    assert capstoners.get_capstoner_registration(1) is None
    assert query(advisory_db, "SELECT COUNT(*) FROM capauth") == [(0,)]
    assert query(advisory_db, "SELECT old_values, new_values FROM audit WHERE action_type = 'rename_advisory_group'") == [
        ("Archive Search Team", "Team CAPRE"),
    ]


def test_group_names_are_unique_per_professor_and_rename_collision_rolls_back(advisory_db, advisory_groups):
    assert not advisories.create_advisory_group(4, "  ARCHIVE SEARCH TEAM  ")[0]
    assert advisories.create_advisory_group(4, "Second team")[0]
    group_id = advisories.get_advisory_groups(4)[1]["group_id"]
    assert not advisories.rename_advisory_group(4, group_id, "archive search team")[0]
    assert advisories.get_advisory_groups(4)[1]["group_name"] == "Second team"
    assert advisories.create_advisory_group(5, "Second team")[0]
    assert query(advisory_db, "SELECT COUNT(*) FROM audit WHERE action_type = 'rename_advisory_group'") == [(0,)]


def test_duplicate_group_creation_is_atomic(advisory_db):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: advisories.create_advisory_group(4, "Same team"), range(2)))
    assert sum(ok for ok, _ in results) == 1
    assert len(advisories.get_advisory_groups(4)) == 1
    assert query(advisory_db, "SELECT COUNT(*) FROM audit WHERE action_type = 'create_advisory_group'") == [(1,)]


def test_group_audit_failure_rolls_back_create_and_rename(advisory_db, advisory_groups, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("Audit unavailable")

    monkeypatch.setattr(advisories, "log_audit", fail)
    assert not advisories.create_advisory_group(4, "Lost team")[0]
    assert not advisories.rename_advisory_group(4, advisory_groups[4], "Lost name")[0]
    assert advisories.get_advisory_groups(4) == [{"group_id": advisory_groups[4], "group_name": "Archive Search Team", "student_count": 0}]


def test_group_migration_is_idempotent_without_creating_empty_groups(advisory_db):
    migration = (ROOT / "migrations/20260908_advisory_groups.sql").read_text(encoding="utf-8")
    query(advisory_db, migration)
    query(advisory_db, migration)
    assert advisories.get_advisory_groups(4) == []
    assert advisories.get_advisory_roster(4) == []


def test_group_migration_preserves_legacy_rosters_and_renames(advisory_db):
    # Reconstruct the previous schema only inside this isolated test database.
    query(advisory_db, """
        ALTER TABLE advisory_student DROP COLUMN group_id;
        DROP TABLE advisory_group;
        INSERT INTO advisory_student (professor_user_id, student_user_id, added_at)
        VALUES (4, 1, '2026-09-07T12:00:00Z'), (4, 2, '2026-09-07T12:00:00Z'), (5, 1, '2026-09-07T12:00:00Z');
    """)
    before = query(advisory_db, "SELECT professor_user_id, student_user_id, added_at FROM advisory_student ORDER BY 1, 2")
    migration = (ROOT / "migrations/20260908_advisory_groups.sql").read_text(encoding="utf-8")
    query(advisory_db, migration)
    group_id = advisories.get_advisory_groups(4)[0]["group_id"]
    assert advisories.get_advisory_groups(4)[0]["group_name"] == "Existing advisory students"
    assert [s["group_id"] for s in advisories.get_advisory_roster(4)] == [group_id, group_id]
    assert advisories.get_advisory_roster(5)[0]["group_id"] != group_id
    assert advisories.rename_advisory_group(4, group_id, "Renamed legacy group")[0]
    query(advisory_db, migration)
    assert advisories.get_advisory_groups(4) == [{"group_id": group_id, "group_name": "Renamed legacy group", "student_count": 2}]
    assert query(advisory_db, "SELECT professor_user_id, student_user_id, added_at FROM advisory_student ORDER BY 1, 2") == before
    assert capstoners.get_capstoner_registration(1) is None


def test_group_routes_validate_ownership_names_and_csrf(advisory_app, advisory_db, advisory_groups):
    rename_path = f"{BASE}/groups/{advisory_groups[4]}/rename"
    with advisory_app.test_client() as client:
        for path in (BASE + "/groups", rename_path):
            assert client.post(path, data={"group_name": "Blocked"}).status_code == 302
        for user_id in (1, 3, 6, 7):
            sign_in(client, user_id)
            for path in (BASE + "/groups", rename_path):
                assert client.post(path, data={"group_name": "Blocked"}).status_code == 302
        sign_in(client, 5)
        assert client.post(rename_path, data={"group_name": "Blocked", "professor_user_id": "4"}).status_code == 400
        sign_in(client, 4)
        for path in (BASE + "/groups", rename_path):
            for name in (" ", "x" * 101):
                assert client.post(path, data={"group_name": name}).status_code == 400
            assert client.get(path).status_code == 405
        assert client.post(BASE + "/add", data={"student_id": "1", "confirmed": "y"}).status_code == 400
        assert client.post(BASE + "/add", data={"student_id": "1", "group_id": advisory_groups[5], "confirmed": "y"}).status_code == 400
        assert client.post(BASE + "/groups", data={"group_name": "New team", "professor_user_id": "5"}).status_code == 302
        assert len(advisories.get_advisory_groups(5)) == 1
        assert client.post(rename_path, data={"group_name": "<script>unsafe()</script>"}).status_code == 302
        page = client.get(BASE).data
        assert b"&lt;script&gt;unsafe()&lt;/script&gt;" in page and b"<script>unsafe()</script>" not in page
        before = advisories.get_advisory_groups(4)
        advisory_app.config["WTF_CSRF_ENABLED"] = True
        for path in (BASE + "/groups", rename_path):
            assert client.post(path, data={"group_name": "No CSRF"}).status_code == 400
        assert advisories.get_advisory_groups(4) == before


def test_no_group_cannot_add_student_even_with_forged_post(advisory_app, advisory_db):
    with advisory_app.test_client() as client:
        sign_in(client, 4)
        assert b"Create a group first, or add students while creating your first group." in client.get(BASE).data
        assert client.post(BASE + "/add", data={"student_id": "1", "group_id": "1", "confirmed": "y"}).status_code == 400
    assert advisories.get_advisory_roster(4) == []
    assert advisories.get_advisory_groups(4) == []


def test_inactive_professors_blocked_changed_students_removable(advisory_app, advisory_db, advisory_groups):
    assert advisories.add_advisory_student(4, 1, advisory_groups[4])[0]
    query(advisory_db, 'UPDATE "user" SET account_status = %s WHERE user_id = 4', ("pending",))
    with advisory_app.test_client() as client:
        sign_in(client, 4)
        assert client.get(BASE).status_code == 403
        assert client.post(BASE + "/add", data={"student_id": "2", "confirmed": "y"}).status_code == 403
        assert client.post(BASE + "/1/remove", data={"confirmed": "y"}).status_code == 403
        assert client.post(BASE + "/groups", data={"group_name": "Blocked"}).status_code == 403
        assert client.post(f"{BASE}/groups/{advisory_groups[4]}/rename", data={"group_name": "Blocked"}).status_code == 403
    query(advisory_db, 'UPDATE "user" SET account_status = %s WHERE user_id = 4', ("active",))
    query(advisory_db, 'UPDATE "user" SET role_id = 2 WHERE user_id = 1')
    assert len(advisories.get_advisory_roster(4)) == 1
    assert advisories.remove_advisory_student(4, 1)[0]
    assert not advisories.add_advisory_student(4, 1, advisory_groups[4])[0]


def test_routes_require_professor_and_explicit_confirmation(advisory_app, advisory_db, advisory_groups):
    with advisory_app.test_client() as client:
        for method, path, data in [("get", BASE, {}), ("post", BASE + "/add", {"student_id": "1", "confirmed": "y"}),
                                   ("post", BASE + "/1/remove", {"confirmed": "y"})]:
            assert getattr(client, method)(path, data=data).status_code == 302
            for user_id in (1, 3, 6, 7):
                sign_in(client, user_id)
                assert getattr(client, method)(path, data=data).status_code == 302
            with client.session_transaction() as state:
                state.clear()
        sign_in(client, 4)
        assert client.post(BASE + "/add", data={"student_id": "1", "group_id": advisory_groups[4]}).status_code == 400
        assert client.post(BASE + "/add", data={"student_id": "7", "group_id": advisory_groups[4], "confirmed": "y"}).status_code == 400
        assert client.post(BASE + "/add", data={"student_id": "1", "group_id": advisory_groups[4], "confirmed": "y", "professor_user_id": "5"}).status_code == 302
        assert advisories.get_advisory_roster(5) == []
        assert client.get(BASE + "/1/remove").status_code == 405
        assert client.post(BASE + "/1/remove").status_code == 400
        assert len(advisories.get_advisory_roster(4)) == 1
        assert client.post(BASE + "/1/remove", data={"confirmed": "y"}).status_code == 302


def test_filters_escaping_navigation_and_csrf(advisory_app, advisory_db, advisory_groups):
    assert advisories.add_advisory_student(4, 1, advisory_groups[4])[0]
    assert advisories.add_advisory_student(4, 2, advisory_groups[4])[0]
    assert capstoners.submit_capstoner_registration(2, "Capstone")[0]
    query(advisory_db, 'UPDATE "user" SET user_first_name = %s WHERE user_id = 2', ("<script>bad()</script>",))
    with advisory_app.test_client() as client:
        sign_in(client, 4)
        page = client.get(BASE).data
        assert b'Advisory Students</span>' in page and b"Jane Professor" in page
        assert b"&lt;script&gt;bad()&lt;/script&gt;" in page and b"<script>bad()</script>" not in page
        page = client.get(BASE, query_string={"status": "pending"}).data
        assert b"1 of 2 students" in page and b'id="student-2"' in page and b'id="student-1"' not in page
        page = client.get(BASE, query_string={"search": "2026-001"}).data
        assert b'id="student-1"' in page and b'id="student-2"' not in page
        assert b"No students match" in client.get(BASE, query_string={"search": "missing"}).data
        advisory_app.config["WTF_CSRF_ENABLED"] = True
        assert client.post(BASE + "/add", data={"student_id": "1", "confirmed": "y"}).status_code == 400
        assert client.post(BASE + "/1/remove", data={"confirmed": "y"}).status_code == 400
        assert len(advisories.get_advisory_roster(4)) == 2


def test_browser_add_search_and_remove(advisory_browser, advisory_db):
    from playwright.sync_api import expect

    page, client = advisory_browser
    sign_in(client, 4)
    page.goto(f"{client.browser_url}{BASE}")
    expect(page.locator(".profile-empty-state")).to_contain_text("No advisory groups yet")
    expect(page.get_by_role("button", name="Add to my roster")).to_have_count(0)
    expect(page.locator(".nav-item.active")).to_contain_text("Advisory Students")
    page.get_by_role("button", name="Create a group", exact=True).first.click()
    create_modal = page.locator("#create-advisory-group-modal")
    create_modal.get_by_label("Group name", exact=True).fill("Archive Search Team")
    create_modal.locator('.advisory-picker-search').fill("2026-001")
    expect(create_modal.locator('.advisory-student-choice input[value="2"]')).to_be_hidden()
    create_modal.locator('.advisory-student-choice input[value="1"]').check()
    create_modal.get_by_label("I am assigned to advise all selected students.", exact=True).check()
    create_modal.get_by_role("button", name="Create group", exact=True).click()
    expect(page.locator(".advisory-student")).to_have_count(1)
    expect(page.locator(".advisory-student")).to_contain_text("Capstoner: Not registered")
    page.locator(".advisory-group-rename summary").click()
    page.get_by_label("New group name", exact=True).fill("Team CAPRE")
    page.get_by_role("button", name="Save group name").click()
    expect(page.locator(".advisory-group__title")).to_contain_text("Team CAPRE")
    expect(page.locator("#group_id option").filter(has_text="Team CAPRE")).to_have_count(1)
    expect(page.locator(".advisory-student")).to_have_count(1)
    page.get_by_label("Find a student").fill("absent")
    page.get_by_role("button", name="Apply filters").click()
    expect(page.locator(".profile-empty-state")).to_contain_text("No students match")
    page.get_by_role("link", name="Clear", exact=True).click()
    page.locator(".advisory-student .advisory-details summary").click()
    page.get_by_label("Remove from my roster only.", exact=True).check()
    page.get_by_role("button", name="Remove student", exact=True).click()
    expect(page.locator(".advisory-student")).to_have_count(0)
    expect(page.locator(".flash-list")).to_contain_text("Their account and capstones are unchanged")
    assert capstoners.get_capstoner_registration(1) is None
    assert advisories.get_advisory_roster(4) == []


def test_roster_panels_leave_with_page_and_groups_collapse_independently(advisory_browser, advisory_db, advisory_groups):
    from playwright.sync_api import expect

    assert advisories.add_advisory_student(4, 1, advisory_groups[4])[0]
    assert advisories.create_advisory_group(4, "Second team")[0]
    page, client = advisory_browser
    sign_in(client, 4)
    page.goto(f"{client.browser_url}{BASE}")
    expect(page.locator(".advisory-group")).to_have_count(2)
    expect(page.locator("#page-content .advisory-page > .profile-body > aside")).to_have_count(1)
    expect(page.locator(".advisory-group__body > .advisory-student")).to_be_visible()

    toggle = page.locator(".advisory-group__summary").first
    toggle.click()
    expect(page.locator(".advisory-student")).to_be_hidden()
    expect(page.locator(".advisory-group").nth(1)).to_have_attribute("open", "")
    toggle.focus()
    page.keyboard.press("Enter")
    expect(page.locator(".advisory-student")).to_be_visible()

    page.evaluate("window.advisoryNavigationCheck = true")
    page.locator('.nav-item[href="/profile"]').click()
    page.wait_for_url(f"{client.browser_url}/profile")
    assert page.evaluate("window.advisoryNavigationCheck === true")  # Actual partial navigation.
    expect(page.locator('aside[aria-label="Advisory tools"]')).to_have_count(0)
    expect(page.locator("#create-advisory-group, #add-advisory-student")).to_have_count(0)

    page.locator(f'.nav-item[href="{BASE}"]').click()
    page.wait_for_url(f"{client.browser_url}{BASE}")
    expect(page.locator('aside[aria-label="Advisory tools"]')).to_have_count(1)
    expect(page.locator("#page-content .advisory-page > .profile-body > aside")).to_have_count(1)


@pytest.mark.parametrize("width,dark", [(1322, False), (768, False), (390, False), (320, False), (1322, True), (390, True)])
def test_roster_uses_open_responsive_theme(advisory_browser, advisory_db, advisory_groups, capacity_students, width, dark, tmp_path):
    from playwright.sync_api import expect

    assert capstoners.submit_capstoner_registration(1, "Archive search project")[0]
    request_id = capstoners.get_capstoner_registration(1)["request_id"]
    assert capstoners.review_capstoner_registration(request_id, "approved", "", 4)[0]
    assert capstones.set_capstone_people(1, [AUTHOR], ADVISER)[0]
    assert advisories.add_advisory_student(4, 1, advisory_groups[4])[0]
    assert advisories.add_advisory_student(4, 2, advisory_groups[4])[0]
    page, client = advisory_browser
    page.set_viewport_size({"width": width, "height": 900})
    sign_in(client, 4)
    page.goto(f"{client.browser_url}{BASE}")
    page.evaluate("theme => document.documentElement.setAttribute('data-theme', theme)", "dark" if dark else "light")
    expect(page.locator(".profile-paper")).to_have_count(0)
    expect(page.locator(".advisory-page > .profile-body")).to_be_visible()
    expect(page.locator(".advisory-group__capacity")).to_contain_text("2 / 4 students")
    page.get_by_role("button", name="Add students", exact=True).click()
    add_modal = page.locator("#add-advisory-student-modal")
    expect(add_modal).to_be_visible()
    expect(add_modal.get_by_role("button", name="Add to my roster")).to_be_disabled()
    if dark:
        assert page.locator(".advisory-details summary").first.evaluate(
            "el => getComputedStyle(el).color === getComputedStyle(document.querySelector('.advisory-page')).color")
    choose_group(add_modal, advisory_groups[4])
    add_modal.locator('.advisory-student-choice input[value="8"]').check()
    expect(add_modal.locator("#student-selection-status")).to_contain_text("1 of 2")
    add_modal.get_by_role("button", name="Cancel").click()
    page.locator(".advisory-group-rename summary").click()
    page.locator(".advisory-student .advisory-details summary").first.click()
    expect(page.locator(".advisory-works")).to_contain_text("Linked Work")
    assert page.locator(".advisory-works a").get_attribute("href") == "/archive?search=Linked+Work"
    assert "Archived Work" not in page.locator(".advisory-students").inner_text()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert page.locator("#page-content").evaluate("el => el.scrollWidth <= el.clientWidth")
    for field in page.locator(".advisory-page input, .advisory-page select, .advisory-page button").all():
        if field.is_visible():
            assert field.evaluate("el => el.getBoundingClientRect().right <= window.innerWidth")
    assert page.locator(".advisory-group__summary").evaluate("el => getComputedStyle(el).borderTopStyle") == "dashed"
    assert page.locator(".profile-body").evaluate('''el => {
        const parent = el.parentElement;
        const style = getComputedStyle(parent);
        const available = parent.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
        return Math.abs(el.getBoundingClientRect().width - available) < 1;
    }''')
    page.locator("#page-content").evaluate("el => el.scrollTop = 0")
    page.screenshot(path=str(tmp_path / f"advisory-{width}-{'dark' if dark else 'light'}.png"), full_page=True)
    page.locator("#add-advisory-student").scroll_into_view_if_needed()
    page.screenshot(path=str(tmp_path / f"advisory-form-{width}-{'dark' if dark else 'light'}.png"), full_page=True)


def test_group_capacity_is_four_and_removing_student_reopens_space(advisory_db, advisory_groups, capacity_students):
    group_id = advisory_groups[4]
    for student_id in capacity_students[:4]:
        assert advisories.add_advisory_student(4, student_id, group_id)[0]
    ok, error = advisories.add_advisory_student(4, 10, group_id)
    assert not ok and "at most 4 students" in error
    assert advisories.get_advisory_groups(4)[0]["student_count"] == 4
    assert query(advisory_db, "SELECT COUNT(*) FROM audit WHERE action_type = 'add_advisory_student'") == [(4,)]
    assert advisories.remove_advisory_student(4, 1)[0]
    assert advisories.add_advisory_student(4, 10, group_id)[0]
    assert advisories.create_advisory_group(4, "Another team")[0]
    second_group = advisories.get_advisory_groups(4)[1]["group_id"]
    assert advisories.add_advisory_student(4, 1, second_group)[0]
    assert [group["student_count"] for group in advisories.get_advisory_groups(4)] == [4, 1]
    assert advisories.add_advisory_student(5, 1, advisory_groups[5])[0]


def test_concurrent_adds_cannot_both_take_last_group_place(advisory_db, advisory_groups, capacity_students):
    group_id = advisory_groups[4]
    for student_id in capacity_students[:3]:
        assert advisories.add_advisory_student(4, student_id, group_id)[0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda student_id: advisories.add_advisory_student(4, student_id, group_id), [9, 10]))
    assert sum(ok for ok, _ in results) == 1
    assert advisories.get_advisory_groups(4)[0]["student_count"] == 4
    assert query(advisory_db, "SELECT COUNT(*) FROM audit WHERE action_type = 'add_advisory_student'") == [(4,)]


def test_stale_form_cannot_add_fifth_student(advisory_app, advisory_db, advisory_groups, capacity_students):
    group_id = advisory_groups[4]
    for student_id in capacity_students[:3]:
        assert advisories.add_advisory_student(4, student_id, group_id)[0]
    with advisory_app.test_client() as client:
        sign_in(client, 4)
        assert b"Archive Search Team (3/4 students)" in client.get(BASE).data
        assert advisories.add_advisory_student(4, 9, group_id)[0]
        result = client.post(BASE + "/add", data={"student_id": "10", "group_id": group_id, "confirmed": "y"})
        assert result.status_code == 400 and b"maximum 4 students" in result.data
        assert b"All your groups are full" in result.data
        assert advisories.get_advisory_groups(4)[0]["student_count"] == 4
        assert advisories.remove_advisory_student(4, 1)[0]
        assert client.post(BASE + "/add", data={"student_id": "10", "group_id": group_id, "confirmed": "y"}).status_code == 302


def test_existing_oversized_groups_are_preserved_and_block_additions(advisory_app, advisory_db, advisory_groups, capacity_students):
    group_id = advisory_groups[4]
    for student_id in capacity_students[:4]:
        assert advisories.add_advisory_student(4, student_id, group_id)[0]
    # Simulate a roster saved before the application capacity rule, in the test DB only.
    query(advisory_db, "INSERT INTO advisory_student (professor_user_id, student_user_id, group_id) VALUES (4, 10, %s)", (group_id,))
    assert not advisories.add_advisory_student(4, 11, group_id)[0]
    with advisory_app.test_client() as client:
        sign_in(client, 4)
        result = client.get(BASE).data
        assert b"5 / 4 students" in result and b"Over limit" in result
        assert b"no one has been removed automatically" in result
    assert len(advisories.get_advisory_roster(4)) == 5
    assert advisories.remove_advisory_student(4, 1)[0]
    assert not advisories.add_advisory_student(4, 11, group_id)[0]
    assert advisories.remove_advisory_student(4, 2)[0]
    assert advisories.add_advisory_student(4, 11, group_id)[0]
    assert advisories.get_advisory_groups(4)[0]["student_count"] == 4


def test_multiple_student_submission_adds_each_membership_and_audit(advisory_app, advisory_db, advisory_groups, capacity_students):
    with advisory_app.test_client() as client:
        sign_in(client, 4)
        response = client.post(BASE + "/add", data={
            "group_id": advisory_groups[4], "student_id": ["1", "2", "8", "9"], "confirmed": "y",
        })
        assert response.status_code == 302
    assert {student["user_id"] for student in advisories.get_advisory_roster(4)} == {1, 2, 8, 9}
    assert query(advisory_db, "SELECT COUNT(*) FROM audit WHERE action_type = 'add_advisory_student'") == [(4,)]
    assert query(advisory_db, "SELECT COUNT(*) FROM request WHERE request_type = 'capstoner'") == [(0,)]
    assert query(advisory_db, "SELECT COUNT(*) FROM capauth") == [(0,)]
    assert advisories.get_advisory_roster(5) == []


def test_group_creation_can_atomically_add_students(advisory_db, capacity_students):
    assert advisories.create_advisory_group_with_students(4, "New Capstone Team", [1, 2, 8, 9])[0]
    group = advisories.get_advisory_groups(4)[0]
    assert group["group_name"] == "New Capstone Team"
    assert group["student_count"] == 4
    assert {student["user_id"] for student in advisories.get_advisory_roster(4)} == {1, 2, 8, 9}
    assert query(advisory_db, "SELECT COUNT(*) FROM audit WHERE action_type = 'create_advisory_group'") == [(1,)]
    assert query(advisory_db, "SELECT COUNT(*) FROM audit WHERE action_type = 'add_advisory_student'") == [(4,)]


def test_group_creation_rolls_back_when_selected_students_are_invalid(advisory_db, capacity_students):
    assert not advisories.create_advisory_group_with_students(4, "Should Roll Back", [1, 7])[0]
    assert advisories.get_advisory_groups(4) == []
    assert advisories.get_advisory_roster(4) == []
    assert query(advisory_db, "SELECT COUNT(*) FROM audit") == [(0,)]


@pytest.mark.parametrize("student_ids", [[], [1, 1], [1, 7], [1, 4], [1, 999], [1, 2, 8, 9, 10]])
def test_invalid_multiple_selection_adds_nobody(advisory_db, advisory_groups, capacity_students, student_ids):
    assert not advisories.add_advisory_students(4, student_ids, advisory_groups[4])[0]
    assert advisories.get_advisory_roster(4) == []
    assert query(advisory_db, "SELECT COUNT(*) FROM audit WHERE action_type = 'add_advisory_student'") == [(0,)]


def test_multiple_selection_checks_capacity_ownership_and_existing_members(advisory_app, advisory_db, advisory_groups, capacity_students):
    group_id = advisory_groups[4]
    assert advisories.add_advisory_students(4, [1, 2, 8], group_id)[0]
    with advisory_app.test_client() as client:
        sign_in(client, 4)
        response = client.post(BASE + "/add", data={
            "group_id": group_id, "student_id": ["9", "10"], "confirmed": "y",
        })
        assert response.status_code == 400
        assert b"at most 4 students" in response.data
    assert advisories.get_advisory_groups(4)[0]["student_count"] == 3
    assert not advisories.add_advisory_students(4, [9], advisory_groups[5])[0]
    assert advisories.create_advisory_group(4, "Second team")[0]
    second_group_id = advisories.get_advisory_groups(4)[1]["group_id"]
    # The first insert must roll back when a later student is already in another group.
    assert not advisories.add_advisory_students(4, [9, 1], second_group_id)[0]
    assert {student["user_id"] for student in advisories.get_advisory_roster(4)} == {1, 2, 8}
    assert query(advisory_db, "SELECT COUNT(*) FROM audit WHERE action_type = 'add_advisory_student'") == [(3,)]


def test_multiple_selection_audit_failure_rolls_back_every_student(advisory_db, advisory_groups, monkeypatch):
    original_audit = advisories.log_audit
    calls = []

    def fail_second_audit(*args, **kwargs):
        calls.append(args)
        if len(calls) == 2:
            raise RuntimeError("Simulated audit failure")
        original_audit(*args, **kwargs)

    monkeypatch.setattr(advisories, "log_audit", fail_second_audit)
    assert not advisories.add_advisory_students(4, [1, 2], advisory_groups[4])[0]
    assert len(calls) == 2
    assert advisories.get_advisory_roster(4) == []
    assert query(advisory_db, "SELECT COUNT(*) FROM audit WHERE action_type = 'add_advisory_student'") == [(0,)]


def test_concurrent_multiple_selections_respect_remaining_capacity(advisory_db, advisory_groups, capacity_students):
    group_id = advisory_groups[4]
    assert advisories.add_advisory_student(4, 10, group_id)[0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda ids: advisories.add_advisory_students(4, ids, group_id), [[1, 2], [8, 9]]))
    assert sum(ok for ok, _ in results) == 1
    assert advisories.get_advisory_groups(4)[0]["student_count"] == 3
    assert query(advisory_db, "SELECT COUNT(*) FROM audit WHERE action_type = 'add_advisory_student'") == [(3,)]


def test_browser_multiple_selection_capacity_and_navigation(advisory_browser, advisory_db, advisory_groups, capacity_students):
    from playwright.sync_api import expect

    assert advisories.create_advisory_group(4, "Almost full")[0]
    second_group_id = advisories.get_advisory_groups(4)[1]["group_id"]
    assert advisories.add_advisory_students(4, [8, 9, 10], second_group_id)[0]
    page, client = advisory_browser
    sign_in(client, 4)
    page.goto(f"{client.browser_url}/profile")
    page.locator(f'.nav-item[href="{BASE}"]').click()
    page.wait_for_url(f"{client.browser_url}{BASE}")
    page.get_by_role("button", name="Add students", exact=True).click()
    add_modal = page.locator("#add-advisory-student-modal")
    submit = add_modal.get_by_role("button", name="Add to my roster")
    choose_group(add_modal, advisory_groups[4])
    add_modal.locator('.advisory-student-choice input[value="1"]').check()
    add_modal.locator('.advisory-student-choice input[value="2"]').check()
    expect(add_modal.locator("#student-selection-status")).to_contain_text("2 of 4")
    add_modal.get_by_label("I am assigned to advise all selected students.", exact=True).check()
    expect(submit).to_be_enabled()

    choose_group(add_modal, second_group_id)
    expect(add_modal.locator("#student-selection-status")).to_contain_text("Select students")
    expect(submit).to_be_disabled()
    add_modal.locator('.advisory-student-choice input[value="2"]').check()
    expect(add_modal.locator('.advisory-student-choice input[value="11"]')).to_be_disabled()
    expect(submit).to_be_enabled()

    choose_group(add_modal, advisory_groups[4])
    add_modal.locator('.advisory-student-choice input[value="1"]').check()
    add_modal.locator('.advisory-student-choice input[value="2"]').check()
    submit.click()
    expect(page.locator(".flash-list")).to_contain_text("2 students added")
    expect(page.locator(f'#advisory-group-{advisory_groups[4]} .advisory-student')).to_have_count(2)
    expect(page.locator('.advisory-student-choice input[value="1"], .advisory-student-choice input[value="2"]')).to_have_count(0)
    expect(page.locator("#page-content .advisory-page > .profile-body > aside")).to_have_count(1)


def test_browser_full_group_disables_add_until_space_reopens(advisory_browser, advisory_db, advisory_groups, capacity_students):
    from playwright.sync_api import expect

    group_id = advisory_groups[4]
    for student_id in capacity_students[:4]:
        assert advisories.add_advisory_student(4, student_id, group_id)[0]
    page, client = advisory_browser
    sign_in(client, 4)
    page.goto(f"{client.browser_url}{BASE}")
    page.get_by_role("button", name="Add students", exact=True).click()
    add_modal = page.locator("#add-advisory-student-modal")
    expect(page.locator(".advisory-group__capacity")).to_contain_text("4 / 4 students")
    expect(add_modal.locator("#advisory-group-help")).to_contain_text("All your groups are full")
    expect(add_modal.locator("#group_id option")).to_have_count(1)
    expect(add_modal.get_by_role("button", name="Add to my roster")).to_be_disabled()
    add_modal.get_by_role("button", name="Cancel").click()
    page.locator(".advisory-student .advisory-details summary").first.click()
    page.get_by_label("Remove from my roster only.", exact=True).first.check()
    page.get_by_role("button", name="Remove student", exact=True).first.click()
    expect(page.locator(".advisory-group__capacity")).to_contain_text("3 / 4 students")
    page.get_by_role("button", name="Add students", exact=True).click()
    add_modal = page.locator("#add-advisory-student-modal")
    choose_group(add_modal, group_id)
    add_modal.locator('.advisory-student-choice input[value="10"]').check()
    add_modal.get_by_label("I am assigned to advise all selected students.", exact=True).check()
    add_modal.get_by_role("button", name="Add to my roster").click()
    expect(page.locator(".advisory-group__capacity")).to_contain_text("4 / 4 students")
    expect(page.locator(".advisory-student")).to_have_count(4)
