from flask import Blueprint, render_template, request, redirect, url_for, flash
import os
from app.config.mysql import (
    get_all_capstones, get_programs, get_specializations,
    insert_keywords, create_capstone_project,
    get_capstone_details, update_capstone_record, update_keyword,
    delete_capstone, get_users
)

admin = Blueprint("admin", __name__)

UPLOAD_FOLDER = os.path.join("app", "static", "uploads")
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx"}


def _allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _save_file(file_obj):
    """Save uploaded file, return stored filename or None."""
    if not file_obj or file_obj.filename == "":
        return None
    if not _allowed(file_obj.filename):
        return None
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    filename = file_obj.filename
    file_obj.save(os.path.join(UPLOAD_FOLDER, filename))
    return filename


# ── Static pages ──────────────────────────────────────────────────────────────

@admin.route("/analytics")
def analytics():
    return render_template("admin/analytics.html", hide_nav=False)


@admin.route("/manage_users")
def manage_users():
    users = get_users()
    return render_template("admin/manage_users.html", users=users, hide_nav=False)


@admin.route("/requests")
def requests():
    return render_template("admin/requests.html", hide_nav=False)


# ── Repository (list + create form on same page) ──────────────────────────────

@admin.route("/repository")
def view_capstone_repository():
    capstones       = get_all_capstones()
    programs        = get_programs()
    specializations = get_specializations()
    return render_template(
        "admin/repository.html",
        hide_nav=False,
        capstones=capstones,
        programs=programs,
        specializations=specializations,
    )


@admin.route("/repository/create", methods=["POST"])
def admin_create_capstone():
    title        = request.form.get("capstone_title", "").strip()
    keywords_raw = request.form.get("capstone_keywords", "").strip()
    program_id   = request.form.get("program_id")
    spec_id      = request.form.get("specialization_id")
    year         = request.form.get("capstone_year")
    semester     = request.form.get("semester")
    term         = request.form.get("term")
    citations    = request.form.get("citation_count", 0)
    file_obj     = request.files.get("capstone_file")

    if not all([title, keywords_raw, program_id, spec_id, year, semester, term]):
        flash("All required fields must be filled.", "error")
        return redirect(url_for("admin.view_capstone_repository"))

    saved_filename = _save_file(file_obj)

    ok, keyword_id = insert_keywords(keywords_raw)
    if not ok:
        flash(f"Could not save keywords: {keyword_id}", "error")
        return redirect(url_for("admin.view_capstone_repository"))

    ok, err = create_capstone_project(
        keyword_id, spec_id, program_id,
        title, year, saved_filename,
        citations, semester, term,
    )

    if ok:
        flash("Capstone created successfully.", "success")
    else:
        flash(f"Error creating capstone: {err}", "error")

    return redirect(url_for("admin.view_capstone_repository"))


@admin.route("/repository/update/<int:capstone_id>", methods=["POST"])
def update_capstone(capstone_id):
    capstone = get_capstone_details(capstone_id)
    if not capstone:
        flash("Capstone not found.", "error")
        return redirect(url_for("admin.view_capstone_repository"))

    title        = request.form.get("capstone_title", "").strip()
    keywords_raw = request.form.get("capstone_keywords", "").strip()
    program_id   = request.form.get("program_id")
    spec_id      = request.form.get("specialization_id")
    year         = request.form.get("capstone_year")
    semester     = request.form.get("semester")
    term         = request.form.get("term")
    citations    = request.form.get("citation_count", 0)
    file_obj     = request.files.get("capstone_file")

    # update keyword text
    update_keyword(capstone["keyword_id"], keywords_raw)

    # keep old file if none uploaded
    saved_filename = _save_file(file_obj) or capstone["capstone_file"]

    ok, err = update_capstone_record(
        capstone_id, capstone["keyword_id"], spec_id, program_id,
        title, year, saved_filename,
        citations, semester, term,
    )

    if ok:
        flash("Capstone updated successfully.", "success")
    else:
        flash(f"Error updating capstone: {err}", "error")

    return redirect(url_for("admin.view_capstone_repository"))


@admin.route("/delete_capstone/<int:capstone_id>", methods=["POST"])
def admin_delete_capstone(capstone_id):
    ok, msg = delete_capstone(capstone_id)
    flash(msg if ok else f"Error: {msg}", "success" if ok else "error")
    return redirect(url_for("admin.view_capstone_repository"))