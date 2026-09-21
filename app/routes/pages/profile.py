"""Pages profile routes and local helpers."""
from . import pages
from flask import render_template, request, flash, session, redirect, url_for
import re
from app.db.users import (
    get_user_contacts,
    upsert_user_contact,
    get_own_profile,
    delete_own_account,
)
from app.db.auth import change_own_password
from app.routes.decorators import login_required
from app.routes.forms import ChangePasswordForm


EMAIL_PATTERN = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


PHONE_PATTERN = re.compile(r'^[0-9+()\-\s]{7,20}$')


@pages.route("/user-info")
@login_required
def user_info():
    user_id = session.get("user_id")
    profile = get_own_profile(user_id)
    contacts = get_user_contacts(user_id)
    contact_labels = [
        ("email", "Email"),
        ("phone", "Contact Number"),
        ("facebook", "Facebook"),
        ("instagram", "Instagram"),
        ("twitter", "Twitter/X"),
    ]
    contact_by_type = {c["contact_type"]: c for c in contacts}

    return render_template(
        "global/user_information.html",
        hide_nav=False,
        profile=profile,
        contacts=contacts,
        contact_labels=contact_labels,
        contact_by_type=contact_by_type,
        password_form=ChangePasswordForm(),
    )


@pages.route("/user-info/contact", methods=["POST"])
@login_required
def update_user_contact_info():
    user_id = session.get("user_id")
    values = {
        "email": request.form.get("email", "").strip(),
        "phone": request.form.get("phone", "").strip(),
        "facebook": request.form.get("facebook", "").strip(),
        "instagram": request.form.get("instagram", "").strip(),
        "twitter": request.form.get("twitter", "").strip(),
    }

    if values["email"] and not EMAIL_PATTERN.match(values["email"]):
        flash("That doesn't look like a valid email address.", "danger")
        return redirect(url_for("pages.user_info"))

    if values["phone"] and not PHONE_PATTERN.match(values["phone"]):
        flash("That doesn't look like a valid contact number.", "danger")
        return redirect(url_for("pages.user_info"))

    any_saved = False
    for contact_type, contact_value in values.items():
        if contact_value:
            ok, err = upsert_user_contact(user_id, contact_type, contact_value, is_primary=True)
            if not ok:
                flash(err, "danger")
                return redirect(url_for("pages.user_info"))
            any_saved = True

    if any_saved:
        flash("Contact information updated successfully.", "success")
    else:
        flash("No contact information was entered.", "warning")
    return redirect(url_for("pages.user_info"))


@pages.route("/user-info/password", methods=["POST"])
@login_required
def update_own_password():
    form = ChangePasswordForm()

    if not form.validate_on_submit():
        for field_errors in form.errors.values():
            for err in field_errors:
                flash(err, "danger")
                break
            break
        return redirect(url_for("pages.user_info"))

    user_id = session.get("user_id")
    ok, err = change_own_password(
        user_id, form.current_password.data, form.new_password.data)

    if ok:
        flash("Password changed successfully.", "success")
    else:
        flash(err, "danger")
    return redirect(url_for("pages.user_info"))


@pages.route("/user-info/delete", methods=["POST"])
@login_required
def delete_own_account_route():
    password = request.form.get("password", "")
    user_id = session.get("user_id")

    if not password:
        flash("Enter your password to confirm account deletion.", "danger")
        return redirect(url_for("pages.user_info"))

    ok, err = delete_own_account(user_id, password)

    if ok:
        session.clear()
        flash("Your account has been deleted.", "success")
        return redirect(url_for("auth.signin"))

    flash(err, "danger")
    return redirect(url_for("pages.user_info"))
