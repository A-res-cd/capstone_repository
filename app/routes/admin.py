from flask import Blueprint, render_template, request, redirect, session, url_for, flash, jsonify, current_app
from werkzeug.utils import secure_filename
import os
import sys
import uuid
import random
import logging
import flask
from app.db.database import (
    delete_user_account, get_all_capstones, get_archived_capstones, get_programs, get_specializations,
    get_used_keyword, insert_keywords, create_capstone_project,
    get_capstone_details, update_capstone_record, update_keyword,
    delete_capstone, get_users, update_user_role, get_all_roles, set_account_status,
    get_all_requests, review_request, set_capstone_people, get_capstone_people,
    get_capstones_by_specialization, get_requests_by_status, get_top_cited_capstones, add_to_bin,
    restore_capstone, ARCHIVE_RETENTION_DAYS,
    get_pending_verifications, review_verification_request,
    get_capstones_by_program, get_capstone_trend_by_specialization, get_capstone_status_flags,
    get_capstone_program_summary
)
from app.routes.decorators import role_required
from app.routes.forms import CreateCapstoneForm, UpdateCapstoneForm
from app.utils.pdf_extractor import extract_capstone_data, _parse_abstract_page

admin = Blueprint("admin", __name__)
logger = logging.getLogger(__name__)

UPLOAD_FOLDER = os.path.join("app", "static", "uploads")
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx"}


def _allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _populate_capstone_choices(form):
    """SelectField choices must be set before validate()/rendering —
    pulled fresh from the DB each request rather than hardcoded."""
    form.program_id.choices = [(p[0], p[1]) for p in get_programs()]
    form.specialization_id.choices = [(s[0], s[1]) for s in get_specializations()]


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
        {"first": a.first_name.data, "middle": a.middle_name.data, "last": a.last_name.data}
        for a in form.authors
    ]
    adviser = {
        "first": form.adviser.first_name.data,
        "middle": form.adviser.middle_name.data,
        "last": form.adviser.last_name.data,
    }
    return authors, adviser


# ── PDF auto-extract ───────────────────────────────────────────────────────

@admin.route("/repository/extract", methods=["POST"])
@role_required(3)
def extract_capstone_pdf():
    file = request.files.get('capstone_file')
    if not file or file.filename == '':
        return jsonify({'success': False, 'error': 'No file uploaded.'}), 400

    if not _allowed(file.filename):
        return jsonify({'success': False, 'error': 'Only PDF, DOC, and DOCX files are accepted.'}), 400

    filename = secure_filename(file.filename)
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    temp_path = os.path.join(UPLOAD_FOLDER, filename)
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
    if not _allowed(file_obj.filename):
        return None, "Invalid file type. Only PDF, DOC, and DOCX are allowed."
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    filename = secure_filename(file_obj.filename)
    name, ext = os.path.splitext(filename)
    filename = f"{name}_{uuid.uuid4().hex[:8]}{ext}"
    file_obj.save(os.path.join(UPLOAD_FOLDER, filename))
    return filename, None


# ── Static pages ──────────────────────────────────────────────────────────────

# Odds the "Developer Debug Tool" nav link actually shows the real
# debug panel instead of the troll image — tune to taste.
DEV_DEBUG_REAL_TOOL_CHANCE = 0.3


@admin.route("/dev-debug")
@role_required(3)
def dev_debug():
    if random.random() >= DEV_DEBUG_REAL_TOOL_CHANCE:
        return render_template("admin/dev_debug_troll.html")

    # ── The real tool — admin-only internal debug panel ──
    sensitive_keys = {"SECRET_KEY", "PG_PASSWORD", "MAIL_PASSWORD"}
    config_items = sorted(
        (k, ("••••••••" if k in sensitive_keys else v))
        for k, v in current_app.config.items()
        if k.isupper() and not callable(v)
    )

    session_items = sorted(session.items())

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
        request_headers=sorted(request.headers.items()),
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

    program_summary, err = get_capstone_program_summary()
    if err:
        db_errors.append(f"Capstone program summary: {err}")

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

    # ── Summary-by-program table rows, with per-metric percentages ──
    def _pct(part, whole):
        return round((part / whole) * 100, 1) if whole else 0

    summary_rows = []
    for row in (program_summary or []):
        total = row["total"]
        summary_rows.append({
            "name": row["program_name"],
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
@role_required(3)
def decide_verification(request_id):
    decision = request.form.get("decision")  # 'approved' or 'rejected'
    status_reason = request.form.get("status_reason", "")
    reviewed_by = session.get("user_id")

    if decision not in ("approved", "rejected"):
        flash("Invalid decision.", "danger")
        return redirect(url_for("admin.manage_users"))

    ok, err = review_verification_request(request_id, decision, status_reason, reviewed_by)
    flash(
        "Account activated." if (ok and decision == "approved")
        else "Account verification rejected." if ok
        else f"Error: {err}",
        "success" if ok else "danger",
    )
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

@admin.route("/repository")
@role_required(3)
def view_capstone_repository():
    capstones = get_all_capstones()
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
    )


@admin.route("/repository/<int:capstone_id>/people")
@role_required(3)
def get_capstone_people_json(capstone_id):
    """Feeds the Edit-panel wizard's Authors/Adviser step — capstone
    people were previously only fetchable server-side, so editing an
    existing capstone silently dropped its authors/adviser."""
    rows = get_capstone_people(capstone_id)

    authors = [
        {"first": r["aut_first_name"], "middle": r["aut_middle_name"] or "", "last": r["aut_last_name"]}
        for r in rows if r["role"] == "Author"
    ][:4]

    adviser_row = next((r for r in rows if r["role"] == "Adviser"), None)
    adviser = (
        {"first": adviser_row["aut_first_name"], "middle": adviser_row["aut_middle_name"] or "", "last": adviser_row["aut_last_name"]}
        if adviser_row else {"first": "", "middle": "", "last": ""}
    )

    return jsonify({"success": True, "authors": authors, "adviser": adviser})


@admin.route("/recyclebin")
@role_required(3)
def view_archived_capstones():
    archived_capstones = get_archived_capstones()
    return render_template(
        "admin/archives.html",
        archived_capstones=archived_capstones,
        archive_retention_days=ARCHIVE_RETENTION_DAYS,
    )


@admin.route("/repository/create", methods=["GET", "POST"])
@role_required(3)
def admin_create_capstone():
    if request.method == "GET":
        return redirect(url_for("admin.view_capstone_repository"))

    form = CreateCapstoneForm()
    _populate_capstone_choices(form)

    def _rerender():
        return render_template(
            "admin/repository.html", hide_nav=False, form=form,
            capstones=get_all_capstones(),
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

        file_path = f"uploads/{filename}"

        success, result = insert_keywords(form.capstone_keywords.data)
        if not success:
            flash(result, "danger")
        else:
            keyword_id = result
            success, message = create_capstone_project(
                keyword_id, form.specialization_id.data, form.program_id.data,
                form.capstone_title.data, form.capstone_year.data,
                file_path, form.citation_count.data or 0, form.semester.data,
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
        return render_template(
            "admin/repository.html", hide_nav=False, form=form,
            capstones=get_all_capstones(),
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
            file_path = f"uploads/{filename}"

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
            form.citation_count.data or 0, form.semester.data,
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
    is_admin = session.get("role_id") == 3
    max_pages = None if is_admin else 1  # Non-admin sees only page 1

    # The template's inline script always references PDF_URL and
    # START_PAGE regardless of max_pages — leaving them unset renders as
    # the literal text "Undefined" in the script and breaks PDF.js.
    pdf_url = None
    try:
        file_rel = capstone.get('capstone_file') if isinstance(capstone, dict) else None
        if file_rel:
            if file_rel.startswith('static' + os.sep) or file_rel.startswith('static/'):
                file_rel = file_rel.split('static' + os.sep, 1)[-1] if os.sep in file_rel else file_rel.split('static/', 1)[-1]
            file_rel = file_rel.replace('\\', '/').lstrip('/')
            pdf_url = url_for('static', filename=file_rel)
    except Exception as e:
        logger.error("Error computing pdf_url: %s", e)

    return render_template(
        "admin/view_capstone.html",
        capstone=capstone,
        max_pages=max_pages,
        start_page=1,
        pdf_url=pdf_url,
        hide_header=True,
    )


@admin.route("/repository/pdf/<int:capstone_id>")
@role_required(1, 2, 3)
def view_capstone_pdf(capstone_id):
    capstone = get_capstone_details(capstone_id)
    if not capstone:
        flash("Capstone not found.", "danger")
        return redirect(url_for("admin.view_capstone_repository"))

    role_name = session.get("role_name")

    # Default values
    max_pages = None
    start_page = 1

    # If user is Student, restrict to abstract page only. Attempt to determine
    # the actual abstract page number from stored capstone data or by parsing
    # the PDF on disk (fall back to page 1).
    if role_name == 'Student':
        max_pages = 1

        # try to read abstract_page from capstone record (dict-like)
        abstract_page = None
        try:
            abstract_page = capstone.get('abstract_page') if isinstance(capstone, dict) else None
        except Exception:
            abstract_page = None

        # If not present, try parsing the PDF to find abstract page
        if not abstract_page:
            file_rel = capstone.get('capstone_file') if isinstance(capstone, dict) else None
            if file_rel:
                pdf_path = os.path.join(current_app.root_path, 'static', file_rel)
                try:
                    if os.path.exists(pdf_path) and pdf_path.lower().endswith('.pdf'):
                        data = extract_capstone_data(pdf_path)
                        abstract_page = data.get('abstract_page')
                except Exception as e:
                    logger.error("Error parsing PDF for abstract page: %s", e)

        if abstract_page:
            start_page = int(abstract_page)

    # Normalize capstone file path for use with url_for('static')
    pdf_url = None
    try:
        file_rel = capstone.get('capstone_file') if isinstance(capstone, dict) else None
        if file_rel:
            # Remove any leading 'static/' segment if present
            if file_rel.startswith('static' + os.sep) or file_rel.startswith('static/'):
                file_rel = file_rel.split('static' + os.sep, 1)[-1] if os.sep in file_rel else file_rel.split('static/', 1)[-1]
            # Also normalize backslashes to forward slashes for URL
            file_rel = file_rel.replace('\\', '/').lstrip('/')
            pdf_url = url_for('static', filename=file_rel)
    except Exception as e:
        logger.error("Error computing pdf_url: %s", e)

    return render_template("admin/view_capstone.html", capstone=capstone, max_pages=max_pages, start_page=start_page, pdf_url=pdf_url, hide_header=True)


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
