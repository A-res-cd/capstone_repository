from flask import Blueprint, flash, render_template, request, redirect, url_for, session
from flask_mail import Message
import psycopg2.extras
from app.db.database import db_connect

from app.db.database import (
    create_user,
    sign_in,
    sign_out,
    lookup_user_for_reset,
    create_otp,
    verify_otp,
    change_password,
    OTP_EXPIRY_MINUTES,
)
from app import mail

from app.routes.forms import (
    SigninForm, SignupForm, ForgotPasswordForm, ResetPasswordForm, VerifyOTPForm)

auth = Blueprint("auth", __name__)


@auth.route("/signin", methods=["GET", "POST"])
def signin():
    locked_until = None
    form = SigninForm()

    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        device_ip = request.headers.get("X-Forwarded-For", request.remote_addr)

        user, error = sign_in(username, password, device_ip=device_ip)

        if error:
            if "locked" in error.lower():
                locked_until = None
                conn = db_connect()
                cur = conn.cursor(
                    cursor_factory=psycopg2.extras.RealDictCursor)
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
                    locked_until = row["locked_until"].isoformat()
            else:
                flash(error, "error")

            return render_template("authentication/signin.html", form=form, hide_nav=True, hide_header=True, locked_until=locked_until)
        if user:
            session["user_id"] = user["user_id"]
            session["username"] = user["username"]
            session["role_id"] = user["role_id"]
            session["role_name"] = user["role_name"]

            if user["role_id"] == 3:    # Admin
                return redirect(url_for("admin.analytics"))
            elif user["role_id"] == 4:  # Capstone Professor
                return redirect(url_for("admin.view_capstone_repository"))
            elif user["role_id"] == 2:  # Faculty
                return redirect(url_for("pages.browse"))
            else:                        # Student (1)
                return redirect(url_for("pages.browse"))
        else:
            flash(error, "error")

    return render_template("authentication/signin.html", form=form, hide_nav=True, hide_header=True)


@auth.route("/signup", methods=["GET", "POST"])
def signup():
    form = SignupForm()

    if form.validate_on_submit():
        success, message = create_user(
            form.first_name.data,
            form.middle_name.data,
            form.last_name.data,
            None,
            form.email.data,
            form.username.data,
            form.password.data,
        )

        if success:
            flash("Account created successfully! Please sign in.", "success")
            return redirect(url_for("auth.signin"))
        else:
            flash(message, "danger")
            return render_template("authentication/signup.html", form=form,
                                   hide_nav=True, hide_header=True,
                                   form_data=request.form)

    return render_template("authentication/signup.html", form=form,
                           hide_nav=True, hide_header=True, form_data={})


@auth.route("/logout")
def logout():
    user_id = session.get("user_id")
    if user_id:
        device_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        sign_out(user_id, device_ip=device_ip)

    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.signin"))


@auth.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    form = ForgotPasswordForm()

    if form.validate_on_submit():
        username = form.username.data
        email = form.email.data

        errors = []
        if not username:
            errors.append("Username is required.")
        if not email:
            errors.append("Email is required.")

        contact_id, user_id, error = lookup_user_for_reset(username, email)
        if error:
            flash(error, "danger")
            return render_template("authentication/forgot_password.html", form=form,
                                   hide_nav=True, hide_header=True)

        try:
            otp, reset_id = create_otp(contact_id)
        except RuntimeError as e:
            flash(str(e), "danger")
            return render_template("authentication/forgot_password.html", form=form,
                                   hide_nav=True, hide_header=True)

        try:
            mail.send(Message(
                subject="Your password reset OTP",
                recipients=[email],
                body=(
                    f"Your one-time password (OTP) is: {otp}\n\n"
                    f"It expires in {OTP_EXPIRY_MINUTES} minutes. Do not share it with anyone.\n\n"
                    "If you did not request this, ignore this email."
                ),
            ))
        except Exception:
            flash("Could not send email. Please try again later.", "danger")
            return render_template("authentication/forgot_password.html", form=form,
                                   hide_nav=True, hide_header=True)

        session["reset_id"] = reset_id
        session["reset_user_id"] = user_id
        flash("OTP sent! Check your email.", "success")
        return redirect(url_for("auth.verify_otp_route"))
    return render_template("authentication/forgot_password.html", form=form,
                           hide_nav=True, hide_header=True)


@auth.route("/verify_otp", methods=["GET", "POST"])
def verify_otp_route():
    reset_id = session.get("reset_id")
    if not reset_id:
        flash("Session expired. Please start again.", "danger")
        return redirect(url_for("auth.forgot_password"))

    form = VerifyOTPForm()

    if form.validate_on_submit():
        otp_entered = form.otp.data
        valid, error = verify_otp(reset_id, otp_entered)
        if valid:
            session["otp_verified"] = True
            return redirect(url_for("auth.reset_password_route"))
        else:
            flash(error, "danger")

    return render_template("authentication/verify_otp.html",
                           form=form, hide_nav=True, hide_header=True,
                           otp_expiry_minutes=OTP_EXPIRY_MINUTES)


@auth.route("/reset_password", methods=["GET", "POST"])
def reset_password_route():
    if not session.get("otp_verified"):
        flash("Please verify your OTP first.", "danger")
        return redirect(url_for("auth.forgot_password"))

    reset_id = session.get("reset_id")
    user_id = session.get("reset_user_id")
    if not reset_id or not user_id:
        flash("Session expired. Please start again.", "danger")
        return redirect(url_for("auth.forgot_password"))

    form = ResetPasswordForm()

    if form.validate_on_submit():
        success, error = change_password(
            reset_id, user_id, form.new_password.data)

        if success:
            session.pop("reset_id",      None)
            session.pop("reset_user_id", None)
            session.pop("otp_verified",  None)
            flash("Password reset successfully! Please sign in.", "success")
            return redirect(url_for("auth.signin"))
        else:
            flash(error, "danger")

    return render_template("authentication/reset_password.html", form=form,
                           hide_nav=True, hide_header=True)


def get_current_user(user_id):
    """Get the current logged-in user from the session."""
    if not user_id:
        return None

    conn = db_connect()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT u.user_id, u.first_name, u.middle_name, u.last_name, u.email, u.role_id, r.role_name, u.locked_until
        FROM "user" u
        JOIN role r ON u.role_id = r.role_id
        WHERE u.user_id = %s
        LIMIT 1
    """, (user_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    return user
