"""Authentication passwords routes and local helpers."""
from . import auth
from flask import flash, render_template, redirect, url_for, session
from app.utils.account_emails import password_reset_email
from smtplib import SMTPException
import logging
from app.db.auth import (
    lookup_user_for_reset,
    create_otp,
    verify_otp,
    change_password,
    OTP_EXPIRY_MINUTES,
)
from app import mail
from app.routes.forms import ForgotPasswordForm, ResetPasswordForm, VerifyOTPForm


logger = logging.getLogger(__name__)


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
        except RuntimeError:
            flash("Could not start password reset. Please try again.", "danger")
            return render_template("authentication/forgot_password.html", form=form,
                                   hide_nav=True, hide_header=True)

        try:
            mail.send(password_reset_email(email, username, otp, OTP_EXPIRY_MINUTES))
        except (SMTPException, OSError) as exc:
            logger.error("Could not send password reset email: %s", exc)
            flash("Could not send the reset email. Please try again.", "danger")
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
