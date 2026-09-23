"""Mobile API authorization and PostgreSQL session lifecycle regressions."""
from importlib import import_module
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from flask import Flask
import pytest

from app import csrf
from app.db import mobile_sessions
from tests.test_author_account_links import author_db, author_postgres
from tests.test_login_username_case import add_credentials


routes = import_module("app.routes.mobile")
USER = {"user_id": 1, "user_first_name": "Maria", "role_name": "Student", "role_id": 1}


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.config.update(SECRET_KEY="mobile-test", TESTING=True)
    csrf.init_app(app)
    app.register_blueprint(routes.mobile)
    monkeypatch.setattr(mobile_sessions, "authenticate", lambda token: USER if token == "valid" else None)
    return app.test_client()


def test_cookie_session_cannot_authenticate_api(client):
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["role_name"] = "Admin"
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.json["error"]
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_identity_is_allowlisted_and_not_cached(client):
    response = client.get("/api/v1/me", headers={"Authorization": "Bearer valid"})
    assert response.status_code == 200
    assert response.json["user"]["user_id"] == 1
    assert "role_id" not in response.json["user"]
    assert response.headers["Cache-Control"] == "no-store"
    assert "Set-Cookie" not in response.headers


@pytest.mark.parametrize("body", [[], None, {}, {"username": [], "password": "x"}])
def test_malformed_login_is_rejected(client, body):
    response = client.post("/api/v1/auth/login", json=body)
    assert response.status_code in (400, 415)
    assert response.is_json


def test_login_uses_existing_auth_without_csrf_or_cookie(client, monkeypatch):
    calls = []
    monkeypatch.setattr(routes, "sign_in", lambda *args: (calls.append(args) or USER, None))
    monkeypatch.setattr(mobile_sessions, "create_session", lambda uid: {"access_token": "a", "refresh_token": "r"})
    response = client.post("/api/v1/auth/login", json={"username": " maria ", "password": "password"})
    assert response.status_code == 200
    assert calls[0][:2] == ("maria", "password")
    assert "Set-Cookie" not in response.headers


def test_repository_omits_storage_paths(client, monkeypatch):
    monkeypatch.setattr(routes, "get_archive_capstones", lambda **kwargs: ([{
        "capstone_id": 1, "capstone_title": "Study", "capstone_file": "private/secret.pdf",
    }], 1))
    response = client.get("/api/v1/capstones", headers={"Authorization": "Bearer valid"})
    assert response.status_code == 200
    assert "capstone_file" not in response.json["items"][0]


def test_manuscript_checks_approval_and_archive_before_file_access(client, monkeypatch):
    monkeypatch.setattr(mobile_sessions, "visible_capstone", lambda cid: cid != 2)
    monkeypatch.setattr(routes, "get_capstone_details", lambda cid: {"capstone_id": cid})
    monkeypatch.setattr(routes, "can_view_full_manuscript", lambda cid, uid: False)
    monkeypatch.setattr(routes, "resolve_manuscript_file", lambda key: pytest.fail("Must not resolve denied file"))
    headers = {"Authorization": "Bearer valid"}
    assert client.get("/api/v1/capstones/1/file", headers=headers).status_code == 403
    assert client.get("/api/v1/capstones/2/file", headers=headers).status_code == 404


def test_approved_pdf_is_served_without_paths(client, monkeypatch, tmp_path):
    pdf = tmp_path / "private.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF")
    monkeypatch.setattr(mobile_sessions, "visible_capstone", lambda cid: True)
    monkeypatch.setattr(routes, "get_capstone_details", lambda cid: {"capstone_file": "private.pdf"})
    monkeypatch.setattr(routes, "can_view_full_manuscript", lambda cid, uid: uid == 1)
    monkeypatch.setattr(routes, "resolve_manuscript_file", lambda key: str(pdf))
    response = client.get("/api/v1/capstones/1/file", headers={"Authorization": "Bearer valid"})
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF")
    assert response.headers["Cache-Control"] == "no-store"
    response.close()


def test_manuscript_permission_tracks_live_approval_not_cookie_role(client, monkeypatch):
    decorators = import_module("app.routes.decorators")
    approved = []
    monkeypatch.setattr(mobile_sessions, "visible_capstone", lambda cid: True)
    monkeypatch.setattr(routes, "get_capstone_details", lambda cid: {"capstone_id": cid})
    monkeypatch.setattr(decorators, "get_user_requests", lambda uid: approved if uid == 1 else [])
    with client.session_transaction() as session:
        session["role_name"] = "Admin"
    headers = {"Authorization": "Bearer valid"}
    assert not client.get("/api/v1/capstones/1", headers=headers).json["can_view"]
    approved.append({"capstone_id": 1, "request_status": "approved"})
    assert client.get("/api/v1/capstones/1", headers=headers).json["can_view"]
    approved.clear()
    assert not client.get("/api/v1/capstones/1", headers=headers).json["can_view"]


def test_mobile_csrf_exemption_does_not_disable_web_protection(client):
    client.application.add_url_rule('/web-write', view_func=lambda: 'ok', methods=['POST'])
    assert client.post('/web-write').status_code == 400
    assert client.post('/api/v1/notifications/read').status_code == 401


def test_notifications_use_bearer_identity(client, monkeypatch):
    calls = []
    monkeypatch.setattr(routes, "mark_all_notifications_read", lambda uid: calls.append(uid) or True)
    response = client.post("/api/v1/notifications/read", headers={"Authorization": "Bearer valid"}, json={})
    assert response.status_code == 204
    assert calls == [1]


@pytest.fixture
def mobile_db(author_db, monkeypatch):
    with author_db() as conn, conn.cursor() as cursor:
        cursor.execute((Path(__file__).resolve().parents[1] / "migrations/20260923_mobile_sessions.sql").read_text())
    conn.close()
    add_credentials(author_db, 1, "maria")
    monkeypatch.setattr(mobile_sessions, "db_connect", author_db)
    return author_db


def test_rotation_revocation_and_digest_storage(mobile_db):
    first = mobile_sessions.create_session(1)
    assert mobile_sessions.authenticate(first["access_token"])["user_id"] == 1
    with mobile_db() as conn, conn.cursor() as cur:
        cur.execute("SELECT access_hash, refresh_hash FROM mobile_session")
        access_hash, refresh_hash = cur.fetchone()
    conn.close()
    assert access_hash == mobile_sessions.token_hash(first["access_token"])
    assert refresh_hash == mobile_sessions.token_hash(first["refresh_token"])
    second = mobile_sessions.refresh_session(first["refresh_token"])
    assert second and second != first
    assert mobile_sessions.authenticate(first["access_token"]) is None
    assert mobile_sessions.refresh_session(first["refresh_token"]) is None
    assert mobile_sessions.revoke_session(second["refresh_token"]) == 1
    assert mobile_sessions.authenticate(second["access_token"]) is None
    assert mobile_sessions.refresh_session(second["refresh_token"]) is None


@pytest.mark.parametrize("change", [
    "UPDATE mobile_session SET access_expires_at = NOW() - INTERVAL '1 second'",
    "UPDATE mobile_session SET refresh_expires_at = NOW() - INTERVAL '1 second'",
    "UPDATE slug SET is_current = FALSE WHERE user_id = 1",
    "UPDATE \"user\" SET account_status = 'rejected' WHERE user_id = 1",
    "UPDATE \"user\" SET locked_until = NOW() + INTERVAL '1 hour' WHERE user_id = 1",
])
def test_expiry_password_change_and_account_restrictions(mobile_db, change):
    pair = mobile_sessions.create_session(1)
    with mobile_db() as conn, conn.cursor() as cur:
        cur.execute(change)
    conn.close()
    assert mobile_sessions.authenticate(pair["access_token"]) is None
    refreshed = mobile_sessions.refresh_session(pair["refresh_token"])
    assert bool(refreshed) == ("SET access_expires_at" in change)


def test_live_role_change_is_used(mobile_db):
    pair = mobile_sessions.create_session(1)
    with mobile_db() as conn, conn.cursor() as cur:
        cur.execute('UPDATE "user" SET role_id = 2 WHERE user_id = 1')
    conn.close()
    assert mobile_sessions.authenticate(pair["access_token"])["role_name"] == "Faculty"


def test_concurrent_refresh_only_issues_one_pair(mobile_db):
    pair = mobile_sessions.create_session(1)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(mobile_sessions.refresh_session, [pair["refresh_token"]] * 2))
    assert sum(result is not None for result in results) == 1
    assert mobile_sessions.authenticate(pair["access_token"]) is None


def test_mobile_cookie_does_not_trigger_web_identity_lookup(client, monkeypatch):
    from app.utils import auth_utils
    client.application.before_request(auth_utils.load_current_user)
    monkeypatch.setattr(auth_utils, "get_current_user", lambda uid: pytest.fail("Mobile must ignore cookies"))
    with client.session_transaction() as session:
        session["user_id"] = 2
    response = client.get("/api/v1/me", headers={"Authorization": "Bearer valid"})
    assert response.json["user"]["user_id"] == 1
