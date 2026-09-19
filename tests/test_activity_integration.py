"""PostgreSQL coverage for deduplicated author activity."""
from datetime import datetime, timezone
from importlib import import_module

from flask import g

from app.db import activity, capstones, qol
from tests.test_author_account_links import ADVISER, AUTHOR, author_db, author_postgres
from tests.test_capstoner_registration import (
    capstoner_db,
    query,
    sign_in,
    workflow_app,
    workflow_browser,
)


def test_activity_dedup_totals_and_private_notifications(author_db, monkeypatch):
    monkeypatch.setattr(activity, "db_connect", author_db)
    monkeypatch.setattr(qol, "db_connect", author_db)

    assert capstones.set_capstone_people(
        1, [AUTHOR, dict(AUTHOR, user_id=2)], ADVISER
    )[0]
    request_id = query(
        author_db,
        """
        INSERT INTO request
            (user_id, capstone_id, request_status, request_reason,
             request_date, request_type)
        VALUES (2, 1, 'pending', 'Need the manuscript', CURRENT_TIMESTAMP, 'manuscript')
        RETURNING request_id
        """,
    )[0][0]

    occurred_at = datetime(2026, 9, 12, 8, 30, tzinfo=timezone.utc)
    assert activity.record_capstone_activity(1, 2, "view", "abstract", occurred_at=occurred_at)
    assert not activity.record_capstone_activity(1, 2, "view", "full", occurred_at=occurred_at)
    assert activity.record_capstone_activity(1, 2, "citation", "download", occurred_at=occurred_at)
    assert not activity.record_capstone_activity(1, 2, "citation", "pdf", occurred_at=occurred_at)
    assert activity.record_capstone_activity(
        1, 2, "request", request_id=request_id, occurred_at=occurred_at
    )
    assert not activity.record_capstone_activity(
        1, 2, "request", request_id=request_id, occurred_at=occurred_at
    )

    assert activity.get_author_activity_summary(1) == {
        "views": 1,
        "citations": 1,
        "requests": 1,
    }
    recent = activity.get_recent_author_activity(1)
    assert {row["event_type"] for row in recent} == {"view", "citation", "request"}

    notifications, unread = qol.get_user_notification_summary(1)
    activity_notifications = [
        item for item in notifications if item["notification_kind"] == "activity"
    ]
    assert unread == 3
    assert len(activity_notifications) == 3
    assert all("2" not in item["notification_message"] for item in activity_notifications)
    assert query(author_db, "SELECT COUNT(*) FROM notification WHERE recipient_user_id = 2")[0][0] == 0


def test_browser_author_bell_shows_private_activity_notifications(
    workflow_browser, workflow_app, capstoner_db, monkeypatch
):
    from playwright.sync_api import expect
    main_routes = import_module("app.routes.main")

    monkeypatch.setattr(activity, "db_connect", capstoner_db)
    monkeypatch.setattr(qol, "db_connect", capstoner_db)
    monkeypatch.setattr(main_routes, "get_user_notification_summary", qol.get_user_notification_summary)

    @workflow_app.before_request
    def add_test_role_name():
        if g.user:
            g.user["role_name"] = "Student"

    query(
        capstoner_db,
        """
        INSERT INTO request (user_id, request_status, request_type)
        VALUES (1, 'approved', 'capstoner'), (2, 'approved', 'capstoner')
        """,
    )
    assert capstones.set_capstone_people(
        1, [AUTHOR, dict(AUTHOR, user_id=2)], ADVISER
    )[0]
    assert activity.record_capstone_activity(1, 2, "view", "abstract")
    assert activity.record_capstone_activity(1, 2, "citation", "download")

    page, client = workflow_browser
    sign_in(client, 1)
    page.goto(f"{client.browser_url}/profile")
    toggle = page.get_by_role("button", name="Notifications, 2 unread")
    toggle.click()
    panel = page.locator("#notification-panel")
    expect(panel).to_be_visible()
    expect(panel).to_contain_text("Your linked capstone received a view.")
    expect(panel).to_contain_text("Your linked capstone was cited.")
    expect(panel).not_to_contain_text("Account #2")

    page.get_by_role("button", name="Mark all read").click()
    expect(page.get_by_role("button", name="Notifications")).to_be_visible()


def test_activity_routes_record_request_view_and_citation(
    workflow_app, capstoner_db, monkeypatch
):
    pages_routes = import_module("app.routes.pages.manuscripts")
    monkeypatch.setattr(activity, "db_connect", capstoner_db)
    monkeypatch.setattr(pages_routes, "can_view_full_manuscript", lambda *_: True)
    query(
        capstoner_db,
        "INSERT INTO keyword (keyword_id, capstone_keywords) VALUES (1, 'archive search')",
    )
    query(
        capstoner_db,
        "INSERT INTO program (program_id, program_name) VALUES (1, 'Computer Science')",
    )
    query(
        capstoner_db,
        "INSERT INTO specialization (specialization_id, specialization_name) VALUES (1, 'Computer Science')",
    )
    query(
        capstoner_db,
        "UPDATE capstone SET keyword_id = 1, specialization_id = 1, program_id = 1 WHERE capstone_id = 1",
    )
    query(
        capstoner_db,
        """
        INSERT INTO request (user_id, request_status, request_type)
        VALUES (1, 'approved', 'capstoner'), (2, 'approved', 'capstoner')
        """,
    )
    assert capstones.set_capstone_people(
        1, [AUTHOR, dict(AUTHOR, user_id=2)], ADVISER
    )[0]

    with workflow_app.test_client() as client:
        sign_in(client, 2)
        assert client.post(
            "/request_manuscript/1",
            data={"request_reason": "Need the manuscript for review."},
        ).status_code == 302
        request_row = query(
            capstoner_db,
            """
            SELECT request_id FROM request
            WHERE user_id = 2 AND capstone_id = 1 AND request_type = 'manuscript'
            ORDER BY request_id DESC LIMIT 1
            """,
        )[0][0]
        query(
            capstoner_db,
            "UPDATE request SET request_status = 'approved' WHERE request_id = %s",
            (request_row,),
        )
        view_response = client.get("/manuscript/view/1")
        assert view_response.status_code == 200, view_response.location
        assert client.get("/cite/1?format=apa").status_code == 200
        assert client.get("/cite/1?format=ris").status_code == 200

    assert query(
        capstoner_db,
        "SELECT event_type, COUNT(*) FROM capstone_activity GROUP BY event_type ORDER BY event_type",
    ) == [("citation", 1), ("request", 1), ("view", 1)]
