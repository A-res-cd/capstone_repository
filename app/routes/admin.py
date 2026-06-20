from flask import Blueprint, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
import os
from app.config.mysql import (
    delete_user_account, get_all_capstones, get_programs, get_specializations,
    get_used_keyword, insert_keywords, create_capstone_project,
    get_capstone_details, update_capstone_record, update_keyword,
    delete_capstone, get_users, update_user_role, get_all_roles,
)

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
    return f"uploads/{filename}", None


# ── Static pages ──────────────────────────────────────────────────────────────

@admin.route("/analytics")
def analytics():
    return render_template("admin/analytics.html")


# ── User management ───────────────────────────────────────────────────────────

@admin.route("/manage_users")
def manage_users():
    users = get_users()
    roles = get_all_roles()
    return render_template("admin/manage_users.html", users=users, roles=roles)


@admin.route("/manage_users/update_role/<int:user_id>", methods=["POST"])
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
def requests():
    return render_template("admin/requests.html")


# ── Repository ────────────────────────────────────────────────────────────────

@admin.route("/repository")
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


@admin.route("/repository/create", methods=["POST"])
def admin_create_capstone():
    programs        = get_programs()
    specializations = get_specializations()

    try:
        file_path, file_err = _save_file(request.files.get("capstone_file"))
        if file_err:
            flash(file_err, "danger")
            return render_template(
                "admin/repository.html",
                form_data=request.form,
                programs=programs,
                specializations=specializations,
            )

        success, result = insert_keywords(request.form.get("capstone_keywords"))
        if not success:
            flash(result, "danger")
        else:
            success, message = create_capstone_project(
                result,
                request.form.get("specialization_id"),
                request.form.get("program_id"),
                request.form.get("capstone_title"),
                request.form.get("capstone_year"),
                file_path,
                request.form.get("citation_count"),
                request.form.get("semester"),
            )
            if success:
                flash("Capstone project created successfully!", "success")
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
def update_capstone(capstone_id):
    programs        = get_programs()
    specializations = get_specializations()
    used_keywords   = get_used_keyword()
    capstone        = get_capstone_details(capstone_id)

    if not capstone:
        flash("Capstone not found.", "danger")
        return redirect(url_for("admin.view_capstone_repository"))

    try:
        file_path = capstone["capstone_file"]
        new_file_path, file_err = _save_file(request.files.get("capstone_file"))
        if file_err:
            flash(file_err, "danger")
            return render_template(
                "admin/update_capstone.html",
                form_data=request.form,
                programs=programs,
                specializations=specializations,
                used_keywords=used_keywords,
                capstone=capstone,
            )
        if new_file_path:
            file_path = new_file_path

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
def delete_capstone_route(capstone_id):
    try:
        success, message = delete_capstone(capstone_id)
        flash(message, "success" if success else "danger")
    except Exception as e:
        flash(f"Error: {e}", "danger")

    return redirect(url_for("admin.view_capstone_repository"))
