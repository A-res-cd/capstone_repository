from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.config.mysql import create_capstone_project, delete_capstone, get_capstone_details, get_programs, get_specializations, get_used_keyword, get_all_capstones, insert_keywords, update_capstone_record, update_keyword
from werkzeug.utils import secure_filename

import os

admin = Blueprint("admin", __name__)

UPLOAD_FOLDER = 'app/static/uploads'
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}

@admin.route("/analytics")
def analytics():
    return render_template("admin/analytics.html", hide_nav=False)


@admin.route("/manage_users")
def manage_users():
    return render_template("admin/manage_users.html", hide_nav=False)


@admin.route("/requests")
def requests():
    return render_template("admin/requests.html", hide_nav=False)


@admin.route("/repository")
def view_capstone_repository():
    capstones = get_all_capstones()
    return render_template("admin/capstone_repository.html", hide_nav=False, capstones=capstones)

@admin.route("/create_capstone", methods=["GET", "POST"])
def admin_create_capstone():
    programs = get_programs()
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
            term = request.form.get('term')

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
                    file_path, citation, sem, term
                )
                if success:
                    flash("Capstone project created successfully!", "success")
                    return redirect(url_for('main.view_capstone_repository'))
                else:
                    flash(message, "danger")

    except Exception as e:
        flash("An error occurred while processing your request.", "danger")

    return render_template("admin/repository.html", hide_nav=False, form_data=request.form, programs=programs, specializations=specializations)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@admin.route("/update_capstone/<int:capstone_id>", methods=["GET", "POST"])
def update_capstone(capstone_id):
    programs = get_programs()
    specializations = get_specializations()
    used_keywords = get_used_keyword()
    capstone = get_capstone_details(capstone_id)

    if not capstone:
        flash("Capstone not found", "danger")
        return redirect(url_for("main.admin_create_capstone"))

    try:
        if request.method == 'POST':
            new_specialization = request.form.get('specialization_id')
            new_program = request.form.get('program_id')
            new_capstone_title = request.form.get('capstone_title')
            new_capstone_year = request.form.get('capstone_year')
            new_citation = request.form.get('citation_count') or 0
            new_sem = request.form.get('semester') or None
            new_term = request.form.get('term', '').strip() or None
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
                new_sem, new_term)

            if not success:
                flash(f"Error updating capstone: {message}", "danger")
            else:
                flash("Capstone updated successfully!", "success")
                return redirect(url_for("main.view_capstone_repository"))

    except Exception as e:
        flash(f"Error: {e}", "danger")
        return render_template("admin/update_capstone.html", hide_nav=False, form_data=capstone, programs=programs, specializations=specializations, used_keywords=used_keywords, capstone=capstone)

    return render_template("admin/update_capstone.html", hide_nav=False, form_data=capstone, programs=programs, specializations=specializations, used_keywords=used_keywords, capstone=capstone)


@admin.route("/delete_capstone/<int:capstone_id>", methods=["POST"])
def delete_capstone_route(capstone_id):
    try:
        success, message = delete_capstone(capstone_id)

        if success:
            flash(message, "success")
        else:
            flash(message, "danger")
    except Exception as e:
        flash(f"Error: {e}", "danger")

    return redirect(url_for("main.view_capstone_repository"))


# @admin.route("/add_capstone_record")
# def add_capstone_record():
#     return render_template("admin/add_capstone_record.html", hide_nav=False)
