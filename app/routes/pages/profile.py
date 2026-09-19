"""Pages profile routes."""
from . import pages
from flask import abort, render_template, request, flash, session, redirect, url_for, send_file, g
import re, logging
from app.db.users import (
    get_user_contacts,
    upsert_user_contact,
    get_own_profile,
    delete_own_account,
    get_all_roles,
    submit_promotion_request,
    get_own_promotion_requests,
    cancel_promotion_request,
)
from app.db.auth import change_own_password
from app.routes.decorators import login_required
from app.routes.forms import ChangePasswordForm, CapstonerRegistrationForm
from app.db.capstones import get_user_authored_capstones
from app.db.capstoners import get_capstoner_registration, submit_capstoner_registration
from app.db.avatars import get_user_avatar, upsert_user_avatar
from app.db.activity import get_author_activity_summary, get_recent_author_activity
from app.db.cor_registrations import get_latest_cor_registration
from app.utils.cor_extractor import extract_cor_fields
from app.utils.cor_upload import read_cor_upload, save_cor_upload, remove_cor_file
from app.utils.avatar_uploads import remove_avatar_file, resolve_avatar_file, save_avatar_upload


logger = logging.getLogger(__name__)


EMAIL_PATTERN = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


PHONE_PATTERN = re.compile(r'^[0-9+()\-\s]{7,20}$')


@pages.route("/user-info")
@login_required
def user_info():
    user_id = session.get("user_id")
    if request.args.get("partial") == "1":
        return render_template(
            "partials/user_information_modal.html",
            **_user_information_context(user_id),
        )

    return redirect(url_for("pages.profile_overview", user_info="1"))


def _user_information_context(user_id):
    profile = get_own_profile(user_id)
    avatar = get_user_avatar(user_id)
    contacts = get_user_contacts(user_id)
    contact_labels = [
        ("email", "Email"),
        ("phone", "Contact Number"),
        ("facebook", "Facebook"),
        ("instagram", "Instagram"),
        ("twitter", "Twitter/X"),
    ]
    contact_by_type = {c["contact_type"]: c for c in contacts}

    roles = get_all_roles()
    promotion_requests = get_own_promotion_requests(user_id)
    has_pending_promotion = any(r["request_status"] == "pending" for r in promotion_requests)

    return {
        "profile": profile,
        "avatar": avatar,
        "contacts": contacts,
        "contact_labels": contact_labels,
        "contact_by_type": contact_by_type,
        "password_form": ChangePasswordForm(),
        "roles": roles,
        "promotion_requests": promotion_requests,
        "has_pending_promotion": has_pending_promotion,
    }


@pages.route("/profile")
@login_required
def profile_overview():
    return _render_profile()


def _render_profile(capstoner_form=None):
    user_id = session.get("user_id")
    profile = get_own_profile(user_id)
    avatar = get_user_avatar(user_id)
    contacts = get_user_contacts(user_id)
    my_works = get_user_authored_capstones(user_id)
    activity_totals = get_author_activity_summary(user_id)
    recent_activity = get_recent_author_activity(user_id)

    return render_template(
        "global/profile.html",
        hide_nav=False,
        profile=profile,
        avatar=avatar,
        contacts=contacts,
        capstoner_registration=get_capstoner_registration(user_id),
        cor_record=get_latest_cor_registration(user_id),
        capstoner_form=capstoner_form or CapstonerRegistrationForm(),
        my_works=my_works,
        activity_totals=activity_totals,
        profile_metrics=[
            {"label": "Works", "value": len(my_works)},
            {"label": "Citations", "value": "—"},
            {"label": "Views", "value": "—"},
            {"label": "Requests", "value": "—"},
        ],
        recent_activity=recent_activity,
    )


@pages.route("/profile/avatar", methods=["GET"])
@login_required
def user_avatar():
    avatar = get_user_avatar(session.get("user_id"))
    path = resolve_avatar_file(avatar.get("storage_key")) if avatar else None
    if not path:
        abort(404)
    return send_file(path, mimetype=avatar["mime_type"], conditional=True)


@pages.route("/profile/avatar", methods=["POST"])
@login_required
def upload_avatar():
    upload = request.files.get("avatar")
    try:
        metadata = save_avatar_upload(upload)
        previous_key = upsert_user_avatar(session["user_id"], metadata)
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("pages.profile_overview"))
    except Exception:
        if "metadata" in locals():
            remove_avatar_file(metadata.get("storage_key"))
        logger.exception("Could not save user avatar")
        flash("The profile image could not be saved. Please try again.", "danger")
        return redirect(url_for("pages.profile_overview"))

    if previous_key and previous_key != metadata["storage_key"]:
        remove_avatar_file(previous_key)
    flash("Profile image updated.", "success")
    return redirect(url_for("pages.profile_overview"))


@pages.route("/profile/capstoner", methods=["POST"])
@login_required
def register_capstoner():
    form = CapstonerRegistrationForm()
    if not form.validate_on_submit():
        flash("Enter capstone details and upload a valid COR.", "danger")
        return _render_profile(form), 400

    user_id = session["user_id"]
    cor_filename = None
    cor_registration = None
    if form.cor.data and form.cor.data.filename:
        try:
            document = read_cor_upload(form.cor.data)
            extracted = extract_cor_fields(document["content"])
        except ValueError as exc:
            flash(str(exc), "danger")
            return _render_profile(form), 400

        if extracted.get("warning") or not extracted.get("year_level"):
            flash("We could not verify the year level from your COR. Upload a clearer COR.", "danger")
            return _render_profile(form), 400
        if int(extracted["year_level"]) not in {3, 4}:
            flash("You must be a third- or fourth-year student to register as a capstoner.", "danger")
            return _render_profile(form), 400

        profile = get_own_profile(user_id) or {}
        normalize = lambda value: re.sub(r"\s+", "", (value or "")).casefold()
        if normalize(extracted.get("student_no")) != normalize(profile.get("university_no")):
            flash("The student number on your COR does not match your account.", "danger")
            return _render_profile(form), 400

        try:
            cor_filename = save_cor_upload(form.cor.data)
        except (ValueError, OSError) as exc:
            logger.exception("Could not save capstoner COR")
            flash(str(exc) if isinstance(exc, ValueError) else "Could not save your COR. Please try again.", "danger")
            return _render_profile(form), 400
        cor_registration = {**extracted, "cor_filename": cor_filename}
    else:
        existing = get_latest_cor_registration(user_id)
        if not existing:
            flash("Upload your current COR before registering as a capstoner.", "danger")
            return _render_profile(form), 400
        if existing.get("year_level") not in {3, 4}:
            flash("You must be a third- or fourth-year student to register as a capstoner.", "danger")
            return _render_profile(form), 400

    ok, error = submit_capstoner_registration(user_id, form.reason.data, cor_registration)
    if not ok:
        if cor_filename:
            try:
                remove_cor_file(cor_filename)
            except OSError:
                logger.exception("Could not clean up unsuccessful capstoner COR")
        flash(error, "danger")
        return _render_profile(form), 400
    flash("Capstoner request sent. A capstone professor will review your details.", "success")
    return redirect(url_for("pages.profile_overview"))


@pages.route("/user-info/promotion", methods=["POST"])
@login_required
def submit_promotion_request_route():
    user_id = session.get("user_id")
    target_role_id = request.form.get("target_role_id")
    reason = request.form.get("reason", "").strip()

    # Admins already hold the top role — block here too, not just by
    # hiding the form, since a direct POST would otherwise still work.
    # Use g.user (loaded fresh from the DB this request) rather than the
    # session copy, so a role change takes effect immediately.
    current_role = g.user.get("role_name") if g.user else None
    if current_role == "Admin":
        flash("Admins can't request a role promotion.", "danger")
        return redirect(url_for("pages.user_info"))

    if not target_role_id or not target_role_id.isdigit():
        flash("Select a role to request.", "danger")
        return redirect(url_for("pages.user_info"))

    # Admin can't be requested as a target role either — it's granted
    # by another admin via Manage Users, not self-service.
    target_role_id = int(target_role_id)
    roles = get_all_roles()
    target_role_name = next((r[1] for r in roles if r[0] == target_role_id), None)
    if target_role_name == "Admin":
        flash("The Admin role can't be requested — it must be assigned by an existing admin.", "danger")
        return redirect(url_for("pages.user_info"))

    if not reason:
        flash("Enter a reason for the request.", "danger")
        return redirect(url_for("pages.user_info"))

    ok, err = submit_promotion_request(user_id, target_role_id, reason)
    flash("Promotion request submitted." if ok else err, "success" if ok else "danger")
    return redirect(url_for("pages.user_info"))


@pages.route("/user-info/promotion/cancel/<int:request_id>", methods=["POST"])
@login_required
def cancel_promotion_request_route(request_id):
    user_id = session.get("user_id")
    ok, err = cancel_promotion_request(request_id, user_id)
    flash("Promotion request cancelled." if ok else err, "success" if ok else "danger")
    return redirect(url_for("pages.user_info"))


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
