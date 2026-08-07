from flask import Blueprint, render_template, request, redirect, session, url_for, flash, jsonify, current_app
from werkzeug.utils import secure_filename
import os
import uuid
import logging
from app.db.database import (
    delete_user_account, get_all_capstones, get_archived_capstones, get_programs, get_specializations,
    get_used_keyword, insert_keywords, create_capstone_project,
    get_capstone_details, update_capstone_record, update_keyword,
    delete_capstone, get_users, update_user_role, get_all_roles,
    get_all_requests, review_request, set_capstone_people, get_capstone_people,
    get_capstones_by_specialization, get_requests_by_status, get_top_cited_capstones, add_to_bin,
    restore_capstone, ARCHIVE_RETENTION_DAYS
)
from app.routes.decorators import role_required
from app.utils.pdf_extractor import extract_capstone_data, _parse_abstract_page

admin = Blueprint("admin", __name__)
logger = logging.getLogger(__name__)

UPLOAD_FOLDER = os.path.join("app", "static", "uploads")
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx"}


def _allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


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


def _parse_capstone_people(form):
    authors = []
    for i in range(1, 5):
        authors.append({
            "first":  form.get(f"author_first_{i}"),
            "middle": form.get(f"author_middle_{i}"),
            "last":   form.get(f"author_last_{i}"),
        })
    adviser = {
        "first":  form.get("adviser_first"),
        "middle": form.get("adviser_middle"),
        "last":   form.get("adviser_last"),
    }
    return authors, adviser


# ── Static pages ──────────────────────────────────────────────────────────────

@admin.route("/analytics")
@role_required(3)
def analytics():
    db_errors = []

    by_specialization, err = get_capstones_by_specialization()
    if err:
        db_errors.append(f"Capstones by specialization: {err}")

    by_status, err = get_requests_by_status()
    if err:
        db_errors.append(f"Requests by status: {err}")

    top_cited, err = get_top_cited_capstones(limit=5)
    if err:
        db_errors.append(f"Top cited capstones: {err}")

    if db_errors:
        for msg in db_errors:
            flash(f"Analytics query failed — {msg}", "danger")

    specialization_labels = [row["specialization_name"] for row in by_specialization]
    specialization_totals = [row["total"] for row in by_specialization]

    status_labels  = [row["request_status"].capitalize() for row in by_status]
    status_totals  = [row["total"]                       for row in by_status]

    # ── Summary card figures ──
    total_capstones  = sum(specialization_totals)
    total_requests   = sum(status_totals)
    pending_requests = next((t for l, t in zip(status_labels, status_totals) if l == "Pending"), 0)
    top_cited_title  = top_cited[0]["capstone_title"]  if top_cited else None
    top_cited_count  = top_cited[0]["citation_count"]  if top_cited else 0

    return render_template(
        "admin/analytics.html",
        specialization_labels=specialization_labels,
        specialization_totals=specialization_totals,
        status_labels=status_labels,
        status_totals=status_totals,
        top_cited=top_cited,
        has_db_errors=bool(db_errors),
        total_capstones=total_capstones,
        total_requests=total_requests,
        pending_requests=pending_requests,
        top_cited_title=top_cited_title,
        top_cited_count=top_cited_count,
    )


# ── User management ───────────────────────────────────────────────────────────

@admin.route("/manage_users")
@role_required(3)
def manage_users():
    users = get_users()
    roles = get_all_roles()
    return render_template("admin/manage_users.html", users=users, roles=roles)


@admin.route("/manage_users/update_role/<int:user_id>", methods=["GET","POST"])
@role_required(3)
def update_role(user_id):
    new_role_id = request.form.get("role_id")
    acting_admin_id = request.form.get("acting_admin_id")

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
    acting_admin_id = request.form.get("acting_admin_id")
    ok, err = delete_user_account(user_id, acting_admin_id)
    flash(
        "User account deleted." if ok else f"Error: {err}",
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
    return render_template(
        "admin/repository.html",
        capstones=capstones,
        programs=programs,
        specializations=specializations,
    )


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

    programs = get_programs()
    specializations = get_specializations()
    try:
        if request.method == 'POST':
            specialization = request.form.get('specialization_id')
            program = request.form.get('program_id')
            capstone_title = request.form.get('capstone_title')
            capstone_year = request.form.get('capstone_year')
            citation = request.form.get('citation_count')
            sem = request.form.get('semester')

            file = request.files.get('capstone_file')
            extracted_filename = request.form.get("extracted_filename")

            if file and file.filename:
                filename, err = _save_file(file)
                if err:
                    flash(err, "danger")
                    return render_template("admin/repository.html", hide_nav=False, form_data=request.form, programs=programs, specializations=specializations)
            elif extracted_filename:
                filename = secure_filename(extracted_filename)
                if not _allowed(filename):
                    flash(
                        "Invalid file type. Only PDF, DOC, and DOCX are allowed.", "danger")
                    return render_template("admin/repository.html", hide_nav=False, form_data=request.form, programs=programs, specializations=specializations)
            else:
                flash("Upload a capstone file first.", "danger")
                return render_template("admin/repository.html", hide_nav=False, form_data=request.form, programs=programs, specializations=specializations)

            file_path = f"uploads/{filename}"

            success, result = insert_keywords(
                request.form.get('capstone_keywords'))
            if not success:
                flash(result, "danger")
            else:
                keyword_id = result
                success, message = create_capstone_project(
                    keyword_id, specialization, program,
                    capstone_title, capstone_year,
                    file_path, citation, sem
                )
                if success:
                    new_capstone_id = message

                    authors, adviser = _parse_capstone_people(request.form)

                    if not (adviser["first"] and adviser["last"]):
                        flash("Adviser information is required.", "danger")
                        return render_template("admin/repository.html", hide_nav=False, form_data=request.form, programs=programs, specializations=specializations)

                    ok, err = set_capstone_people(
                        new_capstone_id, authors, adviser)
                    if not ok:
                        flash(
                            f"Capstone created, but author/adviser save failed: {err}", "warning")
                    else:
                        flash("Capstone created successfully!", "success")

                    return redirect(url_for("admin.view_capstone_repository"))
                else:
                    flash(message, "danger")

    except Exception:
        flash("An error occurred while processing your request.", "danger")

    return render_template(
        "admin/repository.html",
        form_data=request.form,
        programs=programs,
        specializations=specializations,
    )


@admin.route("/repository/update/<int:capstone_id>", methods=["POST"])
@role_required(3)
def update_capstone(capstone_id):
    programs = get_programs()
    specializations = get_specializations()
    used_keywords = get_used_keyword()
    capstone = get_capstone_details(capstone_id)

    if not capstone:
        flash("Capstone not found.", "danger")
        return redirect(url_for("admin.view_capstone_repository"))

    try:
        new_specialization = request.form.get('specialization_id')
        new_program = request.form.get('program_id')
        new_capstone_title = request.form.get('capstone_title')
        new_capstone_year = request.form.get('capstone_year')
        new_citation = request.form.get('citation_count') or 0
        new_sem = request.form.get('semester') or None
        new_keywords = request.form.get('capstone_keywords', '').strip()

        file_path = capstone['capstone_file']
        file = request.files.get('capstone_file')

        if file and file.filename != '':
            filename, err = _save_file(file)
            if err:
                flash(err, "danger")
                return render_template("admin/update_capstone.html", hide_nav=False, form_data=request.form, programs=programs, specializations=specializations, used_keywords=used_keywords, capstone=capstone)
            file_path = f"uploads/{filename}"

        # Update keyword if changed
        keyword_id = capstone['keyword_id']
        if new_keywords and new_keywords != capstone['capstone_keywords']:
            success, error = update_keyword(keyword_id, new_keywords)
            if not success:
                flash(f"Error updating keyword: {error}", "danger")
                return render_template("admin/update_capstone.html", hide_nav=False, form_data=request.form, programs=programs, specializations=specializations, used_keywords=used_keywords, capstone=capstone)

        # Update capstone record
        success, message = update_capstone_record(
            capstone_id, keyword_id, new_specialization, new_program,
            new_capstone_title, new_capstone_year, file_path, new_citation,
            new_sem)

        if not success:
            flash(f"Error updating capstone: {message}", "danger")
            return render_template("admin/update_capstone.html", hide_nav=False, form_data=request.form, programs=programs, specializations=specializations, used_keywords=used_keywords, capstone=capstone)

        authors, adviser = _parse_capstone_people(request.form)

        if not (adviser["first"] and adviser["last"]):
            flash("Adviser information is required.", "danger")
            return render_template("admin/update_capstone.html", hide_nav=False, form_data=request.form, programs=programs, specializations=specializations, used_keywords=used_keywords, capstone=capstone)

        ok, err = set_capstone_people(capstone_id, authors, adviser)
        if not ok:
            flash(
                f"Capstone updated, but author/adviser save failed: {err}", "warning")
        else:
            flash("Capstone updated successfully!", "success")
        return redirect(url_for("admin.view_capstone_repository"))

    except Exception as e:
        flash(f"Error: {e}", "danger")

    return render_template(
        "admin/update_capstone.html",
        form_data=capstone,
        programs=programs,
        specializations=specializations,
        used_keywords=used_keywords,
        capstone=capstone,
    )


@admin.route("/delete_capstone/<int:capstone_id>", methods=["POST"])
@role_required(3)
def delete_capstone_route(capstone_id):
    try:
        success, message = delete_capstone(capstone_id)
        flash(message, "success" if success else "danger")
    except Exception as e:
        flash(f"Error: {e}", "danger")

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
    success, message = add_to_bin(capstone_id)
    flash(message, "success" if success else "danger")
    return redirect(url_for("admin.view_capstone_repository"))


@admin.route("/recyclebin/restore/<int:capstone_id>", methods=["POST"])
@role_required(3)
def restore_capstone_route(capstone_id):
    success, message = restore_capstone(capstone_id)
    flash(message, "success" if success else "danger")
    return redirect(url_for("admin.view_capstone_repository"))
