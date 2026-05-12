from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from .variables.variable import get_nav_links, get_role_meta, resolve_title
from .config.mysql import create_user, sign_in, create_capstone_project, insert_keywords, get_programs, get_specializations, get_used_keyword, update_keyword, get_capstone_details, update_capstone_record, get_all_capstones, delete_capstone
import re
import os
from werkzeug.utils import secure_filename

main = Blueprint("main", __name__)


@main.app_context_processor
def inject_global_template_vars():
    role = session.get("role_name", "admin")

    # 2. Get nav + role meta
    nav_links, nav_sections = get_nav_links(role)
    role_meta = get_role_meta(role)

    # 3. Resolve title automatically
    page_title = resolve_title(nav_sections, nav_links, request.path)

    return {
        "nav_links": nav_links,
        "nav_sections": nav_sections,
        "role_meta": role_meta,
        "page_title": page_title,
    }

# --- Landings & Auth routes ---


@main.route("/")
def home():
    return render_template("index.html", hide_nav=True)


@main.route("/signin", methods=["GET", "POST"])
def signin():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        # Validation
        errors = []
        if not username:
            errors.append("Username is required.")
        if not password:
            errors.append("Password is required.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("authentication/signin.html",
                                   hide_nav=True, hide_header=True)

        # Capture device IP for login table
        device_ip = request.headers.get("X-Forwarded-For",
                                        request.remote_addr)

        user, error = sign_in(username, password, device_ip=device_ip)

        if user:
            session["user_id"] = user["user_id"]
            session["username"] = user["username"]
            session["role_id"] = user["role_id"]
            session["role_name"] = user["role_name"]
            return redirect(url_for("main.view_capstone_repository"))
        else:
            flash(error, "error")

    return render_template("authentication/signin.html", hide_nav=True, hide_header=True)


@main.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        first_name = request.form.get('first_name')
        middle_name = request.form.get('middle_name')
        last_name = request.form.get('last_name')
        university_no = request.form.get('university_no')
        email = request.form.get('email')
        username = request.form.get('username')
        password = request.form.get('password')
        if not university_no:
            flash("University ID is required.", "danger")
            return render_template("authentication/signup.html", hide_nav=True, hide_header=True, form_data=request.form)
        else:
            numeric_format = re.match(r'^2\d{9}$', university_no)
            dash_format = re.match(r'^2\d{3}-\d{5}$', university_no)
            admin_format = re.match(r'^admin\d{3}$', university_no)

            if not numeric_format and not dash_format and not admin_format:
                flash("University ID must follow the format", "danger")
                return render_template("authentication/signup.html", hide_nav=True, hide_header=True, form_data=request.form)

        success, message = create_user(
            first_name, middle_name, last_name,
            university_no, email, username, password
        )
        if success:
            flash("Account created successfully! Please sign in.", "success")
            return redirect(url_for('main.signin'))
        else:
            flash(message, "danger")

            return render_template("authentication/signup.html",
                                   hide_nav=True, hide_header=True,
                                   form_data=request.form)

    return render_template("authentication/signup.html", hide_nav=True, hide_header=True, form_data={})


@main.route("/logout")
def logout():
    session.clear()
    return render_template("index.html", hide_nav=True, hide_header=True)

# forgot password


@main.route("/forgot_password")
def forgot_password():
    return render_template(
        "authentication/forgot_password.html",
        hide_nav=True,
        hide_header=True
    )


# --- Admin specific routes ---
UPLOAD_FOLDER = 'app/static/uploads'
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}


@main.route("/analytics")
def admin_analytics():
    return render_template("admin/analytics.html", hide_nav=False)


@main.route("/manage_users")
def admin_manage_users():
    return render_template("admin/manage_users.html", hide_nav=False)


@main.route("/requests")
def admin_requests():
    return render_template("admin/requests.html", hide_nav=False)


@main.route("/create_capstone", methods=["GET", "POST"])
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


@main.route("/repository")
def view_capstone_repository():
    capstones = get_all_capstones()
    return render_template("admin/capstone_repository.html", hide_nav=False, capstones=capstones)


@main.route("/say_wallahi")
def wallahi():
    return render_template("admin/repository.html", hide_nav=False, form_data=request.form)


@main.route("/update_capstone/<int:capstone_id>", methods=["GET", "POST"])
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


@main.route("/delete_capstone/<int:capstone_id>", methods=["POST"])
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
