from flask import Blueprint, render_template, request, redirect, session, url_for, flash
from werkzeug.utils import secure_filename
import os
from app.db.database import (
    delete_user_account, get_all_capstones, get_programs, get_specializations,
    get_used_keyword, insert_keywords, create_capstone_project,
    get_capstone_details, update_capstone_record, update_keyword,
    delete_capstone, get_users, update_user_role, get_all_roles,
    get_all_requests, review_request, set_capstone_people, get_capstone_people,
    get_capstones_by_program, get_requests_by_status, get_top_cited_capstones
)
from app.routes.decorators import role_required

admin = Blueprint("admin", __name__)

UPLOAD_FOLDER      = os.path.join("app", "static", "uploads")
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx"}


def _allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _save_file(file_obj):
    """Validate and save an uploaded file. Returns (relative_path, error_msg)."""
    if not file_obj or not file_obj.filename:
        return None, None
    if not _allowed(file_obj.filename):
        return None, "Invalid file type. Only PDF, DOC, and DOCX are allowed."
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    filename = secure_filename(file_obj.filename)
    file_obj.save(os.path.join(UPLOAD_FOLDER, filename))
    return filename

#this is new
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
    by_program = get_capstones_by_program()
    by_status  = get_requests_by_status()
    top_cited  = get_top_cited_capstones(limit=5)

    program_labels = [row["program_name"] for row in by_program]
    program_totals = [row["total"] for row in by_program]

    status_labels = [row["request_status"].capitalize() for row in by_status]
    status_totals = [row["total"] for row in by_status]

    return render_template(
        "admin/analytics.html",
        program_labels=program_labels,
        program_totals=program_totals,
        status_labels=status_labels,
        status_totals=status_totals,
        top_cited=top_cited,
    )


# ── User management ───────────────────────────────────────────────────────────

@admin.route("/manage_users")
@role_required(3)
def manage_users():
    users = get_users()
    roles = get_all_roles()
    return render_template("admin/manage_users.html", users=users, roles=roles)


@admin.route("/manage_users/update_role/<int:user_id>", methods=["POST"])
@role_required(3)
def update_role(user_id):
    new_role_id     = request.form.get("role_id")
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

@admin.route("/requests")
@role_required(3)
def view_requests():
    requests = get_all_requests()
    return render_template("admin/requests.html", hide_nav=False, requests=requests)


# ── Repository ────────────────────────────────────────────────────────────────

@admin.route("/repository")
@role_required(3)
def view_capstone_repository():
    capstones       = get_all_capstones()
    programs        = get_programs()
    specializations = get_specializations()
    return render_template(
        "admin/repository.html",
        capstones=capstones,
        programs=programs,
        specializations=specializations,
    )

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@admin.route("/repository/create", methods=["POST"])
@role_required(3)
def admin_create_capstone():
    programs        = get_programs()
    specializations = get_specializations()
    try:
        if request.method == 'POST':
            specialization = request.form.get('specialization_id')
            program = request.form.get('program_id')
            capstone_title = request.form.get('capstone_title')
            capstone_year = request.form.get('capstone_year')
            capstone_file = request.files.get('capstone_file').filename
            citation = request.form.get('citation_count')
            sem = request.form.get('semester')

            file = request.files.get('capstone_file')
            if not file or not allowed_file(file.filename):
                flash(
                    "Invalid file type. Only PDF, DOC, and DOCX are allowed.", "danger")
                return render_template("admin/repository.html", hide_nav=False, form_data=request.form, programs=programs, specializations=specializations)
            filename = secure_filename(file.filename)
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            file.save(os.path.join(UPLOAD_FOLDER, filename))
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
                    
                    ok, err = set_capstone_people(new_capstone_id, authors, adviser)
                    if not ok:
                        flash(f"Capstone created, but author/adviser save failed: {err}", "warning")
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
    programs        = get_programs()
    specializations = get_specializations()
    used_keywords   = get_used_keyword()
    capstone        = get_capstone_details(capstone_id)

    if not capstone:
        flash("Capstone not found.", "danger")
        return redirect(url_for("admin.view_capstone_repository"))

    try:
        if request.method == 'POST':
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
                if not allowed_file(file.filename):
                    flash(
                        "Invalid file type. Only PDF, DOC, and DOCX are allowed.", "danger")
                    return render_template("admin/update_capstone.html", hide_nav=False, form_data=request.form, programs=programs, specializations=specializations, used_keywords=used_keywords, capstone=capstone)

                filename = secure_filename(file.filename)
                os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                file.save(os.path.join(UPLOAD_FOLDER, filename))
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
            else:
                authors, adviser = _parse_capstone_people(request.form)

                if not (adviser["first"] and adviser["last"]):
                    flash("Adviser information is required.", "danger")
                    return render_template("admin/update_capstone.html", hide_nav=False, form_data=request.form, programs=programs, specializations=specializations, used_keywords=used_keywords, capstone=capstone)

                ok, err = set_capstone_people(capstone_id, authors, adviser)
                if not ok:
                    flash(f"Capstone updated, but author/adviser save failed: {err}", "warning")
                else:
                    flash("Capstone updated successfully!", "success")
                return redirect(url_for("admin.view_capstone_repository"))
        keyword_id   = capstone["keyword_id"]
        new_keywords = request.form.get("capstone_keywords", "").strip()
        if new_keywords and new_keywords != capstone["capstone_keywords"]:
            ok, err = update_keyword(keyword_id, new_keywords)
            if not ok:
                flash(f"Error updating keyword: {err}", "danger")
                return render_template(
                    "admin/update_capstone.html",
                    form_data=request.form,
                    programs=programs,
                    specializations=specializations,
                    used_keywords=used_keywords,
                    capstone=capstone,
                )

        success, message = update_capstone_record(
            capstone_id,
            keyword_id,
            request.form.get("specialization_id"),
            request.form.get("program_id"),
            request.form.get("capstone_title"),
            request.form.get("capstone_year"),
            file_path,
            request.form.get("citation_count") or 0,
            request.form.get("semester") or None,
        )

        if success:
            flash("Capstone updated successfully!", "success")
            return redirect(url_for("admin.view_capstone_repository"))
        else:
            flash(f"Error updating capstone: {message}", "danger")

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
    
    return render_template(
        "admin/view_capstone.html",
        capstone=capstone,
        max_pages=max_pages
    )

#this is new
@admin.route("/repository/pdf/<int:capstone_id>")
@role_required(3)
def view_capstone_pdf(capstone_id):
    capstone = get_capstone_details(capstone_id)
    if not capstone:
        flash("Capstone not found.", "danger")
        return redirect(url_for("admin.view_capstone_repository"))
    return render_template("admin/view_capstone.html", capstone=capstone, max_pages=None)


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
