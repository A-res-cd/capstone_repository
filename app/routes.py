from flask import Blueprint, flash, render_template, request, redirect, url_for, session
from flask_mail import Mail, Message
from app.config.mysql import create_user, sign_in
from .variables.variable import get_nav_links, get_role_meta, resolve_title
<<<<<<< HEAD
from .config.mysql import create_user, sign_in
import re
=======
from .config.mysql import create_user, sign_in, lookup_user_for_reset, create_otp, verify_otp, change_password, sign_out
from app import mail
>>>>>>> 18f8eac20cc0bbfbbd6cd58cae6fc5e68d80ca89

main = Blueprint("main", __name__)


@main.app_context_processor
def inject_global_template_vars():
    role = session.get("role_name", "Admin")

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

<<<<<<< HEAD

=======
>>>>>>> 18f8eac20cc0bbfbbd6cd58cae6fc5e68d80ca89
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
            return redirect(url_for("main.home"))
        else:
            flash(error, "error")

    return render_template("authentication/signin.html", hide_nav=True, hide_header=True)

<<<<<<< HEAD

=======
>>>>>>> 18f8eac20cc0bbfbbd6cd58cae6fc5e68d80ca89
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
        errors = []
        if not university_no:
            flash("University ID is required.", "danger")
            return render_template("authentication/signup.html", hide_nav=True, hide_header=True, form_data=request.form)
        else:
            numeric_format = re.match(r'^2\d{9}$', university_no)
            dash_format = re.match(r'^2\{3}-\d{5}$', university_no)

            if not numeric_format and not dash_format:
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
    user_id = session.get("user_id")

    if user_id:
        device_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        success, error = sign_out(user_id, device_ip=device_ip)

        if not success:
            print("Logout DB error:", error)  # won't block logout

    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("main.signin"))

<<<<<<< HEAD
# forfot password


@main.route("/forgot_password")
=======
@main.route("/forgot_password", methods=["GET", "POST"])
>>>>>>> 18f8eac20cc0bbfbbd6cd58cae6fc5e68d80ca89
def forgot_password():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email    = request.form.get("email",    "").strip()
 
        errors = []
        if not username: errors.append("Username is required.")
        if not email:    errors.append("Email is required.")
 
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("authentication/forgot_password.html",
                                   hide_nav=True, hide_header=True)
 
        # 1.4.1 — look up user; both fields must match
        contact_id, user_id, error = lookup_user_for_reset(username, email)
 
        if error:
            flash(error, "danger")
            return render_template("authentication/forgot_password.html",
                                   hide_nav=True, hide_header=True)
 
        # 1.4.2 — generate OTP and email it
        try:
            otp, reset_id = create_otp(contact_id)
        except RuntimeError as e:
            flash(str(e), "danger")
            return render_template("authentication/forgot_password.html",
                                   hide_nav=True, hide_header=True)
 
        # Send OTP email via Flask-Mail
        try:
            msg = Message(
                subject="Your password reset OTP",
                recipients=[email],
                body=(
                    f"Your one-time password (OTP) is: {otp}\n\n"
                    f"It expires in 5 minutes. Do not share it with anyone.\n\n"
                    f"If you did not request this, ignore this email."
                )
            )
            mail.send(msg)
        except Exception as e:
            print("MAIL ERROR:", e)  # ← only this line is new
            flash("Could not send email. Please try again later.", "danger")
            return render_template("authentication/forgot_password.html",
                                   hide_nav=True, hide_header=True)
 
        # Store reset_id and user_id in session to carry across steps
        session["reset_id"] = reset_id
        session["reset_user_id"] = user_id
 
        flash("OTP sent! Check your email.", "success")
        return redirect(url_for("main.verify_otp_route"))
 
    return render_template("authentication/forgot_password.html", hide_nav=True, hide_header=True)

<<<<<<< HEAD
# --- Admin specific routes ---
=======
@main.route("/verify_otp", methods=["GET", "POST"])
def verify_otp_route():
    reset_id = session.get("reset_id")
    if not reset_id:
        flash("Session expired. Please start again.", "danger")
        return redirect(url_for("main.forgot_password"))
 
    if request.method == "POST":
        otp_entered = request.form.get("otp", "").strip()
 
        if not otp_entered:
            flash("Please enter the OTP.", "danger")
            return render_template("authentication/verify_otp.html",
                                   hide_nav=True, hide_header=True)
 
        # 1.4.3 — validate OTP
        valid, error = verify_otp(reset_id, otp_entered)
 
        if valid:
            session["otp_verified"] = True
            return redirect(url_for("main.reset_password_route"))
        else:
            flash(error, "danger")
 
    return render_template("authentication/verify_otp.html",
                           hide_nav=True, hide_header=True)

@main.route("/reset_password", methods=["GET", "POST"])
def reset_password_route():
    # Guard — must have passed OTP step
    if not session.get("otp_verified"):
        flash("Please verify your OTP first.", "danger")
        return redirect(url_for("main.forgot_password"))
 
    reset_id = session.get("reset_id")
    user_id  = session.get("reset_user_id")
 
    if not reset_id or not user_id:
        flash("Session expired. Please start again.", "danger")
        return redirect(url_for("main.forgot_password"))
 
    if request.method == "POST":
        new_password     = request.form.get("new_password",     "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()
 
        errors = []
        if not new_password or len(new_password) < 6:
            errors.append("Password must be at least 6 characters.")
        if new_password != confirm_password:
            errors.append("Passwords do not match.")
 
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("authentication/reset_password.html",
                                   hide_nav=True, hide_header=True)
 
        # 1.4.4 — update password, mark token used, log audit
        success, error = change_password(reset_id, user_id, new_password)
 
        if success:
            # Clear all reset session keys
            session.pop("reset_id",      None)
            session.pop("reset_user_id", None)
            session.pop("otp_verified",  None)
            flash("Password reset successfully! Please sign in.", "success")
            return redirect(url_for("main.signin"))
        else:
            flash(error, "danger")
 
    return render_template("authentication/reset_password.html",
                           hide_nav=True, hide_header=True)
 
 
## --- Admin specific routes ---
>>>>>>> 18f8eac20cc0bbfbbd6cd58cae6fc5e68d80ca89
@main.route("/analytics")
def admin_analytics():
    return render_template("admin/analytics.html", hide_nav=False)


@main.route("/manage_users")
def admin_manage_users():
    return render_template("admin/manage_users.html", hide_nav=False)


@main.route("/requests")
def admin_requests():
    return render_template("admin/requests.html", hide_nav=False)
<<<<<<< HEAD
=======

@main.route("/repository")
def admin_repository():
    return render_template("admin/repository.html", hide_nav=False)

@main.route("/add_capstone_record")
def admin_add_capstone_record():
    return render_template("admin/add_capstone_record.html", hide_nav=False)
>>>>>>> 18f8eac20cc0bbfbbd6cd58cae6fc5e68d80ca89
