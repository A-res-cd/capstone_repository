"""Student views and submissions for adviser-assigned progress requirements."""

from urllib.parse import urlsplit

from flask import abort, flash, redirect, render_template, send_file, session, url_for
from flask import request

from . import pages
from app.constants.roles import ROLE_STUDENT
from app.db.advisory_progress import (
    get_student_progress, get_student_submission_file, submit_advisory_requirement,
)
from app.routes.decorators import role_required
from app.utils.progress_uploads import resolve_progress_upload, save_progress_upload


def _validated_share_url(value):
    value = value.strip()
    parts = urlsplit(value)
    if (len(value) > 2000 or parts.scheme.lower() != "https" or not parts.hostname
            or parts.username or parts.password):
        raise ValueError("Enter a valid HTTPS share link, such as a Google Docs or Drive link.")
    return value


@pages.route("/my-progress")
@role_required(ROLE_STUDENT)
def my_progress():
    requirements = get_student_progress(session["user_id"])
    return render_template("global/my_progress.html", requirements=requirements)


@pages.route("/my-progress/requirements/<int:requirement_id>/submit", methods=["POST"])
@role_required(ROLE_STUDENT)
def submit_progress(requirement_id):
    external_url = request.form.get("external_url", "").strip()
    note = request.form.get("student_note", "").strip()
    upload = request.files.get("upload")
    has_upload = bool(upload and upload.filename)
    saved_file = None

    try:
        if len(note) > 2000:
            raise ValueError("Your note must be 2,000 characters or fewer.")
        if bool(external_url) == has_upload:
            raise ValueError("Submit one Google Docs/Drive link or one file.")

        if has_upload:
            saved_file = save_progress_upload(upload)
            values = {
                "submission_kind": "file",
                "storage_key": saved_file["storage_key"],
                "original_filename": saved_file["original_filename"],
                "mime_type": saved_file["mime_type"],
                "file_size": saved_file["file_size"],
                "student_note": note,
            }
        else:
            values = {
                "submission_kind": "link",
                "external_url": _validated_share_url(external_url),
                "student_note": note,
            }

        submit_advisory_requirement(session["user_id"], requirement_id, values)
        saved_file = None
        flash("Your progress submission was sent to your advisor.", "success")
    except PermissionError:
        if saved_file:
            saved_file["path"].unlink(missing_ok=True)
        abort(404)
    except ValueError as exc:
        if saved_file:
            saved_file["path"].unlink(missing_ok=True)
        flash(str(exc), "danger")
    except Exception:
        if saved_file:
            saved_file["path"].unlink(missing_ok=True)
        raise

    return redirect(url_for("pages.my_progress"))


@pages.route("/my-progress/submissions/<int:submission_id>/file")
@role_required(ROLE_STUDENT)
def my_progress_file(submission_id):
    submission = get_student_submission_file(session["user_id"], submission_id)
    if not submission:
        abort(404)
    path = resolve_progress_upload(submission["storage_key"])
    if not path or not path.is_file():
        abort(404)
    response = send_file(
        path, mimetype=submission["mime_type"], as_attachment=True,
        download_name=submission["original_filename"], conditional=True,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response
