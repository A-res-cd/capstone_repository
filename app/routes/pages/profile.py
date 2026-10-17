"""Pages profile routes and local helpers."""
from . import pages
from flask import render_template, request, flash, session, redirect, url_for, send_file, abort, current_app
from app.utils.contact_policy import normalize_phone
from app.utils.avatars import save_avatar, remove_avatar, avatar_path
from app.db.profile_settings import swap_avatar
from app.db import contact_changes
from app.utils.auth_rate_limit import consume_limit
from app.utils.account_emails import contact_change_email
from app.utils.account_sms import send_sms, send_contact_change_sms
from app import mail
import secrets
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
    contacts = [contact for contact in get_user_contacts(user_id)
                if contact["contact_type"] in ("email", "phone")]
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
        if values["email"] and not EMAIL_PATTERN.fullmatch(values["email"]):
            raise ValueError("Enter a valid email address.")
        if preference not in ('email', 'phone') or not values.get(preference):
            raise ValueError("Provide your preferred contact details.")
        values['email'] = values['email'].lower()
        for destination in values.values():
            if destination and consume_limit('contact-destination', destination, 5, 900):
                raise ValueError('Too many contact requests. Try again later.')
        binding = session.setdefault('contact_change_binding', secrets.token_urlsafe(32))
        pending = contact_changes.request_change(user_id, request.form.get('current_password'), binding, values, preference)
        if pending:
            change_id, code, kind, destination = pending
            try:
                if kind == 'email':
                    mail.send(contact_change_email(destination, code))
                else:
                    send_contact_change_sms(destination, code)
            except Exception:
                contact_changes.finish_delivery(user_id, change_id, False)
                raise ValueError('Could not deliver verification code. Existing contacts are unchanged.')
            contact_changes.finish_delivery(user_id, change_id, True)
            session['contact_change_id'] = change_id
            flash('Code sent to the new destination. Confirm below within 15 minutes.', 'success')
        else:
            flash('Contact preference updated.', 'success')
    except ValueError as exc:
        flash(str(exc), "danger")
    except Exception:
        current_app.logger.error("Contact update failed for account %s", user_id)
        flash("Could not update contacts. Check that the email is not already in use.", "danger")
    return redirect(url_for("pages.user_info"))


@pages.route('/user-info/contact/confirm', methods=['POST'])
@login_required
def confirm_user_contact():
    user_id = session['user_id']
    try:
        change_id = session.get('contact_change_id')
        if not change_id:
            raise ValueError('Request a contact change first.')
        kind, previous = contact_changes.confirm_change(
            user_id, change_id, session.get('contact_change_binding'), request.form.get('code', ''))
    except ValueError as exc:
        flash(str(exc), 'danger')
    except Exception:
        current_app.logger.error('Contact confirmation failed for account %s', user_id)
        flash('Could not confirm contact change. Try again later.', 'danger')
    else:
        session.pop('contact_change_id', None)
        for destination in set(previous):
            try:
                if kind == 'email':
                    mail.send(contact_change_email(destination))
                else:
                    send_sms(destination, 'Your CAPRE recovery phone has changed. Contact support if you did not authorize this.')
            except Exception:
                try:
                    contact_changes.notification_failed(user_id)
                except Exception:
                    current_app.logger.error('Contact notification audit failed for account %s', user_id)
        flash('Recovery contact verified and updated.', 'success')
    return redirect(url_for('pages.user_info'))


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
