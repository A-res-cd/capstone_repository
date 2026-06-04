from flask import Blueprint, flash, render_template, request, redirect, url_for, session

from app.config.mysql import (
    create_user,
    sign_in,
    sign_out,
    lookup_user_for_reset,
    create_otp,
    verify_otp,
    change_password,
)

from app import mail
from flask_mail import Message

auth = Blueprint("auth", __name__)


@auth.route("/signin", methods=["GET", "POST"])
def signin():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        errors = []
        if not username: errors.append("Username is required.")
        if not password: errors.append("Password is required.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("authentication/signin.html", hide_nav=True, hide_header=True, locked_until=None)


        device_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        user, error = sign_in(username, password, device_ip=device_ip)
        if error:
            if "locked" in error.lower():
                from app.config.mysql import db_connect
                import psycopg2.extras
                conn = db_connect()
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cur.execute("""
                    SELECT u.locked_until
                    FROM "user" u
                    JOIN slug sl ON sl.user_id = u.user_id AND sl.is_current = TRUE
                    JOIN kappa k ON k.username_id = sl.username_id
                    WHERE k.username = %s
                    LIMIT 1
                """, (username,))
                row = cur.fetchone()
                cur.close()
                conn.close()
                if row and row["locked_until"]:
                    locked_until = None
                    locked_until = row["locked_until"].isoformat()
            else:
                flash(error, "error")

            return render_template("authentication/signin.html", hide_nav=True, hide_header=True, locked_until=locked_until)
        if user:
            session["user_id"]   = user["user_id"]
            session["username"]  = user["username"]
            session["role_id"]   = user["role_id"]
            session["role_name"] = user["role_name"]

            if user["role_id"] == 1:    # Admin
                return redirect(url_for("admin.analytics"))
            elif user["role_id"] == 4:  # Student
                return redirect(url_for("pages.browse"))
        else:
            flash(error, "error")

    return render_template("authentication/signin.html", hide_nav=True, hide_header=True)


@auth.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        first_name    = request.form.get("first_name")
        middle_name   = request.form.get("middle_name")
        last_name     = request.form.get("last_name")
        university_no = request.form.get("university_no")
        email         = request.form.get("email")
        username      = request.form.get("username")
        password      = request.form.get("password")

        success, message = create_user(
            first_name, middle_name, last_name,
            university_no, email, username, password,
        )

        if success:
            flash("Account created successfully! Please sign in.", "success")
            return redirect(url_for("auth.signin"))
        else:
            flash(message, "danger")
            return render_template("authentication/signup.html",
                                   hide_nav=True, hide_header=True,
                                   form_data=request.form)

    return render_template("authentication/signup.html",
                           hide_nav=True, hide_header=True, form_data={})


@auth.route("/logout")
def logout():
    user_id = session.get("user_id")

    if user_id:
        device_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        success, error = sign_out(user_id, device_ip=device_ip)
        if not success:
            print("Logout DB error:", error)

    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.signin"))


@auth.route("/forgot_password", methods=["GET", "POST"])
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

        contact_id, user_id, error = lookup_user_for_reset(username, email)

        if error:
            flash(error, "danger")
            return render_template("authentication/forgot_password.html",
                                   hide_nav=True, hide_header=True)

        try:
            otp, reset_id = create_otp(contact_id)
        except RuntimeError as e:
            flash(str(e), "danger")
            return render_template("authentication/forgot_password.html",
                                   hide_nav=True, hide_header=True)

        try:
            msg = Message(
                subject="Your password reset OTP",
                recipients=[email],
                body=(
                    f"Your one-time password (OTP) is: {otp}\n\n"
                    f"It expires in 5 minutes. Do not share it with anyone.\n\n"
                    f"If you did not request this, ignore this email."
                ),
            )
            mail.send(msg)
        except Exception as e:
            print("MAIL ERROR:", e)
            flash("Could not send email. Please try again later.", "danger")
            return render_template("authentication/forgot_password.html",
                                   hide_nav=True, hide_header=True)

        session["reset_id"]      = reset_id
        session["reset_user_id"] = user_id

        flash("OTP sent! Check your email.", "success")
        return redirect(url_for("auth.verify_otp_route"))

    return render_template("authentication/forgot_password.html",
                           hide_nav=True, hide_header=True)


@auth.route("/verify_otp", methods=["GET", "POST"])
def verify_otp_route():
    reset_id = session.get("reset_id")
    if not reset_id:
        flash("Session expired. Please start again.", "danger")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        otp_entered = request.form.get("otp", "").strip()

        if not otp_entered:
            flash("Please enter the OTP.", "danger")
            return render_template("authentication/verify_otp.html",
                                   hide_nav=True, hide_header=True)

        valid, error = verify_otp(reset_id, otp_entered)

        if valid:
            session["otp_verified"] = True
            return redirect(url_for("auth.reset_password_route"))
        else:
            flash(error, "danger")

    return render_template("authentication/verify_otp.html",
                           hide_nav=True, hide_header=True)


@auth.route("/reset_password", methods=["GET", "POST"])
def reset_password_route():
    if not session.get("otp_verified"):
        flash("Please verify your OTP first.", "danger")
        return redirect(url_for("auth.forgot_password"))

    reset_id = session.get("reset_id")
    user_id  = session.get("reset_user_id")

    if not reset_id or not user_id:
        flash("Session expired. Please start again.", "danger")
        return redirect(url_for("auth.forgot_password"))

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

        success, error = change_password(reset_id, user_id, new_password)

        if success:
            session.pop("reset_id",      None)
            session.pop("reset_user_id", None)
            session.pop("otp_verified",  None)
            flash("Password reset successfully! Please sign in.", "success")
            return redirect(url_for("auth.signin"))
        else:
            flash(error, "danger")

    return render_template("authentication/reset_password.html",
                           hide_nav=True, hide_header=True)
