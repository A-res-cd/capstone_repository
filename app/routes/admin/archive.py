"""Admin archive routes and local helpers."""
from . import admin
from flask import render_template, request, redirect, session, url_for, flash, current_app
from app.db.archive import (
    get_archived_capstones,
    delete_capstone,
    add_to_bin,
    restore_capstone,
    ARCHIVE_RETENTION_DAYS,
)
from app.db.capstones import get_programs
from app.routes.decorators import role_required


@admin.route("/recyclebin")
@role_required(3)
def view_archived_capstones():
    search = request.args.get("search", "").strip()
    program_id = request.args.get("program", "").strip()
    page = request.args.get("page", 1, type=int)
    page_size = 20

    archived_capstones, total = get_archived_capstones(
        search=search or None,
        program_id=int(program_id) if program_id.isdigit() else None,
        page=page,
        page_size=page_size,
    )
    total_pages = max(1, (total + page_size - 1) // page_size)

    return render_template(
        "admin/archives.html",
        archived_capstones=archived_capstones,
        archive_retention_days=ARCHIVE_RETENTION_DAYS,
        programs=get_programs(),
        search=search,
        selected_program=program_id,
        page=page,
        total_pages=total_pages,
        total_archived=total,
    )


@admin.route("/delete_capstone/<int:capstone_id>", methods=["POST"])
@role_required(3)
def delete_capstone_route(capstone_id):
    try:
        success, message = delete_capstone(capstone_id, acting_user_id=session.get("user_id"))
        flash(message, "success" if success else "danger")
    except Exception as e:
        current_app.logger.error("delete_capstone_route error: %s", e)
        flash("Something went wrong deleting this capstone. Please try again.", "danger")

    return redirect(url_for("admin.view_capstone_repository"))


@admin.route("/repository/archive/<int:capstone_id>", methods=["POST"])
@role_required(3)
def archive_capstone(capstone_id):
    success, message = add_to_bin(capstone_id, acting_user_id=session.get("user_id"))
    flash(message, "success" if success else "danger")
    return redirect(url_for("admin.view_capstone_repository"))


@admin.route("/recyclebin/restore/<int:capstone_id>", methods=["POST"])
@role_required(3)
def restore_capstone_route(capstone_id):
    success, message = restore_capstone(capstone_id, acting_user_id=session.get("user_id"))
    flash(message, "success" if success else "danger")
    return redirect(url_for("admin.view_capstone_repository"))
