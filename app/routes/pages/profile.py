"""Pages profile routes and local helpers."""
from . import pages
from flask import render_template, request, flash, session, redirect, url_for, send_file, abort, current_app
from app.utils.contact_policy import normalize_phone
from app.utils.avatars import save_avatar, remove_avatar, avatar_path
from app.db.profile_settings import save_contact_settings, swap_avatar
import re
from io import BytesIO
from app.db.users import (
    get_user_contacts,
    get_own_profile,
    delete_own_account,
)
from app.db.auth import change_own_password
from app.routes.decorators import login_required
from app.routes.forms import ChangePasswordForm


EMAIL_PATTERN = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


@pages.route("/user-info")
@login_required
def user_info():
    user_id = session.get("user_id")
    profile = get_own_profile(user_id)
    contacts = get_user_contacts(user_id)
    contact_labels = [
        ("email", "Email"),
        ("phone", "Contact Number"),
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
    }

    preference = request.form.get("preferred_contact", "email")
    try:
        values["phone"] = normalize_phone(values["phone"])
        if not EMAIL_PATTERN.fullmatch(values["email"]):
            raise ValueError("Enter a valid email for account recovery.")
        if preference not in ('email', 'phone') or (preference == 'phone' and not values['phone']):
            raise ValueError("Provide your preferred contact details.")
        save_contact_settings(user_id, values['email'].lower(), values['phone'], preference)
        flash("Contact information updated successfully.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    except Exception:
        current_app.logger.exception("Contact update failed")
        flash("Could not update contacts. Check that the email is not already in use.", "danger")
    return redirect(url_for("pages.user_info"))


@pages.route("/user-info/picture", methods=["POST"])
@login_required
def update_picture():
    filename = None
    try:
        if request.form.get('action') != 'remove':
            upload = request.files.get('picture')
            if not upload:
                raise ValueError('Choose a picture first.')
            filename = save_avatar(upload)
        previous = swap_avatar(session['user_id'], filename)
    except ValueError as exc:
        remove_avatar(filename)
        flash(str(exc), 'danger')
    except Exception:
        remove_avatar(filename)
        current_app.logger.exception('Picture update failed')
        flash('Could not update picture. Try again.', 'danger')
    else:
        try:
            remove_avatar(previous)
        except OSError:
            current_app.logger.exception('Could not remove old picture')
        flash('Profile picture updated.', 'success')
    return redirect(url_for('pages.user_info'))


@pages.route("/user-info/picture")
@login_required
def own_picture():
    profile = get_own_profile(session['user_id'])
    if not profile or not profile.get('avatar_filename'):
        abort(404)
    path = avatar_path(profile['avatar_filename'])
    if not path.is_file():
        abort(404)
    # Close the disk handle before streaming so replacement works on Windows.
    response = send_file(BytesIO(path.read_bytes()), mimetype='image/png', max_age=0)
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response



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
