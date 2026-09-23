"""Admin users routes and local helpers."""
from . import admin
from flask import (
    abort,
    render_template,
    request,
    redirect,
    session,
    url_for,
    flash,
    jsonify,
    send_file,
)
import logging
from app.utils.cor_upload import resolve_cor_file
from app.db.verification_documents import get_verification_details, get_verification_document
from app.db.auth import (
    get_verification_request_recipient,
    get_pending_verifications,
    review_verification_request,
)
from app.utils.account_emails import verification_email
from app import mail
from app.db.users import (
    delete_user_account,
    get_users,
    update_user_role,
    get_all_roles,
    set_account_status,
)
from app.routes.decorators import role_required


logger = logging.getLogger(__name__)


def _send_verification_email(recipient, decision, status_reason):
    """Email failure must not undo an already-saved verification decision."""
    if not recipient or not recipient.get('email'):
        return False
    try:
        mail.send(verification_email(recipient, decision, status_reason))
        return True
    except Exception:
        logger.exception('Could not send verification email')
        return False


@admin.route('/manage_users/verify/<int:request_id>/details')
@role_required(3, 4)
def verification_details(request_id):
    details = get_verification_details(request_id)
    if not details:
        abort(404)
    path = resolve_cor_file(details['filename'])
    details['size_bytes'] = path.stat().st_size if path else None
    details['document_url'] = url_for('admin.verification_document', request_id=request_id) if path else None
    response = jsonify(details)
    response.headers['Cache-Control'] = 'no-store'
    return response


@admin.route('/manage_users/verify/<int:request_id>/document')
@role_required(3, 4)
def verification_document(request_id):
    document = get_verification_document(request_id)
    if not document:
        abort(404)
    path = resolve_cor_file(document['filename'])
    if not path:
        abort(404)
    # Treat uploaded PDFs as untrusted: keep them isolated while the browser PDF viewer renders them.
    inline = request.args.get('inline') == '1'
    response = send_file(path, mimetype='application/pdf',
                         as_attachment=not inline, download_name=document['filename'], max_age=0)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Security-Policy'] = "sandbox; default-src 'none'; frame-ancestors 'self'"
    return response


@admin.route("/manage_users")
@role_required(3, 4)
def manage_users():
    search = request.args.get("search", "").strip()
    role_id = request.args.get("role", "").strip()
    status = request.args.get("status", "").strip()
    page = request.args.get("page", 1, type=int)
    page_size = 20

    users, total = get_users(
        search=search or None,
        role_id=int(role_id) if role_id.isdigit() else None,
        status=status or None,
        page=page,
        page_size=page_size,
    )
    total_pages = max(1, (total + page_size - 1) // page_size)

    roles = get_all_roles()
    pending_verifications = get_pending_verifications()
    return render_template(
        "admin/manage_users.html",
        users=users,
        roles=roles,
        pending_verifications=pending_verifications,
        search=search,
        selected_role=role_id,
        selected_status=status,
        page=page,
        total_pages=total_pages,
        total_users=total,
    )


@admin.route("/manage_users/verify/<int:request_id>", methods=["POST"])
@role_required(3, 4)
def decide_verification(request_id):
    decision = request.form.get("decision")  # 'approved' or 'rejected'
    status_reason = request.form.get("status_reason", "")
    reviewed_by = session.get("user_id")

    if decision not in ("approved", "rejected"):
        flash("Invalid decision.", "danger")
        return redirect(url_for("admin.manage_users"))

    recipient = get_verification_request_recipient(request_id)
    ok, err = review_verification_request(request_id, decision, status_reason, reviewed_by)
    if ok:
        email_sent = _send_verification_email(recipient, decision, status_reason)
        message = 'Account activated.' if decision == 'approved' else 'Account verification rejected.'
        if not email_sent:
            message += ' Email notification could not be sent.'
        flash(message, 'success' if email_sent else 'warning')
    else:
        flash(f'Error: {err}', 'danger')
    return redirect(url_for("admin.manage_users"))


@admin.route("/manage_users/update_role/<int:user_id>", methods=["GET","POST"])
@role_required(3)
def update_role(user_id):
    new_role_id = request.form.get("role_id")
    # Derived from the session, not a client-supplied form field — a
    # hidden acting_admin_id input could otherwise be edited in devtools
    # to spoof a different admin, defeating both the audit trail and the
    # self-protection check below.
    acting_admin_id = session.get("user_id")

    if not new_role_id:
        flash("No role selected.", "error")
        return redirect(url_for("admin.manage_users"))

    ok, err = update_user_role(user_id, new_role_id, acting_admin_id)
    flash(
        "Role updated successfully." if ok else f"Error: {err}",
        "success" if ok else "error",
    )
    return redirect(url_for("admin.manage_users"))


@admin.route("/manage_users/delete/<int:user_id>", methods=["POST"])
@role_required(3)
def delete_user(user_id):
    acting_admin_id = session.get("user_id")
    ok, err = delete_user_account(user_id, acting_admin_id)
    flash(
        "User account deleted." if ok else f"Error: {err}",
        "success" if ok else "error",
    )
    return redirect(url_for("admin.manage_users"))


@admin.route("/manage_users/status/<int:user_id>", methods=["POST"])
@role_required(3)
def change_account_status(user_id):
    new_status = request.form.get("status")
    acting_admin_id = session.get("user_id")

    ok, err = set_account_status(user_id, new_status, acting_admin_id)
    flash(
        ("Account deactivated." if new_status == "deactivated" else "Account reactivated.")
        if ok else f"Error: {err}",
        "success" if ok else "error",
    )
    return redirect(url_for("admin.manage_users"))
