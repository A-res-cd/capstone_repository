from flask import Blueprint, abort, render_template, request, flash, session, redirect, url_for, jsonify, send_file, g
import re
import logging
from app.db.database import (
get_archive_capstones, get_archive_years, request_fullview, get_user_requests, get_capstone_details, 
cancel_manuscript_request, add_citations, get_capstone_authors, get_user_contacts, upsert_user_contact,
get_capstones_corpus, get_own_profile, change_own_password, delete_own_account,
get_all_roles, submit_promotion_request, get_own_promotion_requests, cancel_promotion_request,
get_requestable_capstones,
)
from app.routes.decorators import login_required, role_required
from app.routes.forms import ChangePasswordForm
from app.utils.uploads import manuscript_mimetype, resolve_manuscript_file
from app.services.recommender import TopicRecommender

pages = Blueprint("pages", __name__)
logger = logging.getLogger(__name__)

PAGE_SIZE = 12
EMAIL_PATTERN = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
PHONE_PATTERN = re.compile(r'^[0-9+()\-\s]{7,20}$')


@pages.route("/archive")
@login_required
def browse():
    search      = request.args.get("search", "").strip()
    year        = request.args.get("year", "").strip()
    page        = max(1, request.args.get("page", 1, type=int))

    projects, total = get_archive_capstones(
        search=search or None,
        year=year   or None,
        page=page,
        page_size=PAGE_SIZE,
    )

    years       = get_archive_years()
    total_pages = max(1, -(-total // PAGE_SIZE))   # ceiling division

    # sidebar shows the first result by default (or None when list is empty)
    sidebar_project = projects[0] if projects else None

    # Students who already have an approved request for a capstone should
    # see "View Full Manuscript" instead of "View Abstract" / "Request
    # Full Manuscript" — keeps this page in sync with My Requests.
    approved_capstone_ids = []
    current_role = g.user.get("role_name") if g.user else None
    if current_role == "Student":
        user_id = session.get("user_id")
        if user_id:
            approved_capstone_ids = [
                r["capstone_id"] for r in get_user_requests(user_id)
                if r["request_status"] == "approved"
            ]

    return render_template(
        "global/explore_archive.html",
        hide_nav=False,
        projects=projects,
        years=years,
        search=search,
        selected_year=year,
        page=page,
        total=total,
        total_pages=total_pages,
        sidebar_project=sidebar_project,
        approved_capstone_ids=approved_capstone_ids,
    )


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

    roles = get_all_roles()
    promotion_requests = get_own_promotion_requests(user_id)
    has_pending_promotion = any(r["request_status"] == "pending" for r in promotion_requests)

    return render_template(
        "global/user_information.html",
        hide_nav=False,
        profile=profile,
        contacts=contacts,
        contact_labels=contact_labels,
        contact_by_type=contact_by_type,
        password_form=ChangePasswordForm(),
        roles=roles,
        promotion_requests=promotion_requests,
        has_pending_promotion=has_pending_promotion,
    )


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


@pages.route("/my-requests")
@role_required(1)
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
    user_requests = get_user_requests(user_id)
    has_access = any(
        r["capstone_id"] == capstone_id and r["request_status"] == "approved"
        for r in user_requests
    )
    if not has_access:
        flash("You don't have an approved request for this manuscript.", "danger")
        return redirect(url_for("pages.browse"))

    capstone = get_capstone_details(capstone_id)
    if not capstone:
        flash("Capstone not found.", "danger")
        return redirect(url_for("pages.browse"))

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
        "admin/view_capstone.html",
        capstone=capstone,
        max_pages=None,
        start_page=1,
        pdf_url=pdf_url,
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

    user_requests = get_user_requests(user_id)
    has_access = any(
        r["capstone_id"] == capstone_id and r["request_status"] == "approved"
        for r in user_requests
    )
    if not has_access:
        abort(403)

    capstone = get_capstone_details(capstone_id)
    if not capstone:
        abort(404)

    file_path = resolve_manuscript_file(capstone.get("capstone_file"))
    if not file_path:
        abort(404)

    return send_file(file_path, mimetype=manuscript_mimetype(file_path))


@pages.route("/cite/<int:capstone_id>", methods=["POST"])
def cite_capstone(capstone_id):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "You must be logged in to cite this capstone"}), 401

    capstone = get_capstone_details(capstone_id)
    if not capstone:
        return jsonify({"error": "capstone not found"}), 404
    
    authors = get_capstone_authors(capstone_id)

    author_parts = []

    for a in authors:
        last = a["aut_last_name"]
        first_initial = a["aut_first_name"][0] + "." if a ["aut_first_name"] else ""
        middle_intitial = a["aut_middle_name"][0] + "." if a ["aut_middle_name"] else ""
        if middle_intitial:
            author_parts.append(f"{last}, {first_initial} {middle_intitial}")
        else:
            author_parts.append(f"{last}, {first_initial}")

    if len(author_parts) == 0:
        author_str = "Unknown Author"
    elif len(author_parts) == 1:
        author_str = author_parts[0]
    else:
        author_str = ", ".join(author_parts[:-1]) + ", &" + author_parts[-1]

    citation = (
        f"{author_str} ({capstone['capstone_year']}). "
        f"{capstone['capstone_title']} "
        f"[Unpublished capstone project]. "
        f"{capstone['program_name']}."
    )
    ok, err = add_citations(capstone_id, user_id)
    if not ok:
        return jsonify({"error": err}), 500
    
    update = get_capstone_details(capstone_id)
                        
    return jsonify({"citation": citation, "citation_count": update["citation_count"]})


# ─── Data mining: content-based topic-similarity recommender ───────────
# Sub-process (new, not yet in the DFDs — see PROJECT_ANALYSIS notes):
# lets a student check a proposed capstone title/keywords against the
# existing archive before formally submitting a topic, using TF-IDF +
# cosine similarity over capstone_title + keyword.capstone_keywords.

@pages.route("/propose-topic")
@role_required(1)
def propose_topic():
    return render_template("global/propose_topic.html")


@pages.route("/api/topic-similarity", methods=["POST"])
@role_required(1)
def topic_similarity():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    keywords = (data.get("keywords") or "").strip()

    if len(title) < 4:
        return jsonify({"matches": []})

    corpus = get_capstones_corpus()
    engine = TopicRecommender(corpus)
    matches = engine.find_similar(title, keywords, top_n=5)

    return jsonify({"matches": matches})
