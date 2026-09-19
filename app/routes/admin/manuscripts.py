"""Admin manuscripts routes and local helpers."""
from . import admin
from flask import abort, render_template, redirect, url_for, flash, send_file, g
from app.db.capstones import get_capstone_details, get_capstone_authors
from app.routes.decorators import role_required, can_view_full_manuscript
from app.utils.pdf_extractor import extract_abstract_text
from app.utils.uploads import manuscript_mimetype, resolve_manuscript_file


@admin.route("/repository/view/<int:capstone_id>")
@role_required(3)
def view_capstone(capstone_id):
    capstone = get_capstone_details(capstone_id)
    authors = get_capstone_authors(capstone_id)
    # g.user is reloaded from the DB on every request (see load_current_user),
    # so this reflects the caller's current role even if it changed mid-session.
    is_admin = bool(g.user) and g.user.get("role_id") == 3
    max_pages = None if is_admin else 1  # Non-admin sees only page 1

    # The template's inline script always references PDF_URL and
    # START_PAGE regardless of max_pages — leaving them unset renders as
    # the literal text "Undefined" in the script and breaks PDF.js.
    pdf_url = None
    file_rel = capstone.get('capstone_file') if isinstance(capstone, dict) else None
    if file_rel:
        pdf_url = url_for('admin.manuscript_file', capstone_id=capstone_id)

    return render_template(
        "admin/view_capstone.html",
        capstone=capstone,
        authors=authors,
        max_pages=max_pages,
        start_page=1,
        pdf_url=pdf_url,
    )


@admin.route("/repository/pdf/<int:capstone_id>")
@role_required(1, 2, 3, 4)
def view_capstone_pdf(capstone_id):
    capstone = get_capstone_details(capstone_id)
    if not capstone:
        flash("Capstone not found.", "danger")
        return redirect(url_for("admin.view_capstone_repository"))

    # Use g.user (reloaded from the DB every request) instead of the
    # session copy, so a role change is respected immediately rather
    # than on next login.
    role_name = g.user.get("role_name") if g.user else None

    has_full_access = can_view_full_manuscript(capstone_id)
    if not has_full_access and role_name != 'Student':
        abort(403)

    abstract_only = role_name == 'Student' and not has_full_access
    authors = get_capstone_authors(capstone_id) if abstract_only else []
    max_pages = 1 if abstract_only else None
    pdf_url = None
    abstract_text = None
    file_rel = capstone.get('capstone_file') if isinstance(capstone, dict) else None
    if file_rel and has_full_access:
        pdf_url = url_for('admin.manuscript_file', capstone_id=capstone_id)
    elif file_rel:
        pdf_path = resolve_manuscript_file(file_rel)
        if pdf_path and pdf_path.lower().endswith('.pdf'):
            abstract_text = extract_abstract_text(pdf_path)

    if abstract_only and not abstract_text:
        abstract_text = "Abstract is not available for this manuscript."

    return render_template(
        "admin/view_capstone.html" if abstract_only else "admin/native_pdf_viewer.html",
        capstone=capstone,
        authors=authors,
        max_pages=max_pages,
        start_page=1,
        pdf_url=pdf_url,
        abstract_text=abstract_text,
        abstract_only=abstract_only,
        hide_nav=True,
        hide_header=not abstract_only,
    )


@admin.route("/repository/file/<int:capstone_id>")
@role_required(1, 2, 3, 4)
def manuscript_file(capstone_id):
    capstone = get_capstone_details(capstone_id)
    if not capstone:
        abort(404)

    # role_required(1, 2, 3) only confirms the caller is logged in as
    # *some* role — with just three roles in the system, that's every
    # authenticated user, not a real permission check. Admin/Faculty get
    # full access by design (matches the role check in view_capstone_pdf
    # above), but a Student must have an approved request for this exact
    # capstone — the same rule pages.manuscript_file already enforces for
    # the "View Full Manuscript" flow. Without this, any logged-in
    # student could fetch any capstone's complete PDF straight from this
    # URL, whether they'd ever requested it or not.
    if not can_view_full_manuscript(capstone_id):
        abort(403)

    file_path = resolve_manuscript_file(capstone.get("capstone_file"))
    if not file_path:
        abort(404)

    return send_file(file_path, mimetype=manuscript_mimetype(file_path))
