"""Pages manuscripts routes."""
from . import pages
from flask import (
    Response,
    abort,
    render_template,
    request,
    flash,
    session,
    redirect,
    url_for,
    jsonify,
    send_file,
)
from app.db.requests import (
    request_fullview,
    get_user_requests,
    cancel_manuscript_request,
    get_requestable_capstones,
)
from app.db.capstones import get_capstone_details, get_capstone_authors
from app.routes.decorators import role_required, can_view_full_manuscript
from app.constants.roles import ROLE_STUDENT
from app.db.activity import record_capstone_activity
from app.utils.uploads import manuscript_mimetype, resolve_manuscript_file
from app.services.citations import citation_download_metadata, format_citation


@pages.route("/my-requests")
@role_required(ROLE_STUDENT)
def all_requests():
    user_id = session.get("user_id")
    if not user_id:
        flash("you must log in", "warning")
        return redirect(url_for("auth.signin"))

    user_requests = get_user_requests(user_id)
    requestable_capstones = get_requestable_capstones(user_id)
    return render_template(
        "global/all_requests.html",
        user_requests=user_requests,
        requestable_capstones=requestable_capstones,
        capstone=None,
        has_active_request=False,
        hide_nav=False,
    )


@pages.route("/request_manuscript/<int:capstone_id>", methods=['POST'])
def request_manuscript(capstone_id):
    user_id = session.get("user_id")
    if not user_id:
        flash("You must be logged in to request a manuscript", "warning")
        return redirect(url_for("auth.signin"))

    # Guard against duplicate requests — the form is hidden client-side
    # once one exists, but a direct POST could still slip through.
    existing = get_user_requests(user_id)
    if any(r["capstone_id"] == capstone_id and r["request_status"] in ("pending", "approved")
           for r in existing):
        flash("You already have a request for this capstone.", "warning")
        return redirect(url_for("pages.all_requests"))

    reason = request.form.get("request_reason", "").strip()
    if not reason:
        flash("Please give a reason for your request", "danger")
        # Validation failed — send them back to the form itself, not the
        # all-requests list, so they don't lose their place.
        return redirect(url_for("pages.request_capstone", capstone_id=capstone_id))
    
    ok, err = request_fullview(user_id, capstone_id, reason)
    flash("request submitted successfully" 
          if ok else f"Error: {err}","success" if ok else "danger")
    # Submission is done (success or failure past validation) — the
    # action is complete, so land on the all-requests view.
    return redirect(url_for("pages.all_requests"))


@pages.route("/requests/<int:capstone_id>", methods=["GET"])
def request_capstone(capstone_id):
    user_id = session.get("user_id")
    
    if not user_id:
        flash("you must log in", "warning")
        return redirect(url_for("auth.signin"))
    
    capstone = get_capstone_details(capstone_id)
    if not capstone:
        flash("capstone not found", "danger")
        return redirect(url_for("pages.browse"))
    
    user_requests = get_user_requests(user_id)

    # If there's already a pending or approved request for this exact
    # capstone, don't show the form — there's nothing to submit. A
    # rejected request is the one case that should still show the form,
    # since "Resubmit" needs somewhere to resubmit to.
    has_active_request = any(
        r["request_status"] in ("pending", "approved") and r["capstone_id"] == capstone_id
        for r in user_requests
    )

    return render_template(
        "global/all_requests.html",
        capstone=capstone,
        user_requests=user_requests,
        has_active_request=has_active_request,
        hide_nav=False,
    )


@pages.route("/manuscript/view/<int:capstone_id>")
def view_approved_manuscript(capstone_id):
    user_id = session.get("user_id")
    if not user_id:
        flash("You must be logged in to view this manuscript.", "warning")
        return redirect(url_for("auth.signin"))

    # Confirm this user actually has an approved request for this capstone
    # before letting them view it — otherwise this would just be a second
    # admin-only route under a different name. See BUGS.md #1.
    if not can_view_full_manuscript(capstone_id, user_id):
        flash("You don't have an approved request for this manuscript.", "danger")
        return redirect(url_for("pages.browse"))

    capstone = get_capstone_details(capstone_id)
    if not capstone:
        flash("Capstone not found.", "danger")
        return redirect(url_for("pages.browse"))

    record_capstone_activity(
        capstone_id,
        user_id,
        "view",
        event_variant="full",
    )

    # The template's inline script always references PDF_URL and START_PAGE
    # (regardless of max_pages), so both must be passed here — leaving them
    # out renders as the literal text "Undefined" in the script, which is
    # not valid JS/JSON and breaks the PDF.js loader.
    pdf_url = None
    file_rel = capstone.get('capstone_file') if isinstance(capstone, dict) else None
    if file_rel:
        pdf_url = url_for('pages.manuscript_file', capstone_id=capstone_id)

    # This route only runs after an approved-access check above, so the
    # requester gets the full document, not the abstract-only restriction.
    return render_template(
        "admin/native_pdf_viewer.html",
        capstone=capstone,
        max_pages=None,
        start_page=1,
        pdf_url=pdf_url,
        hide_nav=True,
        hide_header=True,
    )


@pages.route("/cancel_request/<int:request_id>", methods=["POST"])
def cancel_request(request_id):
    user_id = session.get("user_id")

    if not user_id:
        flash("you must log in", "warning")
        return redirect(url_for("auth.signin"))
    
    ok, err = cancel_manuscript_request(request_id, user_id)

    flash("request cancelled" 
          if ok else f"Error: {err}","success" if ok else "danger") 
    return redirect(url_for("pages.all_requests"))


@pages.route("/manuscript/file/<int:capstone_id>")
def manuscript_file(capstone_id):
    user_id = session.get("user_id")
    if not user_id:
        abort(401)

    if not can_view_full_manuscript(capstone_id, user_id):
        abort(403)

    capstone = get_capstone_details(capstone_id)
    if not capstone:
        abort(404)

    file_path = resolve_manuscript_file(capstone.get("capstone_file"))
    if not file_path:
        abort(404)

    return send_file(file_path, mimetype=manuscript_mimetype(file_path))


@pages.route("/cite/<int:capstone_id>", methods=["GET", "POST"])
def cite_capstone(capstone_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "You must be logged in to cite this capstone"}), 401

    capstone = get_capstone_details(capstone_id)
    if not capstone:
        return jsonify({"error": "capstone not found"}), 404
    
    payload = request.get_json(silent=True) or {}
    format_name = str(
        payload.get("format") or request.args.get("format") or "apa"
    ).lower()
    authors = list(get_capstone_authors(capstone_id))

    try:
        citation = format_citation(capstone, authors, format_name)
        filename, mimetype = citation_download_metadata(capstone, format_name)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    record_capstone_activity(
        capstone_id,
        user_id,
        "citation",
        event_variant=format_name,
    )

    if request.args.get("download") == "1":
        response = Response(citation, content_type=f"{mimetype}; charset=utf-8")
        response.headers.set("Content-Disposition", "attachment", filename=filename)
        return response

    return jsonify({
        "citation": citation,
        "format": format_name,
        "filename": filename,
    })
