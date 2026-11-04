"""Pages manuscripts routes and local helpers."""
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
    g,
    current_app,
)
from app.db.capstones import get_capstone_details, get_capstone_authors
from app.routes.decorators import can_view_full_manuscript, can_download_manuscript
from app.utils.uploads import manuscript_mimetype, resolve_manuscript_file
from app.services.citations import citation_download_metadata, format_citation
from app.services import manuscript_reader
from pypdfium2 import PdfiumError


@pages.route("/manuscript/view/<int:capstone_id>")
def view_approved_manuscript(capstone_id):
    user_id = session.get("user_id")
    if not user_id:
        flash("You must be logged in to view this manuscript.", "warning")
        return redirect(url_for("auth.signin"))

    if not can_view_full_manuscript(capstone_id, user_id):
        abort(403)

    capstone = get_capstone_details(capstone_id)
    if not capstone:
        flash("Capstone not found.", "danger")
        return redirect(url_for("pages.browse"))

    if not can_download_manuscript():
        return render_template(
            "global/manuscript_reader.html", capstone=capstone,
            authors=get_capstone_authors(capstone_id),
            hide_nav=True, hide_header=False,
        )

    pdf_url = None
    file_rel = capstone.get('capstone_file') if isinstance(capstone, dict) else None
    if file_rel:
        pdf_url = url_for('pages.manuscript_file', capstone_id=capstone_id)

    # Independent privileged roles retain full manuscript access.
    return render_template(
        "admin/native_pdf_viewer.html",
        capstone=capstone,
        max_pages=None,
        start_page=1,
        pdf_url=pdf_url,
        hide_nav=True,
        hide_header=True,
    )


@pages.route("/manuscript/file/<int:capstone_id>")
def manuscript_file(capstone_id):
    user_id = session.get("user_id")
    if not user_id:
        abort(401)

    if not can_download_manuscript():
        abort(403)

    capstone = get_capstone_details(capstone_id)
    if not capstone:
        abort(404)

    file_path = resolve_manuscript_file(capstone.get("capstone_file"))
    if not file_path:
        abort(404)

    return send_file(file_path, mimetype=manuscript_mimetype(file_path))


def _readable_manuscript(capstone_id):
    user_id = session.get("user_id")
    if not user_id or not getattr(g, "user", None):
        abort(401)
    if not can_view_full_manuscript(capstone_id, user_id):
        abort(403)
    capstone = get_capstone_details(capstone_id)
    if not capstone:
        abort(404)
    path = resolve_manuscript_file(capstone.get("capstone_file"))
    if not path:
        abort(404)
    if not path.lower().endswith(".pdf"):
        abort(415)
    return path


@pages.route("/manuscript/pages/<int:capstone_id>")
def manuscript_pages(capstone_id):
    path = _readable_manuscript(capstone_id)
    try:
        return jsonify(page_count=manuscript_reader.page_count(path))
    except (PdfiumError, ValueError, OSError):
        current_app.logger.warning("Cannot open manuscript %s for protected reading", capstone_id)
        abort(422)


@pages.route("/manuscript/pages/<int:capstone_id>/<int:page_number>")
def manuscript_page_image(capstone_id, page_number):
    path = _readable_manuscript(capstone_id)
    output_format = "PDF" if request.args.get("format") == "pdf" else "JPEG"
    try:
        image = manuscript_reader.page_image(
            path, page_number, session["user_id"], capstone_id, output_format=output_format,
        )
    except IndexError:
        abort(404)
    except (PdfiumError, ValueError, OSError):
        current_app.logger.warning("Cannot render manuscript %s page %s", capstone_id, page_number)
        abort(422)
    return Response(image, mimetype="application/pdf" if output_format == "PDF" else "image/jpeg")


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

    if request.args.get("download") == "1":
        response = Response(citation, content_type=f"{mimetype}; charset=utf-8")
        response.headers.set("Content-Disposition", "attachment", filename=filename)
        return response

    return jsonify({
        "citation": citation,
        "format": format_name,
        "filename": filename,
    })
