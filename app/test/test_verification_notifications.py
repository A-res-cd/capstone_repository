from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

from flask import Flask, render_template

from app.db import auth as auth_db


auth_routes = import_module("app.routes.authentication")
admin_routes = import_module("app.routes.admin")
ROOT = Path(__file__).resolve().parents[2]


class RecordingCursor:
    def __init__(self):
        self.calls = []
        self._first_fetch = True

    def execute(self, query, params=None):
        self.calls.append((" ".join(query.split()), params))

    def fetchone(self):
        if self._first_fetch:
            self._first_fetch = False
            return {"user_id": 12, "request_type": "verification_student"}
        return None

    def close(self):
        pass


class RecordingConnection:
    def __init__(self, cursor):
        self.cursor_value = cursor
        self.committed = False

    def cursor(self, cursor_factory=None):
        return self.cursor_value

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        pass


class RecipientCursor:
    def __init__(self):
        self.query = ""
        self.params = None

    def execute(self, query, params=None):
        self.query = " ".join(query.split())
        self.params = params

    def fetchone(self):
        return {"full_name": "Amy Sapin", "email": "amy@example.com"}

    def close(self):
        pass


def test_verification_decision_resets_notification_seen_at(monkeypatch):
    cursor = RecordingCursor()
    connection = RecordingConnection(cursor)
    monkeypatch.setattr(auth_db, "db_connect", lambda: connection)
    monkeypatch.setattr(auth_db, "log_audit", lambda *args, **kwargs: None)

    ok, error = auth_db.review_verification_request(44, "approved", "", 3)

    assert (ok, error) == (True, None)
    request_update = next(query for query, _ in cursor.calls if "UPDATE request SET" in query)
    assert "notification_seen_at = NULL" in request_update
    assert any('UPDATE "user" SET account_status = %s' in query for query, _ in cursor.calls)
    assert connection.committed


def test_verification_recipient_reads_pending_primary_email(monkeypatch):
    cursor = RecipientCursor()
    connection = RecordingConnection(cursor)
    monkeypatch.setattr(auth_db, "db_connect", lambda: connection)

    recipient = auth_db.get_verification_request_recipient(44)

    assert recipient == {"full_name": "Amy Sapin", "email": "amy@example.com"}
    assert cursor.params == (44,)
    assert "request_status = 'pending'" in cursor.query


def test_verification_email_contains_approval_notice(monkeypatch):
    sent = []
    app = Flask(__name__, template_folder=str(ROOT / "app/templates"))
    app.config["MAIL_DEFAULT_SENDER"] = "noreply@example.com"
    admin_routes.mail.init_app(app)

    with app.app_context():
        monkeypatch.setattr(admin_routes, "mail", SimpleNamespace(send=sent.append))
        assert admin_routes._send_verification_email(
            {"full_name": "Amy Sapin", "email": "amy@example.com"},
            "approved",
            "",
        )

    assert sent[0].subject == "Your CAPRE account has been verified"
    assert sent[0].recipients == ["amy@example.com"]
    assert "Your CAPRE account has been verified" in sent[0].body
    assert "Your account is ready" in sent[0].html


def test_verification_email_contains_rejection_reason_and_handles_failure(monkeypatch):
    sent = []
    app = Flask(__name__, template_folder=str(ROOT / "app/templates"))
    app.config["MAIL_DEFAULT_SENDER"] = "noreply@example.com"
    admin_routes.mail.init_app(app)

    with app.app_context():
        monkeypatch.setattr(admin_routes, "mail", SimpleNamespace(send=sent.append))
        assert admin_routes._send_verification_email(
            {"full_name": "Amy Sapin", "email": "amy@example.com"},
            "rejected",
            "Documents were incomplete.",
        )
        assert "Documents were incomplete." in sent[0].body

        def fail_send(message):
            raise OSError("mail server unavailable")

        monkeypatch.setattr(admin_routes, "mail", SimpleNamespace(send=fail_send))
        assert not admin_routes._send_verification_email(
            {"full_name": "Amy Sapin", "email": "amy@example.com"},
            "approved",
            "",
        )


def test_pending_signin_explains_verification_wait(monkeypatch):
    app = Flask(__name__, template_folder=str(ROOT / "app/templates"))
    app.config.update(TESTING=True, SECRET_KEY="verification-test", WTF_CSRF_ENABLED=False)
    app.jinja_env.globals["csrf_token"] = lambda: ""
    app.register_blueprint(auth_routes.auth)
    app.add_url_rule("/", "main.home", lambda: "Home")
    monkeypatch.setattr(
        auth_routes,
        "sign_in",
        lambda username, password, device_ip=None: (
            None,
            "Your account is waiting for verification. Please wait for approval.",
        ),
    )

    response = app.test_client().post(
        "/signin",
        data={"username": "pending-user", "password": "correct-password"},
    )

    assert response.status_code == 200
    assert b"Your account is waiting for verification" in response.data


def test_verification_notification_uses_clear_status_copy():
    app = Flask(__name__, template_folder=str(ROOT / "app/templates"))
    app.config.update(TESTING=True, SECRET_KEY="verification-template-test")
    app.add_url_rule("/user-info", "pages.user_info", lambda: "")
    app.add_url_rule("/profile", "pages.profile_overview", lambda: "")
    app.add_url_rule("/my-requests", "pages.all_requests", lambda: "")
    app.add_url_rule("/header", "test.header", lambda: render_template(
        "partials/header.html",
        notification_unread_count=2,
        notifications=[
            {
                "request_type": "verification_student",
                "request_status": "approved",
                "notification_seen_at": None,
                "decision_date": datetime.now(timezone.utc),
                "status_reason": None,
                "capstone_title": None,
                "target_role_name": None,
            },
            {
                "request_type": "verification_faculty",
                "request_status": "rejected",
                "notification_seen_at": None,
                "decision_date": datetime.now(timezone.utc),
                "status_reason": "Documents were incomplete.",
                "capstone_title": None,
                "target_role_name": None,
            },
        ],
        current_user={"initials": "VU", "display_name": "Verified User"},
        role_meta={"badge_class": "", "icon": "bx-user", "label": "Student"},
    ))

    response = app.test_client().get("/header")

    assert b"Account verified" in response.data
    assert b"Your account has been verified." in response.data
    assert b"Account verification rejected" in response.data
    assert b"Documents were incomplete." in response.data
