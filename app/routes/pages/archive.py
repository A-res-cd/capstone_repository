"""Pages archive routes and local helpers."""
from . import pages
from flask import render_template, request, session, jsonify, g
from app.db.archive import get_archive_capstones, get_archive_years
from app.db.requests import get_user_requests
from app.db.capstones import get_programs, get_specializations
from app.db.qol import get_saved_capstone_ids, toggle_saved_capstone
from app.routes.decorators import login_required


PAGE_SIZE = 12


@pages.route("/archive")
@login_required
def browse():
    search = request.args.get("search", "").strip()
    year = request.args.get("year", "").strip()
    adviser = request.args.get("adviser", "").strip()
    selected_specialization = request.args.get("specialization", type=int)
    selected_program        = request.args.get("program", type=int)
    sort = request.args.get("sort", "newest")
    saved_only = request.args.get("saved") == "1"
    page = max(1, request.args.get("page", 1, type=int))

    if sort not in {"relevance", "newest", "oldest", "title"}:
        sort = "newest"

    user_id = session.get("user_id")
    saved_capstone_ids = get_saved_capstone_ids(user_id) if user_id else set()

    projects, total = get_archive_capstones(
        search=search or None,
        year=year   or None,
        page=page,
        page_size=PAGE_SIZE,
        specialization=selected_specialization,
        program=selected_program,
        adviser=adviser or None,
        sort=sort,
        saved_by=user_id if saved_only else None,
    )

    years       = get_archive_years()
    programs = sorted(get_programs(), key=lambda row: str(row[1] or ""))
    specializations = sorted(get_specializations(), key=lambda row: str(row[1] or ""))
    total_pages = max(1, -(-total // PAGE_SIZE))   # ceiling division

    # sidebar shows the first result by default (or None when list is empty)
    sidebar_project = projects[0] if projects else None

    # Students who already have an approved request for a capstone should
    # see "View Full Manuscript" instead of "View Abstract" / "Request
    # Full Manuscript" — keeps this page in sync with My Requests.
    approved_capstone_ids = []
    current_role = g.user.get("role_name") if g.user else None
    if current_role == "Student":
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
        adviser=adviser,
        programs=programs,
        specializations=specializations,
        selected_program=selected_program,
        selected_specialization=selected_specialization,
        selected_sort=sort,
        saved_only=saved_only,
        saved_capstone_ids=saved_capstone_ids,
        page=page,
        page_size=PAGE_SIZE,
        total=total,
        total_pages=total_pages,
        sidebar_project=sidebar_project,
        approved_capstone_ids=approved_capstone_ids,
    )


@pages.route("/saved-capstones/<int:capstone_id>", methods=["POST"])
@login_required
def toggle_saved_capstone_route(capstone_id):
    ok, saved, error = toggle_saved_capstone(session.get("user_id"), capstone_id)
    if not ok:
        return jsonify({"error": error}), 400
    return jsonify({"saved": saved})
