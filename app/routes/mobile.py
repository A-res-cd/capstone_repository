"""Versioned, bearer-only API for the bundled mobile client."""
from flask import Blueprint, abort, current_app, g, jsonify, request, send_file
from werkzeug.exceptions import HTTPException

from app import csrf
from app.db import mobile_sessions
from app.db.auth import sign_in, sign_out
from app.db.archive import get_archive_capstones
from app.db.capstones import get_capstone_details
from app.db.qol import get_user_notification_summary, mark_all_notifications_read
from app.routes.decorators import can_view_full_manuscript
from app.utils.uploads import manuscript_mimetype, resolve_manuscript_file


mobile = Blueprint("mobile", __name__, url_prefix="/api/v1")
# This blueprint never accepts ambient cookie authentication. Every protected
# request requires an explicit bearer token; login/refresh/logout use JSON.
csrf.exempt(mobile)
PUBLIC_ENDPOINTS = {"mobile.login", "mobile.refresh", "mobile.logout"}
CAPSTONE_FIELDS = (
    "capstone_id", "capstone_title", "capstone_year", "semester", "term",
    "capstone_keywords", "specialization_name", "program_name",
)
PROFILE_FIELDS = ("user_id", "user_first_name", "user_middle_name", "user_last_name", "role_name")
NOTIFICATION_FIELDS = (
    "request_id", "request_type", "request_status", "decision_date", "status_reason",
    "notification_seen_at", "capstone_title", "target_role_name", "notification_kind",
    "notification_title", "notification_message",
)


def _pick(row, fields):
    return {key: row.get(key) for key in fields}


def _json_body():
    if not request.is_json:
        abort(415, description="Send application/json.")
    body = request.get_json()
    if not isinstance(body, dict):
        abort(400, description="Expected a JSON object.")
    return body


def _string(body, key, maximum=512):
    value = body.get(key)
    if not isinstance(value, str) or not value or len(value) > maximum:
        abort(400, description=f"Invalid {key}.")
    return value


@mobile.before_request
def require_mobile_identity():
    g.user = None
    if request.endpoint in PUBLIC_ENDPOINTS:
        return
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token or len(token) > 512:
        abort(401, description="Sign in to continue.")
    g.user = mobile_sessions.authenticate(token)
    if not g.user:
        abort(401, description="Session expired. Sign in again.")


@mobile.after_request
def private_response(response):
    response.headers["Cache-Control"] = "no-store"
    if response.status_code == 401:
        response.headers["WWW-Authenticate"] = "Bearer"
    return response


@mobile.errorhandler(HTTPException)
def api_error(error):
    return jsonify(error=error.description), error.code


@mobile.errorhandler(Exception)
def unexpected_error(error):
    current_app.logger.exception("Mobile API request failed")
    return jsonify(error="Service unavailable. Please try again."), 503


@mobile.post("/auth/login")
def login():
    body = _json_body()
    username = _string(body, "username", 150).strip()
    password = _string(body, "password", 1024)
    user, error = sign_in(username, password, request.remote_addr)
    if not user:
        return jsonify(error=error), 401
    credentials = mobile_sessions.create_session(user["user_id"])
    if not credentials:
        abort(401, description="Account is not allowed to sign in.")
    return jsonify(**credentials)


@mobile.post("/auth/refresh")
def refresh():
    credentials = mobile_sessions.refresh_session(_string(_json_body(), "refresh_token"))
    if not credentials:
        abort(401, description="Session expired. Sign in again.")
    return jsonify(**credentials)


@mobile.post("/auth/logout")
def logout():
    user_id = mobile_sessions.revoke_session(_string(_json_body(), "refresh_token"))
    if user_id:
        sign_out(user_id, request.remote_addr)
    return "", 204


@mobile.get("/me")
def profile():
    return jsonify(user=_pick(g.user, PROFILE_FIELDS))


@mobile.get("/capstones")
def capstones():
    page = request.args.get("page", 1, type=int)
    search = request.args.get("search", "").strip()
    if page is None or not 1 <= page <= 100000 or len(search) > 200:
        abort(400, description="Invalid search or page.")
    rows, total = get_archive_capstones(search=search or None, page=page, page_size=12)
    return jsonify(items=[_pick(row, CAPSTONE_FIELDS) for row in rows],
                   total=total, page=page, page_size=12)


def _capstone(capstone_id):
    if not mobile_sessions.visible_capstone(capstone_id):
        abort(404, description="Manuscript not found.")
    row = get_capstone_details(capstone_id)
    if not row:
        abort(404, description="Manuscript not found.")
    return row


@mobile.get("/capstones/<int:capstone_id>")
def capstone_detail(capstone_id):
    row = _capstone(capstone_id)
    return jsonify(item=_pick(row, CAPSTONE_FIELDS),
                   can_view=can_view_full_manuscript(capstone_id, g.user["user_id"]))


@mobile.get("/capstones/<int:capstone_id>/file")
def manuscript(capstone_id):
    row = _capstone(capstone_id)
    if not can_view_full_manuscript(capstone_id, g.user["user_id"]):
        abort(403, description="Approval is required to read this manuscript.")
    path = resolve_manuscript_file(row.get("capstone_file"))
    if not path:
        abort(404, description="Manuscript file not found.")
    if manuscript_mimetype(path) != "application/pdf":
        abort(415, description="Only PDF manuscripts can be viewed in the mobile app.")
    return send_file(path, mimetype="application/pdf", download_name=f"manuscript-{capstone_id}.pdf")


@mobile.get("/notifications")
def notifications():
    rows, unread = get_user_notification_summary(g.user["user_id"], limit=30)
    return jsonify(items=[_pick(row, NOTIFICATION_FIELDS) for row in rows], unread_count=unread)


@mobile.post("/notifications/read")
def read_notifications():
    if not mark_all_notifications_read(g.user["user_id"]):
        abort(503, description="Could not update notifications.")
    return "", 204
