from flask import Blueprint, abort, render_template, request, redirect, session, url_for, flash, jsonify, current_app, send_file, g
from flask_mail import Message
from werkzeug.utils import secure_filename
import os
import sys
import random
import logging
import flask
from app.db.database import (
    delete_user_account, get_all_capstones, get_archived_capstones, get_programs, get_specializations,
    get_used_keyword, insert_keywords, create_capstone_project,
    get_capstone_details, update_capstone_record, update_keyword,
    delete_capstone, get_users, update_user_role, get_all_roles, set_account_status,
    get_all_requests, review_request, set_capstone_people, get_capstone_people, get_capstone_authors,
    get_capstones_by_specialization, get_requests_by_status, add_to_bin,
    restore_capstone, ARCHIVE_RETENTION_DAYS,
    get_pending_verifications, get_verification_request_recipient, review_verification_request,
    get_pending_promotion_requests, review_promotion_request,
    get_capstones_by_program, get_capstone_trend_by_specialization, get_capstone_status_flags
)
from app.routes.decorators import role_required, can_view_full_manuscript
from app.routes.forms import CreateCapstoneForm, UpdateCapstoneForm, CapstonerReviewForm, CapstonerAssignmentForm
from app.db.analytics import get_all_specialization_reports, get_specialization_report
from app.db.capstones import get_author_account_choices
from app.db.capstoners import (
    get_pending_capstoners, review_capstoner_registration,
    get_capstoner_assignment_choices, assign_capstoner_credit,
)
from app.utils.pdf_extractor import extract_abstract_text, extract_capstone_data
from app.utils.xlsx_export import build_specialization_workbook, build_table_workbook
from app.utils.uploads import (
    allowed_manuscript,
    manuscript_mimetype,
    manuscript_upload_folder,
    resolve_manuscript_file,
    save_manuscript_upload,
    stored_manuscript_path,
    unique_manuscript_filename,
)
from app import mail
admin = Blueprint("admin", __name__)
logger = logging.getLogger(__name__)

def _allowed(filename):
    return allowed_manuscript(filename)


def _send_verification_email(recipient, decision, status_reason):
    """Send the verification result without affecting the saved decision."""
    if not recipient or not recipient.get("email"):
        return False

    name = recipient.get("full_name") or "there"
    if decision == "approved":
        subject = "Your CAPRE account has been verified"
        body = (
            f"Hello {name},\n\n"
            "Your CAPRE account has been verified. You may now sign in.\n\n"
            "Thank you,\nCAPRE"
        )
    else:
        subject = "Update on your CAPRE account verification"
        body = (
            f"Hello {name},\n\n"
            "Your CAPRE account verification was rejected.\n"
            f"Reason: {status_reason or 'No reason was provided.'}\n\n"
            "Please contact support if you need help.\n\n"
            "Thank you,\nCAPRE"
        )

    try:
        mail.send(Message(subject=subject, recipients=[recipient["email"]], body=body))
        return True
    except Exception as exc:
        logger.error("Could not send verification email: %s", exc)
        return False


def _populate_capstone_choices(form):
    """SelectField choices must be set before validate()/rendering —
    pulled fresh from the DB each request rather than hardcoded."""
    form.program_id.choices = [(p[0], p[1]) for p in get_programs()]
    form.specialization_id.choices = [(s[0], s[1]) for s in get_specializations()]
    accounts = [(0, "No linked account")]
    author_accounts = get_author_account_choices() if getattr(g, "user", None) and g.user.get("role_id") in (3, 4) else []
    for account in author_accounts:
        name = " ".join(account[key] for key in ("user_first_name", "user_middle_name", "user_last_name") if account[key])
        university_no = f" · {account['university_no']}" if account["university_no"] else ""
        accounts.append((account["user_id"], f"{name or 'Unnamed user'}{university_no} · Account #{account['user_id']}"))
    for author in form.authors:
        author.user_id.choices = accounts


def _first_form_error(form):
    """Flattens WTForms' nested error dict (FieldList/FormField errors
    are dicts-of-lists, not flat lists) into one readable message for
    the flash banner."""
    def _flatten(errors):
        for err in errors:
            if isinstance(err, dict):
                for sub in err.values():
                    yield from _flatten(sub)
            elif isinstance(err, list):
                yield from _flatten(err)
            else:
                yield err

    for field_errors in form.errors.values():
        for msg in _flatten(field_errors if isinstance(field_errors, list) else [field_errors]):
            return msg
    return "Please check the form for errors."


def _people_for_db(form):
    """Adapts CreateCapstoneForm's authors/adviser field names
    (first_name/middle_name/last_name) to the shape set_capstone_people()
    already expects (first/middle/last)."""
    authors = [
        {"first": a.first_name.data, "middle": a.middle_name.data, "last": a.last_name.data,
         "author_id": a.author_id.data, "user_id": a.user_id.data}
        for a in form.authors
    ]
    adviser = {
        "author_id": form.adviser.author_id.data,
        "first": form.adviser.first_name.data,
        "middle": form.adviser.middle_name.data,
        "last": form.adviser.last_name.data,
    }
    return authors, adviser


# ── PDF auto-extract ───────────────────────────────────────────────────────

@admin.route("/repository/extract", methods=["POST"])
@role_required(3, 4)
def extract_capstone_pdf():
    file = request.files.get('capstone_file')

    if not file or file.filename == '':
        return jsonify({'success': False, 'error': 'No file uploaded.'}), 400

    if not _allowed(file.filename):
        return jsonify({'success': False, 'error': 'Only PDF, DOC, and DOCX files are accepted.'}), 400

    filename = unique_manuscript_filename(file.filename)
    os.makedirs(manuscript_upload_folder(), exist_ok=True)
    temp_path = os.path.join(manuscript_upload_folder(), filename)
    file.save(temp_path)

    # Only PDF files can be parsed for metadata — DOC/DOCX silently skip
    if filename.lower().endswith('.pdf'):
        data = extract_capstone_data(temp_path)
    else:
        data = {}

    return jsonify({
        'success':       True,
        'data':          data,
        'temp_filename': filename,
    })


def _save_file(file_obj):
    """Validate and save an uploaded file. Returns (filename, error_msg) —
    exactly one of the two will be set."""
    if not file_obj or not file_obj.filename:
        return None, None
    return save_manuscript_upload(file_obj)


# ── Static pages ──────────────────────────────────────────────────────────────

# Odds the "Developer Debug Tool" nav link actually shows the real
# debug panel instead of the troll image — tune to taste.
DEV_DEBUG_REAL_TOOL_CHANCE = 1


def _dev_debug_enabled():
    """The real panel dumps session data, full config keys, and request
    headers — that's too much to hand to every admin account in
    production. Require an explicit opt-in env var (or actual Flask
    debug mode) on top of the admin role check."""
    return current_app.debug or os.environ.get("ENABLE_DEV_DEBUG", "").lower() in ("1", "true", "yes")


@admin.route("/dev-debug")
@role_required(3)
def dev_debug():
    if not _dev_debug_enabled():
        abort(404)

    if random.random() >= DEV_DEBUG_REAL_TOOL_CHANCE:
        return render_template("admin/dev_debug_troll.html")

    # ── The real tool — admin-only internal debug panel ──
    safe_config_keys = {
        "DEBUG", "TESTING", "MAX_CONTENT_LENGTH",
        "SESSION_COOKIE_HTTPONLY", "SESSION_COOKIE_SAMESITE",
        "SESSION_COOKIE_SECURE",
    }
    config_items = sorted(
        (k, v)
        for k, v in current_app.config.items()
        if k in safe_config_keys and not callable(v)
    )

    session_items = sorted((key, "set") for key in session.keys())

    safe_header_names = {
        "Accept", "Accept-Encoding", "Accept-Language", "Host", "User-Agent",
    }
    request_headers = sorted(
        (key, value)
        for key, value in request.headers.items()
        if key in safe_header_names
    )

    routes = sorted(
        (
            r.endpoint,
            ", ".join(sorted(m for m in r.methods if m not in ("HEAD", "OPTIONS"))),
            str(r),
        )
        for r in current_app.url_map.iter_rules()
    )

    return render_template(
        "admin/dev_debug_real.html",
        session_items=session_items,
        config_items=config_items,
        routes=routes,
        python_version=sys.version.split()[0],
        flask_version=flask.__version__,
        request_headers=request_headers,
        troll_odds_pct=round((1 - DEV_DEBUG_REAL_TOOL_CHANCE) * 100),
        debug_mode=current_app.debug,
    )


@admin.route("/analytics")
@role_required(3)
def analytics():
    db_errors = []

    by_specialization, err = get_capstones_by_specialization()
    if err:
        db_errors.append(f"Capstones by specialization: {err}")

    by_program, err = get_capstones_by_program()
    if err:
        db_errors.append(f"Capstones by program: {err}")

    trend_years, trend_series, err = get_capstone_trend_by_specialization()
    if err:
        db_errors.append(f"Capstone trend by specialization: {err}")

    status_flags, err = get_capstone_status_flags()
    if err:
        db_errors.append(f"Capstone status flags: {err}")

    if db_errors:
        for msg in db_errors:
            flash(f"Analytics query failed — {msg}", "danger")

    specialization_labels = [row["specialization_name"] for row in by_specialization]
    specialization_totals = [row["total"] for row in by_specialization]

    program_labels = [row["program_name"] for row in by_program]
    program_totals = [row["total"] for row in by_program]

    # ── Summary card figures ──
    total_capstones = sum(program_totals)

    # ── Published / Utilized / Presented / Copyright Registered donuts.
    # Every archived-in record is inherently "published" (no draft
    # workflow state exists), so Published is always total/total. ──
    status_flags = status_flags or {}
    published_labels = ["Published", "Not Published"]
    published_totals = [total_capstones, 0]

    utilized_labels = ["Utilized", "Not Utilized"]
    utilized_totals = [status_flags.get("utilized", 0), status_flags.get("not_utilized", 0)]

    presented_labels = ["Presented", "Not Presented"]
    presented_totals = [status_flags.get("presented", 0), status_flags.get("not_presented", 0)]

    copyright_labels = ["Registered", "Not Registered"]
    copyright_totals = [status_flags.get("copyright_registered", 0), status_flags.get("not_copyright_registered", 0)]

    # ── Per-program stat cards, in the reference dashboard's style ──
    program_cards = []
    for row in by_program:
        pct = round((row["total"] / total_capstones) * 100, 1) if total_capstones else 0
        program_cards.append({
            "name": row["program_name"],
            "total": row["total"],
            "pct": pct,
        })

    # ── Summary-by-specialization table rows, with per-metric percentages ──
    def _pct(part, whole):
        return round((part / whole) * 100, 1) if whole else 0

    summary_rows = []
    for row in (by_specialization or []):
        total = row["total"]
        summary_rows.append({
            "id": row["specialization_id"],
            "name": row["specialization_name"],
            "total": total,
            "total_pct": _pct(total, total_capstones),
            "published": total,
            "published_pct": _pct(total, total),
            "utilized": row["utilized"],
            "utilized_pct": _pct(row["utilized"], total),
            "presented": row["presented"],
            "presented_pct": _pct(row["presented"], total),
            "copyright_registered": row["copyright_registered"],
            "copyright_pct": _pct(row["copyright_registered"], total),
        })

    summary_totals = {
        "total": total_capstones,
        "published": total_capstones,
        "utilized": sum(r["utilized"] for r in summary_rows),
        "presented": sum(r["presented"] for r in summary_rows),
        "copyright_registered": sum(r["copyright_registered"] for r in summary_rows),
    }

    return render_template(
        "admin/analytics.html",
        specialization_labels=specialization_labels,
        specialization_totals=specialization_totals,
        program_labels=program_labels,
        program_totals=program_totals,
        program_cards=program_cards,
        trend_years=trend_years,
        trend_series=trend_series,
        has_db_errors=bool(db_errors),
        total_capstones=total_capstones,
        published_labels=published_labels,
        published_totals=published_totals,
        utilized_labels=utilized_labels,
        utilized_totals=utilized_totals,
        presented_labels=presented_labels,
        presented_totals=presented_totals,
        copyright_labels=copyright_labels,
        copyright_totals=copyright_totals,
        summary_rows=summary_rows,
        summary_totals=summary_totals,
    )


# ── User management ───────────────────────────────────────────────────────────

@admin.route("/analytics/specialization/<int:specialization_id>/report")
@role_required(3)
def analytics_specialization_report(specialization_id):
    rows, specialization, err = get_specialization_report(specialization_id)
    if err:
        return jsonify({"success": False, "error": err}), 500
    if specialization is None:
        return jsonify({"success": False, "error": "Specialization not found."}), 404

    return jsonify({
        "success": True,
        "specialization": specialization,
        "records": rows,
    })


@admin.route("/analytics/specialization/<int:specialization_id>/report.xlsx")
@role_required(3)
def analytics_specialization_workbook(specialization_id):
    rows, specialization, err = get_specialization_report(specialization_id)
    if err:
        return jsonify({"success": False, "error": err}), 500
    if specialization is None:
        return jsonify({"success": False, "error": "Specialization not found."}), 404

    workbook = build_specialization_workbook([{
        "specialization_id": specialization_id,
        "specialization_name": specialization,
        "records": rows,
    }])
    filename = secure_filename(specialization).lower() or "specialization"
    return send_file(
        workbook,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"capre-{filename}-capstones.xlsx",
    )


@admin.route("/analytics/report.xlsx")
@role_required(3)
def analytics_workbook():
    by_specialization, specialization_err = get_capstones_by_specialization()
    by_program, program_err = get_capstones_by_program()
    trend_years, trend_series, trend_err = get_capstone_trend_by_specialization()
    status_flags, status_err = get_capstone_status_flags()
    if any((specialization_err, program_err, trend_err, status_err)):
        return jsonify({
            "success": False,
            "error": "Analytics data is temporarily unavailable.",
        }), 500

    total = sum(row["total"] for row in by_program)
    status_flags = status_flags or {}

    def share(value, whole=total):
        return f"{((value / whole) * 100) if whole else 0:.1f}%"

    status_groups = (
        ("Publication", (("Published", total), ("Not Published", 0))),
        ("Utilization", (("Utilized", status_flags.get("utilized", 0)),
                         ("Not Utilized", status_flags.get("not_utilized", 0)))),
        ("Presentation", (("Presented", status_flags.get("presented", 0)),
                          ("Not Presented", status_flags.get("not_presented", 0)))),
        ("Copyright", (("Registered", status_flags.get("copyright_registered", 0)),
                       ("Not Registered", status_flags.get("not_copyright_registered", 0)))),
    )
    status_rows = [
        (metric, label, value, share(value))
        for metric, values in status_groups
        for label, value in values
    ]
    trend_names = list(trend_series)
    tables = [
        {
            "title": "Overview",
            "headers": ("Metric", "Value"),
            "rows": (("Total Capstones", total),),
            "widths": (32, 18),
        },
        {
            "title": "Programs",
            "headers": ("Program", "Capstones", "Share of Total"),
            "rows": tuple(
                (row["program_name"], row["total"], share(row["total"]))
                for row in by_program
            ),
            "widths": (30, 15, 18),
        },
        {
            "title": "Status",
            "headers": ("Metric", "Status", "Count", "Share"),
            "rows": tuple(status_rows),
            "widths": (20, 24, 14, 14),
        },
        {
            "title": "Yearly Trend",
            "headers": ("Year", *trend_names),
            "rows": tuple(
                (year, *(trend_series[name][index] for name in trend_names))
                for index, year in enumerate(trend_years)
            ),
            "widths": (12, *(16 for _ in trend_names)),
        },
        {
            "title": "Specializations",
            "headers": ("Specialization", "Capstones", "Share of Total"),
            "rows": tuple(
                (row["specialization_name"], row["total"], share(row["total"]))
                for row in by_specialization
            ),
            "widths": (28, 15, 18),
        },
        {
            "title": "Summary",
            "headers": ("Specialization", "Total Capstone", "Published", "Utilized",
                        "Presented", "Copyright Registered"),
            "rows": tuple(
                (
                    row["specialization_name"],
                    f'{row["total"]} ({share(row["total"])})',
                    f'{row["total"]} ({share(row["total"], row["total"])})',
                    f'{row["utilized"]} ({share(row["utilized"], row["total"])})',
                    f'{row["presented"]} ({share(row["presented"], row["total"])})',
                    f'{row["copyright_registered"]} '
                    f'({share(row["copyright_registered"], row["total"])})',
                )
                for row in by_specialization
            ),
            "widths": (28, 18, 18, 18, 18, 25),
        },
    ]
    return send_file(
        build_table_workbook(tables),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="capre-analytics-report.xlsx",
    )


@admin.route("/analytics/specializations/report")
@role_required(3)
def analytics_all_specializations_report():
    specializations, err = get_all_specialization_reports()
    if err:
        return jsonify({"success": False, "error": err}), 500

    return jsonify({
        "success": True,
        "specializations": specializations,
    })


@admin.route("/analytics/specializations/report.xlsx")
@role_required(3)
def analytics_all_specializations_workbook():
    specializations, err = get_all_specialization_reports()
    if err:
        return jsonify({"success": False, "error": err}), 500

    return send_file(
        build_specialization_workbook(specializations),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="capre-all-specializations.xlsx",
    )


@admin.route("/manage_users")
@role_required(3)
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
    pending_promotions = get_pending_promotion_requests()
    return render_template(
        "admin/manage_users.html",
        users=users,
        roles=roles,
        pending_verifications=pending_verifications,
        pending_promotions=pending_promotions,
        search=search,
        selected_role=role_id,
        selected_status=status,
        page=page,
        total_pages=total_pages,
        total_users=total,
    )


@admin.route("/manage_users/promotion/<int:request_id>", methods=["POST"])
@role_required(3)
def decide_promotion(request_id):
    decision = request.form.get("decision")  # 'approved' or 'rejected'
    status_reason = request.form.get("status_reason", "")
    reviewed_by = session.get("user_id")

    if decision not in ("approved", "rejected"):
        flash("Invalid decision.", "danger")
        return redirect(url_for("admin.manage_users"))

    ok, err = review_promotion_request(request_id, decision, status_reason, reviewed_by)
    flash(
        "Promotion approved." if (ok and decision == "approved")
        else "Promotion request rejected." if ok
        else f"Error: {err}",
        "success" if ok else "danger",
    )
    return redirect(url_for("admin.manage_users"))


@admin.route("/manage_users/verify/<int:request_id>", methods=["POST"])
@role_required(3)
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
        message = (
            "Account activated." if decision == "approved"
            else "Account verification rejected."
        )
        if not email_sent:
            message += " Email notification could not be sent."
        flash(message, "success" if email_sent else "warning")
    else:
        flash(f"Error: {err}", "danger")
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




# ── Requests ──────────────────────────────────────────────────────────────────

from flask import request

@admin.route("/requests")
@role_required(3)
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


# ── Repository ────────────────────────────────────────────────────────────────

def _capstoner_assignment_form():
    form = CapstonerAssignmentForm()
    accounts, credits = get_capstoner_assignment_choices()
    form.user_id.choices = [(0, "Choose an account")]
    for account in accounts:
        if account["user_id"] != session["user_id"]:
            label = f"{account['full_name']} · {account['university_no'] or 'No university ID'} · Account #{account['user_id']}"
            form.user_id.choices.append((account["user_id"], label))
    form.credit.choices = [("", "Choose an unlinked author credit")] + [
        (f"{credit['capstone_id']}:{credit['author_id']}",
         f"{credit['author_name']} — {credit['capstone_title']} ({credit['capstone_year']}) · Credit #{credit['author_id']}")
        for credit in credits
    ]
    return form


def _render_capstoner_review(assignment_form=None):
    return render_template(
        "admin/capstoners.html", pending_capstoners=get_pending_capstoners(),
        review_form=CapstonerReviewForm(),
        assignment_form=assignment_form or _capstoner_assignment_form(),
    )


@admin.route("/capstoners")
@role_required(4)
def capstoner_review():
    return _render_capstoner_review()


@admin.route("/capstoners/review/<int:request_id>", methods=["POST"])
@role_required(4)
def decide_capstoner(request_id):
    form = CapstonerReviewForm()
    if not form.validate_on_submit():
        flash(_first_form_error(form), "danger")
        return _render_capstoner_review(), 400
    ok, error = review_capstoner_registration(request_id, form.decision.data, form.status_reason.data, session["user_id"])
    flash("Capstoner request reviewed. No capstone was linked automatically." if ok else error, "success" if ok else "danger")
    if not ok:
        return _render_capstoner_review(), 400
    return redirect(url_for("admin.capstoner_review"))


@admin.route("/capstoners/assign", methods=["POST"])
@role_required(4)
def assign_capstoner():
    form = _capstoner_assignment_form()
    if not form.validate_on_submit():
        flash(_first_form_error(form), "danger")
        return _render_capstoner_review(form), 400
    capstone_id, author_id = (int(value) for value in form.credit.data.split(":"))
    ok, error = assign_capstoner_credit(capstone_id, author_id, form.user_id.data, session["user_id"])
    flash("Author credit linked. The user is an approved capstoner." if ok else error, "success" if ok else "danger")
    if not ok:
        return _render_capstoner_review(form), 400
    return redirect(url_for("admin.capstoner_review"))


@admin.route("/repository")
@role_required(2, 3, 4)
def view_capstone_repository():
    search = request.args.get("search", "").strip()
    program_id = request.args.get("program", "").strip()
    page = request.args.get("page", 1, type=int)
    page_size = 20

    capstones, total = get_all_capstones(
        search=search or None,
        program_id=int(program_id) if program_id.isdigit() else None,
        page=page,
        page_size=page_size,
    )
    total_pages = max(1, (total + page_size - 1) // page_size)

    programs = get_programs()
    specializations = get_specializations()
    form = CreateCapstoneForm()
    _populate_capstone_choices(form)
    return render_template(
        "admin/repository.html",
        capstones=capstones,
        programs=programs,
        specializations=specializations,
        form=form,
        search=search,
        selected_program=program_id,
        page=page,
        total_pages=total_pages,
        total_capstones=total,
    )


@admin.route("/repository/<int:capstone_id>/people")
@role_required(3)
def get_capstone_people_json(capstone_id):
    """Feeds the Edit-panel wizard's Authors/Adviser step — capstone
    people were previously only fetchable server-side, so editing an
    existing capstone silently dropped its authors/adviser."""
    try:
        rows = get_capstone_people(capstone_id)
    except Exception:
        return jsonify({"success": False, "error": "Could not load author links."}), 503

    authors = [
        {"first": r["aut_first_name"], "middle": r["aut_middle_name"] or "", "last": r["aut_last_name"],
         "author_id": r["author_id"], "user_id": r["user_id"]}
        for r in rows if r["role"] == "Author"
    ][:4]

    adviser_row = next((r for r in rows if r["role"] == "Adviser"), None)
    adviser = (
        {"first": adviser_row["aut_first_name"], "middle": adviser_row["aut_middle_name"] or "", "last": adviser_row["aut_last_name"],
         "author_id": adviser_row["author_id"]}
        if adviser_row else {"first": "", "middle": "", "last": ""}
    )

    return jsonify({"success": True, "authors": authors, "adviser": adviser})


@admin.route("/recyclebin")
@role_required(3)
def view_archived_capstones():
    search = request.args.get("search", "").strip()
    program_id = request.args.get("program", "").strip()
    page = request.args.get("page", 1, type=int)
    page_size = 20

    archived_capstones, total = get_archived_capstones(
        search=search or None,
        program_id=int(program_id) if program_id.isdigit() else None,
        page=page,
        page_size=page_size,
    )
    total_pages = max(1, (total + page_size - 1) // page_size)

    return render_template(
        "admin/archives.html",
        archived_capstones=archived_capstones,
        archive_retention_days=ARCHIVE_RETENTION_DAYS,
        programs=get_programs(),
        search=search,
        selected_program=program_id,
        page=page,
        total_pages=total_pages,
        total_archived=total,
    )


@admin.route("/repository/create", methods=["GET", "POST"])
@role_required(3, 4)
def admin_create_capstone():
    if request.method == "GET":
        return redirect(url_for("admin.view_capstone_repository"))

    form = CreateCapstoneForm()
    _populate_capstone_choices(form)

    def _rerender():
        capstones, _ = get_all_capstones()
        return render_template(
            "admin/repository.html", hide_nav=False, form=form,
            capstones=capstones,
            programs=get_programs(), specializations=get_specializations(),
        )

    if not form.validate_on_submit():
        flash(_first_form_error(form), "danger")
        return _rerender()

    try:
        file = form.capstone_file.data
        extracted_filename = form.extracted_filename.data

        if file and getattr(file, "filename", ""):
            filename, err = _save_file(file)
            if err:
                flash(err, "danger")
                return _rerender()
        elif extracted_filename:
            filename = secure_filename(extracted_filename)
            if not _allowed(filename):
                flash(
                    "Invalid file type. Only PDF, DOC, and DOCX are allowed.", "danger")
                return _rerender()
        else:
            flash("Upload a capstone file first.", "danger")
            return _rerender()

        file_path = stored_manuscript_path(filename)

        success, result = insert_keywords(form.capstone_keywords.data)
        if not success:
            flash(result, "danger")
        else:
            keyword_id = result
            success, message = create_capstone_project(
                keyword_id, form.specialization_id.data, form.program_id.data,
                form.capstone_title.data, form.capstone_year.data,
                file_path, form.semester.data,
                acting_user_id=session.get("user_id"),
                is_utilized=form.is_utilized.data,
                is_presented=form.is_presented.data,
                is_copyright_registered=form.is_copyright_registered.data
            )
            if success:
                new_capstone_id = message
                authors, adviser = _people_for_db(form)

                ok, err = set_capstone_people(
                    new_capstone_id, authors, adviser,
                    acting_user_id=session.get("user_id"))
                if not ok:
                    flash(
                        f"Capstone created, but author/adviser save failed: {err}", "warning")
                else:
                    flash("Capstone created successfully!", "success")

                return redirect(url_for("admin.view_capstone_repository"))
            else:
                flash(message, "danger")

    except Exception as exc:
        logger.error("admin_create_capstone error: %s", exc)
        flash("An error occurred while processing your request.", "danger")

    return _rerender()


@admin.route("/repository/update/<int:capstone_id>", methods=["POST"])
@role_required(3)
def update_capstone(capstone_id):
    used_keywords = get_used_keyword()
    capstone = get_capstone_details(capstone_id)

    if not capstone:
        flash("Capstone not found.", "danger")
        return redirect(url_for("admin.view_capstone_repository"))

    form = UpdateCapstoneForm()
    _populate_capstone_choices(form)

    def _rerender():
        capstones, _ = get_all_capstones()
        return render_template(
            "admin/repository.html", hide_nav=False, form=form,
            capstones=capstones,
            programs=get_programs(), specializations=get_specializations(),
            used_keywords=used_keywords, capstone=capstone,
        )

    if not form.validate_on_submit():
        flash(_first_form_error(form), "danger")
        return _rerender()

    try:
        new_keywords = (form.capstone_keywords.data or "").strip()

        file_path = capstone['capstone_file']
        file = form.capstone_file.data

        if file and getattr(file, "filename", ""):
            filename, err = _save_file(file)
            if err:
                flash(err, "danger")
                return _rerender()
            file_path = stored_manuscript_path(filename)

        # Update keyword if changed
        keyword_id = capstone['keyword_id']
        if new_keywords and new_keywords != capstone['capstone_keywords']:
            success, error = update_keyword(keyword_id, new_keywords)
            if not success:
                flash(f"Error updating keyword: {error}", "danger")
                return _rerender()

        # Update capstone record
        success, message = update_capstone_record(
            capstone_id, keyword_id, form.specialization_id.data, form.program_id.data,
            form.capstone_title.data, form.capstone_year.data, file_path,
            form.semester.data,
            acting_user_id=session.get("user_id"),
            is_utilized=form.is_utilized.data,
            is_presented=form.is_presented.data,
            is_copyright_registered=form.is_copyright_registered.data)

        if not success:
            flash(f"Error updating capstone: {message}", "danger")
            return _rerender()

        authors, adviser = _people_for_db(form)

        ok, err = set_capstone_people(capstone_id, authors, adviser,
                                       acting_user_id=session.get("user_id"))
        if not ok:
            flash(
                f"Capstone updated, but author/adviser save failed: {err}", "warning")
        else:
            flash("Capstone updated successfully!", "success")
        return redirect(url_for("admin.view_capstone_repository"))

    except Exception as e:
        logger.error("update_capstone_route error: %s", e)
        flash("Something went wrong updating this capstone. Please try again.", "danger")

    return _rerender()


@admin.route("/delete_capstone/<int:capstone_id>", methods=["POST"])
@role_required(3)
def delete_capstone_route(capstone_id):
    try:
        success, message = delete_capstone(capstone_id, acting_user_id=session.get("user_id"))
        flash(message, "success" if success else "danger")
    except Exception as e:
        current_app.logger.error("delete_capstone_route error: %s", e)
        flash("Something went wrong deleting this capstone. Please try again.", "danger")

    return redirect(url_for("admin.view_capstone_repository"))


@admin.route("/repository/view/<int:capstone_id>")
@role_required(3)
def view_capstone(capstone_id):
    capstone = get_capstone_details(capstone_id)
    authors = get_capstone_authors(capstone_id)
    # g.user is reloaded from the DB on every request (see load_current_user),
    # so this reflects the caller's current role even if it changed mid-session.
    is_admin = bool(g.user) and g.user.get("role_id") == 3
    max_pages = None if is_admin else 1  # Non-admin sees only page 1

    # The template's inline script always references PDF_URL and
    # START_PAGE regardless of max_pages — leaving them unset renders as
    # the literal text "Undefined" in the script and breaks PDF.js.
    pdf_url = None
    file_rel = capstone.get('capstone_file') if isinstance(capstone, dict) else None
    if file_rel:
        pdf_url = url_for('admin.manuscript_file', capstone_id=capstone_id)

    return render_template(
        "admin/view_capstone.html",
        capstone=capstone,
        authors=authors,
        max_pages=max_pages,
        start_page=1,
        pdf_url=pdf_url,
    )


@admin.route("/repository/pdf/<int:capstone_id>")
@role_required(1, 2, 3, 4)
def view_capstone_pdf(capstone_id):
    capstone = get_capstone_details(capstone_id)
    if not capstone:
        flash("Capstone not found.", "danger")
        return redirect(url_for("admin.view_capstone_repository"))

    # Use g.user (reloaded from the DB every request) instead of the
    # session copy, so a role change is respected immediately rather
    # than on next login.
    role_name = g.user.get("role_name") if g.user else None

    has_full_access = can_view_full_manuscript(capstone_id)
    if not has_full_access and role_name != 'Student':
        abort(403)

    abstract_only = role_name == 'Student' and not has_full_access
    authors = get_capstone_authors(capstone_id) if abstract_only else []
    max_pages = 1 if abstract_only else None
    pdf_url = None
    abstract_text = None
    file_rel = capstone.get('capstone_file') if isinstance(capstone, dict) else None
    if file_rel and has_full_access:
        pdf_url = url_for('admin.manuscript_file', capstone_id=capstone_id)
    elif file_rel:
        pdf_path = resolve_manuscript_file(file_rel)
        if pdf_path and pdf_path.lower().endswith('.pdf'):
            abstract_text = extract_abstract_text(pdf_path)

    if abstract_only and not abstract_text:
        abstract_text = "Abstract is not available for this manuscript."

    return render_template(
        "admin/view_capstone.html" if abstract_only else "admin/native_pdf_viewer.html",
        capstone=capstone,
        authors=authors,
        max_pages=max_pages,
        start_page=1,
        pdf_url=pdf_url,
        abstract_text=abstract_text,
        abstract_only=abstract_only,
        hide_nav=True,
        hide_header=not abstract_only,
    )


@admin.route("/repository/file/<int:capstone_id>")
@role_required(1, 2, 3, 4)
def manuscript_file(capstone_id):
    capstone = get_capstone_details(capstone_id)
    if not capstone:
        abort(404)

    # role_required(1, 2, 3) only confirms the caller is logged in as
    # *some* role — with just three roles in the system, that's every
    # authenticated user, not a real permission check. Admin/Faculty get
    # full access by design (matches the role check in view_capstone_pdf
    # above), but a Student must have an approved request for this exact
    # capstone — the same rule pages.manuscript_file already enforces for
    # the "View Full Manuscript" flow. Without this, any logged-in
    # student could fetch any capstone's complete PDF straight from this
    # URL, whether they'd ever requested it or not.
    if not can_view_full_manuscript(capstone_id):
        abort(403)

    file_path = resolve_manuscript_file(capstone.get("capstone_file"))
    if not file_path:
        abort(404)

    return send_file(file_path, mimetype=manuscript_mimetype(file_path))


@admin.route("/repository/decide/<int:request_id>", methods=["POST"])
@role_required(3)
def decide_request(request_id):
    status = request.form.get("status")
    status_reason = request.form.get("status_reason", "")
    reviewed_by = session.get("user_id")

    ok, err = review_request(request_id, status, status_reason, reviewed_by)
    flash("Request updated." if ok else f"Error: {err}",
          "success" if ok else "danger")
    return redirect(url_for("admin.view_requests"))

# ==========add the capstone to the archive and prepare for fetus deletus==========


@admin.route("/repository/archive/<int:capstone_id>", methods=["POST"])
@role_required(3)
def archive_capstone(capstone_id):
    success, message = add_to_bin(capstone_id, acting_user_id=session.get("user_id"))
    flash(message, "success" if success else "danger")
    return redirect(url_for("admin.view_capstone_repository"))


@admin.route("/recyclebin/restore/<int:capstone_id>", methods=["POST"])
@role_required(3)
def restore_capstone_route(capstone_id):
    success, message = restore_capstone(capstone_id, acting_user_id=session.get("user_id"))
    flash(message, "success" if success else "danger")
    return redirect(url_for("admin.view_capstone_repository"))
