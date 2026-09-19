"""Admin requests routes."""
from . import admin
from flask import render_template, request, redirect, session, url_for, flash
from app.db.requests import get_all_requests, review_request
from app.routes.decorators import role_required
from app.constants.roles import ROLE_ADMIN


@admin.route("/requests")
@role_required(ROLE_ADMIN)
def view_requests():
    selected_status = request.args.get("status", "all").lower()

    requests = get_all_requests(selected_status)

    statuses = [
        "all",
        "pending",
        "approved",
        "rejected"
    ]

    return render_template(
        "admin/requests.html",
        hide_nav=False,
        requests=requests,
        statuses=statuses,
        selected_status=selected_status
    )


@admin.route("/repository/decide/<int:request_id>", methods=["POST"])
@role_required(ROLE_ADMIN)
def decide_request(request_id):
    status = request.form.get("status")
    status_reason = request.form.get("status_reason", "")
    reviewed_by = session.get("user_id")

    ok, err = review_request(request_id, status, status_reason, reviewed_by)
    flash("Request updated." if ok else f"Error: {err}",
          "success" if ok else "danger")
    return redirect(url_for("admin.view_requests"))
