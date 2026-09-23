"""Admin repository routes and local helpers."""
from . import admin
from flask import render_template, request, redirect, session, url_for, flash, jsonify
import os, logging
from tempfile import TemporaryDirectory
from app.db.capstones import (
    get_all_capstones,
    get_programs,
    get_specializations,
    get_used_keyword,
    insert_keywords,
    create_capstone_project,
    get_capstone_details,
    update_capstone_record,
    update_keyword,
    set_capstone_people,
    get_capstone_people,
)
from app.routes.decorators import role_required
from app.routes.forms import CreateCapstoneForm, UpdateCapstoneForm
from app.utils.pdf_extractor import extract_capstone_data
from app.utils.uploads import (
    allowed_manuscript,
    save_manuscript_upload,
    stored_manuscript_path,
)


logger = logging.getLogger(__name__)


def _allowed(filename):
    return allowed_manuscript(filename)


def _populate_capstone_choices(form):
    """SelectField choices must be set before validate()/rendering —
    pulled fresh from the DB each request rather than hardcoded."""
    form.program_id.choices = [(p[0], p[1]) for p in get_programs()]
    form.specialization_id.choices = [(s[0], s[1]) for s in get_specializations()]


def _first_form_error(form):
    """Flattens WTForms' nested error dict (FieldList/FormField errors
    are dicts-of-lists, not flat lists) into one readable message for
    the flash banner."""
    def _flatten(errors):
        for err in errors:
            if isinstance(err, dict):
                for sub in err.values():
                    yield from _flatten(sub)
            elif isinstance(err, list):
                yield from _flatten(err)
            else:
                yield err

    for field_errors in form.errors.values():
        for msg in _flatten(field_errors if isinstance(field_errors, list) else [field_errors]):
            return msg
    return "Please check the form for errors."


def _people_for_db(form):
    """Adapts CreateCapstoneForm's authors/adviser field names
    (first_name/middle_name/last_name) to the shape set_capstone_people()
    already expects (first/middle/last)."""
    authors = [
        {"first": a.first_name.data, "middle": a.middle_name.data, "last": a.last_name.data}
        for a in form.authors
    ]
    adviser = {
        "first": form.adviser.first_name.data,
        "middle": form.adviser.middle_name.data,
        "last": form.adviser.last_name.data,
    }
    return authors, adviser


@admin.route("/repository/extract", methods=["POST"])
@role_required(3, 4)
def extract_capstone_pdf():
    file = request.files.get('capstone_file')

    if not file or file.filename == '':
        return jsonify({'success': False, 'error': 'No file uploaded.'}), 400

    if not _allowed(file.filename):
        return jsonify({'success': False, 'error': 'Only PDF, DOC, and DOCX files are accepted.'}), 400

    # Only PDF files can be parsed for metadata — DOC/DOCX silently skip
    if file.filename.lower().endswith('.pdf'):
        with TemporaryDirectory(prefix='capstone-extract-') as temp_dir:
            temp_path = os.path.join(temp_dir, 'manuscript.pdf')
            file.save(temp_path)
            data = extract_capstone_data(temp_path)
    else:
        data = {}

    return jsonify({
        'success':       True,
        'data':          data,
    })


def _save_file(file_obj):
    """Validate and save an uploaded file. Returns (filename, error_msg) —
    exactly one of the two will be set."""
    if not file_obj or not file_obj.filename:
        return None, None
    return save_manuscript_upload(file_obj)


@admin.route("/repository")
@role_required(2, 3, 4)
def view_capstone_repository():
    search = request.args.get("search", "").strip()
    program_id = request.args.get("program", "").strip()
    page = request.args.get("page", 1, type=int)
    page_size = 20

    capstones, total = get_all_capstones(
        search=search or None,
        program_id=int(program_id) if program_id.isdigit() else None,
        page=page,
        page_size=page_size,
    )
    total_pages = max(1, (total + page_size - 1) // page_size)

    programs = get_programs()
    specializations = get_specializations()
    form = CreateCapstoneForm()
    _populate_capstone_choices(form)
    return render_template(
        "admin/repository.html",
        capstones=capstones,
        programs=programs,
        specializations=specializations,
        form=form,
        search=search,
        selected_program=program_id,
        page=page,
        total_pages=total_pages,
        total_capstones=total,
    )


@admin.route("/repository/<int:capstone_id>/people")
@role_required(3)
def get_capstone_people_json(capstone_id):
    """Feeds the Edit-panel wizard's Authors/Adviser step — capstone
    people were previously only fetchable server-side, so editing an
    existing capstone silently dropped its authors/adviser."""
    rows = get_capstone_people(capstone_id)

    authors = [
        {"first": r["aut_first_name"], "middle": r["aut_middle_name"] or "", "last": r["aut_last_name"]}
        for r in rows if r["role"] == "Author"
    ][:4]

    adviser_row = next((r for r in rows if r["role"] == "Adviser"), None)
    adviser = (
        {"first": adviser_row["aut_first_name"], "middle": adviser_row["aut_middle_name"] or "", "last": adviser_row["aut_last_name"]}
        if adviser_row else {"first": "", "middle": "", "last": ""}
    )

    return jsonify({"success": True, "authors": authors, "adviser": adviser})


@admin.route("/repository/create", methods=["GET", "POST"])
@role_required(3, 4)
def admin_create_capstone():
    if request.method == "GET":
        return redirect(url_for("admin.view_capstone_repository"))

    form = CreateCapstoneForm()
    _populate_capstone_choices(form)

    def _rerender():
        capstones, _ = get_all_capstones()
        return render_template(
            "admin/repository.html", hide_nav=False, form=form,
            capstones=capstones,
            programs=get_programs(), specializations=get_specializations(),
        )

    if not form.validate_on_submit():
        flash(_first_form_error(form), "danger")
        return _rerender()

    try:
        file = form.capstone_file.data

        if file and getattr(file, "filename", ""):
            filename, err = _save_file(file)
            if err:
                flash(err, "danger")
                return _rerender()
        else:
            flash("Upload a capstone file first.", "danger")
            return _rerender()

        file_path = stored_manuscript_path(filename)

        success, result = insert_keywords(form.capstone_keywords.data)
        if not success:
            flash(result, "danger")
        else:
            keyword_id = result
            success, message = create_capstone_project(
                keyword_id, form.specialization_id.data, form.program_id.data,
                form.capstone_title.data, form.capstone_year.data,
                file_path, form.semester.data,
                acting_user_id=session.get("user_id"),
                is_utilized=form.is_utilized.data,
                is_presented=form.is_presented.data,
                is_copyright_registered=form.is_copyright_registered.data
            )
            if success:
                new_capstone_id = message
                authors, adviser = _people_for_db(form)

                ok, err = set_capstone_people(
                    new_capstone_id, authors, adviser,
                    acting_user_id=session.get("user_id"))
                if not ok:
                    flash(
                        f"Capstone created, but author/adviser save failed: {err}", "warning")
                else:
                    flash("Capstone created successfully!", "success")

                return redirect(url_for("admin.view_capstone_repository"))
            else:
                flash(message, "danger")

    except Exception as exc:
        logger.error("admin_create_capstone error: %s", exc)
        flash("An error occurred while processing your request.", "danger")

    return _rerender()


@admin.route("/repository/update/<int:capstone_id>", methods=["POST"])
@role_required(3)
def update_capstone(capstone_id):
    used_keywords = get_used_keyword()
    capstone = get_capstone_details(capstone_id)

    if not capstone:
        flash("Capstone not found.", "danger")
        return redirect(url_for("admin.view_capstone_repository"))

    form = UpdateCapstoneForm()
    _populate_capstone_choices(form)

    def _rerender():
        capstones, _ = get_all_capstones()
        return render_template(
            "admin/repository.html", hide_nav=False, form=form,
            capstones=capstones,
            programs=get_programs(), specializations=get_specializations(),
            used_keywords=used_keywords, capstone=capstone,
        )

    if not form.validate_on_submit():
        flash(_first_form_error(form), "danger")
        return _rerender()

    try:
        new_keywords = (form.capstone_keywords.data or "").strip()

        file_path = capstone['capstone_file']
        file = form.capstone_file.data

        if file and getattr(file, "filename", ""):
            filename, err = _save_file(file)
            if err:
                flash(err, "danger")
                return _rerender()
            file_path = stored_manuscript_path(filename)

        # Update keyword if changed
        keyword_id = capstone['keyword_id']
        if new_keywords and new_keywords != capstone['capstone_keywords']:
            success, error = update_keyword(keyword_id, new_keywords)
            if not success:
                flash(f"Error updating keyword: {error}", "danger")
                return _rerender()

        # Update capstone record
        success, message = update_capstone_record(
            capstone_id, keyword_id, form.specialization_id.data, form.program_id.data,
            form.capstone_title.data, form.capstone_year.data, file_path,
            form.semester.data,
            acting_user_id=session.get("user_id"),
            is_utilized=form.is_utilized.data,
            is_presented=form.is_presented.data,
            is_copyright_registered=form.is_copyright_registered.data)

        if not success:
            flash(f"Error updating capstone: {message}", "danger")
            return _rerender()

        authors, adviser = _people_for_db(form)

        ok, err = set_capstone_people(capstone_id, authors, adviser,
                                       acting_user_id=session.get("user_id"))
        if not ok:
            flash(
                f"Capstone updated, but author/adviser save failed: {err}", "warning")
        else:
            flash("Capstone updated successfully!", "success")
        return redirect(url_for("admin.view_capstone_repository"))

    except Exception as e:
        logger.error("update_capstone_route error: %s", e)
        flash("Something went wrong updating this capstone. Please try again.", "danger")

    return _rerender()
